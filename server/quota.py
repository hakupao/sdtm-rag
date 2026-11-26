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
    "quota_free_per_ip_day": 50,       # … and per client IP (cookie clearing / cookieless clients)
    "quota_site_cap_usd": 5.0,         # ALL server-key spend combined, per UTC day (hard)
    "quota_byok_side_budget_usd": 2.0,  # carved out of the cap for BYOK requests' server-key calls
    "quota_rate_per_min": 6,           # questions per visitor per minute (BYOK too)
    "quota_rate_burst": 3,
    "quota_ip_rate_per_min": 20,       # questions per client IP per minute
    "quota_ip_rate_burst": 6,
    "quota_byok_web_per_day": 30,      # Tavily searches per BYOK visitor per UTC day
    "quota_free_web_enabled": False,   # PLAN Q2: free questions do not search the web (L1 enforces)
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
    # P2.9 fixes (checkpoint p2.9_fix.md)
    "quota_abort_buffer_tokens": 4096,  # usage-less stream closed early: output still generated upstream
    "quota_busy_retry_s": 15,          # site_busy: open reservations (not settled spend) fill the pool
    "quota_inflight_per_ip": 5,        # concurrent metered requests per client IP (0 = off)
    "quota_byok_side_per_ip_usd": 0.5,  # one IP's share of the BYOK side budget per UTC day
    "quota_byok_bad_key_per_ip_day": 20,  # byok_key_invalid refusals per IP per day, then 429
    "quota_retention_days": 14,        # counters / spend / reservations older than this are pruned
    "flag_bytes_per_ip_day": 512_000,  # /api/flag bytes appended per client IP per UTC day
    "flag_file_max_bytes": 64_000_000,  # dogfood log size ceiling (507 storage_full)
}

_ANSWER_PURPOSES = frozenset({"answer", "continue", "regen"})
# Reserving one of these = the request started producing its answer; a later cap refusal keeps the
# free question (the visitor got a partial result / used real spend). Before it: refunded.
_FIRST_ROUND_PURPOSES = frozenset({"answer", "continue", "regen", "compare", "review"})
# Deny-by-default: every metered endpoint counts as (weighted) free questions and is rate-limited
# unless listed here. None are exempt today: ask/ask_stream/validate = 1, ask_compare = N answers.
_EXEMPT_ENDPOINTS: frozenset = frozenset()
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
# Env families validate() owns: an SDTM_RAG_* name with one of these prefixes that is neither a
# _DEFAULTS key nor a Settings field is a typo (e.g. SDTM_RAG_QUOTA_ENABLD) => refuse to start.
_ENV_FAMILIES = ("SDTM_RAG_QUOTA_", "SDTM_RAG_VISITOR_", "SDTM_RAG_FLAG_", "SDTM_RAG_FREE_")
_SECRET_KEYS = frozenset({"visitor_secret"})
# Prompt-side allowance for the public per-round estimate (instance.check_startup): history
# (≤ quota_history_max_chars, 1 token/char worst case) + this (question ≤ 10k chars, system prompt,
# retrieved context).
PROMPT_OVERHEAD_TOKENS = 40_000
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
        v = raw.strip().lower()
        if v in _TRUE:
            return True
        if v in _FALSE:
            return False
        # strict: a kill-switch / enable typo ("ture", "y") must not silently mean False
        raise ValueError(f"SDTM_RAG_{key.upper()}={raw!r} is not a boolean "
                         f"(use one of {sorted(_TRUE | _FALSE)})")
    return type(default)(raw)


