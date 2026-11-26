"""P2 L2 unit tests: SQLite store (atomicity, idempotency, persistence), history trimming, cost
estimation, hook pass-through, and reservation accounting through the real outbound seam."""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from server import outbound, quota
from server.config import Settings
from server.quota_store import QuotaStore
from server.request_context import Credentials, RequestContext, ServiceRefusal


class S:
    """Settings proxy: real Settings plus L2 keys L3 has not added yet (Settings is extra=ignore)."""

    def __init__(self, base, **over):
        self._base = base
        self.__dict__.update(over)

    def __getattr__(self, name):
        return getattr(self._base, name)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    for k in ("SDTM_RAG_QUOTA_ENABLED", "SDTM_RAG_FREE_TIER_DISABLED"):
        monkeypatch.delenv(k, raising=False)
    quota._STORES.clear()
    return S(Settings(), quota_enabled=True, quota_db_path=str(tmp_path / "q.sqlite"),
             quota_rate_per_min=10_000, quota_rate_burst=10_000,
             quota_ip_rate_per_min=10_000, quota_ip_rate_burst=10_000)


def _ctx(s, endpoint="ask", creds=None, visitor="v1", ip="1.2.3.4"):
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=s)),
                          scope={"state": {"sdtm_visitor": visitor, "sdtm_client_ip": ip}})
    return RequestContext(endpoint=endpoint, request=req, credentials=creds)


def _body(history=(), web=False):
    return SimpleNamespace(history=[SimpleNamespace(role=r, content=c) for r, c in history], web=web)


# ── store ──

