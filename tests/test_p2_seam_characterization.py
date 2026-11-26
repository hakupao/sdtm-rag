"""P2.0 seam characterization: every server-key outbound call + response bytes, pinned.

Recorded on the PRE-refactor code (main 36499a7) and committed as a golden; the P2.0 seam
refactor (server/request_context.py + hook modules) must leave it identical. Real rag.py /
federation.py / router.py / compare.py / reviewer.py code runs; only the wire is faked:
litellm.embedding / completion / acompletion (module attributes), the Router object, and
Tavily's requests.post. Content is synthetic (no study data).

Regenerate ONLY on purpose:  P2_SEAM_REGEN=1 .venv/bin/python -m pytest tests/test_p2_seam_characterization.py
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

GOLDEN = Path(__file__).parent / "fixtures" / "p2_seam_characterization.json"
DIM = 8

_DOCS = {
    "cdisc_t": [
        ("c1", "domains/AE/spec.md", "AE", "spec", "AE variables",
         "AETERM is the reported term for the adverse event. AE domain Events class."),
        ("c2", "domains/AE/assumptions.md", "AE", "assumptions", "AE assumptions",
         "AE domain assumptions: one record per adverse event per subject."),
        ("c3", "domains/DM/spec.md", "DM", "spec", "DM variables",
         "DM demographics domain: AGE, SEX, RACE. One record per subject."),
        ("c4", "terminology/C66742.md", None, "terminology", "No Yes Response",
         "Codelist C66742 No Yes Response: N, Y, U, NA."),
    ],
    "study_t": [
        ("s1", "card_form_a.md", None, "card", "Form A",
         "Synthetic form A: adverse event term field, onset date field."),
        ("s2", "card_form_b.md", None, "card", "Form B",
         "Synthetic form B: vital signs, systolic pressure, unit mmHg."),
    ],
}


def _vec(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    v = [b / 255.0 + 0.01 for b in h[:DIM]]
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v]


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     default=str).encode()).hexdigest()[:16]


def _norm_kwargs(kw: dict) -> dict:
    out = {"keys": sorted(kw)}
    for k in ("model", "stream", "stream_options", "temperature", "max_tokens", "timeout",
              "num_retries"):
        if k in kw:
            out[k] = kw[k]
    if "messages" in kw:
        out["messages_sha"] = _digest(kw["messages"])
        out["roles"] = [m.get("role") for m in kw["messages"]]
    if "input" in kw:
        out["input_sha"] = _digest(kw["input"])
    if "tools" in kw:
        out["tools"] = [t["function"]["name"] for t in kw["tools"]]
    out["api_key"] = bool(kw.get("api_key"))
    out["api_base"] = bool(kw.get("api_base"))
    return out


class _Rec:
    def __init__(self):
        self.calls: list[dict] = []

    def add(self, kind, kw):
        self.calls.append({"call": kind, **_norm_kwargs(kw)})


def _resp(content, finish="stop", model="m-x"):
    return SimpleNamespace(
        model=model,
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3, total_tokens=13))


def _chunk(text=None, finish=None, tool=None, usage=False, model="m-stream"):
    if usage:
        return SimpleNamespace(model=model, choices=[], usage=SimpleNamespace(
            prompt_tokens=7, completion_tokens=2, total_tokens=9))
    delta = SimpleNamespace(content=text, tool_calls=[tool] if tool else None)
    return SimpleNamespace(model=model, usage=None,
                           choices=[SimpleNamespace(delta=delta, finish_reason=finish)])


class _FakeRouter:
    """Router double. Scripted per-model replies; records every call's kwargs."""

    def __init__(self, rec: _Rec):
        self.rec = rec
        self.ask_script: list = []
        self.stream_script: list = []

    def completion(self, **kw):
        self.rec.add("router.completion", kw)
        if kw["model"] == "light":
            return _resp('{"corpus": "cdisc"}')
        if kw["model"] == "hard":
            return _resp("[]")
        return self.ask_script.pop(0)

    async def acompletion(self, **kw):
        self.rec.add("router.acompletion", kw)
        chunks = self.stream_script.pop(0)

        async def agen():
            for c in chunks:
                yield c
        return agen()


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    import chromadb

    mp = pytest.MonkeyPatch()
    for k in list(os.environ):
        if k.startswith("SDTM_RAG_"):
            mp.delenv(k)
    mp.setenv("TAVILY_API_KEY", "tavily-sentinel")

    root = tmp_path_factory.mktemp("p2seam")
    kb = root / "kb"
    kb.mkdir()
    (kb / "ROUTING.md").write_text("# ROUTING\nsynthetic routing table\n", encoding="utf-8")
    (kb / "INDEX.md").write_text("# INDEX\nsynthetic index\n", encoding="utf-8")
    chroma = root / "chroma"
    client = chromadb.PersistentClient(path=str(chroma))
    for name, docs in _DOCS.items():
        col = client.create_collection(name, metadata={"hnsw:space": "cosine"})
        col.add(ids=[d[0] for d in docs], documents=[d[5] for d in docs],
                embeddings=[_vec(d[5]) for d in docs],
                metadatas=[{"source": d[1], "file_type": d[3], "section": d[4],
                            **({"domain": d[2]} if d[2] else {})} for d in docs])

    rec = _Rec()
    import litellm

    def fake_embedding(**kw):
        rec.add("litellm.embedding", kw)
        return SimpleNamespace(data=[{"embedding": _vec(kw["input"][0])}])

    def fake_completion(**kw):
        rec.add("litellm.completion", kw)
        return _resp("Hypothetical passage about AETERM.")

    async def fake_acompletion(**kw):
        rec.add("litellm.acompletion", kw)
        if kw["model"] == "deepseek/deepseek-chat" and kw.get("temperature") == 0.0:
            return _resp('{"ranking": [{"label": "A", "rank": 1, "comment": "ok"}, '
                         '{"label": "B", "rank": 2, "comment": "meh"}], "best": "A", '
                         '"rationale": "grounded"}')
        return _resp(f"Answer from {kw['model']}.")

    mp.setattr(litellm, "embedding", fake_embedding)
    mp.setattr(litellm, "completion", fake_completion)
    mp.setattr(litellm, "acompletion", fake_acompletion)

    import server.web_search as ws

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        rec.calls.append({"call": "tavily.post", "url": url,
                          "auth": bool((headers or {}).get("Authorization")),
                          "json": json, "timeout": timeout})
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"results": [
            {"url": "https://example.org/aeterm", "title": "AETERM", "content": "synthetic web text"}]})

    mp.setattr(ws.requests, "post", fake_post)
    mp.setattr(ws.WebSearcher, "_day_used", 0)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from scripts.spec_loader import SpecLoader
    from server.config import Settings
    from server.federation import FederatedEngine
    from server.rag import RAGEngine
    from server.router import api_router

    s = Settings(chroma_dir=chroma, kb_root=kb, collection_name="cdisc_t", top_k=3)
    common = dict(chroma_dir=chroma, kb_root=kb, embedding_model=s.embedding_model, top_k=3,
                  hybrid_enabled=True, prompt_guardrail_enabled=True, web_search_enabled=True)
    rag = RAGEngine(collection_name="cdisc_t", **common)
    # HyDE (query_expansion) is OFF in production; the study engine turns it on here only so the
    # rag._llm outbound call path is characterized too.
    rag_study = RAGEngine(collection_name="study_t", query_expansion="hyde_rrf",
                          expansion_model="deepseek/deepseek-chat", **common)
    router = _FakeRouter(rec)
    app = FastAPI()
    app.include_router(api_router)
    app.state.settings = s
    app.state.rag = rag
    app.state.llm_router = router
    app.state.federation = FederatedEngine(rag, rag_study, router, top_k=3)
    from server.config import settings as global_settings
    app.state.spec_loader = SpecLoader(global_settings.kb_root)
    yield TestClient(app), rec, router
    mp.undo()


