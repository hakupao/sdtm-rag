"""P2 L1 end-to-end through the real router (characterization harness, faked wire): BYOK routing,
no Router / no server key for BYOK, server-side calls keep the server key, refusal codes, each
downgrade marker on the wire, and key redaction in the router's own rendered log lines."""
from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

from server import providers
from server.config import SelectableModel
from tests.test_p2_seam_characterization import _chunk, _resp, _tool_delta, harness  # noqa: F401

KEY = "-".join(["sk", "wire", "USERKEY", "fedcba9876543210"])
HDR = {providers.BYOK_KEY_HEADER: KEY}


@pytest.fixture
def tier(harness):  # noqa: F811
    """Set undeclared L3 settings keys (instance / byok_enabled / public_models) on the harness
    settings for one test, then remove them."""
    s = harness[0].app.state.settings
    added = []

    def set_(**kw):
        for k, v in kw.items():
            object.__setattr__(s, k, v)
            added.append(k)
    yield set_
    for k in added:
        s.__dict__.pop(k, None)


@pytest.fixture
def wire(monkeypatch):
    """Fake litellm.completion / acompletion for BYOK calls (the harness fakes are not streams)."""
    import litellm

    calls = []
    script = {"completion": [], "acompletion": []}

    def completion(**kw):
        calls.append(("completion", kw))
        item = script["completion"].pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def acompletion(**kw):
        calls.append(("acompletion", kw))
        item = script["acompletion"].pop(0)
        if isinstance(item, BaseException):
            raise item

        async def agen():
            for c in item:
                if isinstance(c, BaseException):
                    raise c
                yield c
        return agen() if kw.get("stream") else item

    monkeypatch.setattr(litellm, "completion", completion)
    monkeypatch.setattr(litellm, "acompletion", acompletion)
    return SimpleNamespace(calls=calls, script=script)


class _Upstream(Exception):  # noqa: N818
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status_code = status


