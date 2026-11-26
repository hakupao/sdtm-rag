"""P2.0 seam wiring: every outbound call reaches providers.resolve + quota hooks with the request's
ctx, refusals are not swallowed, and the response-shaping hooks reach the wire.

Uses the characterization harness (real rag/federation/router/compare/reviewer code, faked wire).
"""
from __future__ import annotations

import json

import pytest

from server import instance, outbound, providers, quota
from server.request_context import Credentials, RequestContext, ServiceRefusal
from tests.test_p2_seam_characterization import _chunk, _resp, _run_all, harness  # noqa: F401


@pytest.fixture
def spy(monkeypatch):
    seen = {"resolve": [], "reserve": [], "settle": [], "admit": [], "finalize": []}
    real_resolve = providers.resolve

    def resolve(ctx, purpose, kind, llm_router, kw):
        seen["resolve"].append((ctx and ctx.endpoint, purpose, kind))
        return real_resolve(ctx, purpose, kind, llm_router, kw)

    def reserve(ctx, p, kw):
        seen["reserve"].append((ctx and ctx.endpoint, p))
        return ("H", len(seen["reserve"]))       # handle must come back to settle

    def settle(ctx, p, handle, usage, model, **_kw):   # v1.2: + streamed_text=
        seen["settle"].append((ctx and ctx.endpoint, p, usage is not None, handle, model))

    monkeypatch.setattr(providers, "resolve", resolve)
    monkeypatch.setattr(quota, "reserve", reserve)
    monkeypatch.setattr(quota, "settle", settle)
    monkeypatch.setattr(quota, "admit", lambda ctx, body: seen["admit"].append(ctx.endpoint))
    monkeypatch.setattr(quota, "finalize", lambda ctx: seen["finalize"].append(ctx.endpoint))
    return seen


def test_every_inventory_purpose_goes_through_the_hooks_with_request_ctx(harness, spy):  # noqa: F811
    client, rec, router = harness
    out = _run_all(client, rec, router)
    assert all(v["status"] == 200 for v in out.values())
    by_ep = {}
    for ep, purpose, _kind in spy["resolve"]:
        by_ep.setdefault(ep, set()).add(purpose)
    assert None not in by_ep, "an outbound call ran without the request ctx"
    assert by_ep["ask"] == {"route", "embedding", "answer", "continue"}
    assert by_ep["ask_stream"] >= {"embedding", "answer", "continue", "hyde", "route"}
    assert by_ep["ask_compare"] == {"embedding", "compare", "judge"}
    assert by_ep["validate"] == {"embedding", "review"}
    # web goes through reserve/settle (not resolve: Tavily is not an LLM call)
    assert ("ask_stream", "web") in spy["reserve"]
    # every reserve is settled exactly once, with its own handle (stream rounds settle at stream end)
    handles = [h for *_, h, _m in spy["settle"]]
    assert sorted(handles) == [("H", i) for i in range(1, len(spy["reserve"]) + 1)]
    assert sorted(spy["reserve"]) == sorted((e, p) for e, p, *_ in spy["settle"])
    assert all(has for e, p, has, *_ in spy["settle"] if p in ("answer", "continue"))
    # the answering model as the provider reported it reaches settle (stream: last chunk's model)
    models = {(e, p): m for e, p, _u, _h, m in spy["settle"]}
    assert models[("ask", "answer")] == "m-x" and models[("ask_stream", "answer")] == "m-stream"
    assert models[("ask_stream", "web")] == "tavily"
    # one admit + exactly one finalize per metered request (info is not metered)
    assert sorted(spy["admit"]) == sorted(spy["finalize"]) == sorted(
        ["ask", "ask_stream", "ask_stream", "ask_stream", "ask_compare", "validate"])


def test_admit_refusal_is_a_json_429_before_any_outbound_call(harness, spy, monkeypatch):  # noqa: F811
    client, rec, router = harness

    def refuse(ctx, body):
        raise ServiceRefusal(429, "free_quota_exhausted", "no free questions left",
                             headers={"Retry-After": "60"}, remaining=0)

    monkeypatch.setattr(quota, "admit", refuse)
    for path in ("/api/ask", "/api/ask_stream"):
        rec.calls.clear()
        r = client.post(path, json={"question": "q"})
        assert r.status_code == 429
        assert r.headers["retry-after"] == "60"
        assert r.json() == {"detail": {"code": "free_quota_exhausted",
                                       "message": "no free questions left", "remaining": 0}}
        assert rec.calls == []
    assert spy["finalize"] == ["ask", "ask_stream"]   # finalize still runs on refusal