def _tool_delta(idx, tc_id, name, args):
    return SimpleNamespace(index=idx, id=tc_id,
                           function=SimpleNamespace(name=name, arguments=args))


def _run_all(client, rec: _Rec, router: _FakeRouter) -> dict:
    out: dict = {}

    def step(name, fn):
        rec.calls.clear()
        r = fn()
        body = r.text
        if r.headers.get("content-type", "").startswith("application/json"):
            j = r.json()
            if name == "ask_compare":
                for a in j["answers"]:
                    a["latency_ms"] = 0
            body = j
        out[name] = {"status": r.status_code, "body": body if name != "validate" else None,
                     "calls": list(rec.calls)}

    step("info", lambda: client.get("/api/info"))

    router.ask_script = [_resp("Part one. ", finish="length"), _resp("Part two [Source: x].")]
    step("ask_auto_continue", lambda: client.post("/api/ask", json={
        "question": "What is AETERM in AE?", "corpus": "auto"}))

    router.stream_script = [
        [_chunk(tool=_tool_delta(0, "call_1", "web_search", '{"query": "AETERM definition"}'),
                finish="tool_calls"), _chunk(usage=True)],
        [_chunk("Answer with web "), _chunk(finish="length"), _chunk(usage=True)],
        [_chunk("[Web: https://example.org/aeterm]."), _chunk(finish="stop"), _chunk(usage=True)],
    ]
    step("ask_stream_web_continue", lambda: client.post("/api/ask_stream", json={
        "question": "Define AETERM", "corpus": "cdisc", "web": True}))

    router.stream_script = [[_chunk("Study answer."), _chunk(finish="stop"), _chunk(usage=True)]]
    step("ask_stream_study_hyde", lambda: client.post("/api/ask_stream", json={
        "question": "Which form has the adverse event term?", "corpus": "study",
        "model": "opus-5"}))

    router.stream_script = [[_chunk("Auto answer."), _chunk(finish="stop"), _chunk(usage=True)]]
    step("ask_stream_auto", lambda: client.post("/api/ask_stream", json={
        "question": "DM AGE meaning", "history": [{"role": "user", "content": "hi"},
                                                  {"role": "assistant", "content": "hello"}]}))

    step("ask_compare", lambda: client.post("/api/ask_compare", json={
        "question": "What is AETERM?", "models": ["openai/gpt-4o", "deepseek/deepseek-v4-pro"],
        "judge": {"enabled": True, "model": "deepseek/deepseek-chat"}}))

    csv = b"STUDYID,DOMAIN,USUBJID,AETERM\nS1,AE,S1-1,HEADACHE\n"
    step("validate", lambda: client.post(
        "/api/validate", files={"file": ("ae.csv", io.BytesIO(csv), "text/csv")},
        data={"semantic_review": "true"}))
    return out