def _events(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        out.append((lines[0][len("event: "):], json.loads(lines[1][len("data: "):])))
    return out


# ── routing / key placement ─────────────────────────────────────────────

def test_byok_ask_goes_direct_with_user_key_and_preset_base(harness, tier, wire):  # noqa: F811
    client, rec, router = harness
    tier(byok_enabled=True)
    wire.script["completion"] = [_resp("BYOK answer.", model="qwen3-max")]
    rec.calls.clear()
    r = client.post("/api/ask", json={"question": "What is AETERM?", "corpus": "auto",
                                      "provider": "qwen", "model": "qwen3-max"}, headers=HDR)
    assert r.status_code == 200, r.text
    assert r.json()["answer"] == "BYOK answer."
    (kind, kw), = wire.calls
    assert kind == "completion" and kw["model"] == "openai/qwen3-max" and kw["api_key"] == KEY
    assert kw["api_base"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert kw["max_tokens"] == 32768 and kw["num_retries"] == 1
    # never the Router for the answer; server-side calls (route / embedding) keep the server key
    answer_on_router = [c for c in rec.calls if c["call"].startswith("router.")
                        and c.get("model") not in ("light", "hard")]
    assert answer_on_router == []
    assert any(c["call"] == "router.completion" and c["model"] == "light" for c in rec.calls)
    emb = [c for c in rec.calls if c["call"] == "litellm.embedding"]
    assert emb and not any(c["api_key"] or c["api_base"] for c in emb)


def test_byok_stream_continue_rounds_all_use_user_key(harness, tier, wire):  # noqa: F811
    client, rec, _router = harness
    tier(byok_enabled=True)
    wire.script["acompletion"] = [
        [_chunk("Part one "), _chunk(finish="length"), _chunk(usage=True)],
        [_chunk("part two."), _chunk(finish="stop"), _chunk(usage=True)]]
    rec.calls.clear()
    ev = _events(client.post("/api/ask_stream", json={
        "question": "Define AETERM", "corpus": "cdisc", "provider": "anthropic",
        "model": "claude-sonnet-5-5"}, headers=HDR).text)
    assert [e for e, _ in ev][-1] == "done"
    assert len(wire.calls) == 2
    assert all(kw["api_key"] == KEY and kw["model"] == "anthropic/claude-sonnet-5-5"
               for _, kw in wire.calls)
    assert not any(c["call"] == "router.acompletion" for c in rec.calls)


def test_server_key_request_unchanged_when_byok_enabled(harness, tier):  # noqa: F811
    client, rec, router = harness
    tier(byok_enabled=True)
    router.ask_script = [_resp("server answer")]
    rec.calls.clear()
    r = client.post("/api/ask", json={"question": "q", "corpus": "cdisc"})
    assert r.status_code == 200
    ans = [c for c in rec.calls if c["call"] == "router.completion"]
    assert ans and ans[-1]["model"] == "default" and not ans[-1]["api_key"]


# ── refusals ────────────────────────────────────────────────────────────

def test_upstream_401_is_byok_key_invalid_and_never_retries_on_server_key(harness, tier, wire):  # noqa: F811
    client, rec, router = harness
    tier(byok_enabled=True)
    wire.script["completion"] = [_Upstream(401, f"invalid x-api-key {KEY}")]
    rec.calls.clear()
    r = client.post("/api/ask", json={"question": "q", "corpus": "cdisc", "provider": "openai",
                                      "model": "gpt-5.5"}, headers=HDR)
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "byok_key_invalid" and KEY not in r.text
    assert not any(c["call"].startswith("router.") for c in rec.calls)
    assert len(wire.calls) == 1


def test_upstream_5xx_on_answer_is_byok_provider_error(harness, tier, wire):  # noqa: F811
    client, _rec, _router = harness
    tier(byok_enabled=True)
    wire.script["completion"] = [_Upstream(503, f"overloaded; key={KEY}")]
    r = client.post("/api/ask", json={"question": "q", "corpus": "cdisc", "provider": "deepseek",
                                      "model": "deepseek-v4-pro"}, headers=HDR)
    assert r.status_code == 502 and KEY not in r.text
    d = r.json()["detail"]
    assert d == {"code": "byok_provider_error", "message": d["message"], "provider": "deepseek",
                 "upstream_status": 503}


def test_stream_open_failure_after_narrow_retry_is_error_event_with_code(harness, tier, wire):  # noqa: F811
    client, _rec, _router = harness
    tier(byok_enabled=True)
    wire.script["acompletion"] = [_Upstream(400, "bad param"), _Upstream(500, f"boom {KEY}")]
    ev = _events(client.post("/api/ask_stream", json={
        "question": "q", "corpus": "cdisc", "provider": "openai", "model": "gpt-5.5"},
        headers=HDR).text)
    assert len(wire.calls) == 2 and "stream_options" not in wire.calls[1][1]   # narrow retry ran
    assert ev[-1][0] == "error" and ev[-1][1]["code"] == "byok_provider_error"
    assert KEY not in json.dumps(ev)


def test_stream_401_is_error_event_byok_key_invalid(harness, tier, wire):  # noqa: F811
    client, _rec, _router = harness
    tier(byok_enabled=True)
    wire.script["acompletion"] = [_Upstream(401, "nope")]
    ev = _events(client.post("/api/ask_stream", json={
        "question": "q", "corpus": "cdisc", "provider": "openai", "model": "gpt-5.5"},
        headers=HDR).text)
    assert ev[-1] == ("error", {"code": "byok_key_invalid", "message": ev[-1][1]["message"],
                                "provider": "openai"})
    assert len(wire.calls) == 1


def test_combo_refusals_on_the_wire(harness, tier):  # noqa: F811
    client, _rec, _router = harness
    tier(byok_enabled=True)
    for body, headers, want in (
            ({"provider": None}, HDR, (400, "provider_required")),
            ({"provider": "openai", "model": "gpt-5.5"}, {}, (400, "byok_key_missing")),
            ({"provider": "openai", "model": "opus-5"}, HDR, (422, "model_not_allowed"))):
        for ep in ("/api/ask", "/api/ask_stream"):
            r = client.post(ep, json={"question": "q", "corpus": "cdisc", **body}, headers=headers)
            assert (r.status_code, r.json()["detail"]["code"]) == want, (ep, body, r.text)


def test_byok_headers_refused_when_byok_off(harness):  # noqa: F811
    client, rec, _router = harness
    rec.calls.clear()
    r = client.post("/api/ask", json={"question": "q", "corpus": "cdisc", "provider": "openai",
                                      "model": "gpt-5.5"}, headers=HDR)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_on_this_tier"
    assert rec.calls == []


# ── downgrade markers on the wire (contract §2.4), one per downgrade ─────

def test_downgrade_web_tools_no_tool_calling(harness, tier, wire, monkeypatch):  # noqa: F811
    client, rec, _router = harness
    tier(byok_enabled=True)
    import server.provider_registry_net as net
    monkeypatch.setattr(net, "_resolve", lambda h, p: ["93.184.216.34"])
    wire.script["acompletion"] = [[_chunk("no web."), _chunk(finish="stop"), _chunk(usage=True)]]
    rec.calls.clear()
    ev = dict(_events(client.post("/api/ask_stream", json={
        "question": "q", "corpus": "cdisc", "web": True, "provider": "custom", "model": "my-llm"},
        headers={**HDR, providers.BYOK_BASE_HEADER: "https://llm.example.com/v1"}).text))
    dg = [{"capability": "web_tools", "reason": "no_tool_calling"}]
    assert ev["sources"]["downgrades"] == dg and ev["done"]["downgrades"] == dg
    assert "tools" not in wire.calls[0][1] and wire.calls[0][1]["client"] is not None
    assert not any(c["call"] == "tavily.post" for c in rec.calls)


def test_downgrade_web_tools_free_tier_no_web(harness, tier, monkeypatch, tmp_path):  # noqa: F811
    client, rec, router = harness
    s = client.app.state.settings
    free = SelectableModel(id="ds-free", label="DS", model="deepseek/deepseek-v4-pro", verified=False)
    monkeypatch.setattr(s, "selectable_models", [*s.selectable_models, free])
    tier(instance="public", quota_db_path=str(tmp_path / "quota.sqlite"))   # L2 store off repo data/
    router.stream_script = [[_chunk("ok"), _chunk(finish="stop"), _chunk(usage=True)]]
    rec.calls.clear()
    ev = dict(_events(client.post("/api/ask_stream", json={
        "question": "q", "corpus": "cdisc", "web": True, "model": "ds-free"}).text))
    dg = [{"capability": "web_tools", "reason": "free_tier_no_web"}]
    assert ev["sources"]["downgrades"] == dg and ev["done"]["downgrades"] == dg
    call = [c for c in rec.calls if c["call"] == "router.acompletion"][0]
    assert call["model"] == "ds-free" and "tools" not in call


def test_downgrade_vision_no_vision(harness, tier, wire, monkeypatch):  # noqa: F811
    client, _rec, _router = harness
    tier(byok_enabled=True)
    touched = []
    builder = SimpleNamespace(index=SimpleNamespace(form_named_in=lambda q: touched.append(q)))
    monkeypatch.setattr(client.app.state, "pdf_context", builder, raising=False)
    wire.script["completion"] = [_resp("x")]
    body = client.post("/api/ask", json={"question": "q", "corpus": "cdisc", "provider": "deepseek",
                                         "model": "deepseek-v4-pro"}, headers=HDR).json()
    assert body["downgrades"] == [{"capability": "vision", "reason": "no_vision"}]
    assert touched == [] and body["pdf_pages"] is None


def test_byok_never_auto_attaches_dossier_but_server_key_small_context_downgrades(  # noqa: PLR0913
        harness, tier, wire, monkeypatch):  # noqa: F811
    """Decision (PLAN D5): BYOK => dossier auto OFF (explicit dossier=on still allowed); server-key
    allowlisted model below the context threshold => dossier_auto/context_too_small marker."""
    client, _rec, router = harness
    tier(byok_enabled=True)
    s = client.app.state.settings
    small = SelectableModel(id="glm-small", label="GLM", model="zai/glm-5.1", verified=False)
    monkeypatch.setattr(s, "selectable_models", [*s.selectable_models, small])
    monkeypatch.setattr(s, "dossier_auto_attach_models", ["opus-5", "glm-small"])
    import server.dossier_trigger as dt
    seen = []
    monkeypatch.setattr(dt, "decide_dossier", lambda *a, **kw: seen.append(kw["auto_attach"])
                        or SimpleNamespace(attach=False, reason="r", domains=()))
    monkeypatch.setattr(client.app.state, "dossier",
                        SimpleNamespace(sha="x", sections=(), chars=0, text=""), raising=False)
    wire.script["acompletion"] = [[_chunk("b"), _chunk(finish="stop"), _chunk(usage=True)]]
    ev = dict(_events(client.post("/api/ask_stream", json={
        "question": "q", "corpus": "cdisc", "provider": "gemini", "model": "gemini-3.5-flash"},
        headers=HDR).text))
    assert "downgrades" not in ev["done"]            # 1M-context BYOK model: still no auto, no marker
    router.stream_script = [[_chunk("a"), _chunk(finish="stop"), _chunk(usage=True)],
                            [_chunk("c"), _chunk(finish="stop"), _chunk(usage=True)]]
    ev = dict(_events(client.post("/api/ask_stream", json={
        "question": "q", "corpus": "cdisc", "model": "glm-small"}).text))
    assert ev["done"]["downgrades"] == [{"capability": "dossier_auto", "reason": "context_too_small",
                                         "detail": "200000"}]
    client.post("/api/ask_stream", json={"question": "q", "corpus": "cdisc", "model": "opus-5"})
    assert seen == [False, False, True]               # BYOK, small server model, 1M server model


# ── Anthropic BYOK prompt cache (contract §3 L1 follow-up) ──────────────

def test_byok_anthropic_dossier_layout_gets_cache_breakpoint_without_mutating_router_messages():
    from server.config import Settings
    from server.request_context import Credentials, RequestContext

    s = Settings()
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=s)))
    ctx = RequestContext(endpoint="ask", request=req, credentials=Credentials(api_key=KEY),
                         provider="anthropic")
    caps = SimpleNamespace(prompt_cache=True)
    ctx.flags["byok"] = {"provider": "anthropic", "model": "anthropic/claude-sonnet-5-5",
                         "api_base": None, "max_tokens": 1, "caps": caps, "pin": None,
                         "timeout": 1, "num_retries": 0}
    sys_with = "rules ... 【本研究 研読パッケージ】 ..."
    msgs = [{"role": "system", "content": sys_with}, {"role": "user", "content": "q"}]
    _fn, kw = providers.resolve(ctx, "answer", "completion", object(), {"model": "x", "messages": msgs})
    assert kw["messages"][0]["content"] == [{"type": "text", "text": sys_with,
                                             "cache_control": {"type": "ephemeral"}}]
    assert msgs[0]["content"] == sys_with                     # router's list untouched
    plain = [{"role": "system", "content": "no dossier"}, {"role": "user", "content": "q"}]
    _fn, kw = providers.resolve(ctx, "answer", "completion", object(), {"model": "x", "messages": plain})
    assert kw["messages"] is plain
    # kill switch (dossier_prompt_cache=False): legacy layout also carries the marker -> no rewrite
    s.dossier_prompt_cache = False
    _fn, kw = providers.resolve(ctx, "answer", "completion", object(), {"model": "x", "messages": msgs})
    assert kw["messages"] is msgs


