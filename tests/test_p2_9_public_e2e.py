"""P2.9 #9 (CR test gap): the PUBLIC tier end to end — `create_app(public settings)` with quota on (its
default), real middleware stack (BodyLimit / Visitor / FlagRateLimit / SecurityHeaders), real
instance/providers/quota hooks and outbound seam, through /api/ask and /api/ask_stream. Only the
wire is faked (router double, litellm.embedding / completion), no lifespan (no chroma build)."""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from server import providers, quota
from server.config import SelectableModel, Settings
from server.main import create_app
from tests.conftest import set_public_quota_env
from tests.test_p2_l2_integration import (
    engines,  # noqa: F401 — module fixture (tiny chroma + fakes)
)
from tests.test_p2_seam_characterization import _chunk, _FakeRouter, _resp

MODEL = "ds-v4"
PUBLIC_MODELS = [SelectableModel(id=MODEL, label="DeepSeek V4 Pro", model="deepseek/deepseek-v4-pro",
                                 verified=False, max_output_tokens=32000)]


@pytest.fixture
def pub(engines, tmp_path, monkeypatch):  # noqa: F811
    """pub(**settings) -> (TestClient, router, settings). A fresh app + store per call."""
    for k in list(os.environ):
        if k.startswith("SDTM_RAG_"):
            monkeypatch.delenv(k)
    set_public_quota_env(monkeypatch)
    for k in ("RATE_PER_MIN", "RATE_BURST", "IP_RATE_PER_MIN", "IP_RATE_BURST"):
        monkeypatch.setenv(f"SDTM_RAG_QUOTA_{k}", "10000")
    base, rag, rec, _root = engines
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    nostudy = tmp_path / "nostudy"

    def _make(**kw):
        quota._STORES.clear()
        s = Settings(instance="public", selectable_models=PUBLIC_MODELS, data_dir_override=str(data),
                     study_kb_root=nostudy / "cards", study_catalog_path=nostudy / "catalog.json",
                     study_aliases_path=nostudy / "aliases.yml", chroma_dir=base.chroma_dir,
                     kb_root=base.kb_root, collection_name="cdisc_t", top_k=3, **kw)
        app = create_app(s)             # check_startup + install_security run; no lifespan
        router = _FakeRouter(rec)
        app.state.rag, app.state.llm_router = rag, router
        rec.calls.clear()
        # https: the public visitor cookie is Secure (an http:// client would mint a new visitor
        # on every request and only the per-IP limit would apply)
        return TestClient(app, base_url="https://testserver"), router, s

    yield _make
    quota._STORES.clear()