def test_take_is_atomic_across_threads(tmp_path):
    st = QuotaStore(tmp_path / "q.sqlite")
    ok = []
    barrier = threading.Barrier(40)

    def worker():
        barrier.wait()
        ok.append(st.take([("v:a", 10), ("ip:x", 1000)], "2026-11-26"))

    ts = [threading.Thread(target=worker) for _ in range(40)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert ok.count(True) == 10
    assert st.count("v:a", "2026-11-26") == 10 and st.count("ip:x", "2026-11-26") == 10


def test_take_is_all_or_nothing(tmp_path):
    st = QuotaStore(tmp_path / "q.sqlite")
    assert st.take([("ip:x", 1)], "d")
    assert not st.take([("v:new", 10), ("ip:x", 1)], "d")   # ip full -> visitor not charged
    assert st.count("v:new", "d") == 0


def test_reserve_never_exceeds_cap_across_threads(tmp_path):
    st = QuotaStore(tmp_path / "q.sqlite")
    ok = []
    barrier = threading.Barrier(60)

    def worker(i):
        barrier.wait()
        ok.append(st.reserve(f"r{i}", "d", 0.05, 1.0, 0.0))

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(60)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert ok.count(True) == 20
    assert st.spent("d") == pytest.approx(1.0)


def test_settle_close_expire_are_idempotent(tmp_path):
    st = QuotaStore(tmp_path / "q.sqlite")
    assert st.reserve("a", "d", 0.5, None, 0.0)
    assert st.settle("a", 0.1)
    assert st.spent("d") == pytest.approx(0.1)
    assert not st.settle("a", 0.3)                  # second settle: no-op
    assert st.spent("d") == pytest.approx(0.1)
    assert st.reserve("b", "d", 0.5, None, 0.0)
    assert st.close("b")                            # finalize keeps the reservation
    assert not st.settle("b", 0.0)                  # settle after finalize: no refund
    assert st.spent("d") == pytest.approx(0.6)
    assert st.reserve("c", "d", 0.5, None, 100.0)
    assert st.expire(older_than=200.0) == 1         # never closed -> expired, still charged
    assert not st.settle("c", 0.0)
    assert st.spent("d") == pytest.approx(1.1)


def test_counts_and_spend_survive_reopen(tmp_path):
    p = tmp_path / "q.sqlite"
    st = QuotaStore(p)
    st.take([("v:a", 10)], "d")
    st.reserve("r", "d", 0.25, None, 0.0)
    st2 = QuotaStore(p)
    assert st2.count("v:a", "d") == 1 and st2.spent("d") == pytest.approx(0.25)
    assert st2.status("r") == "open"


# ── trimming ──

def _m(role, n):
    return SimpleNamespace(role=role, content="x" * n)


def test_trim_keeps_last_8():
    h = [_m("user" if i % 2 == 0 else "assistant", 10) for i in range(12)]
    out = quota.trim_history(h, 8, 20000)
    assert out == h[4:]


def test_trim_char_budget_and_leading_assistant():
    h = [_m("user", 5000), _m("assistant", 5000), _m("user", 5000), _m("assistant", 9000),
         _m("user", 5000)]
    out = quota.trim_history(h, 8, 20000)
    # newest-first: 5000 + 9000 + 5000 = 19000 fits; next 5000 would exceed. Kept starts at user.
    assert [len(m.content) for m in out] == [5000, 9000, 5000] and out[0].role == "user"
    h2 = [_m("user", 100), _m("assistant", 15000), _m("user", 6000)]
    out2 = quota.trim_history(h2, 8, 20000)   # cut leaves assistant first -> dropped
    assert [m.role for m in out2] == ["user"]


def test_trim_single_message_over_budget_is_dropped():
    assert quota.trim_history([_m("user", 20001)], 8, 20000) == []


# ── estimates ──

def test_estimate_uses_deployment_max_tokens_and_never_zero(settings):
    s = settings
    est, model = quota._estimate(s, "answer", {"model": "default",
                                               "messages": [{"role": "user", "content": "hi"}]})
    assert model == s.default_model
    exp = quota._price(s, s.default_model, 1 + 4, s.default_max_output_tokens)
    assert est == pytest.approx(exp) and est > 0
    unknown, _ = quota._estimate(s, "answer", {"model": "nobody/unknown-model-x", "max_tokens": 1000,
                                               "messages": [{"role": "user", "content": "x"}]})
    assert unknown == pytest.approx((5 * 5.0 + 1000 * 25.0) / 1e6)
    assert quota._estimate(s, "web", {"query": "q"})[0] == pytest.approx(0.016)


def test_cjk_estimate_is_not_ascii_rate():
    assert quota._text_tokens("中文" * 50) == 100
    assert quota._text_tokens("a" * 300) == 100


# ── hooks ──

def test_every_hook_passes_through_none_and_disabled(tmp_path):
    for fn, args in ((quota.admit, (None, None)), (quota.reserve, (None, "answer", {})),
                     (quota.settle, (None, "answer", "h", None, None)), (quota.finalize, (None,))):
        assert fn(*args) is None
    assert quota.response_fields(None) == {}
    s = S(Settings(), quota_db_path=str(tmp_path / "never.sqlite"))   # private, quota unset
    ctx = _ctx(s)
    quota.admit(ctx, _body([("user", "x" * 50000)] * 3))
    assert quota.reserve(ctx, "answer", {"model": "default"}) is None
    assert quota.response_fields(ctx) == {}
    assert not (tmp_path / "never.sqlite").exists()


def test_admit_order_refusal_does_not_burn_a_question(settings):
    s = settings
    s.free_tier_disabled = True
    with pytest.raises(ServiceRefusal) as e:
        quota.admit(_ctx(s), _body())
    assert e.value.status_code == 503 and e.value.detail["code"] == "free_tier_disabled"
    assert quota._store(s).count("v:v1", quota._day()) == 0


def test_admit_counts_visitor_and_ip(settings):
    s = settings
    s.quota_free_per_day = 2
    for _ in range(2):
        quota.admit(_ctx(s), _body())
    with pytest.raises(ServiceRefusal) as e:
        quota.admit(_ctx(s), _body())
    d = e.value.detail
    assert e.value.status_code == 429 and d["code"] == "free_quota_exhausted" and d["remaining"] == 0
    assert d["reset_at"].endswith("T00:00:00Z") and int(e.value.headers["Retry-After"]) >= 1
    quota.admit(_ctx(s, visitor="v2"), _body())   # new cookie, same IP: IP limit 30 still has room
    s.quota_free_per_ip_day = 3
    with pytest.raises(ServiceRefusal):
        quota.admit(_ctx(s, visitor="v3"), _body())   # cookie cleared again: IP limit hits


def test_day_rollover_resets(settings, monkeypatch):
    s = settings
    s.quota_free_per_day = 1
    monkeypatch.setattr(quota, "_now", lambda: 1_800_000_000.0)
    quota.admit(_ctx(s), _body())
    with pytest.raises(ServiceRefusal):
        quota.admit(_ctx(s), _body())
    monkeypatch.setattr(quota, "_now", lambda: 1_800_000_000.0 + 86400)
    quota.admit(_ctx(s), _body())


def test_byok_not_counted_free_web_downgraded(settings):
    s = settings
    s.quota_free_per_day = 1
    creds = Credentials(api_key="sk-user")
    for _ in range(3):
        quota.admit(_ctx(s, creds=creds), _body(web=True))
    assert quota._store(s).count("v:v1", quota._day()) == 0
    ctx, body = _ctx(s), _body(web=True)
    quota.admit(ctx, body)
    assert body.web is False
    assert ctx.notes == [{"capability": "web_tools", "reason": "free_tier_no_web"}]


def test_rate_limit_applies_to_byok(settings):
    s = settings
    s.quota_rate_per_min, s.quota_rate_burst = 1, 2
    creds = Credentials(api_key="sk-user")
    ctx_app = _ctx(s, creds=creds)
    quota.admit(ctx_app, _body())
    quota.admit(_ctx_same_app(ctx_app, creds), _body())
    with pytest.raises(ServiceRefusal) as e:
        quota.admit(_ctx_same_app(ctx_app, creds), _body())
    assert e.value.detail["code"] == "rate_limited" and e.value.detail["retry_after_s"] >= 1


def _ctx_same_app(ctx, creds=None, visitor="v1"):
    req = SimpleNamespace(app=ctx.request.app, scope={"state": {"sdtm_visitor": visitor,
                                                                "sdtm_client_ip": "1.2.3.4"}})
    return RequestContext(endpoint="ask", request=req, credentials=creds)


def test_reserve_rejects_over_remaining_budget_free_only(settings):
    s = settings
    s.quota_site_cap_usd, s.quota_byok_side_budget_usd = 0.002, 0.001   # free share 0.001
    ctx = _ctx(s)
    quota.admit(ctx, _body())
    big = {"model": "default", "messages": [{"role": "user", "content": "x" * 30000}]}
    with pytest.raises(ServiceRefusal) as e:
        quota.reserve(ctx, "answer", big)
    assert e.value.status_code == 429 and e.value.detail["code"] == "site_cap_reached"
    assert quota._store(s).spent(quota._day()) == 0
    # BYOK request: server-key embedding is charged but not refused; its answer is user-paid
    bctx = _ctx(s, creds=Credentials(api_key="sk-user"))
    quota.admit(bctx, _body())
    h = quota.reserve(bctx, "embedding", {"model": "text-embedding-3-small", "input": ["x" * 3000]})
    assert h is not None
    assert quota.reserve(bctx, "answer", big) is None
    assert quota.reserve(bctx, "route", {**big, "api_key": "sk-user"}) is None
    with pytest.raises(ServiceRefusal):   # BYOK Tavily is server-paid: from the BYOK pool
        quota.reserve(bctx, "web", {"query": "q"})


def test_byok_web_daily_quota(settings):
    s = settings
    s.quota_byok_web_per_day = 2
    ctx = _ctx(s, creds=Credentials(api_key="sk-user"))
    quota.admit(ctx, _body())
    for _ in range(2):
        quota.settle(ctx, "web", quota.reserve(ctx, "web", {"query": "q"}), {"status": "ok"}, "tavily")
    with pytest.raises(ServiceRefusal):
        quota.reserve(ctx, "web", {"query": "q"})
    searcher = SimpleNamespace(search=lambda q: pytest.fail("Tavily must not be called"))
    assert outbound.web_search(ctx, searcher, "q") == ([], "quota_exceeded")


def test_settle_uses_reported_model_and_actual_usage(settings):
    s = settings
    ctx = _ctx(s)
    quota.admit(ctx, _body())
    h = quota.reserve(ctx, "answer", {"model": "default", "messages": [{"role": "user", "content": "q"}]})
    usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=100)
    quota.settle(ctx, "answer", h, usage, "deepseek-v4-pro")
    assert quota._store(s).spent(quota._day()) == pytest.approx(
        (1000 * 0.435 + 100 * 0.87) / 1e6)
    quota.settle(ctx, "answer", h, usage, "deepseek-v4-pro")   # repeat: no-op
    assert quota._store(s).spent(quota._day()) == pytest.approx((1000 * 0.435 + 100 * 0.87) / 1e6)


