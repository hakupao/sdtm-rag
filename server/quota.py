"""Quota / cost-cap hooks — owned by L2 (P2 steps 2.2 / 2.7).

Lifecycle per request (design doc §3):
  admit(ctx, body)                once, after validation, BEFORE retrieval and before the prompt is
                                  built: count the free question, refuse with ServiceRefusal(429/413),
                                  and may clip `body.history` in place (2.2). Visitor identity:
                                  ctx.request (cookies, CF-Connecting-IP); settings: ctx.request.app.state.settings
  reserve(ctx, purpose, kw)       before EVERY outbound call (outbound.py) -> opaque handle (or None);
                                  kw has the final model/messages/max_tokens; may raise ServiceRefusal
  settle(ctx, purpose, handle, usage, model)
                                  after every call with reserve's handle. usage may be None (failed /
                                  client stopped reading) and may be litellm-ESTIMATED: when a stream
                                  ends without a usage chunk — including an upstream mid-stream cut,
                                  which litellm does NOT raise (BYOK probe §5) — litellm synthesizes
                                  it. model = what the provider reported (a Router fallback changes it).
  finalize(ctx)                   exactly once at request end (normal, error, client disconnect);
                                  charge whatever was reserved but never settled. An open stream is
                                  closed (and settled) before finalize; any settle that still arrives
                                  after finalize MUST be a no-op (idempotent per handle).
Thread safety: hooks are called from the threadpool (/api/ask is a sync endpoint; web search runs in
asyncio.to_thread) — the store must be safe across threads.
ctx is None outside a request (eval/scripts) ⇒ every hook must be a pass-through for None.

L2 policy (checkpoint .work/10_split_and_public/evidence/checkpoints/p2_l2.md):
- Enabled iff `quota_enabled` is true, or unset and the tier is public. Disabled ⇒ every hook is the
  P2.0 no-op (private default byte-identical; no DB file is created).
- Free (server-key) request: kill switch → site cap → rate limit → history trim → free count (visitor
  AND client IP, both must have room). Free questions get no web search (downgrade note).
- Spend pools (user decision): total server-key spend ≤ quota_site_cap_usd. BYOK requests'
  server-key calls (embedding, routing, Tavily…) draw on their own pool of quota_byok_side_budget_usd
  carved OUT of the cap; free requests get the rest. Free exhausting its share does not stop BYOK
  until the BYOK pool is used; the two pools together never exceed the cap. BYOK Tavily also has a
  per-visitor daily quota.
- Every server-key call reserves an estimate (charged at once); settle swaps in the actual cost.
- Config: `cfg(settings, key)` = settings attribute if L3 added it, else env `SDTM_RAG_<KEY>`,
  else `_DEFAULTS`.
"""
from __future__ import annotations

import datetime
import functools
import math
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from server.request_context import ServiceRefusal

_DEFAULTS: dict = {
    "quota_enabled": None,             # None = on iff tier == "public"
    "free_tier_disabled": False,       # kill switch: no server-key questions at all (503)
    "quota_free_per_day": 10,          # free questions per visitor (cookie) per UTC day
    "quota_free_per_ip_day": 30,       # … and per client IP (cookie clearing / cookieless clients)
    "quota_site_cap_usd": 5.0,         # ALL server-key spend combined, per UTC day (hard)
    "quota_byok_side_budget_usd": 2.0,  # carved out of the cap for BYOK requests' server-key calls
    "quota_rate_per_min": 6,           # questions per visitor per minute (BYOK too)
    "quota_rate_burst": 3,
    "quota_ip_rate_per_min": 20,       # questions per client IP per minute
    "quota_ip_rate_burst": 6,
    "quota_byok_web_per_day": 30,      # Tavily searches per BYOK visitor per UTC day
    "quota_free_web_enabled": False,   # PLAN Q2: free questions do not search the web
    "quota_history_max_messages": 8,
    "quota_history_max_chars": 20000,
    "quota_max_body_bytes": 2_000_000,
    "quota_db_path": "",               # "" = <dir of dogfood_log_path>/quota.sqlite (the data/ mount)
    "quota_reservation_ttl_s": 900.0,
    "quota_web_search_usd": 0.016,     # Tavily advanced = 2 credits; UNVERIFIED price, conservative
    "quota_fallback_in_usd_per_mtok": 5.0,    # model cost.py cannot price -> assume this rate
    "quota_fallback_out_usd_per_mtok": 25.0,
    "quota_default_max_output_tokens": 8192,
    "quota_trusted_proxies": "",       # comma list of IPs/CIDRs allowed to set CF-Connecting-IP
    "quota_ipv6_prefix": 64,           # IPv6 clients are keyed by this prefix (one /64 = one client)
    "visitor_secret": "",              # signs the visitor cookie; required when quota is enabled
    "visitor_cookie_name": "sdtm_visitor",
    "visitor_cookie_secure": None,     # None = Secure iff public tier
    "visitor_cookie_max_age_s": 31_536_000,
    "flag_rate_per_min": 5,
    "flag_rate_burst": 3,
}

