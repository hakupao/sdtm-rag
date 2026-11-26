"""P2 L1 unit tests: provider registry / capability matrix, header+provider combos, SSRF guard and
IP pinning, log redaction through main.py's rendered chain, registry pricing. No network."""
from __future__ import annotations

import io
from types import SimpleNamespace

import httpx
import pytest

from server import provider_registry as reg_mod
from server import provider_registry_net as net
from server import providers
from server.config import SelectableModel, Settings
from server.request_context import Credentials, RequestContext, ServiceRefusal, _CURRENT

KEY = "-".join(["sk", "l1", "TESTKEY", "0123456789abcdef"])   # not a literal: rich prints source


def _req(headers=None, **attrs):
    s = Settings()
    for k, v in attrs.items():
        object.__setattr__(s, k, v)       # undeclared L3 keys (instance / byok_enabled / public_models)
    return SimpleNamespace(headers={k: v for k, v in (headers or {}).items()},
                           app=SimpleNamespace(state=SimpleNamespace(settings=s)))


def _ctx(req, *, model="default", provider=None, endpoint="ask"):
    from server import instance

    return RequestContext(endpoint=endpoint, request=req, tier=instance.tier(req), model=model,
                          provider=provider, credentials=providers.credentials_from(req))


def _check(req, **kw):
    ctx = _ctx(req, **kw)
    providers.check_model(ctx, req.app.state.settings)
    return ctx


def _code(excinfo):
    return excinfo.value.status_code, excinfo.value.detail["code"]


# ── registry / capability matrix ────────────────────────────────────────

def test_registry_has_required_providers_and_one_capability_table():
    reg = reg_mod.load()
    ids = [p.id for p in reg.providers]
    assert {"anthropic", "openai", "gemini", "deepseek", "qwen", "kimi", "glm", "siliconflow",
            "custom"} <= set(ids)
    for pid in ("qwen", "kimi", "glm", "siliconflow"):       # domestic presets: fixed https base
        assert reg.provider(pid).api_base.startswith("https://")
    assert reg.provider("custom").private_only and reg.provider("custom").custom_base
    rows = reg_mod.capability_matrix()
    assert {"provider", "model_id", "tools", "vision", "context_tokens", "prompt_cache"} <= set(rows[0])
    assert all(r["context_tokens"] > 0 for r in rows)
    for p in reg.providers:                                    # every preset: explicit official https base
        assert p.custom_base or p.api_base.startswith("https://"), p.id
    with pytest.raises(ValueError):
        reg_mod.parse({"dossier_auto_min_context_tokens": 1, "providers": [
            {"id": "p", "models": [{"id": "a", "model": "openai/x"}]}]})


def test_registry_ids_do_not_collide_with_router_groups():
    from server.llm_config import INTERNAL_GROUPS

    selectable = {m.id for m in Settings().selectable_models}
    for p in reg_mod.load().providers:
        for m in p.models:
            assert m.id not in set(INTERNAL_GROUPS) | selectable, (p.id, m.id)
    with pytest.raises(ValueError):
        reg_mod.parse({"dossier_auto_min_context_tokens": 1, "providers": [
            {"id": "p", "api_base": "https://x.example", "models": [{"id": "hard", "model": "openai/x"}]}]})


def test_capabilities_come_from_litellm_unless_overridden():
    reg = reg_mod.parse({"dossier_auto_min_context_tokens": 1, "providers": [
        {"id": "p", "api_base": "https://x.example", "models": [
            {"id": "a", "model": "deepseek/deepseek-v4-pro"},
            {"id": "b", "model": "deepseek/deepseek-v4-pro", "capabilities": {"vision": True}},
            {"id": "c", "model": "openai/unknown-zzz"}]}]})
    a, b, c = reg.provider("p").models
    assert (a.caps.tools, a.caps.vision, a.caps.context_tokens) == (True, False, 1000000)
    assert b.caps.vision is True
    assert (c.caps.tools, c.caps.vision, c.caps.context_tokens) == (False, False, 0)   # conservative