def validate(s) -> dict:
    """Startup check (auth._install_quota): parse every key (malformed => RuntimeError naming the
    key) and, when quota is on, refuse unknown names in the quota env families. Returns the
    effective values with secrets reduced to "set"/"unset" (safe to log)."""
    from server.config import Settings

    eff = {}
    for key in _DEFAULTS:
        try:
            v = cfg(s, key)
        except ValueError as e:
            raise RuntimeError(f"bad quota setting SDTM_RAG_{key.upper()}: {e}") from None
        if isinstance(v, (int, float)) and not isinstance(v, bool) \
                and (not math.isfinite(v) or v < 0):
            # fail closed: inf / nan / negative caps would disable or invert a limit
            raise RuntimeError(f"bad quota setting SDTM_RAG_{key.upper()}: {v!r} (must be finite, ≥ 0)")
        eff[key] = ("set" if v else "unset") if key in _SECRET_KEYS else v
    if app_enabled(s):
        known = {"SDTM_RAG_" + k.upper() for k in (*_DEFAULTS, *Settings.model_fields)}
        unknown = sorted(k for k in (n.upper() for n in os.environ)
                         if k.startswith(_ENV_FAMILIES) and k not in known)
        if unknown:
            raise RuntimeError(f"unknown quota setting(s) {unknown} (typo?); known keys: "
                               "server/quota.py _DEFAULTS")
    return eff


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
    return getattr(getattr(getattr(ctx.request, "app", None), "state", None), "settings", None)


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
        store = _STORES[key]
    _maybe_prune(s, store)
    return store


def _maybe_prune(s, store) -> None:
    """Drop rows older than quota_retention_days, at most once per store per UTC day."""
    today = _day()
    if getattr(store, "_pruned_for", None) == today:
        return
    store._pruned_for = today
    cutoff = (datetime.date.fromisoformat(today)
              - datetime.timedelta(days=int(cfg(s, "quota_retention_days")))).isoformat()
    store.prune(cutoff)


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


# ── in-flight cap (per client IP, process memory) ────────────────────────────

_INFLIGHT_LOCK = threading.Lock()


def _inflight_acquire(ctx, ip: str, cap: int, ttl: float) -> str | None:
    """A slot token, or None when `ip` already has `cap` live requests. Slots older than `ttl`
    are dropped (finalize may be delayed to GC on a client disconnect; never lock an IP out)."""
    state = ctx.request.app.state
    now = _now()
    with _INFLIGHT_LOCK:
        table = getattr(state, "quota_inflight", None)
        if table is None:
            table = state.quota_inflight = {}
        slots = {t: t0 for t, t0 in table.get(ip, {}).items() if now - t0 < ttl}
        if len(slots) >= cap:
            table[ip] = slots
            return None
        tok = uuid.uuid4().hex
        slots[tok] = now
        table[ip] = slots
        return tok


def _inflight_release(ctx, ip: str, tok: str) -> None:
    with _INFLIGHT_LOCK:
        table = getattr(ctx.request.app.state, "quota_inflight", None) or {}
        slots = table.get(ip)
        if slots is not None:
            slots.pop(tok, None)     # idempotent
            if not slots:
                table.pop(ip, None)


# ── per-request state (ctx.quota) ────────────────────────────────────────────

@dataclass
class _Open:
    """One open reservation: what reserve charged and what settle needs to replace it."""
    est: float          # USD charged at reserve
    model: str          # priced model
    pt: int             # estimated prompt tokens (an aborted stream settles at pt + 1.5 x streamed)
    day: str
    sub: tuple | None = None   # (counter key, micro-USD charged) — BYOK per-IP side budget


@dataclass
class _ReqState:
    visitor: str | None
    ip: str
    byok: bool
    day: str
    open: dict = field(default_factory=dict)   # rid -> _Open; guarded by `lock`
    lock: threading.Lock = field(default_factory=threading.Lock)
    taken: tuple | None = None   # (keys, day, n) of the free questions this request counted
    answered: bool = False       # a first answering round got its reservation
    inflight: str | None = None  # in-flight slot token (released by finalize)


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

    cap = int(cfg(s, "quota_inflight_per_ip"))
    if metered and cap > 0:
        tok = _inflight_acquire(ctx, st.ip, cap, float(cfg(s, "quota_reservation_ttl_s")))
        if tok is None:
            _refuse(429, "rate_limited", "同时进行的提问太多, 请等上一个回答结束。", 5, retry_after_s=5)
        st.inflight = tok

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
    # Free questions and the web: one owner = providers.capability("web_tools") via free_web_allowed.


