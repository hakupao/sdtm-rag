"""P2 L2 acceptance through the real app stack: api_router + install_security (visitor cookie, body
limit, flag limiter) + the real outbound/finalizing seam, with the wire faked (no paid calls)."""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from server import providers, quota
from tests.test_p2_seam_characterization import _DOCS, _chunk, _FakeRouter, _Rec, _resp, _vec


class S:
    def __init__(self, base, **over):
        self._base = base
        self.__dict__.update(over)

    def __getattr__(self, name):
        return getattr(self._base, name)


@pytest.fixture(scope="module")
def engines(tmp_path_factory):
    import chromadb
    import litellm

    import server.web_search as ws
    from server.rag import RAGEngine

    mp = pytest.MonkeyPatch()
    for k in list(os.environ):
        if k.startswith("SDTM_RAG_"):
            mp.delenv(k)
    mp.setenv("TAVILY_API_KEY", "tavily-sentinel")
    root = tmp_path_factory.mktemp("p2l2")
    kb = root / "kb"
    kb.mkdir()
    (kb / "ROUTING.md").write_text("# ROUTING\n", encoding="utf-8")
    (kb / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    chroma = root / "chroma"
    client = chromadb.PersistentClient(path=str(chroma))
    docs = _DOCS["cdisc_t"]
    col = client.create_collection("cdisc_t", metadata={"hnsw:space": "cosine"})
    col.add(ids=[d[0] for d in docs], documents=[d[5] for d in docs],
            embeddings=[_vec(d[5]) for d in docs],
            metadatas=[{"source": d[1], "file_type": d[3], "section": d[4],
                        **({"domain": d[2]} if d[2] else {})} for d in docs])
    rec = _Rec()

    def fake_embedding(**kw):
        rec.add("litellm.embedding", kw)
        return SimpleNamespace(data=[{"embedding": _vec(kw["input"][0])}])

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        rec.calls.append({"call": "tavily.post"})
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"results": []})

    mp.setattr(litellm, "embedding", fake_embedding)
    mp.setattr(ws.requests, "post", fake_post)
    mp.setattr(ws.WebSearcher, "_day_used", 0)
    from server.config import Settings

    base = Settings(chroma_dir=chroma, kb_root=kb, collection_name="cdisc_t", top_k=3)
    rag = RAGEngine(collection_name="cdisc_t", chroma_dir=chroma, kb_root=kb,
                    embedding_model=base.embedding_model, top_k=3, hybrid_enabled=True,
                    prompt_guardrail_enabled=True, web_search_enabled=True)
    yield base, rag, rec, root
    mp.undo()