def test_p2_seam_outbound_calls_and_responses_unchanged(harness):
    client, rec, router = harness
    got = _run_all(client, rec, router)
    if os.environ.get("P2_SEAM_REGEN") == "1":
        GOLDEN.write_text(json.dumps(got, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                          encoding="utf-8")
        pytest.skip("golden regenerated")
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    # per-step compare first: a failure names the step instead of dumping the whole blob
    assert sorted(got) == sorted(want)
    for name in want:
        assert got[name]["calls"] == want[name]["calls"], f"{name}: outbound calls drifted"
        assert got[name]["status"] == want[name]["status"], f"{name}: status drifted"
        assert got[name]["body"] == want[name]["body"], f"{name}: response bytes drifted"


def test_p2_seam_golden_covers_every_outbound_family():
    """Non-vacuity: the golden must actually contain every inventory family (P2_request_context §1),
    so an empty / truncated golden cannot pass the test above."""
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    seen = {(c["call"], c.get("model")) for st in want.values() for c in st["calls"]}
    kinds = {k for k, _ in seen}
    assert {"router.completion", "router.acompletion", "litellm.embedding", "litellm.completion",
            "litellm.acompletion", "tavily.post"} <= kinds
    assert ("router.completion", "light") in seen      # federation 判库
    assert ("router.completion", "hard") in seen       # validate semantic review
    assert ("router.completion", "default") in seen    # /api/ask (+ continuation)
    assert ("router.acompletion", "opus-5") in seen    # selectable model, stream
    assert want["ask_stream_web_continue"]["body"].count("event: continue") == 1
    assert sum(1 for c in want["ask_auto_continue"]["calls"]
               if c["call"] == "router.completion" and c["model"] == "default") == 2