def test_registry_price_feeds_cost_badge():
    from server.cost import estimate_cost

    u = {"prompt_tokens": 1000, "completion_tokens": 1000}
    assert estimate_cost("openai/qwen3-max", u) is not None        # alias priced via price_ref
    assert estimate_cost("qwen3-max", u) == estimate_cost("openai/qwen3-max", u)  # provider-reported bare
    # 2026-11-26: litellm rate $1.32/$3.96 per 1M (verify vs official page before P3)
    assert estimate_cost("deepseek/deepseek-v4-pro", {"prompt_tokens": 10, "completion_tokens": 3}) \
        == 2.5e-05
    assert estimate_cost("openai/totally-unknown-zz", u) is None


# ── contract §2.1 combo table + model checks ─────────────────────────────

def test_byok_off_private_default_is_pre_p2():
    req = _req()
    assert providers.credentials_from(_req({providers.BYOK_KEY_HEADER: KEY})) is None
    assert providers.info_fields(req) == {}
    _check(req, model="opus-5")
    with pytest.raises(Exception) as e:
        _check(req, model="nope")
    assert e.value.status_code == 422 and isinstance(e.value.detail, str)   # old string shape


def test_byok_off_refuses_any_byok_attempt_instead_of_using_server_key():
    for headers, provider in (({providers.BYOK_KEY_HEADER: KEY}, "openai"),
                              ({providers.BYOK_KEY_HEADER: KEY}, None), ({}, "openai")):
        with pytest.raises(ServiceRefusal) as e:
            _check(_req(headers), model="gpt-5.5", provider=provider)
        assert _code(e) == (403, "not_on_this_tier")


@pytest.mark.parametrize("tier_attrs", [{"byok_enabled": True}, {"instance": "public"}])
def test_combo_table(tier_attrs):
    pub = tier_attrs.get("instance") == "public"
    k = {providers.BYOK_KEY_HEADER: KEY}
    # key + registry provider -> BYOK target
    ctx = _check(_req(k, **tier_attrs), model="gpt-5.5", provider="openai")
    assert ctx.flags["byok"]["model"] == "openai/gpt-5.5"
    # key + null provider -> provider_required
    with pytest.raises(ServiceRefusal) as e:
        _check(_req(k, **tier_attrs), model="gpt-5.5", provider=None)
    assert _code(e) == (400, "provider_required") and "allowed" not in e.value.detail
    # no key + provider -> byok_key_missing
    with pytest.raises(ServiceRefusal) as e:
        _check(_req({}, **tier_attrs), model="gpt-5.5", provider="openai")
    assert _code(e) == (400, "byok_key_missing") and e.value.detail["provider"] == "openai"
    # no key + null provider -> server key path
    if not pub:
        _check(_req({}, **tier_attrs), model="opus-5")


def test_byok_unknown_model_or_provider():
    k = {providers.BYOK_KEY_HEADER: KEY}
    with pytest.raises(ServiceRefusal) as e:
        _check(_req(k, byok_enabled=True), model="opus-5", provider="openai")
    assert _code(e) == (422, "model_not_allowed") and "gpt-5.5" in e.value.detail["allowed"]
    with pytest.raises(ServiceRefusal) as e:
        _check(_req(k, byok_enabled=True), model="x", provider="nope")
    assert _code(e) == (400, "provider_required")
    with pytest.raises(ServiceRefusal) as e:
        _check(_req({providers.BYOK_KEY_HEADER: "bad\x00key"}, byok_enabled=True),
               model="gpt-5.5", provider="openai")
    assert _code(e) == (401, "byok_key_invalid")


def test_public_server_key_whitelist_is_l3s_and_both_refusals_agree():
    from server import instance

    free = SelectableModel(id="ds-free", label="DS", model="deepseek/deepseek-v4-pro", verified=False)
    req = _req(instance="public")
    object.__setattr__(req.app.state.settings, "selectable_models", [free])
    _check(req, model="ds-free")
    instance.check_request(_ctx(req, model="ds-free"), None)
    for bad in ("default", "hard", "light", "default-fallback", "opus-5", "nope"):
        with pytest.raises(ServiceRefusal) as l1:
            _check(req, model=bad)
        with pytest.raises(ServiceRefusal) as l3:
            instance.check_request(_ctx(req, model=bad), None)
        assert _code(l1) == _code(l3) == (422, "model_not_allowed")
        assert l1.value.detail == l3.value.detail
        assert l1.value.detail["allowed"] == instance.public_model_ids(req.app.state.settings) == ["ds-free"]


