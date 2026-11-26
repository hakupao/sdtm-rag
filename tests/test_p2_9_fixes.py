"""P2.9 fix round (two independent reviews of main..p2): one test per new check. Checkpoint
.work/10_split_and_public/evidence/checkpoints/p2.9_fix.md maps finding -> test -> mutation."""
from __future__ import annotations

import asyncio
import io
import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from server import outbound, providers, quota
from server.auth import install_security
from server.config import Settings  # noqa: F401 — import (dotenv) before the env-clearing fixtures
from server.quota_store import QuotaStore
from server.request_context import Credentials, ServiceRefusal
from tests.test_p2_l2_integration import (  # noqa: F401
    BYOK_BODY,
    BYOK_KEY,
    S,
    _ask,
    _byok,
    engines,
    make,
)
from tests.test_p2_l2_quota import _body, _ctx, settings  # noqa: F401

PUB = dict(instance="public", visitor_secret="t" * 32, quota_trusted_proxies="10.0.0.1/32")


# ── #2 / #3: strict bools, unknown keys, public never unmetered ─────────────

@pytest.mark.parametrize("raw", ["ture", "y", "enable", "2"])
def test_quota_bool_typo_raises_not_false(monkeypatch, raw):
    monkeypatch.setenv("SDTM_RAG_FREE_TIER_DISABLED", raw)
    with pytest.raises(ValueError, match="not a boolean"):
        quota.cfg(None, "free_tier_disabled")
    with pytest.raises(RuntimeError, match="SDTM_RAG_FREE_TIER_DISABLED"):
        quota.validate(Settings())


@pytest.mark.parametrize(("raw", "want"), [("1", True), ("On", True), ("off", False), ("NO", False)])
def test_quota_bool_accepts_known_spellings(monkeypatch, raw, want):
    monkeypatch.setenv("SDTM_RAG_FREE_TIER_DISABLED", raw)
    assert quota.cfg(None, "free_tier_disabled") is want


def test_validate_refuses_misspelt_key_when_enabled_and_masks_secret(monkeypatch, engines):  # noqa: F811
    base = engines[0]
    monkeypatch.setenv("SDTM_RAG_QUOTA_SITE_CAP_USDD", "50")
    with pytest.raises(RuntimeError, match="SDTM_RAG_QUOTA_SITE_CAP_USDD"):
        quota.validate(S(base, quota_enabled=True))
    quota.validate(S(base))          # private, quota off: a stray name is not fatal
    monkeypatch.delenv("SDTM_RAG_QUOTA_SITE_CAP_USDD")
    eff = quota.validate(S(base, quota_enabled=True, visitor_secret="s3cret-value"))
    assert eff["visitor_secret"] == "set" and "s3cret-value" not in repr(eff)
    monkeypatch.setenv("SDTM_RAG_QUOTA_FREE_PER_DAY", "ten")
    with pytest.raises(RuntimeError, match="SDTM_RAG_QUOTA_FREE_PER_DAY"):
        quota.validate(S(base, quota_enabled=True))


def test_public_refuses_to_start_unmetered(engines):  # noqa: F811
    base = engines[0]
    with pytest.raises(RuntimeError, match="unmetered"):
        install_security(FastAPI(), S(base, quota_enabled=False, **PUB))
    install_security(FastAPI(), S(base, **PUB))   # unset = on for public
    install_security(FastAPI(), S(base, quota_enabled=False))   # private may run unmetered


# ── #6 / #7: trusted proxies narrow; global rate limit keyed on the real visitor ──

@pytest.mark.parametrize(("cidr", "ok"), [("10.0.0.0/8", False), ("10.0.0.0/23", False),
                                          ("10.0.0.0/24", True), ("10.0.0.1/32", True),
                                          ("fd00::/64", False), ("fd00::/120", True),
                                          ("10.0.0.1/32,0.0.0.0/0", False)])
def test_public_trusted_proxies_must_be_narrow(engines, cidr, ok):  # noqa: F811
    s = S(engines[0], **{**PUB, "quota_trusted_proxies": cidr})
    if ok:
        install_security(FastAPI(), s)
    else:
        with pytest.raises(RuntimeError, match="too broad"):
            install_security(FastAPI(), s)


def test_private_trusted_proxies_breadth_unchanged(engines):  # noqa: F811
    install_security(FastAPI(), S(engines[0], quota_enabled=True, visitor_secret="t" * 32,
                                  quota_trusted_proxies="10.0.0.0/8"))