_ANSWER_PURPOSES = frozenset({"answer", "continue", "regen"})
# Reserving one of these = the request started producing its answer; a later cap refusal keeps the
# free question (the visitor got a partial result / used real spend). Before it: refunded.
_FIRST_ROUND_PURPOSES = frozenset({"answer", "continue", "regen", "compare", "review"})
# Deny-by-default: every metered endpoint counts as (weighted) free questions and is rate-limited
# unless listed here. None are exempt today: ask/ask_stream/validate = 1, ask_compare = N answers.
_EXEMPT_ENDPOINTS: frozenset = frozenset()
_TRUE = {"1", "true", "yes", "on"}
_CAP_MSG = "今日全站免费额度已用完, 请明天再来或使用自己的 API key。"

_now = time.time   # monkeypatched by tests (day rollover / expiry)


def cfg(s, key: str):
    default = _DEFAULTS[key]
    v = getattr(s, key, None) if s is not None else None
    if v is not None:
        return v
    raw = os.environ.get("SDTM_RAG_" + key.upper())
    if raw is None or raw == "":
        return default
    if default is None or isinstance(default, bool):
        return raw.strip().lower() in _TRUE
    return type(default)(raw)


def _on(s, tier: str) -> bool:
    v = cfg(s, "quota_enabled")
    return bool(v) if v is not None else tier == "public"


def app_enabled(s) -> bool:
    return _on(s, getattr(s, "instance", "private"))


def _pool_caps(s) -> dict:
    """{"free": cap - byok_budget, "byok": byok_budget}; the budget is clamped into [0, cap]."""
    cap = float(cfg(s, "quota_site_cap_usd"))
    byok = min(max(0.0, float(cfg(s, "quota_byok_side_budget_usd"))), cap)
    return {"free": cap - byok, "byok": byok}


def _settings(ctx):
    return getattr(ctx.request.app.state, "settings", None)


def _enabled(ctx) -> bool:
    return ctx is not None and ctx.request is not None and _on(_settings(ctx), ctx.tier)


# ── store + limiters ─────────────────────────────────────────────────────────

_STORES: dict = {}
_STORES_LOCK = threading.Lock()


def db_path(s) -> Path:
    p = cfg(s, "quota_db_path")
    return Path(p) if p else Path(s.dogfood_log_path).parent / "quota.sqlite"


def _store(s):
    from server.quota_store import QuotaStore

    key = str(db_path(s).resolve())
    with _STORES_LOCK:
        if key not in _STORES:
            _STORES[key] = QuotaStore(Path(key))
        return _STORES[key]


class _Limiter:
    """auth.TokenBucketLimiter behind a lock (admit also runs in the threadpool)."""

    def __init__(self, per_min: int, burst: int):
        from server.auth import TokenBucketLimiter

        self._b = TokenBucketLimiter(per_min, burst)
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float]:
        with self._lock:
            return self._b.allow(key)


_LIMITERS_LOCK = threading.Lock()


def _limiters(ctx):
    state = ctx.request.app.state
    with _LIMITERS_LOCK:
        lim = getattr(state, "quota_limiters", None)
        if lim is None:
            s = _settings(ctx)
            lim = (_Limiter(int(cfg(s, "quota_rate_per_min")), int(cfg(s, "quota_rate_burst"))),
                   _Limiter(int(cfg(s, "quota_ip_rate_per_min")), int(cfg(s, "quota_ip_rate_burst"))))
            state.quota_limiters = lim
        return lim


# ── per-request state (ctx.quota) ────────────────────────────────────────────