def test_custom_provider_rules():
    good = {providers.BYOK_KEY_HEADER: KEY, providers.BYOK_BASE_HEADER: "https://llm.example.com/v1"}
    # public: custom provider hidden, base header refused
    with pytest.raises(ServiceRefusal) as e:
        _check(_req(good, instance="public"), model="m", provider="custom")
    assert _code(e) == (400, "custom_base_not_allowed")
    with pytest.raises(ServiceRefusal) as e:
        _check(_req({providers.BYOK_KEY_HEADER: KEY}, instance="public"), model="m", provider="custom")
    assert _code(e) == (400, "provider_required")
    assert "custom" not in [p["id"] for p in providers.info_fields(_req(instance="public"))["providers"]]
    # private: base header only with provider=custom
    with pytest.raises(ServiceRefusal) as e:
        _check(_req(good, byok_enabled=True), model="gpt-5.5", provider="openai")
    assert _code(e) == (400, "custom_base_not_allowed")
    with pytest.raises(ServiceRefusal) as e:   # custom without a base
        _check(_req({providers.BYOK_KEY_HEADER: KEY}, byok_enabled=True), model="m", provider="custom")
    assert _code(e) == (400, "custom_base_not_allowed")
    with pytest.raises(ServiceRefusal) as e:   # model name must not be a Router group
        _check(_req(good, byok_enabled=True), model="hard", provider="custom")
    assert _code(e) == (422, "model_not_allowed")


# ── SSRF guard ───────────────────────────────────────────────────────────

SSRF_REJECT = [
    ("http://api.example.com/v1", ["93.184.216.34"]),          # not https
    ("https://user:pw@api.example.com/v1", ["93.184.216.34"]),  # userinfo
    ("https://localhost/v1", ["127.0.0.1"]),
    ("https://127.0.0.1/v1", ["127.0.0.1"]),                    # loopback v4
    ("https://[::1]/v1", ["::1"]),                              # loopback v6
    ("https://10.0.0.5/v1", ["10.0.0.5"]),                      # RFC1918
    ("https://172.16.3.4/v1", ["172.16.3.4"]),
    ("https://192.168.1.10/v1", ["192.168.1.10"]),
    ("https://100.64.0.1/v1", ["100.64.0.1"]),                  # CGNAT
    ("https://169.254.169.254/latest", ["169.254.169.254"]),    # cloud metadata (link-local)
    ("https://metadata.google.internal/", ["169.254.169.254"]),
    ("https://[fe80::1]/v1", ["fe80::1"]),                      # link-local v6
    ("https://[fd00:ec2::254]/v1", ["fd00:ec2::254"]),          # IPv6 ULA (AWS metadata v6)
    ("https://[::ffff:127.0.0.1]/v1", ["::ffff:127.0.0.1"]),    # IPv4-mapped loopback
    ("https://[::ffff:10.1.2.3]/v1", ["::ffff:10.1.2.3"]),      # IPv4-mapped private
    ("https://[64:ff9b::a00:1]/v1", ["64:ff9b::a00:1"]),        # NAT64 -> 10.0.0.1
    ("https://[2002:a00:1::]/v1", ["2002:a00:1::"]),            # 6to4 -> 10.0.0.1
    ("https://0.0.0.0/v1", ["0.0.0.0"]),                        # unspecified
    ("https://[::]/v1", ["::"]),
    ("https://224.0.0.1/v1", ["224.0.0.1"]),                    # multicast
    ("https://2130706433/v1", ["127.0.0.1"]),                   # decimal form resolves to loopback
    ("https://evil.example.com/v1", ["93.184.216.34", "10.0.0.7"]),   # any private answer rejects
    ("https://rebind.example.com/v1", ["192.168.0.1"]),         # name resolving to LAN
    ("https://nx.example.com/v1", []),                          # unresolvable
    ("https://api.example.com:99999/v1", ["93.184.216.34"]),    # bad port
    ("https://api.example.com/v1\r\nX: y", ["93.184.216.34"]),  # header injection chars
]


@pytest.mark.parametrize("url,addrs", SSRF_REJECT)
def test_ssrf_set_all_rejected(url, addrs):
    with pytest.raises(net.UnsafeBase):
        net.validate_custom_base(url, resolver=lambda h, p: list(addrs))


def test_public_address_accepted_and_pinned():
    pin = net.validate_custom_base("https://API.example.com:8443/v1",
                                   resolver=lambda h, p: ["93.184.216.34", "2606:2800:220:1::1"])
    assert (pin.host, pin.port, pin.ip) == ("api.example.com", 8443, "93.184.216.34")