def free_web_allowed(ctx) -> bool:
    """Server-key (free) request may use web search? Metered (public / quota on) ⇒ only when
    quota_free_web_enabled. Unmetered private ⇒ yes (pre-P2). The policy owner is L1's
    capability gate, which calls this (single source of the key)."""
    s = _settings(ctx)
    if ctx.tier != "public" and not (ctx.request is not None and _on(s, ctx.tier)):
        return True
    return bool(cfg(s, "quota_free_web_enabled"))


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
    usd, model, _pt = _estimate_parts(s, purpose, kw)
    return usd, model


def _estimate_parts(s, purpose: str, kw: dict) -> tuple[float, str, int]:
    """(reserved USD, priced model, estimated prompt tokens)."""
    if purpose == "web":
        return float(cfg(s, "quota_web_search_usd")), "tavily", 0
    model, max_out = _group_model(s, str(kw.get("model", "")))
    if purpose == "embedding":
        inp = kw.get("input") or []
        inp = [inp] if isinstance(inp, str) else inp
        pt = sum(_text_tokens(str(x)) for x in inp)
        return _price(s, model, pt, 0), model, pt
    pt = sum(_text_tokens(_content_text(m.get("content"))) + 4 for m in kw.get("messages") or [])
    ct = int(kw.get("max_tokens") or max_out or cfg(s, "quota_default_max_output_tokens"))
    return _price(s, model, pt, ct), model, pt


def round_estimate_usd(s, model_id: str) -> float:
    """Worst-case reservation of ONE answer round on `model_id` (same pricing path as reserve):
    prompt = full trimmed history + PROMPT_OVERHEAD_TOKENS, output = the deployment max_tokens."""
    model, max_out = _group_model(s, model_id)
    pt = int(cfg(s, "quota_history_max_chars")) + PROMPT_OVERHEAD_TOKENS
    ct = int(max_out or cfg(s, "quota_default_max_output_tokens"))
    return _price(s, model, pt, ct)


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
    now = _now()
    day = _day(now)
    web_taken = None
    if purpose == "web" and st.byok:
        limits = [(f"w:{k}", int(cfg(s, "quota_byok_web_per_day"))) for k in _keys(st)]
        if not store.take(limits, day):
            _refuse(429, "rate_limited", "今日联网检索次数已用完。", reset_s, retry_after_s=reset_s)
        web_taken = ([k for k, _ in limits], day)
    est, model, pt = _estimate_parts(s, purpose, kw)
    store.expire(now - float(cfg(s, "quota_reservation_ttl_s")))
    pool = "byok" if st.byok else "free"   # BYOK requests' server-key calls use the carved-out pool
    sub = None
    if st.byok:
        # One IP's share of the BYOK side budget (micro-USD counter): one IP cannot drain the pool.
        key, micros = f"bs:{st.ip}", math.ceil(est * 1e6)
        if not store.take([(key, int(float(cfg(s, "quota_byok_side_per_ip_usd")) * 1e6))], day, micros):
            if web_taken:
                store.untake(*web_taken)
            _refuse(429, "rate_limited", "今日自带 key 的附加调用额度已用完, 请明天再来。", reset_s,
                    retry_after_s=reset_s)
        sub = (key, micros)
    rid = uuid.uuid4().hex
    cap = _pool_caps(s)[pool]
    if not store.reserve(rid, day, est, cap, now, pool):
        with st.lock:
            refund = None if st.answered else st.taken
            if refund:
                st.taken = None
        if refund:
            store.untake(*refund)
        if web_taken:
            store.untake(*web_taken)
        if sub:
            store.untake([sub[0]], day, sub[1])
        if store.settled(day, pool) + est <= cap + 1e-9:
            # Only still-open reservations (upper-bound estimates of in-flight calls) are in the
            # way, not real spend: transient, retry shortly.
            r = int(cfg(s, "quota_busy_retry_s"))
            _refuse(503, "site_busy", "当前提问的人较多, 请稍后再试。", r, retry_after_s=r)
        _refuse(429, "site_cap_reached", _CAP_MSG, reset_s, reset_at=reset_at)
    with st.lock:
        st.open[rid] = _Open(est=est, model=model, pt=pt, day=day, sub=sub)
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