@pytest.mark.parametrize("purpose", ["embedding", "route"])
def test_refusal_inside_retrieval_is_not_turned_into_502_or_both(harness, spy, monkeypatch,  # noqa: F811
                                                                 purpose):
    client, _rec, _router = harness

    def reserve(ctx, p, kw):
        if p == purpose:
            raise ServiceRefusal(429, "site_cap_reached", "daily cap")

    monkeypatch.setattr(quota, "reserve", reserve)
    r = client.post("/api/ask", json={"question": "q", "corpus": "auto"})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "site_cap_reached"


def _events(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        out.append((lines[0][len("event: "):], json.loads(lines[1][len("data: "):])))
    return out


def test_refusal_after_stream_opened_is_an_error_event_with_code(harness, spy, monkeypatch):  # noqa: F811
    client, _rec, router = harness

    def reserve(ctx, p, kw):
        if p == "continue":
            raise ServiceRefusal(429, "site_cap_reached", "daily cap", remaining_usd=0)

    monkeypatch.setattr(quota, "reserve", reserve)
    router.stream_script = [[_chunk("part"), _chunk(finish="length"), _chunk(usage=True)]]
    r = client.post("/api/ask_stream", json={"question": "q", "corpus": "cdisc"})
    ev = _events(r.text)
    assert [e for e, _ in ev] == ["sources", "token", "continue", "error"]
    assert ev[-1][1] == {"code": "site_cap_reached", "message": "daily cap", "remaining_usd": 0}
    assert spy["finalize"] == ["ask_stream"]


def test_web_refusal_becomes_quota_exceeded_tool_status(harness, monkeypatch):  # noqa: F811
    client, rec, router = harness

    def reserve(ctx, p, kw):
        if p == "web":
            raise ServiceRefusal(429, "web_quota_exhausted", "no web today")

    monkeypatch.setattr(quota, "reserve", reserve)
    from tests.test_p2_seam_characterization import _tool_delta
    router.stream_script = [
        [_chunk(tool=_tool_delta(0, "c1", "web_search", '{"query": "x"}')), _chunk(usage=True)],
        [_chunk("ans"), _chunk(finish="stop"), _chunk(usage=True)]]
    rec.calls.clear()
    ev = _events(client.post("/api/ask_stream", json={"question": "q", "corpus": "cdisc",
                                                      "web": True}).text)
    tr = [d for e, d in ev if e == "tool_result"]
    assert tr and tr[0]["status"] == "quota_exceeded"
    assert ev[-1][0] == "done" and ev[-1][1]["web_status"] == "quota_exceeded"
    assert not any(c["call"] == "tavily.post" for c in rec.calls)


def test_shaping_hooks_reach_the_wire(harness, monkeypatch):  # noqa: F811
    client, _rec, router = harness

    def note(ctx, name, default):
        if name == "web_tools":
            ctx.notes.append({"capability": "web_tools", "reason": "provider_has_no_tools"})
            return False
        return default

    monkeypatch.setattr(providers, "capability", note)
    monkeypatch.setattr(quota, "response_fields", lambda ctx: {"quota": {"free_remaining": 3}})
    router.stream_script = [[_chunk("a"), _chunk(finish="stop"), _chunk(usage=True)]]
    ev = dict(_events(client.post("/api/ask_stream", json={
        "question": "q", "corpus": "cdisc", "web": True}).text))
    dg = [{"capability": "web_tools", "reason": "provider_has_no_tools"}]
    assert ev["sources"]["downgrades"] == dg and ev["done"]["downgrades"] == dg
    assert ev["done"]["quota"] == {"free_remaining": 3}

    router.ask_script = [_resp("x")]
    body = client.post("/api/ask", json={"question": "q", "corpus": "cdisc"}).json()
    assert body["quota"] == {"free_remaining": 3} and "downgrades" not in body

    monkeypatch.setattr(providers, "info_fields", lambda req: {"providers": []})
    monkeypatch.setattr(quota, "info_fields", lambda req: {"quota": {"free_per_day": 10}})
    info = client.get("/api/info").json()
    assert info["providers"] == [] and info["quota"] == {"free_per_day": 10}
    assert "collection_name" in info


def test_instance_check_request_can_refuse(harness, monkeypatch):  # noqa: F811
    client, _rec, _router = harness

    def deny(ctx, body):
        if getattr(body, "dossier", None) == "on":
            raise ServiceRefusal(403, "not_on_this_tier", "dossier is private-only")

    monkeypatch.setattr(instance, "check_request", deny)
    r = client.post("/api/ask_stream", json={"question": "q", "dossier": "on"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_on_this_tier"


def test_defaults_add_no_kwargs_and_ctx_none_passes_through():
    kw = {"model": "m", "messages": []}
    router = object()
    fn, out = providers.resolve(None, "answer", "completion", None, kw)
    assert out is kw
    import litellm
    assert fn is litellm.completion
    with pytest.raises(AttributeError):
        providers.resolve(None, "answer", "completion", router, kw)
    assert outbound.PURPOSES == ("answer", "continue", "regen", "route", "hyde", "multiquery",
                                 "embedding", "review", "compare", "judge", "web")


def test_credentials_and_ctx_repr_never_show_the_key():
    c = Credentials(api_key="sk-secret-123", api_base="https://x")
    ctx = RequestContext(endpoint="ask", credentials=c)
    for s in (repr(c), str(c), repr(ctx), str(ctx), f"{ctx}", f"{c!r}"):
        assert "sk-secret-123" not in s
    assert "byok=True" in repr(ctx)


def test_admit_can_clip_history_before_the_prompt_is_built(harness, monkeypatch):  # noqa: F811
    client, rec, router = harness

    def clip(ctx, body):
        body.history = body.history[-1:]

    monkeypatch.setattr(quota, "admit", clip)
    hist = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"}, {"role": "assistant", "content": "d"}]
    router.ask_script = [_resp("x")]
    rec.calls.clear()
    assert client.post("/api/ask", json={"question": "q", "corpus": "cdisc",
                                         "history": hist}).status_code == 200
    answer = [c for c in rec.calls if c["call"] == "router.completion"][-1]
    assert answer["roles"] == ["system", "assistant", "user"]   # 4 history turns -> 1


def test_ctx_carries_the_request_for_identity_and_settings(harness, monkeypatch):  # noqa: F811
    client, _rec, router = harness
    got = {}

    def admit(ctx, body):
        got["ip"] = ctx.request.headers.get("cf-connecting-ip")
        got["settings"] = ctx.request.app.state.settings is not None

    monkeypatch.setattr(quota, "admit", admit)
    router.ask_script = [_resp("x")]
    client.post("/api/ask", json={"question": "q", "corpus": "cdisc"},
                headers={"CF-Connecting-IP": "203.0.113.7"})
    assert got == {"ip": "203.0.113.7", "settings": True}


def _fake_request(**state):
    from types import SimpleNamespace

    from server.config import Settings
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=Settings(), **state)))