# ── reservation accounting through the real outbound seam ──

class _Router:
    def __init__(self, chunks):
        self.chunks = chunks

    async def acompletion(self, **kw):
        async def agen():
            for c in self.chunks:
                yield c
        return agen()


def _chunk(text="t", usage=None):
    return SimpleNamespace(model="m", usage=usage, choices=[
        SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None), finish_reason=None)])


def _spent(s):
    return quota._store(s).spent(quota._day())


def test_aborted_stream_is_charged_the_reservation(settings):
    s = settings
    ctx = _ctx(s, endpoint="ask_stream")
    quota.admit(ctx, _body())
    kw = {"model": "default", "messages": [{"role": "user", "content": "q"}], "stream": True}
    est = quota._estimate(s, "answer", kw)[0]

    async def run():
        stream = await outbound.acompletion(ctx, "answer", _Router([_chunk(), _chunk()]), **kw)
        await stream.__anext__()     # client reads one chunk, then goes away
        await stream.aclose()

    asyncio.run(run())
    assert ctx.quota.open == {}
    assert _spent(s) == pytest.approx(est)
    quota.finalize(ctx)
    assert _spent(s) == pytest.approx(est)


def test_finalize_charges_unsettled_and_late_settle_is_noop(settings):
    s = settings
    ctx = _ctx(s, endpoint="ask_stream")
    quota.admit(ctx, _body())
    kw = {"model": "default", "messages": [{"role": "user", "content": "q"}]}
    h = quota.reserve(ctx, "answer", kw)
    est = quota._estimate(s, "answer", kw)[0]
    quota.finalize(ctx)
    assert quota._store(s).status(h) == "charged"
    quota.settle(ctx, "answer", h, SimpleNamespace(prompt_tokens=1, completion_tokens=1), "m")
    assert _spent(s) == pytest.approx(est)