def test_ssrf_check_runs_in_check_model(monkeypatch):
    monkeypatch.setattr(net, "_resolve", lambda h, p: ["127.0.0.1"])
    h = {providers.BYOK_KEY_HEADER: KEY, providers.BYOK_BASE_HEADER: "https://x.example.com/v1"}
    with pytest.raises(ServiceRefusal) as e:
        _check(_req(h, byok_enabled=True), model="m1", provider="custom")
    assert _code(e) == (400, "custom_base_not_allowed")
    monkeypatch.setattr(net, "_resolve", lambda h, p: ["93.184.216.34"])
    ctx = _check(_req(h, byok_enabled=True), model="m1", provider="custom")
    assert ctx.flags["byok"]["pin"].ip == "93.184.216.34"


def _chat_json(model="m1"):
    return {"id": "x", "object": "chat.completion", "created": 1, "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


def test_pinned_transport_connects_to_validated_ip_even_if_dns_changes(monkeypatch):
    """Real litellm + OpenAI SDK, network replaced at the socket-transport layer: the connect target
    is the IP validated in check_model; a later DNS answer (rebinding to loopback) is never used."""
    import litellm

    answers = iter([["93.184.216.34"], ["127.0.0.1"], ["127.0.0.1"]])
    monkeypatch.setattr(net, "_resolve", lambda h, p: next(answers))
    seen = []

    def handler(r):
        seen.append((r.url.host, r.headers.get("host"), r.extensions.get("sni_hostname")))
        return httpx.Response(200, json=_chat_json())

    monkeypatch.setattr(net, "SYNC_INNER", httpx.MockTransport(handler))
    h = {providers.BYOK_KEY_HEADER: KEY, providers.BYOK_BASE_HEADER: "https://llm.example.com/v1"}
    ctx = _check(_req(h, byok_enabled=True), model="m1", provider="custom")
    fn, kw = providers.resolve(ctx, "answer", "completion", object(), {
        "model": "m1", "messages": [{"role": "user", "content": "q"}]})
    r = fn(**kw)
    assert r.choices[0].message.content == "hi"
    assert seen == [("93.184.216.34", "llm.example.com", "llm.example.com")]
    assert kw["client"].is_closed()                       # per-call client released


def test_async_pinned_transport_connects_to_validated_ip_even_if_dns_changes(monkeypatch):
    import asyncio

    answers = iter([["93.184.216.34"], ["127.0.0.1"], ["127.0.0.1"]])
    monkeypatch.setattr(net, "_resolve", lambda h, p: next(answers))
    seen = []

    def handler(r):
        seen.append((r.url.host, r.headers.get("host"), r.extensions.get("sni_hostname")))
        return httpx.Response(200, json=_chat_json())

    monkeypatch.setattr(net, "ASYNC_INNER", httpx.MockTransport(handler))
    h = {providers.BYOK_KEY_HEADER: KEY, providers.BYOK_BASE_HEADER: "https://llm.example.com/v1"}
    ctx = _check(_req(h, byok_enabled=True), model="m1", provider="custom")
    fn, kw = providers.resolve(ctx, "answer", "acompletion", object(), {
        "model": "m1", "messages": [{"role": "user", "content": "q"}]})
    r = asyncio.run(fn(**kw))
    assert r.choices[0].message.content == "hi"
    assert seen == [("93.184.216.34", "llm.example.com", "llm.example.com")]
    assert kw["client"].is_closed()


def test_pinned_transport_refuses_redirects_and_foreign_hosts():
    pin = net.PinnedBase(url="https://llm.example.com/v1", host="llm.example.com", port=443,
                         ip="93.184.216.34")
    t = net.PinnedTransport(pin, httpx.MockTransport(
        lambda r: httpx.Response(302, headers={"location": "http://169.254.169.254/"})))
    with httpx.Client(transport=t, follow_redirects=True) as c:
        with pytest.raises(net.RedirectRefused):
            c.get("https://llm.example.com/v1/models")
        with pytest.raises(httpx.ConnectError):
            c.get("https://other.example.com/v1/models")


def test_pinned_async_transport_refuses_redirects():
    import asyncio

    pin = net.PinnedBase(url="https://llm.example.com/v1", host="llm.example.com", port=443,
                         ip="93.184.216.34")
    t = net.AsyncPinnedTransport(pin, httpx.MockTransport(
        lambda r: httpx.Response(307, headers={"location": "https://10.0.0.1/"})))

    async def go():
        async with httpx.AsyncClient(transport=t, follow_redirects=True) as c:
            await c.get("https://llm.example.com/v1/models")
    with pytest.raises(net.RedirectRefused):
        asyncio.run(go())


# ── redaction: rendered through main.py's configured chain ───────────────

def _render(fn):
    import structlog

    import server.main as main_mod

    buf = io.StringIO()
    log = structlog.wrap_logger(structlog.PrintLogger(buf), processors=main_mod.LOG_PROCESSORS)
    fn(log)
    return buf.getvalue()


def test_rendered_log_line_redacts_key_in_message_cause_and_fields():
    ctx = RequestContext(endpoint="ask", credentials=Credentials(api_key=KEY))
    tok = _CURRENT.set(ctx)
    try:
        def emit(log):
            try:
                try:
                    raise RuntimeError(f"inner upstream echoed headers x-api-key: {KEY}")
                except RuntimeError as inner:
                    raise ValueError(f"AuthenticationError: Incorrect API key provided: {KEY}") from inner
            except ValueError as e:
                log.error("llm_failed", error=str(e), model="gpt-5.5", exc_info=True)
            log.warning("other", detail={"hdr": KEY, "list": [KEY]}, obj=SimpleNamespace(k=KEY))
        text = _render(emit)
    finally:
        _CURRENT.reset(tok)
    assert KEY not in text
    assert "llm_failed" in text and "Incorrect API key provided" in text and "gpt-5.5" in text
    assert "inner upstream echoed" in text and "ValueError" in text      # traceback + cause kept
    assert providers.REDACTED in text


def test_rendered_log_line_redacts_shapeless_key_of_current_request():
    odd = "".join(["q9", "Zx", "77", "Lm", "Np", "0w"]) * 3          # matches no generic key pattern
    tok = _CURRENT.set(RequestContext(endpoint="ask", credentials=Credentials(api_key=odd)))
    try:
        text = _render(lambda log: log.error("llm_failed", error=f"rejected token {odd} upstream"))
    finally:
        _CURRENT.reset(tok)
    assert odd not in text and "rejected token" in text and providers.REDACTED in text


def test_rendered_log_line_redacts_key_shapes_without_request_ctx():
    other = "sk-ant-api03-" + "Z" * 24                       # a key that is not the current request's
    goog = "AIza" + "Q" * 30
    text = _render(lambda log: log.error("x", error=f"bad {other} / {goog} / Bearer {'t' * 20}"))
    assert other not in text and goog not in text and "t" * 20 not in text


def test_byok_answer_without_checked_target_fails_closed():
    ctx = RequestContext(endpoint="ask", credentials=Credentials(api_key=KEY), provider="openai")
    router = SimpleNamespace(completion=lambda **kw: pytest.fail("server Router used for BYOK"))
    with pytest.raises(ServiceRefusal) as e:
        providers.resolve(ctx, "answer", "completion", router, {"model": "default", "messages": []})
    assert _code(e) == (400, "provider_required")
    # server-side purposes keep the server path and never see the user key
    for purpose in ("route", "review", "hyde", "multiquery", "compare", "judge"):
        fn, kw = providers.resolve(ctx, purpose, "completion", router, {"model": "light"})
        assert fn is router.completion and "api_key" not in kw
    import litellm
    fn, kw = providers.resolve(ctx, "embedding", "embedding", None, {"model": "e", "input": ["x"]})
    assert fn is litellm.embedding and "api_key" not in kw


def test_generic_patterns_do_not_eat_ordinary_words():
    text = _render(lambda log: log.info("ask", question="risk-benefit-assessment of task-specific AIzaWord"))
    assert "risk-benefit-assessment" in text and "task-specific" in text


def test_redaction_boundaries_encoded_escaped_and_ordinary_words():
    k1 = "sk-proj-" + "a1B2c3D4e5F6g7H8"
    k2 = "AIza" + "Q1w2E3r4" * 4
    glm = "0123456789abcdef" * 2 + "." + "AbCdEf1234567890"
    samples = [f"url?key%3D{k1}&x=1", repr(f"\n{k1}"), f"={k2}", f"json \\u003d{k1}", f"zhipu {glm}"]
    text = _render(lambda log: log.error("x", a=samples))
    for k in (k1, k2, glm):
        assert k not in text, k
    words = ("risk-benefit-assessment of task-specific sk-benefit-assessment-plan desk-research-notes"
             " task-force-2024-q3-report")
    assert words in _render(lambda log: log.info("ask", question=words))


def test_redaction_scrubs_dict_keys():
    tok = _CURRENT.set(RequestContext(endpoint="ask", credentials=Credentials(api_key="odd" + "Q7" * 9)))
    try:
        text = _render(lambda log: log.error("x", headers={"odd" + "Q7" * 9: "v"}, **{"odd" + "Q7" * 9: 1}))
    finally:
        _CURRENT.reset(tok)
    assert "odd" + "Q7" * 9 not in text


def test_registry_cost_honours_provider_registry_path(tmp_path):
    f = tmp_path / "reg.yaml"
    f.write_text(
        "dossier_auto_min_context_tokens: 1\nproviders:\n  - id: p\n    api_base: https://x.example\n"
        "    models:\n      - {id: m, model: openai/zz-custom-priced, price: [1.0, 2.0]}\n", encoding="utf-8")
    from server.cost import estimate_cost

    u = {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}
    assert estimate_cost("openai/zz-custom-priced", u) is None          # default registry: unknown
    req = _req(provider_registry_path=str(f))
    tok = _CURRENT.set(RequestContext(endpoint="ask_compare", request=req))
    try:
        assert estimate_cost("openai/zz-custom-priced", u) == 3.0
    finally:
        _CURRENT.reset(tok)


PRESET_CALLS = [("openai", "gpt-5.5", "api.openai.com"), ("anthropic", "claude-sonnet-5-5", "api.anthropic.com"),
                ("gemini", "gemini-3.5-flash", "generativelanguage.googleapis.com"),
                ("deepseek", "deepseek-v4-pro", "api.deepseek.com"),
                ("qwen", "qwen3-max", "dashscope.aliyuncs.com"), ("kimi", "kimi-k3", "api.moonshot.cn"),
                ("glm", "glm-5.1", "open.bigmodel.cn"), ("siliconflow", "deepseek-ai/DeepSeek-V3.2", "api.siliconflow.cn")]


@pytest.mark.parametrize("provider,model,host", PRESET_CALLS)
def test_operator_env_base_cannot_redirect_user_key(provider, model, host, monkeypatch):
    """Real litellm with every *_API_BASE / *_BASE_URL env pointing at an operator proxy: the BYOK
    request still goes to the preset's official host (HTTP intercepted at httpx send; no network)."""
    import asyncio

    import litellm

    for v in ("OPENAI_API_BASE", "OPENAI_BASE_URL", "ANTHROPIC_API_BASE", "ANTHROPIC_BASE_URL",
              "GEMINI_API_BASE", "DEEPSEEK_API_BASE", "DEEPSEEK_API_URL", "DASHSCOPE_API_BASE",
              "MOONSHOT_API_BASE", "ZAI_API_BASE"):
        monkeypatch.setenv(v, "https://operator-proxy.invalid/v1")
    seen = []

    def send(self, request, *a, **k):
        seen.append((request.url.host, request.headers.get("authorization") or
                     request.headers.get("x-api-key") or request.headers.get("x-goog-api-key")))
        return httpx.Response(401, json={"error": {"message": "no"}}, request=request)

    async def asend(self, request, *a, **k):
        return send(self, request)

    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setattr(httpx.AsyncClient, "send", asend)
    ctx = _check(_req({providers.BYOK_KEY_HEADER: KEY}, byok_enabled=True), model=model, provider=provider)
    msgs = [{"role": "user", "content": "q"}]
    fn, kw = providers.resolve(ctx, "answer", "completion", object(), {"model": model, "messages": msgs})
    with pytest.raises(ServiceRefusal):
        fn(**kw)
    afn, akw = providers.resolve(ctx, "answer", "acompletion", object(), {"model": model, "messages": msgs})
    with pytest.raises(ServiceRefusal):
        asyncio.run(afn(**akw))
    assert seen and all(h == host for h, _ in seen), seen
    assert all(KEY in (a or "") for _, a in seen)
    assert litellm  # imported for the real call path