def test_public_refuses_rate_limit_trust_forwarded(engines):  # noqa: F811
    with pytest.raises(RuntimeError, match="TRUST_FORWARDED"):
        install_security(FastAPI(), S(engines[0], rate_limit_trust_forwarded=True, **PUB))


def test_public_global_rate_limit_keys_on_cf_connecting_ip(make):  # noqa: F811
    client, _router = make(client_addr=("10.0.0.1", 1), rate_limit_enabled=True,
                           rate_limit_per_min=1, rate_limit_burst=1, **PUB)

    def hit(ip):
        return client.get("/api/info", headers={"CF-Connecting-IP": ip}).status_code

    assert hit("198.51.100.1") == 200
    assert hit("198.51.100.2") == 200      # another visitor behind the same tunnel peer
    assert hit("198.51.100.1") == 429      # the first visitor's own bucket


def test_private_global_rate_limit_still_keys_on_peer(make):  # noqa: F811
    client, _router = make(client_addr=("10.0.0.1", 1), rate_limit_enabled=True,
                           rate_limit_per_min=1, rate_limit_burst=1,
                           quota_trusted_proxies="10.0.0.1/32")
    assert client.get("/api/info", headers={"CF-Connecting-IP": "198.51.100.1"}).status_code == 200
    assert client.get("/api/info", headers={"CF-Connecting-IP": "198.51.100.2"}).status_code == 429


# ── #5: open-reservation saturation is site_busy, settled spend is site_cap_reached ──

def _fill(s, usd, settle):
    store = quota._store(s)
    assert store.reserve("other", quota._day(), usd, None, quota._now())
    if settle:
        assert store.settle("other", usd)


@pytest.mark.parametrize(("settled", "code", "status"), [(False, "site_busy", 503),
                                                         (True, "site_cap_reached", 429)])
def test_reserve_refusal_busy_vs_cap(settings, settled, code, status):  # noqa: F811
    s = settings
    s.quota_site_cap_usd, s.quota_byok_side_budget_usd = 1.0, 0.0
    ctx = _ctx(s)
    quota.admit(ctx, _body())
    _fill(s, 0.9999, settled)
    with pytest.raises(ServiceRefusal) as e:
        quota.reserve(ctx, "answer", {"model": "default", "max_tokens": 10,
                                      "messages": [{"role": "user", "content": "q"}]})
    assert e.value.status_code == status and e.value.detail["code"] == code
    if code == "site_busy":
        assert e.value.headers["Retry-After"] == "15" and e.value.detail["retry_after_s"] == 15
    # refused before any answering round: the free question is refunded either way
    assert quota._store(s).count("v:v1", quota._day()) == 0


# ── #10: per-IP in-flight cap ───────────────────────────────────────────────

def test_inflight_cap_per_ip_released_by_finalize(settings):  # noqa: F811
    s = settings
    s.quota_inflight_per_ip = 2
    a = _ctx(s)
    app = a.request.app
    quota.admit(a, _body())

    def same_app(ip="1.2.3.4", visitor="v1"):
        c = _ctx(s, ip=ip, visitor=visitor)
        c.request.app = app
        return c

    b = same_app()
    quota.admit(b, _body())
    with pytest.raises(ServiceRefusal) as e:
        quota.admit(same_app(), _body())
    assert e.value.detail["code"] == "rate_limited"
    quota.admit(same_app(ip="5.6.7.8", visitor="v2"), _body())   # other IP unaffected
    quota.finalize(a)
    quota.finalize(a)                                            # idempotent release
    quota.admit(same_app(), _body())
    with pytest.raises(ServiceRefusal):
        quota.admit(same_app(), _body())


def test_inflight_slot_expires_if_finalize_never_runs(settings, monkeypatch):  # noqa: F811
    s = settings
    s.quota_inflight_per_ip = 1
    t = [1_800_000_000.0]
    monkeypatch.setattr(quota, "_now", lambda: t[0])
    a = _ctx(s)
    quota.admit(a, _body())                  # leaked: never finalized
    b = _ctx(s)
    b.request.app = a.request.app
    with pytest.raises(ServiceRefusal):
        quota.admit(b, _body())
    t[0] += float(quota.cfg(s, "quota_reservation_ttl_s")) + 1
    quota.admit(b, _body())