@dataclass
class _ReqState:
    visitor: str | None
    ip: str
    byok: bool
    day: str
    open: dict = field(default_factory=dict)   # rid -> (est_usd, model); guarded by `lock`
    lock: threading.Lock = field(default_factory=threading.Lock)
    taken: tuple | None = None   # (keys, day, n) of the free questions this request counted
    answered: bool = False       # a first answering round got its reservation


def _day(t: float | None = None) -> str:
    return datetime.datetime.fromtimestamp(_now() if t is None else t, datetime.UTC).date().isoformat()


def _reset_at() -> tuple[str, int]:
    now = datetime.datetime.fromtimestamp(_now(), datetime.UTC)
    nxt = datetime.datetime.combine(now.date() + datetime.timedelta(days=1), datetime.time(),
                                    datetime.UTC)
    return nxt.strftime("%Y-%m-%dT%H:%M:%SZ"), max(1, math.ceil((nxt - now).total_seconds()))


def _identity(request) -> tuple[str | None, str]:
    """(visitor id, client ip). The visitor middleware (auth.py) puts both in scope state; without
    it (bare test apps) there is no visitor and the IP is resolved the same way here."""
    state = request.scope.get("state") or {}
    ip = state.get("sdtm_client_ip")
    if ip is None:
        from server.auth import resolve_client_ip

        s = getattr(request.app.state, "settings", None)
        ip = resolve_client_ip(request.scope, cfg(s, "quota_trusted_proxies"),
                               int(cfg(s, "quota_ipv6_prefix")))
    return state.get("sdtm_visitor"), ip


def _keys(st: _ReqState) -> list[str]:
    return ([f"v:{st.visitor}"] if st.visitor else []) + [f"ip:{st.ip}"]


def _free_remaining(s, st: _ReqState) -> int:
    store = _store(s)
    rem = int(cfg(s, "quota_free_per_ip_day")) - store.count(f"ip:{st.ip}", st.day)
    if st.visitor:
        rem = min(rem, int(cfg(s, "quota_free_per_day")) - store.count(f"v:{st.visitor}", st.day))
    return max(0, rem)


def _quota_shape(s, st: _ReqState) -> dict:
    return {"free_remaining": _free_remaining(s, st),
            "free_per_day": int(cfg(s, "quota_free_per_day")),
            "reset_at": _reset_at()[0], "byok": st.byok}


def _refuse(status: int, code: str, message: str, retry_s: int | None = None, **fields):
    headers = {"Retry-After": str(retry_s)} if retry_s is not None else None
    raise ServiceRefusal(status, code, message, headers=headers, **fields)


# ── history trimming (2.2) ───────────────────────────────────────────────────

def trim_history(history: list, max_messages: int, max_chars: int) -> list:
    """Keep the most recent contiguous messages with count ≤ max_messages and total content
    ≤ max_chars; a message that does not fit ends the walk (never cut mid-text, so one message
    over the budget ⇒ empty history). A leading assistant turn left by the cut is dropped too."""
    kept: list = []
    total = 0
    for m in reversed(history):
        n = len(m.content)
        if len(kept) >= max_messages or total + n > max_chars:
            break
        kept.append(m)
        total += n
    kept.reverse()
    while kept and kept[0].role != "user":
        kept.pop(0)
    return kept


# ── hooks ────────────────────────────────────────────────────────────────────