def _events(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        out.append((lines[0][len("event: "):], json.loads(lines[1][len("data: "):])))
    return out


def _remaining(client):
    return client.get("/api/info").json()["quota"]["free_remaining"]


def _ask(client, router, **body):
    router.ask_script = [_resp("Answer [Source: x].")]
    return client.post("/api/ask", json={"question": "What is AETERM?", "model": MODEL, **body})


def test_quota_off_refuses_to_start(pub, monkeypatch):  # noqa: F811
    monkeypatch.setenv("SDTM_RAG_QUOTA_ENABLED", "false")
    with pytest.raises(RuntimeError, match="unmetered"):
        pub()
    monkeypatch.setenv("SDTM_RAG_QUOTA_ENABLED", "flase")     # typo: refuses too, never fails open
    with pytest.raises(RuntimeError, match="not a boolean"):
        pub()


def test_l3_and_l1_refusals_do_not_consume_a_free_question(pub, monkeypatch):  # noqa: F811
    monkeypatch.setenv("SDTM_RAG_QUOTA_FREE_PER_DAY", "2")
    client, router, _s = pub()
    assert _remaining(client) == 2
    refusals = [
        ("/api/ask", {"dossier": "on"}, 403, "not_on_this_tier"),           # L3
        ("/api/ask_stream", {"corpus": "study"}, 403, "not_on_this_tier"),  # L3
        ("/api/ask", {"model": "default"}, 422, "model_not_allowed"),       # L3 internal group
        ("/api/ask_stream", {"model": "nope"}, 422, "model_not_allowed"),   # L1 public whitelist
        ("/api/ask", {"provider": "openai"}, 400, "byok_key_missing"),      # L1 combo table
    ]
    for path, extra, status, code in refusals:
        r = client.post(path, json={"question": "q", "model": MODEL, **extra})
        assert (r.status_code, r.json()["detail"]["code"]) == (status, code), (path, extra, r.text)
    assert _remaining(client) == 2
    assert _ask(client, router).status_code == 200
    router.stream_script = [[_chunk("ok"), _chunk(finish="stop"), _chunk(usage=True)]]
    r = client.post("/api/ask_stream", json={"question": "q", "model": MODEL})
    assert [d for e, d in _events(r.text) if e == "done"][0]["quota"]["free_remaining"] == 0
    r = _ask(client, router)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "free_quota_exhausted"


def test_byok_on_public_charges_the_byok_pool_not_the_free_count(pub, monkeypatch):  # noqa: F811
    import litellm

    seen = []

    def fake_completion(**kw):
        seen.append(kw)
        return _resp("BYOK answer [Source: x].", model=kw["model"])

    monkeypatch.setattr(litellm, "completion", fake_completion)
    client, _router, s = pub()
    before = _remaining(client)
    r = client.post("/api/ask", json={"question": "Public BYOK question about AESER?",
                                      "provider": "openai", "model": "gpt-5.4-mini"},
                    headers={providers.BYOK_KEY_HEADER: "sk-user-public-e2e"})
    assert r.status_code == 200, r.text
    assert r.json()["quota"]["byok"] is True
    assert seen and all(kw["api_key"] == "sk-user-public-e2e" for kw in seen)
    assert _remaining(client) == before
    store = quota._store(s)
    assert store.spent(quota._day(), "byok") > 0      # its server-key embedding
    assert store.spent(quota._day(), "free") == 0


def test_free_web_is_downgraded_once_and_reported_off(pub):  # noqa: F811
    client, router, _s = pub()
    router.stream_script = [[_chunk("ok"), _chunk(finish="stop"), _chunk(usage=True)]]
    r = client.post("/api/ask_stream", json={"question": "q", "model": MODEL, "web": True})
    ev = _events(r.text)
    note = [{"capability": "web_tools", "reason": "free_tier_no_web"}]
    assert ev[0][1]["downgrades"] == note
    done = [d for e, d in ev if e == "done"][0]
    assert done["downgrades"] == note and done["web_status"] == "off"
    calls = [c for c in router.rec.calls if c["call"] == "router.acompletion"]
    assert calls and all("tools" not in c for c in calls)


def test_free_web_key_actually_enables_web(pub, monkeypatch):  # noqa: F811
    monkeypatch.setenv("SDTM_RAG_QUOTA_FREE_WEB_ENABLED", "true")
    client, router, _s = pub()
    router.stream_script = [[_chunk("ok"), _chunk(finish="stop"), _chunk(usage=True)]]
    r = client.post("/api/ask_stream", json={"question": "q", "model": MODEL, "web": True})
    ev = _events(r.text)
    assert "downgrades" not in ev[0][1]
    calls = [c for c in router.rec.calls if c["call"] == "router.acompletion"]
    assert calls and "tools" in calls[0]


def test_upstream_cut_charges_prompt_plus_streamed(pub):  # noqa: F811
    client, router, s = pub()
    router.stream_script = [[_chunk("partial answer " * 20), RuntimeError("upstream cut")]]
    r = client.post("/api/ask_stream", json={"question": "q", "model": MODEL})
    assert [e for e, _ in _events(r.text)][-1] == "error"
    store = quota._store(s)
    full = quota.round_estimate_usd(s, MODEL)
    spent = store.spent(quota._day())
    out_floor = quota._price(s, "m-stream", 0, quota._text_tokens("partial answer " * 20))
    assert out_floor < spent < full / 10      # charged what streamed (x1.5 + prompt), not 32K out
    rows = store._db.execute("SELECT status FROM reservations").fetchall()
    assert rows and all(st in ("settled", "charged") for (st,) in rows)


def test_client_closing_the_stream_early_settles_partial(pub):  # noqa: F811
    client, router, s = pub()
    router.stream_script = [[_chunk(f"tok{i} ") for i in range(200)]
                            + [_chunk(finish="stop")]]   # no usage chunk ever
    with client.stream("POST", "/api/ask_stream", json={"question": "q", "model": MODEL}) as r:
        for line in r.iter_lines():
            if line.startswith("event: token"):
                break                         # reader goes away mid-answer
    store = quota._store(s)
    rows = store._db.execute("SELECT status, usd FROM reservations").fetchall()
    # settled from what streamed (prompt + 1.5 x text) — not left open, not the 32K-output charge
    assert rows and all(st == "settled" for st, _ in rows)
    assert 0 < store.spent(quota._day()) < quota.round_estimate_usd(s, MODEL) / 2


def test_public_info_is_not_cacheable(pub):  # noqa: F811
    client, _router, _s = pub()
    r = client.get("/api/info")
    assert r.headers["cache-control"] == "no-store" and r.json()["tier"] == "public"