def settle(ctx, purpose: str, handle, usage, model, *, streamed_text: str | None = None,
           closed_early: bool = False) -> None:
    """usage given => priced from it. Else streamed_text None (failed non-streamed call, ambiguous
    stream failure, web) => the reservation is the charge. Else (a stream that ended without usage,
    or "" = an open the provider clearly rejected) => estimated prompt + ceil(1.5 x streamed
    tokens); closed_early (client / router closed it) => at least streamed + abort buffer. Never
    more than the reservation."""
    st = getattr(ctx, "quota", None) if ctx is not None else None
    if handle is None or not isinstance(st, _ReqState):
        return
    with st.lock:
        entry = st.open.pop(handle, None)
    if entry is None:       # already settled / finalized: no-op
        return
    s = _settings(ctx)
    tokens = _usage_tokens(usage) if purpose != "web" else None
    if tokens is not None:
        actual = _price(s, model or entry.model, *tokens)
    elif streamed_text is not None and purpose != "web":
        n = _text_tokens(streamed_text)
        out = math.ceil(1.5 * n)
        if closed_early:
            out = max(out, n + int(cfg(s, "quota_abort_buffer_tokens")))
        actual = min(entry.est, _price(s, model or entry.model, entry.pt, out))
    else:
        actual = entry.est
    store = _store(s)
    if store.settle(handle, actual) and entry.sub:
        key, micros = entry.sub
        diff = math.ceil(actual * 1e6) - micros
        if diff < 0:
            store.untake([key], entry.day, -diff)
        elif diff > 0:
            store.take([(key, 2**62)], entry.day, diff)


def finalize(ctx) -> None:
    st = getattr(ctx, "quota", None) if ctx is not None else None
    if not isinstance(st, _ReqState):
        return
    store = _store(_settings(ctx))
    with st.lock:
        rids, st.open = list(st.open), {}
        tok, st.inflight = st.inflight, None
    for rid in rids:
        store.close(rid)
    if tok is not None:
        _inflight_release(ctx, st.ip, tok)


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


# ── BYOK bad-key probing (L1 calls these) ────────────────────────────────────

def _bad_key_counter(ctx):
    """(store, key, limit, day) when metering is on, else None. No ASGI scope (a bare request
    object outside the app stack) = no client identity to key on => not counted."""
    if not _enabled(ctx) or getattr(ctx.request, "scope", None) is None:
        return None
    s = _settings(ctx)
    _visitor, ip = _identity(ctx.request)
    return _store(s), f"bk:{ip}", int(cfg(s, "quota_byok_bad_key_per_ip_day")), _day()


def check_byok_probing(ctx) -> None:
    """Refuse a BYOK request from an IP that already had N byok_key_invalid refusals today: each
    bad-key attempt runs server-key side calls (retrieval, routing) from the BYOK pool."""
    c = _bad_key_counter(ctx)
    if c is None:
        return
    store, key, limit, day = c
    if store.count(key, day) >= limit:
        reset_at, reset_s = _reset_at()
        _refuse(429, "rate_limited", "API key 校验失败次数过多, 请明天再试。", reset_s,
                retry_after_s=reset_s)


def note_bad_key(ctx) -> None:
    c = _bad_key_counter(ctx)
    if c is not None:
        store, key, _limit, day = c
        store.take([(key, 2**62)], day)


# ── /api/flag (not a request_scope endpoint) ─────────────────────────────────

def admit_flag(request, nbytes: int) -> None:
    """Metered tiers: bound the dogfood log (507 storage_full) and each IP's daily flag bytes
    (429 rate_limited). Unmetered private: no-op."""
    from server import instance

    s = getattr(request.app.state, "settings", None)
    if not _on(s, instance.tier(request)):
        return
    path = s.dogfood_log_path
    size = path.stat().st_size if path.exists() else 0
    if size + nbytes > int(cfg(s, "flag_file_max_bytes")):
        raise ServiceRefusal(507, "storage_full", "反馈记录已满, 请联系站长。")
    _visitor, ip = _identity(request)
    if not _store(s).take([(f"fb:{ip}", int(cfg(s, "flag_bytes_per_ip_day")))], _day(), nbytes):
        reset_at, reset_s = _reset_at()
        _refuse(429, "rate_limited", "今日反馈已达上限, 请明天再来。", reset_s, retry_after_s=reset_s)