@pytest.fixture
def make(engines, tmp_path):
    """make(**settings_overrides) -> (TestClient, router). Each call = a fresh app ("process");
    quota._STORES is cleared so a second app reopens the SQLite file like a restart."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from server.auth import install_security
    from server.router import api_router

    base, rag, rec, _root = engines
    db = tmp_path / "quota.sqlite"

    def _make(client_addr=("testclient", 50000), **over):
        quota._STORES.clear()
        opts = dict(quota_enabled=True, quota_db_path=str(db), visitor_secret="t" * 32,
                    quota_rate_per_min=10_000, quota_rate_burst=10_000,
                    quota_ip_rate_per_min=10_000, quota_ip_rate_burst=10_000,
                    dogfood_log_path=tmp_path / "dogfood.md")
        opts.update(over)
        s = S(base, **opts)
        app = FastAPI()
        app.include_router(api_router)
        router = _FakeRouter(rec)
        app.state.settings, app.state.rag, app.state.llm_router = s, rag, router
        install_security(app, s)
        rec.calls.clear()
        return TestClient(app, client=client_addr), router

    yield _make
    quota._STORES.clear()


def _ask(client, router, **body):
    router.ask_script = [_resp("Answer [Source: x].")]
    return client.post("/api/ask", json={"question": "What is AETERM?", "corpus": "cdisc", **body})


def _events(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        out.append((lines[0][len("event: "):], json.loads(lines[1][len("data: "):])))
    return out


def test_n_plus_1_question_is_429_with_quota_fields(make):
    client, router = make(quota_free_per_day=3)
    r = _ask(client, router)
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()
    assert r.json()["quota"]["free_remaining"] == 2 and r.json()["quota"]["byok"] is False
    router.stream_script = [[_chunk("ok"), _chunk(finish="stop"), _chunk(usage=True)]]
    r = client.post("/api/ask_stream", json={"question": "q", "corpus": "cdisc"})
    done = [d for e, d in _events(r.text) if e == "done"][0]
    assert done["quota"]["free_remaining"] == 1 and done["quota"]["free_per_day"] == 3
    assert _ask(client, router).status_code == 200
    r = _ask(client, router)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    d = r.json()["detail"]
    assert d["code"] == "free_quota_exhausted" and d["remaining"] == 0 and "reset_at" in d
    info = client.get("/api/info").json()
    assert info["quota"]["free_remaining"] == 0


def test_cookieless_client_is_bounded_by_ip(make):
    client, router = make(quota_free_per_day=10, quota_free_per_ip_day=4)
    codes = []
    for _ in range(5):
        client.cookies.clear()
        codes.append(_ask(client, router).status_code)
    assert codes == [200, 200, 200, 200, 429]


def test_cf_connecting_ip_only_trusted_from_tunnel_peer(make):
    # untrusted peer: spoofed header ignored -> all requests counted on the peer IP
    client, router = make(client_addr=("10.0.0.2", 1), quota_free_per_ip_day=2,
                          quota_trusted_proxies="10.0.0.1/32")
    codes = []
    for i in range(3):
        client.cookies.clear()
        router.ask_script = [_resp("a")]
        codes.append(client.post("/api/ask", json={"question": "q", "corpus": "cdisc"},
                                 headers={"CF-Connecting-IP": f"203.0.113.{i}"}).status_code)
    assert codes == [200, 200, 429]
    # trusted tunnel peer: each CF-Connecting-IP is its own client
    client, router = make(client_addr=("10.0.0.1", 1), quota_free_per_ip_day=2,
                          quota_trusted_proxies="10.0.0.1/32")
    for i in range(3):
        client.cookies.clear()
        router.ask_script = [_resp("a")]
        r = client.post("/api/ask", json={"question": "q", "corpus": "cdisc"},
                        headers={"CF-Connecting-IP": f"198.51.100.{i}"})
        assert r.status_code == 200


def test_counts_survive_restart(make):
    client, router = make(quota_free_per_day=2)
    assert _ask(client, router).status_code == 200
    assert _ask(client, router).status_code == 200
    jar = dict(client.cookies)
    client2, router2 = make(quota_free_per_day=2)     # new app + store reopened from disk
    client2.cookies.update(jar)
    r = _ask(client2, router2)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "free_quota_exhausted"


def test_tampered_cookie_is_a_new_visitor(make):
    client, router = make(quota_free_per_day=1, quota_free_per_ip_day=100)
    assert _ask(client, router).status_code == 200
    assert _ask(client, router).status_code == 429
    name = quota.cfg(None, "visitor_cookie_name")
    vid_signed = client.cookies[name]
    client.cookies.clear()
    client.cookies.set(name, "attacker" + vid_signed[8:])   # forged signature
    r = _ask(client, router)
    assert r.status_code == 200 and "set-cookie" in r.headers  # re-minted, not the old visitor


BYOK_KEY = "sk-user-test-key"
BYOK_BODY = {"provider": "openai", "model": "gpt-5.4-mini"}   # an L1 registry provider/model


def _byok(monkeypatch):
    """Real L1 BYOK path (byok_enabled on private + registry provider/model); only the provider wire
    (litellm.completion, which L1 calls directly for BYOK answers) is faked. Returns its calls."""
    import litellm

    seen = []

    def fake_completion(**kw):
        seen.append(kw)
        return _resp("BYOK answer [Source: x].", model=kw["model"])

    monkeypatch.setattr(litellm, "completion", fake_completion)
    return seen


def test_cap_reached_free_off_byok_still_works(make, monkeypatch):
    seen = _byok(monkeypatch)
    client, router = make(quota_site_cap_usd=5.0, quota_byok_side_budget_usd=2.0, byok_enabled=True)
    store = quota._store(client.app.state.settings)
    assert store.reserve("seed", quota._day(), 3.0, None, quota._now())   # free share used up
    assert store.settle("seed", 3.0)
    r = _ask(client, router)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "site_cap_reached"
    before = store.spent(quota._day(), "byok")
    # fresh question: the query-embedding cache must not hide the server-key embedding call
    r = client.post("/api/ask", json={"question": "BYOK question about AESEV?", "corpus": "cdisc",
                                      **BYOK_BODY}, headers={providers.BYOK_KEY_HEADER: BYOK_KEY})
    assert r.status_code == 200 and r.json()["quota"]["byok"] is True
    assert seen and all(kw["api_key"] == BYOK_KEY for kw in seen)   # answer on the user's key
    assert store.spent(quota._day(), "byok") > before   # its server-key embedding: BYOK pool
    assert store.spent(quota._day()) <= 5.0 + 1e-9


def test_kill_switch_disables_free_not_byok(make, monkeypatch):
    seen = _byok(monkeypatch)
    monkeypatch.setenv("SDTM_RAG_FREE_TIER_DISABLED", "1")
    client, router = make(byok_enabled=True)
    r = _ask(client, router)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "free_tier_disabled"
    r = client.post("/api/ask", json={"question": "q", "corpus": "cdisc", **BYOK_BODY},
                    headers={providers.BYOK_KEY_HEADER: BYOK_KEY})
    assert r.status_code == 200 and seen


def test_cap_hit_mid_request_keeps_the_partial_answer(make, engines):
    # P2.9 #13 (CR5) — deliberate change of this pinned test: it asserted 429 + the half answer
    # discarded (contract v1.1 §2.3). v1.2: a refused CONTINUATION round is treated like a failed
    # one: 200, the parts so far, truncated=True, continue_error=<refusal code>.
    _base, _rag, rec, _ = engines
    client, router = make(quota_site_cap_usd=5.0)
    s = client.app.state.settings
    store = quota._store(s)
    real = router.completion

    def completion(**kw):
        out = real(**kw)
        if kw["model"] == "default":   # after the first answer round: the day's spend hits the cap
            store.reserve("other-visitors", quota._day(), 5.0, None, quota._now())
            store.settle("other-visitors", 5.0)   # SETTLED spend (open-only would be site_busy)
        return out

    router.completion = completion
    router.ask_script = [_resp("Part one. ", finish="length"), _resp("never")]
    rec.calls.clear()
    r = client.post("/api/ask", json={"question": "q", "corpus": "cdisc"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["answer"].startswith("Part one.") and "never" not in j["answer"]
    assert j["truncated"] is True and j["continue_error"] == "site_cap_reached"
    answers = [c for c in rec.calls if c["call"] == "router.completion" and c["model"] == "default"]
    assert len(answers) == 1          # first round ran; the continuation was refused before the wire


def test_ipv6_clients_keyed_by_64(make):
    client, router = make(client_addr=("2001:db8:1:2::1", 1), quota_free_per_ip_day=1)
    assert _ask(client, router).status_code == 200
    client, router = make(client_addr=("2001:db8:1:2:ffff::9", 1), quota_free_per_ip_day=1)
    assert _ask(client, router).status_code == 429     # same /64, new cookie jar
    client, router = make(client_addr=("2001:db8:1:3::1", 1), quota_free_per_ip_day=1)
    assert _ask(client, router).status_code == 200     # different /64


def test_aborted_stream_is_still_charged(make):
    client, router = make()
    store_s = client.app.state.settings
    router.stream_script = [[_chunk("partial "), RuntimeError("upstream cut")]]
    r = client.post("/api/ask_stream", json={"question": "q", "corpus": "cdisc"})
    assert [e for e, _ in _events(r.text)][-1] == "error"
    st = quota._store(store_s)
    est = quota._estimate(store_s, "answer", {"model": "default", "messages": [
        {"role": "user", "content": "x"}]})[0]
    # P2.9 #1 (deliberate change; was ">= est", the whole max_output reservation): no usage =>
    # prompt + 1.5 x what streamed. Strictly above zero, far below one full reservation.
    assert 0 < st.spent(quota._day()) < est / 10
    rows = st._db.execute("SELECT status FROM reservations").fetchall()
    assert rows and all(s in ("settled", "charged") for (s,) in rows)


def test_oversized_history_is_trimmed(make, engines):
    _base, _rag, rec, _ = engines
    client, router = make()
    hist = [{"role": "user" if i % 2 == 0 else "assistant", "content": chr(97 + i) * 3000}
            for i in range(12)]
    rec.calls.clear()
    r = _ask(client, router, history=hist)
    assert r.status_code == 200
    answer = [c for c in rec.calls if c["call"] == "router.completion" and c["model"] == "default"][0]
    # system + 6 kept (6 x 3000 = 18000 <= 20000, 7 would exceed) + question
    assert answer["roles"] == ["system"] + ["user", "assistant"] * 3 + ["user"]


def test_body_too_large_is_413(make):
    client, router = make(quota_max_body_bytes=5000)
    r = client.post("/api/ask", json={"question": "x" * 6000})
    assert r.status_code == 413
    assert r.json() == {"detail": {"code": "request_too_large", "message": "请求体过大。",
                                   "limit": 5000}}

    def chunks():
        yield b'{"question": "'
        yield b"x" * 6000
        yield b'"}'

    r = client.post("/api/ask", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert _ask(client, router).status_code == 200   # small body passes through intact


def test_flag_rate_limited(make, engines, tmp_path):
    real = engines[0].dogfood_log_path                 # the base settings' (repo data/) path
    before = real.stat().st_mtime_ns if real.exists() else None
    client, _router = make(flag_rate_per_min=1, flag_rate_burst=2)
    assert client.app.state.settings.dogfood_log_path.is_relative_to(tmp_path)
    codes = [client.post("/api/flag", json={"question": "q", "note": "n"}).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]
    r = client.post("/api/flag", json={"question": "q"})
    assert r.json()["detail"]["code"] == "rate_limited" and "retry-after" in r.headers
    assert (tmp_path / "dogfood.md").read_text(encoding="utf-8").count("**Q:** q") == 2
    assert (real.stat().st_mtime_ns if real.exists() else None) == before   # nothing outside tmp


def test_free_stream_gets_no_web(make, engines):
    _base, _rag, rec, _ = engines
    client, router = make()
    router.stream_script = [[_chunk("ok"), _chunk(finish="stop"), _chunk(usage=True)]]
    rec.calls.clear()
    r = client.post("/api/ask_stream", json={"question": "q", "corpus": "cdisc", "web": True})
    ev = _events(r.text)
    assert ev[0][1]["downgrades"] == [{"capability": "web_tools", "reason": "free_tier_no_web"}]
    stream_calls = [c for c in rec.calls if c["call"] == "router.acompletion"]
    assert stream_calls and all("tools" not in c for c in stream_calls)


def test_enabled_without_secret_fails_at_startup(engines):
    from fastapi import FastAPI

    from server.auth import install_security

    base = engines[0]
    with pytest.raises(RuntimeError, match="VISITOR_SECRET"):
        install_security(FastAPI(), S(base, quota_enabled=True))


def test_private_default_installs_nothing(engines):
    from fastapi import FastAPI

    from server.auth import install_security

    base = engines[0]
    app = FastAPI()
    install_security(app, base)
    names = [m.cls.__name__ for m in app.user_middleware]
    assert names == ["SecurityHeadersMiddleware"]


def test_declared_oversized_body_is_refused_without_reading_it():
    import asyncio

    from server.auth import BodyLimitMiddleware

    async def app(scope, receive, send):
        pytest.fail("app must not run")

    async def receive():
        pytest.fail("body must not be read when Content-Length is over the limit")

    sent = []

    async def send(msg):
        sent.append(msg)

    mw = BodyLimitMiddleware(app, limit=10)
    scope = {"type": "http", "method": "POST", "path": "/api/ask",
             "headers": [(b"content-length", b"999999999")]}
    asyncio.run(mw(scope, receive, send))
    assert sent[0]["status"] == 413


def test_public_tier_requires_trusted_proxies(engines):
    from fastapi import FastAPI

    from server.auth import install_security

    base = engines[0]
    with pytest.raises(RuntimeError, match="TRUSTED_PROXIES"):
        install_security(FastAPI(), S(base, instance="public", visitor_secret="t" * 32))
    install_security(FastAPI(), S(base, instance="public", visitor_secret="t" * 32,
                                  quota_trusted_proxies="10.0.0.1/32"))


def test_validate_body_exempt_only_on_private(make):
    big = {"file": ("a.csv", b"x" * 6000, "text/csv")}
    from scripts.spec_loader import SpecLoader
    from server.config import settings as global_settings

    client, _ = make(quota_max_body_bytes=5000)
    client.app.state.spec_loader = SpecLoader(global_settings.kb_root)
    assert client.post("/api/validate", files=big).status_code != 413
    client, _ = make(quota_max_body_bytes=5000, instance="public",
                     quota_trusted_proxies="10.0.0.1/32")
    r = client.post("/api/validate", files=big)
    assert r.status_code == 413 and r.json()["detail"]["code"] == "request_too_large"