def admit(ctx, body) -> None:
    if not _enabled(ctx):
        return
    s = _settings(ctx)
    visitor, ip = _identity(ctx.request)
    st = _ReqState(visitor=visitor, ip=ip, byok=ctx.credentials is not None, day=_day())
    ctx.quota = st
    reset_at, reset_s = _reset_at()
    store = _store(s)

    pool = "byok" if st.byok else "free"
    if not st.byok and cfg(s, "free_tier_disabled"):
        _refuse(503, "free_tier_disabled", "免费体验已暂停, 请使用自己的 API key。")
    # Gate on SETTLED spend of this request's pool: open reservations are upper-bound estimates of
    # in-flight calls and would refuse new visitors while real spend is far below the cap. The hard
    # guarantee stays in reserve (atomic, counts open reservations); a question refused there before
    # its first answering round is refunded.
    if store.settled(st.day, pool) >= _pool_caps(s)[pool]:
        _refuse(429, "site_cap_reached", _CAP_MSG, reset_s, reset_at=reset_at)

    metered = ctx.endpoint not in _EXEMPT_ENDPOINTS
    if metered:
        v_lim, ip_lim = _limiters(ctx)
        for lim, key in ((v_lim, st.visitor), (ip_lim, f"ip:{st.ip}")):
            if key is None:
                continue
            ok, retry = lim.allow(key)
            if not ok:
                r = max(1, math.ceil(retry))
                _refuse(429, "rate_limited", "提问太频繁, 请稍后再试。", r, retry_after_s=r)

    if body is not None and getattr(body, "history", None):
        body.history = trim_history(body.history, int(cfg(s, "quota_history_max_messages")),
                                    int(cfg(s, "quota_history_max_chars")))

    if st.byok or not metered:
        return
    limits = [(f"ip:{st.ip}", int(cfg(s, "quota_free_per_ip_day")))]
    if st.visitor:
        limits.append((f"v:{st.visitor}", int(cfg(s, "quota_free_per_day"))))
    n = _weight(ctx, body, s)
    if not store.take(limits, st.day, n):
        _refuse(429, "free_quota_exhausted", "今日免费提问次数已用完, 请明天再来或使用自己的 API key。",
                reset_s, remaining=0, reset_at=reset_at)
    st.taken = ([k for k, _ in limits], st.day, n)
    if getattr(body, "web", False) and not cfg(s, "quota_free_web_enabled"):
        body.web = False
        ctx.notes.append({"capability": "web_tools", "reason": "free_tier_no_web"})


def _weight(ctx, body, s) -> int:
    """Free questions one request costs: ask_compare = one per answering model (+1 for the judge)."""
    if ctx.endpoint != "ask_compare" or body is None:
        return 1
    models = getattr(body, "models", None) or getattr(s, "compare_models", None) or []
    judge = getattr(getattr(body, "judge", None), "enabled", False)
    return max(1, len(models)) + (1 if judge else 0)


def _text_tokens(text: str) -> int:
    """Conservative token estimate: 1 per non-ASCII char (CJK), 1 per 3 ASCII chars."""
    non_ascii = sum(1 for ch in text if ord(ch) > 127)
    return non_ascii + math.ceil((len(text) - non_ascii) / 3)


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    return ""


def _group_model(s, name: str) -> tuple[str, int | None]:
    """Router group / selectable id -> (real model string, deployment max_tokens)."""
    groups = {
        "default": ("default_model", "default_max_output_tokens"),
        "default-fallback": ("fallback_model", "fallback_max_output_tokens"),
        "hard": ("hard_model", "hard_max_output_tokens"),
        "light": ("light_model", "light_max_output_tokens"),
    }
    if name in groups:
        m, mt = groups[name]
        return getattr(s, m, name), getattr(s, mt, None)
    for sm in getattr(s, "selectable_models", None) or []:
        if sm.id == name:
            return sm.model, sm.max_output_tokens
    return name, None


@functools.lru_cache(maxsize=256)
def _rates(model: str) -> tuple[float | None, float | None]:
    """USD per 1M (input, output) tokens from cost.estimate_cost. Asked per million tokens because
    it rounds to 6 decimals (a query embedding would otherwise price at $0)."""
    from server.cost import estimate_cost

    return (estimate_cost(model, {"prompt_tokens": 1_000_000, "completion_tokens": 0}),
            estimate_cost(model, {"prompt_tokens": 0, "completion_tokens": 1_000_000}))


def _price(s, model: str, pt: int, ct: int) -> float:
    r_in, r_out = _rates(model)
    if r_in is None and r_out is None:   # unknown model: never $0 — assume a conservative rate
        r_in = float(cfg(s, "quota_fallback_in_usd_per_mtok"))
        r_out = float(cfg(s, "quota_fallback_out_usd_per_mtok"))
    return (pt * (r_in or 0.0) + ct * (r_out or 0.0)) / 1_000_000


def _estimate(s, purpose: str, kw: dict) -> tuple[float, str]:
    if purpose == "web":
        return float(cfg(s, "quota_web_search_usd")), "tavily"
    model, max_out = _group_model(s, str(kw.get("model", "")))
    if purpose == "embedding":
        inp = kw.get("input") or []
        inp = [inp] if isinstance(inp, str) else inp
        return _price(s, model, sum(_text_tokens(str(x)) for x in inp), 0), model
    pt = sum(_text_tokens(_content_text(m.get("content"))) + 4 for m in kw.get("messages") or [])
    ct = int(kw.get("max_tokens") or max_out or cfg(s, "quota_default_max_output_tokens"))
    return _price(s, model, pt, ct), model