def test_vision_gate_false_skips_pdf_channel_without_touching_builder(monkeypatch):
    from types import SimpleNamespace

    import server.router as router_mod
    touched = []
    builder = SimpleNamespace(index=SimpleNamespace(form_named_in=lambda q: touched.append(q)))
    req = _fake_request(pdf_context=builder, study_lookup=None)
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    assert router_mod.maybe_attach_pdf_pages(req, "q", [], msgs) == (None, None)
    assert touched == ["q"]                                     # default: channel consulted
    monkeypatch.setattr(providers, "capability",
                        lambda ctx, name, d: False if name == "vision" else d)
    touched.clear()
    assert router_mod.maybe_attach_pdf_pages(req, "q", [], msgs) == (None, None)
    assert touched == [] and msgs[-1]["content"] == "u"


def test_dossier_auto_gate_value_reaches_decide_dossier(monkeypatch):
    from types import SimpleNamespace

    import server.dossier_trigger as dt
    import server.router as router_mod
    seen = []
    monkeypatch.setattr(dt, "decide_dossier", lambda *a, **kw: seen.append(kw["auto_attach"])
                        or SimpleNamespace(attach=False, reason="r", domains=()))
    dossier = SimpleNamespace(sha="x", sections=(), chars=0, text="")
    req = _fake_request(dossier=dossier, rag=None, federation=None)
    router_mod.maybe_attach_dossier(req, "q", [], None, "auto")
    sentinel = object()
    monkeypatch.setattr(providers, "capability",
                        lambda ctx, name, d: sentinel if name == "dossier_auto" else d)
    router_mod.maybe_attach_dossier(req, "q", [], None, "auto")
    assert seen[0] is router_mod._auto_attach_allowed(req.app.state.settings, "default")
    assert seen[1] is sentinel