def test_reservation_never_finalized_expires_charged(settings, monkeypatch):
    s = settings
    t = [1_800_000_000.0]
    monkeypatch.setattr(quota, "_now", lambda: t[0])
    ctx = _ctx(s)
    quota.admit(ctx, _body())
    kw = {"model": "default", "messages": [{"role": "user", "content": "q"}]}
    h = quota.reserve(ctx, "answer", kw)     # request vanishes: no settle, no finalize
    t[0] += 1000                              # > ttl 900
    other = _ctx(s, visitor="v9")
    quota.admit(other, _body())
    quota.reserve(other, "answer", kw)       # any later reserve sweeps expired rows
    assert quota._store(s).status(h) == "charged"
    # a store reopened after a "restart" still has the money
    quota._STORES.clear()
    assert QuotaStore(Path(s.quota_db_path)).status(h) == "charged"


def test_admit_refuses_at_cap_before_counting(settings):
    s = settings
    s.quota_site_cap_usd, s.quota_byok_side_budget_usd = 3.0, 1.0      # free share = 2.0
    assert quota._store(s).reserve("seed", quota._day(), 2.0, None, quota._now())
    quota.admit(_ctx(s, visitor="early"), _body())   # only an OPEN reservation: admit lets it in
    assert quota._store(s).settle("seed", 2.0)       # settled at the free share -> admit refuses
    with pytest.raises(ServiceRefusal) as e:
        quota.admit(_ctx(s), _body())
    assert e.value.status_code == 429 and e.value.detail["code"] == "site_cap_reached"
    assert quota._store(s).count("v:v1", quota._day()) == 0
    quota.admit(_ctx(s, creds=Credentials(api_key="sk-user")), _body())   # BYOK admitted


def test_question_refunded_if_cap_refuses_before_first_answer_round(settings):
    s = settings
    s.quota_site_cap_usd, s.quota_byok_side_budget_usd = 1.0, 0.0
    store = quota._store(s)
    big = {"model": "default", "messages": [{"role": "user", "content": "q"}]}   # est > $1
    ctx = _ctx(s)
    quota.admit(ctx, _body())
    assert store.count("v:v1", quota._day()) == 1
    with pytest.raises(ServiceRefusal):
        quota.reserve(ctx, "answer", big)
    assert store.count("v:v1", quota._day()) == 0 and store.count("ip:1.2.3.4", quota._day()) == 0
    # after the first answering round reserved, a later refusal keeps the question
    s.quota_site_cap_usd = 100.0
    ctx2 = _ctx(s)
    quota.admit(ctx2, _body())
    quota.reserve(ctx2, "answer", {**big, "max_tokens": 10})
    s.quota_site_cap_usd = 0.0001
    with pytest.raises(ServiceRefusal):
        quota.reserve(ctx2, "continue", big)
    assert store.count("v:v1", quota._day()) == 1