def test_refused_admit_releases_its_slot(settings):  # noqa: F811
    s = settings
    s.quota_inflight_per_ip, s.quota_free_per_day = 1, 1
    a = _ctx(s)
    quota.admit(a, _body())
    quota.finalize(a)
    b = _ctx(s)
    b.request.app = a.request.app
    with pytest.raises(ServiceRefusal) as e:     # free count exhausted AFTER the slot was taken
        quota.admit(b, _body())
    assert e.value.detail["code"] == "free_quota_exhausted"
    quota.finalize(b)
    assert not a.request.app.state.quota_inflight


# ── #11: /api/flag byte caps ────────────────────────────────────────────────

def test_flag_per_ip_daily_bytes_and_file_cap(make, tmp_path):  # noqa: F811
    client, _ = make(flag_bytes_per_ip_day=600, flag_rate_burst=100, flag_rate_per_min=100)
    body = {"question": "q", "note": "n", "answer": "a" * 200}
    assert client.post("/api/flag", json=body).status_code == 200
    r = client.post("/api/flag", json={**body, "answer": "a" * 500})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"
    assert "retry-after" in r.headers
    client, _ = make(flag_file_max_bytes=100, flag_rate_burst=100, flag_rate_per_min=100)
    r = client.post("/api/flag", json=body)
    assert r.status_code == 507 and r.json()["detail"]["code"] == "storage_full"


def test_flag_caps_are_off_on_unmetered_private(engines, tmp_path):  # noqa: F811
    from fastapi.testclient import TestClient

    from server.router import api_router

    s = S(engines[0], dogfood_log_path=tmp_path / "d.md", flag_file_max_bytes=1)
    app = FastAPI()
    app.include_router(api_router)
    app.state.settings = s
    assert TestClient(app).post("/api/flag", json={"question": "q"}).status_code == 200


# ── #12: stdlib logging redaction ───────────────────────────────────────────

def test_stdlib_child_logger_record_is_redacted_on_root_handler():
    root = logging.getLogger()
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    root.addHandler(h)
    lg = logging.getLogger("httpcore.http11")
    old = lg.level
    try:
        providers.install_log_redaction(public=False)
        lg.setLevel(logging.INFO)
        lg.warning("send headers: %s", "Authorization: Bearer sk-live0123456789abcdef")
        try:
            raise RuntimeError("upstream said x-api-key: sk-ant-0123456789abcdefXYZ")
        except RuntimeError:
            lg.exception("boom")
    finally:
        root.removeHandler(h)
        lg.setLevel(old)
    out = buf.getvalue()
    assert "sk-live0123456789abcdef" not in out and "sk-ant-0123456789abcdefXYZ" not in out
    assert out.count(providers.REDACTED) >= 2 and "RuntimeError" in out


def test_public_holds_third_party_loggers_at_warning():
    lg = logging.getLogger("LiteLLM")
    old = lg.level
    try:
        lg.setLevel(logging.DEBUG)
        providers.install_log_redaction(public=False)
        assert lg.level == logging.DEBUG
        providers.install_log_redaction(public=True)
        assert lg.getEffectiveLevel() >= logging.WARNING
        assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    finally:
        lg.setLevel(old)


# ── #15 / #21: BYOK abuse bounds ────────────────────────────────────────────

def test_bad_byok_keys_per_ip_are_capped(make, monkeypatch):  # noqa: F811
    _byok(monkeypatch)
    client, router = make(byok_enabled=True, quota_byok_bad_key_per_ip_day=2)
    bad = {providers.BYOK_KEY_HEADER: "k" * 600}          # > _MAX_KEY_LEN: byok_key_invalid
    for _ in range(2):
        r = client.post("/api/ask", json={"question": "q", **BYOK_BODY}, headers=bad)
        assert r.status_code == 401 and r.json()["detail"]["code"] == "byok_key_invalid"
    r = client.post("/api/ask", json={"question": "q", "corpus": "cdisc", **BYOK_BODY},
                    headers={providers.BYOK_KEY_HEADER: BYOK_KEY})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"
    assert _ask(client, router).status_code == 200          # free (server-key) questions unaffected