@pytest.fixture
def order(monkeypatch):
    seq = []
    monkeypatch.setattr(quota, "settle", lambda ctx, p, h, u, m, **_kw: seq.append(("settle", p)))
    monkeypatch.setattr(quota, "finalize", lambda ctx: seq.append(("finalize", ctx.endpoint)))
    return seq


def test_disconnect_settles_the_open_stream_before_finalize(harness, order):  # noqa: F811
    import asyncio

    from starlette.requests import Request

    import server.router as router_mod
    client, _rec, router = harness
    router.stream_script = [[_chunk("A"), _chunk("B"), _chunk(finish="stop"), _chunk(usage=True)]]
    req = Request({"type": "http", "app": client.app, "method": "POST", "path": "/", "headers": []})

    async def run():
        resp = await router_mod.ask_stream(
            body=router_mod.AskStreamRequest(question="q", corpus="cdisc"), request=req)
        it = resp.body_iterator
        await it.__anext__()          # sources
        await it.__anext__()          # first token: the answer stream is open
        await it.aclose()             # client went away

    asyncio.run(run())
    assert order[-2:] == [("settle", "answer"), ("finalize", "ask_stream")]


def test_loop_body_error_closes_metered_stream_before_finalize(harness, order):  # noqa: F811
    from types import SimpleNamespace
    client, _rec, router = harness
    broken = SimpleNamespace(model="m", usage=None, choices=[SimpleNamespace(finish_reason=None)])
    router.stream_script = [[_chunk("A"), broken, _chunk("never")]]   # no .delta -> body raises
    ev = _events(client.post("/api/ask_stream", json={"question": "q", "corpus": "cdisc"}).text)
    assert ev[-1][0] == "error"
    assert order[-2:] == [("settle", "answer"), ("finalize", "ask_stream")]


def test_compare_refusal_is_a_request_level_429(harness, monkeypatch):  # noqa: F811
    client, _rec, _router = harness

    def reserve(ctx, p, kw):
        if p in ("compare", "judge"):
            raise ServiceRefusal(429, "site_cap_reached", "daily cap")

    monkeypatch.setattr(quota, "reserve", reserve)
    r = client.post("/api/ask_compare", json={"question": "q", "models": ["openai/gpt-4o"]})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "site_cap_reached"


def test_route_corpus_without_router_keeps_pre_p2_fallback(monkeypatch):
    import litellm

    from server.federation import route_corpus
    called = []
    monkeypatch.setattr(litellm, "completion", lambda **kw: called.append(kw))
    assert route_corpus(None, "q") == ("both", True)
    assert called == []


def test_rendered_exception_log_line_has_no_frame_locals():
    """main.py's structlog chain must not print frame locals (BYOK key would sit in outbound's
    kw). Renders a real line through the configured processors, then greps it."""
    import io

    import structlog

    import server.main as main_mod

    def boom(api_key):
        secret_local = api_key  # noqa: F841 — what show_locals would print
        raise RuntimeError("upstream failed")

    # main.py's own chain object (not the global config, which other tests may reconfigure)
    buf = io.StringIO()
    log = structlog.wrap_logger(structlog.PrintLogger(buf), processors=main_mod.LOG_PROCESSORS)
    key = "-".join(["sk", "NEVER", "PRINT", str(1234)])   # not a literal: rich prints source lines
    try:
        boom(key)
    except RuntimeError:
        log.error("llm_failed", exc_info=True)
    text = buf.getvalue()
    assert "upstream failed" in text and "llm_failed" in text
    assert key not in text


def test_main_installs_provider_log_processors():
    import inspect

    import server.main as main_mod
    assert "*providers.log_processors()" in inspect.getsource(main_mod)
    assert isinstance(providers.log_processors(), list)   # L1 fills it (redaction); P2.0 shipped []