# shapeless key (no sk-/AIza/Bearer shape): only the exact-key scrub via the request ctx catches it
ODD = "".join(["q9", "Zx", "77", "Lm", "Np", "0w"]) * 3


@pytest.fixture
def rendered_log():
    import structlog

    import server.main as main_mod

    buf = io.StringIO()
    old = structlog.get_config()
    structlog.configure(processors=main_mod.LOG_PROCESSORS,
                        logger_factory=structlog.PrintLoggerFactory(buf),
                        cache_logger_on_first_use=False)
    yield buf
    structlog.configure(**old)


def test_router_log_line_with_upstream_error_containing_key_is_redacted(harness, tier, wire,  # noqa: F811
                                                                        rendered_log):
    """/api/ask continue-round failure keeps the raw upstream exception (router logs error=str(e) +
    exc_info): render through main.py's processors and grep."""
    client, _rec, _router = harness
    tier(byok_enabled=True)
    wire.script["completion"] = [_resp("Half ", finish="length"),
                                 _Upstream(500, f"upstream echoed token {ODD} in body")]
    r = client.post("/api/ask", json={"question": "q", "corpus": "cdisc", "provider": "glm",
                                      "model": "glm-5.1"}, headers={providers.BYOK_KEY_HEADER: ODD})
    text = rendered_log.getvalue()
    assert r.status_code == 200 and r.json()["truncated"] is True
    assert "continue_round_failed" in text and "upstream echoed token" in text and "Traceback" in text
    assert ODD not in text and ODD not in r.text