def test_upstream_401_counts_as_bad_key(make, monkeypatch):  # noqa: F811
    import litellm

    class _Up(Exception):  # noqa: N818
        status_code = 401

    def fake_completion(**kw):
        raise _Up("unauthorized")

    monkeypatch.setattr(litellm, "completion", fake_completion)
    client, _router = make(byok_enabled=True, quota_byok_bad_key_per_ip_day=1)
    body = {"question": "BYOK 401 probe?", "corpus": "cdisc", **BYOK_BODY}
    hdr = {providers.BYOK_KEY_HEADER: BYOK_KEY}
    r = client.post("/api/ask", json=body, headers=hdr)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "byok_key_invalid"
    r = client.post("/api/ask", json=body, headers=hdr)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"


def test_byok_side_budget_is_shared_per_ip(settings):  # noqa: F811
    s = settings
    s.quota_byok_side_per_ip_usd = 0.001
    creds = Credentials(api_key="sk-user")
    kw = {"model": "light", "max_tokens": 200, "messages": [{"role": "user", "content": "q" * 30}]}
    est = quota._estimate(s, "route", kw)[0]
    assert 0.001 < est < 0.5                       # one routing call reserves more than the IP's share
    ctx = _ctx(s, creds=creds)
    quota.admit(ctx, _body())
    with pytest.raises(ServiceRefusal) as e:
        quota.reserve(ctx, "route", kw)
    assert e.value.detail["code"] == "rate_limited"
    assert quota._store(s).spent(quota._day(), "byok") == 0     # nothing charged to the pool
    s.quota_byok_side_per_ip_usd = 0.5
    h = quota.reserve(ctx, "route", kw)
    store = quota._store(s)
    assert store.count("bs:1.2.3.4", quota._day()) == pytest.approx(est * 1e6, abs=1)
    quota.settle(ctx, "route", h, SimpleNamespace(prompt_tokens=10, completion_tokens=0), "m")
    actual = quota._price(s, "m", 10, 0)
    assert store.count("bs:1.2.3.4", quota._day()) == pytest.approx(actual * 1e6, abs=1)
    other = _ctx(s, creds=creds, ip="9.9.9.9", visitor="v9")
    quota.admit(other, _body())
    assert quota.reserve(other, "route", kw)


def test_byok_web_counter_untaken_when_cap_refuses(settings):  # noqa: F811
    s = settings
    s.quota_site_cap_usd, s.quota_byok_side_budget_usd = 1.0, 0.01
    creds = Credentials(api_key="sk-user")
    ctx = _ctx(s, creds=creds)
    quota.admit(ctx, _body())
    store = quota._store(s)
    assert store.reserve("x", quota._day(), 0.01, None, quota._now(), "byok")
    assert store.settle("x", 0.01)
    with pytest.raises(ServiceRefusal) as e:
        quota.reserve(ctx, "web", {"query": "q"})
    assert e.value.detail["code"] == "site_cap_reached"
    assert store.count("w:v:v1", quota._day()) == 0 and store.count("w:ip:1.2.3.4", quota._day()) == 0
    assert store.count("bs:1.2.3.4", quota._day()) == 0


# ── #16: retention ───────────────────────────────────────────────────────────

def test_store_prunes_old_days_once_per_day(settings, monkeypatch):  # noqa: F811
    s = settings
    store = quota._store(s)
    store.take([("ip:old", 10)], "2020-01-01")
    store.reserve("old", "2020-01-01", 0.1, None, 0.0)
    store.take([("ip:new", 10)], quota._day())
    store._pruned_for = None
    quota._store(s)
    assert store.count("ip:old", "2020-01-01") == 0 and store.status("old") is None
    assert store.count("ip:new", quota._day()) == 1
    calls = []
    monkeypatch.setattr(QuotaStore, "prune", lambda self, d: calls.append(d))
    quota._store(s)
    assert calls == []                       # same day: not again


# ── #17: pinned clients ignore proxy env ────────────────────────────────────

@pytest.mark.parametrize("is_async", [False, True])
def test_pinned_client_does_not_trust_env(is_async):
    from server.provider_registry_net import PinnedBase, openai_client

    pin = PinnedBase(url="https://llm.example.com/v1", host="llm.example.com", port=443,
                     ip="93.184.215.14")
    c = openai_client(pin, "sk-test-0000000000000", is_async=is_async, timeout=5.0)
    assert c._client.trust_env is False


# ── #20: compare stops siblings on the first refusal ────────────────────────