def _user_paid(ctx, purpose: str, kw: dict) -> bool:
    """A BYOK request's answer rounds never fall back to the server key (contract §2.1); any other
    call is user-paid only if L1 put the user's key into this call's kwargs."""
    creds = ctx.credentials
    if creds is None or purpose == "web":
        return False
    return purpose in _ANSWER_PURPOSES or kw.get("api_key") == creds.api_key


def reserve(ctx, purpose: str, kw: dict):
    st = getattr(ctx, "quota", None) if ctx is not None else None
    if not isinstance(st, _ReqState) or not _enabled(ctx) or _user_paid(ctx, purpose, kw):
        return None
    s = _settings(ctx)
    store = _store(s)
    reset_at, reset_s = _reset_at()
    if purpose == "web" and st.byok:
        limits = [(f"w:{k}", int(cfg(s, "quota_byok_web_per_day"))) for k in _keys(st)]
        if not store.take(limits, _day()):
            _refuse(429, "rate_limited", "今日联网检索次数已用完。", reset_s, retry_after_s=reset_s)
    est, model = _estimate(s, purpose, kw)
    now = _now()
    store.expire(now - float(cfg(s, "quota_reservation_ttl_s")))
    pool = "byok" if st.byok else "free"   # BYOK requests' server-key calls use the carved-out pool
    rid = uuid.uuid4().hex
    if not store.reserve(rid, _day(now), est, _pool_caps(s)[pool], now, pool):
        with st.lock:
            refund = None if st.answered else st.taken
            if refund:
                st.taken = None
        if refund:
            store.untake(*refund)
        _refuse(429, "site_cap_reached", _CAP_MSG, reset_s, reset_at=reset_at)
    with st.lock:
        st.open[rid] = (est, model)
        if purpose in _FIRST_ROUND_PURPOSES:
            st.answered = True
    return rid


def _usage_tokens(usage) -> tuple[int, int] | None:
    if usage is None:
        return None
    get = usage.get if isinstance(usage, dict) else (lambda k: getattr(usage, k, None))
    pt, ct = get("prompt_tokens"), get("completion_tokens")
    if pt is None and ct is None:
        return None
    return int(pt or 0), int(ct or 0)


def settle(ctx, purpose: str, handle, usage, model) -> None:
    st = getattr(ctx, "quota", None) if ctx is not None else None
    if handle is None or not isinstance(st, _ReqState):
        return
    with st.lock:
        entry = st.open.pop(handle, None)
    if entry is None:       # already settled / finalized: no-op
        return
    s = _settings(ctx)
    est, est_model = entry
    tokens = _usage_tokens(usage) if purpose != "web" else None
    # No usable usage (failed call, aborted stream, web) => the reservation is the charge.
    actual = est if tokens is None else _price(s, model or est_model, *tokens)
    _store(s).settle(handle, actual)


def finalize(ctx) -> None:
    st = getattr(ctx, "quota", None) if ctx is not None else None
    if not isinstance(st, _ReqState):
        return
    store = _store(_settings(ctx))
    with st.lock:
        rids, st.open = list(st.open), {}
    for rid in rids:
        store.close(rid)


def response_fields(ctx) -> dict:
    """Extra keys for AskResponse / SSE `done` ({"quota": {...}} when enabled). Default: none."""
    st = getattr(ctx, "quota", None) if ctx is not None else None
    if not isinstance(st, _ReqState) or not _enabled(ctx):
        return {}
    return {"quota": _quota_shape(_settings(ctx), st)}


def info_fields(request) -> dict:
    """Extra /api/info keys (`quota` for this visitor when enabled). Default: none."""
    from server import instance, providers

    s = getattr(request.app.state, "settings", None)
    if not _on(s, instance.tier(request)):
        return {}
    visitor, ip = _identity(request)
    st = _ReqState(visitor=visitor, ip=ip, byok=providers.credentials_from(request) is not None,
                   day=_day())
    return {"quota": _quota_shape(s, st)}