def test_stream_log_line_with_upstream_error_containing_key_is_redacted(harness, tier, wire,  # noqa: F811
                                                                        rendered_log):
    """Chat UI path: continue round fails on open (+ narrow retry) -> router logs stream_failed."""
    client, _rec, _router = harness
    tier(byok_enabled=True)
    wire.script["acompletion"] = [[_chunk("Half "), _chunk(finish="length"), _chunk(usage=True)],
                                  _Upstream(500, f"echo {ODD}"), _Upstream(500, f"echo again {ODD}")]
    r = client.post("/api/ask_stream", json={"question": "q", "corpus": "cdisc", "provider": "glm",
                                             "model": "glm-5.1"},
                    headers={providers.BYOK_KEY_HEADER: ODD})
    text = rendered_log.getvalue()
    ev = _events(r.text)
    assert ev[-1] == ("error", {"message": "LLM stream failed"})
    assert "stream_failed" in text and "echo again" in text and "Traceback" in text
    assert ODD not in text and ODD not in r.text


def test_byok_midstream_failure_is_coded_error_event(harness, tier, wire):  # noqa: F811
    client, _rec, _router = harness
    tier(byok_enabled=True)
    wire.script["acompletion"] = [[_chunk("Half "), _Upstream(502, f"cut {KEY}")]]
    ev = _events(client.post("/api/ask_stream", json={
        "question": "q", "corpus": "cdisc", "provider": "openai", "model": "gpt-5.5"},
        headers=HDR).text)
    assert [e for e, _ in ev] == ["sources", "token", "error"]
    assert ev[-1][1]["code"] == "byok_provider_error" and ev[-1][1]["upstream_status"] == 502
    assert KEY not in json.dumps(ev)


def test_byok_headers_on_compare_and_validate_are_refused(harness, tier):  # noqa: F811
    import io as _io

    client, rec, _router = harness
    tier(byok_enabled=True)
    rec.calls.clear()
    r = client.post("/api/ask_compare", headers=HDR, json={
        "question": "What is AETERM?", "models": ["openai/gpt-4o"]})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_on_this_tier"
    assert r.json()["detail"]["feature"] == "byok"
    csv = b"STUDYID,DOMAIN,USUBJID,AETERM\nS1,AE,S1-1,HEADACHE\n"
    r = client.post("/api/validate", headers=HDR, data={"semantic_review": "true"},
                    files={"file": ("ae.csv", _io.BytesIO(csv), "text/csv")})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_on_this_tier"
    assert not any(c["call"] in ("litellm.acompletion", "router.completion") for c in rec.calls)