def test_compare_cancels_siblings_on_refusal(monkeypatch):
    from server import compare

    cancelled = []

    async def fake(ctx, purpose, router, **kw):
        if kw["model"] == "refused":
            await asyncio.sleep(0.01)
            raise ServiceRefusal(429, "site_cap_reached", "cap")
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled.append(kw["model"])
            raise

    monkeypatch.setattr(outbound, "acompletion", fake)

    async def run():
        t0 = asyncio.get_running_loop().time()
        with pytest.raises(ServiceRefusal):
            await compare.run_compare(["slow-a", "refused", "slow-b"], [])
        return asyncio.get_running_loop().time() - t0

    assert asyncio.run(run()) < 2
    assert sorted(cancelled) == ["slow-a", "slow-b"]


# ── #4: public cost / header startup gates (instance.check_startup) ─────────

def _pub_settings(tmp_path, **kw):
    from server.config import SelectableModel

    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    st = tmp_path / "nostudy"
    base = dict(instance="public", data_dir_override=str(data), study_kb_root=st / "cards",
                study_catalog_path=st / "catalog.json", study_aliases_path=st / "aliases.yml",
                selectable_models=[SelectableModel(id="ds-v4", label="DS", model="deepseek/deepseek-v4-pro",
                                                   verified=False, max_output_tokens=32000)])
    return Settings(**{**base, **kw})


def _startup_error(s):
    from server import instance

    try:
        instance.check_startup(s)
    except RuntimeError as e:
        return str(e)
    return None


def test_public_cost_gates_pass_for_a_bounded_model(tmp_path, monkeypatch):
    monkeypatch.delenv("SDTM_RAG_SELECTABLE_MODELS", raising=False)
    assert _startup_error(_pub_settings(tmp_path)) is None


def test_public_requires_explicit_selectable_models(tmp_path, monkeypatch):
    monkeypatch.delenv("SDTM_RAG_SELECTABLE_MODELS", raising=False)
    s = _pub_settings(tmp_path)
    kw = {k: getattr(s, k) for k in s.model_fields_set if k != "selectable_models"}
    err = _startup_error(Settings(**kw))      # built-in list: the private Claude set
    assert "SDTM_RAG_SELECTABLE_MODELS not set" in err


def test_public_model_needs_explicit_max_output_and_a_bounded_round(tmp_path):
    from server.config import SelectableModel

    implicit = SelectableModel(id="ds-v4", label="DS", model="deepseek/deepseek-v4-pro", verified=False)
    err = _startup_error(_pub_settings(tmp_path, selectable_models=[implicit]))
    assert "no explicit max_output_tokens" in err
    assert "free pool / 10" in err            # implicit 128000 x $3.96/M > $0.30
    big = SelectableModel(id="ds-v4", label="DS", model="deepseek/deepseek-v4-pro", verified=False,
                          max_output_tokens=100_000)
    err = _startup_error(_pub_settings(tmp_path, selectable_models=[big]))
    assert "free pool / 10" in err and "no explicit" not in err


def test_public_requires_security_headers(tmp_path):
    err = _startup_error(_pub_settings(tmp_path, security_headers_enabled=False))
    assert "security_headers_enabled=false" in err


def test_private_ignores_public_cost_gates(tmp_path):
    from server.config import SelectableModel

    implicit = SelectableModel(id="x", label="X", model="anthropic/claude-opus-5", verified=False)
    assert _startup_error(Settings(selectable_models=[implicit], security_headers_enabled=False)) is None


# ── #1: the router's narrow stream_options retry is charged as ONE round ───

def test_narrow_retry_spends_one_round(make):  # noqa: F811
    from tests.test_p2_seam_characterization import _chunk

    client, router = make()
    store = quota._store(client.app.state.settings)
    ok = [_chunk("ok"), _chunk(finish="stop"), _chunk(usage=True)]

    def spend(script):
        router.stream_script = script
        before = store.spent(quota._day())
        r = client.post("/api/ask_stream", json={"question": "narrow retry q", "corpus": "cdisc"})
        assert r.status_code == 200 and "event: done" in r.text
        return store.spent(quota._day()) - before

    spend([list(ok)])                                  # warm the query-embedding cache
    plain = spend([list(ok)])
    class _BadRequest(Exception):  # noqa: N818   # litellm BadRequestError shape: a clear 400 on open
        status_code = 400

    retried = spend([_BadRequest("stream_options unsupported"), list(ok)])
    assert plain > 0 and retried == pytest.approx(plain)