def test_open_handles_are_settled_or_closed_once_across_threads(settings):
    s = settings
    ctx = _ctx(s)
    quota.admit(ctx, _body())
    kw = {"model": "default", "messages": [{"role": "user", "content": "q"}], "max_tokens": 10}
    handles = [quota.reserve(ctx, "embedding", kw) for _ in range(40)]
    barrier = threading.Barrier(41)

    def settle(h):
        barrier.wait()
        quota.settle(ctx, "embedding", h, None, None)

    ts = [threading.Thread(target=settle, args=(h,)) for h in handles]
    ts.append(threading.Thread(target=lambda: (barrier.wait(), quota.finalize(ctx))))
    [t.start() for t in ts]
    [t.join() for t in ts]
    st = quota._store(s)
    assert ctx.quota.open == {}
    assert all(st.status(h) in ("settled", "charged") for h in handles)


def test_client_key_normalizes_ipv6():
    from server.auth import client_key

    assert client_key("2001:db8:1:2:aaaa::1") == "2001:db8:1:2::/64"
    assert client_key("2001:db8:1:2:aaaa::1", 48) == "2001:db8:1::/48"
    assert client_key("::ffff:203.0.113.7") == "203.0.113.7"
    assert client_key("203.0.113.7") == "203.0.113.7"
    assert client_key("testclient") == "testclient"


def test_byok_sub_budget_is_carved_out_of_the_cap(settings):
    s = settings
    s.quota_site_cap_usd, s.quota_byok_side_budget_usd = 5.0, 2.0
    assert quota._pool_caps(s) == {"free": 3.0, "byok": 2.0}
    store, day = quota._store(s), quota._day()
    assert store.reserve("free-seed", day, 3.0, None, quota._now()) and store.settle("free-seed", 3.0)
    with pytest.raises(ServiceRefusal) as e:          # free share used up -> free off
        quota.admit(_ctx(s), _body())
    assert e.value.detail["code"] == "site_cap_reached"
    ctx = _ctx(s, creds=Credentials(api_key="junk-key"))
    quota.admit(ctx, _body())                         # BYOK still works
    emb = {"model": "text-embedding-3-small", "input": ["x"]}
    assert quota.reserve(ctx, "embedding", emb) is not None
    assert store.spent(day, "byok") > 0
    assert store.reserve("byok-seed", day, 2.0 - store.spent(day, "byok"), None, quota._now(), "byok")
    with pytest.raises(ServiceRefusal):               # BYOK pool used up -> refused at reserve
        quota.reserve(ctx, "embedding", emb)
    quota.finalize(ctx)
    assert store.spent(day) <= 5.0 + 1e-9             # total never exceeds the cap
    store._db.execute("UPDATE reservations SET status='settled' WHERE id='byok-seed'")
    with pytest.raises(ServiceRefusal):               # ... and at admit once settled
        quota.admit(_ctx(s, creds=Credentials(api_key="junk-key"), visitor="b2"), _body())
    s.quota_byok_side_budget_usd = 99.0               # budget is clamped into the cap
    assert quota._pool_caps(s) == {"free": 0.0, "byok": 5.0}


def test_every_metered_endpoint_counts_compare_weighted(settings):
    s = settings
    s.quota_free_per_day = 5
    body = SimpleNamespace(history=[], models=["a", "b", "c"], judge=SimpleNamespace(enabled=True))
    quota.admit(_ctx(s, endpoint="ask_compare"), body)                 # 3 answers + judge = 4
    assert quota._store(s).count("v:v1", quota._day()) == 4
    quota.admit(_ctx(s, endpoint="validate"), None)                    # validate counts too
    assert quota._store(s).count("v:v1", quota._day()) == 5
    with pytest.raises(ServiceRefusal):
        quota.admit(_ctx(s, endpoint="ask_compare"), body)


def test_rate_limit_covers_non_ask_endpoints(settings):
    s = settings
    s.quota_rate_per_min, s.quota_rate_burst = 1, 1
    c = _ctx(s, endpoint="validate")
    quota.admit(c, None)
    with pytest.raises(ServiceRefusal) as e:
        quota.admit(_ctx_same_app(c), None)
    assert e.value.detail["code"] == "rate_limited"
