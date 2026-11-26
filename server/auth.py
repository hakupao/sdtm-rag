"""Phase 3 sharing — shared-password login gate + hardening (DEPLOY_PLAN §3).

Everything here is OFF unless explicitly enabled in settings, so importing/wiring it is a
no-op for the current localhost service. At go-live (after IT signoff) the service-dir
.env flips auth_enabled / rate_limit_enabled / sanitize_errors on together.

Design constraints:
- The chat UI streams via SSE (StreamingResponse). All custom middleware here is therefore
  PURE ASGI (operating on scope/receive/send), NOT BaseHTTPMiddleware — the latter buffers
  the response body and breaks streaming. Starlette's built-in SessionMiddleware is also
  pure ASGI, so the whole stack is streaming-safe.
- Plain HTTP over the LAN (no TLS, §1): the session cookie cannot be Secure (it would never
  be sent) — HttpOnly + SameSite=Lax only. The shared password and cookie travel in
  cleartext on the LAN; this is the accepted residual risk of the §1 "shared password"
  decision (mitigation path = VPN / TLS / Cloudflare Tunnel, §6 roadmap).
"""
from __future__ import annotations

import hashlib
import html
import ipaddress
import math
import os
import secrets
import time
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

log = structlog.get_logger()

# ── Password hashing (scrypt, stdlib — no new dependency) ───────────────────
# Single shared password, not a user table; scrypt with these fixed params is ample.
# Format stored in .env: "<salt_hex>$<hash_hex>". Changing params invalidates old hashes
# (just regenerate with scripts/gen_password_hash.py).
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "maxmem": 2**26, "dklen": 32}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verify against a "salt_hex$hash_hex" string. Any malformed stored
    value returns False (never raises)."""
    try:
        salt_hex, hash_hex = stored.split("$", 1)
        if not salt_hex or not hash_hex:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
        return secrets.compare_digest(dk, expected)
    except (ValueError, AttributeError):
        return False


# ── Helpers ─────────────────────────────────────────────────────────────────

def _client_ip(scope, trust_forwarded: bool) -> str:
    if trust_forwarded:
        for k, v in scope.get("headers", []):
            if k == b"x-forwarded-for":
                return v.decode("latin1").split(",")[0].strip() or "unknown"
    client = scope.get("client")
    return client[0] if client else "unknown"


def _trusted_nets(trusted: str) -> list:
    return [ipaddress.ip_network(p.strip(), strict=False)
            for p in (trusted or "").split(",") if p.strip()]


def resolve_client_ip(scope, trusted: str) -> str:
    """Socket peer, or `CF-Connecting-IP` ONLY when the peer is a configured trusted proxy (the
    Cloudflare tunnel connector). The header from any other peer is ignored (spoofable)."""
    client = scope.get("client")
    peer = client[0] if client else "unknown"
    nets = _trusted_nets(trusted)
    try:
        if not nets or not any(ipaddress.ip_address(peer) in n for n in nets):
            return peer
    except ValueError:
        return peer
    for k, v in scope.get("headers", []):
        if k == b"cf-connecting-ip":
            try:
                return str(ipaddress.ip_address(v.decode("latin1").strip()))
            except ValueError:
                return peer
    return peer


def _json_refusal(status: int, code: str, message: str, headers=None, **fields) -> JSONResponse:
    """Same body shape as request_context.ServiceRefusal (contract v1.1 §2.3)."""
    return JSONResponse({"detail": {"code": code, "message": message, **fields}},
                        status_code=status, headers=headers)


def _safe_next(raw: str | None) -> str:
    """Open-redirect guard: only allow a local absolute path. Reject scheme-relative
    (//host), backslash tricks (/\\host), and any control/whitespace char — browsers strip a
    leading TAB/LF/CR/space before parsing, so '/\\t//evil' or '/ //evil' would otherwise be
    read as scheme-relative -> external. Defense-in-depth even though Starlette percent-quotes
    the Location header; the function now does what its contract says regardless of downstream."""
    if not raw or not raw.startswith("/"):
        return "/"
    if raw.startswith("//") or raw.startswith("/\\"):
        return "/"
    if any(ch < " " or ch == "\x7f" for ch in raw):  # any control char (covers TAB/LF/CR)
        return "/"
    if len(raw) >= 2 and raw[1] == " ":  # leading space right after the first '/'
        return "/"
    return raw


# ── Security headers (pure ASGI; streaming-safe) ────────────────────────────
# Strict CSP: the chat UI loads only same-origin assets (vendored marked/dompurify/
# highlight + app.js) — no inline scripts, no external origins. 'unsafe-inline' is granted
# to styles only (highlight theme + the minimal inline login-page style). This is
# defense-in-depth atop DOMPurify (which already strips active content from model output).
_CSP = (
    "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; "
    "object-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'"
)


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app
        self._headers = [
            (b"content-security-policy", _CSP.encode("latin1")),
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
        ]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                present = {k.lower() for k, _ in headers}
                for k, v in self._headers:
                    if k not in present:
                        headers.append((k, v))
            await send(message)

        return await self.app(scope, receive, send_wrapper)


# ── Rate limiting (hand-rolled per-IP token bucket; pure ASGI) ──────────────

class TokenBucketLimiter:
    """In-memory per-key token bucket. Single-process / single-event-loop (§1): there is no
    await between read and write of a bucket, so the asyncio event loop serializes access —
    no lock needed. `allow` returns (ok, retry_after_seconds)."""

    def __init__(self, per_min: int, burst: int):
        self.rate = per_min / 60.0  # tokens per second
        self.burst = max(1, burst)
        self._buckets: dict[str, tuple[float, float]] = {}
        self._calls = 0

    def allow(self, key: str) -> tuple[bool, float]:
        now = time.monotonic()
        tokens, last = self._buckets.get(key, (float(self.burst), now))
        tokens = min(self.burst, tokens + (now - last) * self.rate)
        self._maybe_prune(now)
        if tokens >= 1.0:
            self._buckets[key] = (tokens - 1.0, now)
            return True, 0.0
        self._buckets[key] = (tokens, now)
        retry = (1.0 - tokens) / self.rate if self.rate > 0 else 60.0
        return False, retry

    def _maybe_prune(self, now: float) -> None:
        # Bound memory: every 1000 calls, drop buckets idle long enough to have refilled
        # fully (they're indistinguishable from a fresh key, so dropping them is lossless).
        self._calls += 1
        if self._calls % 1000:
            return
        idle = self.burst / self.rate if self.rate > 0 else 3600.0
        self._buckets = {
            k: (t, ts) for k, (t, ts) in self._buckets.items() if now - ts < idle
        }


class RateLimitMiddleware:
    # 静态壳子整体豁免: 前端拆成 ES 模块后, 冷加载一次 `/` 就是 ~16 个请求 (`/` + style.css
    # + app.js + 7 个 `/static/js/*.js` + vendor), 远超 BURST=10, 于是每次刷新都有几个模块
    # 随机吃 429, 页面起不来 —— 而这些是一次页面加载的固定开销, 不是攻击面。静态壳子按设计
    # 发 no-cache (必须回源校验), 缓存并不能把请求数压下去。真正要挡的 `/api/*` 一个不放。
    def __init__(self, app, *, limiter: TokenBucketLimiter, trust_forwarded: bool = False,
                 exempt: tuple[str, ...] = ("/api/health", "/"),
                 exempt_prefixes: tuple[str, ...] = ("/static/",)):
        self.app = app
        self.limiter = limiter
        self.trust_forwarded = trust_forwarded
        self.exempt = set(exempt)
        self.exempt_prefixes = tuple(exempt_prefixes)

    def _is_exempt(self, path: str) -> bool:
        return path in self.exempt or path.startswith(self.exempt_prefixes)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self._is_exempt(scope["path"]):
            return await self.app(scope, receive, send)
        ip = _client_ip(scope, self.trust_forwarded)
        ok, retry = self.limiter.allow(ip)
        if ok:
            return await self.app(scope, receive, send)
        resp = PlainTextResponse(
            "Too Many Requests", status_code=429,
            headers={"Retry-After": str(int(math.ceil(retry)))},
        )
        return await resp(scope, receive, send)


# ── Auth gate (pure ASGI; reads scope["session"] set by SessionMiddleware) ──

class AuthGateMiddleware:
    def __init__(self, app, *, exempt: tuple[str, ...] = ("/api/health", "/login", "/logout")):
        self.app = app
        self.exempt = set(exempt)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in self.exempt:
            return await self.app(scope, receive, send)
        session = scope.get("session") or {}
        if session.get("auth") is True:
            return await self.app(scope, receive, send)
        if scope["path"].startswith("/api/"):
            resp = JSONResponse({"detail": "authentication required"}, status_code=401)
        else:
            nxt = quote(scope["path"], safe="/")
            resp = RedirectResponse(url=f"/login?next={nxt}", status_code=302)
        return await resp(scope, receive, send)


# ── P2 L2 quota middleware (only installed when server.quota.app_enabled) ────

_VISITOR_SALT = "sdtm-rag.visitor.v1"


class VisitorMiddleware:
    """Signed visitor cookie (own secret, separate from the login SessionMiddleware) + client IP.
    Puts `sdtm_visitor` / `sdtm_client_ip` into scope state for server.quota; mints and sets the
    cookie when absent or tampered. Applies to /api/* only."""

    def __init__(self, app, *, secret: str, cookie_name: str, secure: bool, max_age: int,
                 trusted_proxies: str):
        from itsdangerous import Signer

        self.app = app
        self.signer = Signer(secret, salt=_VISITOR_SALT)
        self.cookie_name = cookie_name
        self.secure = secure
        self.max_age = max_age
        self.trusted = trusted_proxies

    def _read(self, scope) -> str | None:
        from itsdangerous import BadSignature
        from starlette.requests import cookie_parser

        for k, v in scope.get("headers", []):
            if k == b"cookie":
                raw = cookie_parser(v.decode("latin1")).get(self.cookie_name)
                if raw:
                    try:
                        return self.signer.unsign(raw).decode("ascii")
                    except (BadSignature, UnicodeDecodeError):
                        return None
        return None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        vid = self._read(scope)
        fresh = vid is None
        if fresh:
            vid = secrets.token_urlsafe(16)
        state = scope.setdefault("state", {})
        state["sdtm_visitor"] = vid
        state["sdtm_client_ip"] = resolve_client_ip(scope, self.trusted)
        if not fresh:
            return await self.app(scope, receive, send)
        cookie = (f"{self.cookie_name}={self.signer.sign(vid).decode('ascii')}; Path=/; "
                  f"Max-Age={self.max_age}; HttpOnly; SameSite=Lax"
                  + ("; Secure" if self.secure else ""))

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"set-cookie", cookie.encode("latin1")))
            await send(message)

        return await self.app(scope, receive, send_wrapper)


class BodyLimitMiddleware:
    """Reject request bodies over `limit` bytes with 413 `request_too_large` (contract §2.3), by
    Content-Length up front and by counting chunked bodies. The body (bounded by the limit) is
    buffered and replayed; later receive() calls go to the server (disconnect detection)."""

    def __init__(self, app, *, limit: int,
                 exempt: tuple[str, ...] = ("/api/validate", "/api/validate-study")):
        self.app = app
        self.limit = limit
        self.exempt = set(exempt)

    def _too_large(self):
        return _json_refusal(413, "request_too_large", "请求体过大。", limit=self.limit)

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH")
                or not scope["path"].startswith("/api/") or scope["path"] in self.exempt):
            return await self.app(scope, receive, send)
        for k, v in scope.get("headers", []):
            if k == b"content-length":
                try:
                    declared = int(v)
                except ValueError:
                    declared = self.limit + 1
                if declared > self.limit:
                    return await self._too_large()(scope, receive, send)
        chunks, total = [], 0
        while True:
            msg = await receive()
            if msg["type"] != "http.request":   # client went away before the body arrived
                return await self.app(scope, _replay([msg], receive), send)
            body = msg.get("body", b"")
            total += len(body)
            if total > self.limit:
                return await self._too_large()(scope, receive, send)
            chunks.append(body)
            if not msg.get("more_body", False):
                break
        return await self.app(scope, _replay(
            [{"type": "http.request", "body": b"".join(chunks), "more_body": False}], receive), send)


def _replay(messages: list, receive):
    pending = list(messages)

    async def wrapped():
        if pending:
            return pending.pop(0)
        return await receive()
    return wrapped


class FlagRateLimitMiddleware:
    """Per-client-IP token bucket on POST /api/flag (contract §2.7: flag is open on both tiers).
    Event-loop only (no await between bucket read/write), like RateLimitMiddleware."""

    def __init__(self, app, *, limiter: TokenBucketLimiter, trusted_proxies: str,
                 path: str = "/api/flag"):
        self.app = app
        self.limiter = limiter
        self.trusted = trusted_proxies
        self.path = path

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != self.path or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        ok, retry = self.limiter.allow(resolve_client_ip(scope, self.trusted))
        if ok:
            return await self.app(scope, receive, send)
        r = max(1, int(math.ceil(retry)))
        resp = _json_refusal(429, "rate_limited", "操作太频繁, 请稍后再试。",
                             headers={"Retry-After": str(r)}, retry_after_s=r)
        return await resp(scope, receive, send)


def _install_quota(app, settings) -> None:
    from server import quota

    if not quota.app_enabled(settings):
        return
    secret = quota.cfg(settings, "visitor_secret")
    if not secret:
        raise RuntimeError("quota enabled (public tier or SDTM_RAG_QUOTA_ENABLED) requires "
                           "SDTM_RAG_VISITOR_SECRET (fail-loud, no unsigned visitor ids).")
    trusted = quota.cfg(settings, "quota_trusted_proxies")
    _trusted_nets(trusted)   # malformed CIDR => fail at startup, not per request
    secure = quota.cfg(settings, "visitor_cookie_secure")
    if secure is None:
        secure = getattr(settings, "instance", "private") == "public"
    app.add_middleware(FlagRateLimitMiddleware, trusted_proxies=trusted, limiter=TokenBucketLimiter(
        int(quota.cfg(settings, "flag_rate_per_min")), int(quota.cfg(settings, "flag_rate_burst"))))
    app.add_middleware(VisitorMiddleware, secret=secret,
                       cookie_name=quota.cfg(settings, "visitor_cookie_name"), secure=bool(secure),
                       max_age=int(quota.cfg(settings, "visitor_cookie_max_age_s")),
                       trusted_proxies=trusted)
    app.add_middleware(BodyLimitMiddleware, limit=int(quota.cfg(settings, "quota_max_body_bytes")))


# ── Login brute-force throttle (failure-based, per-IP) ──────────────────────

class LoginThrottle:
    """Per-IP lockout that counts only FAILED logins, independent of the general request
    rate limit. Legitimate users (correct password) are never penalized; after `max_fails`
    consecutive failures an IP is locked out with exponential backoff. This protects the
    single shared secret (the whole security boundary) against online guessing far more
    tightly than the generous 30/min request limit would. Same single-event-loop, no-lock
    model as TokenBucketLimiter."""

    def __init__(self, max_fails: int = 5, base_lockout_s: float = 30.0,
                 max_lockout_s: float = 3600.0):
        self.max_fails = max_fails
        self.base = base_lockout_s
        self.cap = max_lockout_s
        self._state: dict[str, tuple[int, float]] = {}  # ip -> (consecutive_fails, locked_until)
        self._calls = 0

    def check(self, key: str) -> tuple[bool, float]:
        _, until = self._state.get(key, (0, 0.0))
        now = time.monotonic()
        return (False, until - now) if until > now else (True, 0.0)

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        fails = self._state.get(key, (0, 0.0))[0] + 1
        until = now + min(self.cap, self.base * (2 ** (fails - self.max_fails))) \
            if fails >= self.max_fails else 0.0
        self._state[key] = (fails, until)
        self._maybe_prune(now)

    def record_success(self, key: str) -> None:
        self._state.pop(key, None)

    def _maybe_prune(self, now: float) -> None:
        # Bound memory: every 1000 calls drop entries not currently locked (an unlocked
        # entry is equivalent to a fresh key — dropping it just resets a benign counter).
        self._calls += 1
        if self._calls % 1000:
            return
        self._state = {k: v for k, v in self._state.items() if v[1] > now}


# ── Login routes ────────────────────────────────────────────────────────────

_LOGIN_PAGE = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SDTM 知识库助手 · 登录</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", sans-serif; background: #f7f7f8;
         display: flex; min-height: 100vh; margin: 0; align-items: center; justify-content: center; }}
  form {{ background: #fff; padding: 32px; border-radius: 12px; border: 1px solid #e5e5e5;
          width: 320px; display: flex; flex-direction: column; gap: 14px; }}
  h1 {{ font-size: 17px; margin: 0 0 4px; color: #333; }}
  input {{ padding: 12px; border: 1px solid #d0d0d0; border-radius: 8px; font-size: 15px; }}
  button {{ padding: 12px; border: none; border-radius: 8px; background: #19c37d; color: #fff;
            font-size: 15px; cursor: pointer; }}
  .err {{ color: #c00; font-size: 13px; margin: 0; }}
</style></head><body>
<form method="post" action="/login?next={next_attr}">
  <h1>SDTM 知识库助手</h1>
  {error_block}
  <input type="password" name="password" placeholder="访问口令" autofocus required>
  <button type="submit">登录</button>
</form></body></html>"""


def _render_login(next_raw: str | None, error: bool = False) -> HTMLResponse:
    next_attr = html.escape(_safe_next(next_raw), quote=True)
    error_block = '<p class="err">口令错误，请重试。</p>' if error else ""
    page = _LOGIN_PAGE.format(next_attr=next_attr, error_block=error_block)
    status = 401 if error else 200
    return HTMLResponse(page, status_code=status)


def build_auth_router(settings) -> APIRouter:
    router = APIRouter()
    throttle = LoginThrottle()

    @router.get("/login")
    def login_form(request: Request):
        if request.session.get("auth") is True:
            return RedirectResponse(_safe_next(request.query_params.get("next")), status_code=302)
        return _render_login(request.query_params.get("next"))

    @router.post("/login")
    def login_submit(request: Request, password: str = Form(...)):
        ip = request.client.host if request.client else "unknown"
        ok, retry = throttle.check(ip)
        if not ok:  # locked out after repeated failures (brute-force guard)
            log.warning("login_throttled", ip=ip, retry_s=round(retry))
            return PlainTextResponse(
                "Too many failed attempts. Try again later.", status_code=429,
                headers={"Retry-After": str(int(math.ceil(retry)))},
            )
        if verify_password(password, settings.shared_password_hash):
            throttle.record_success(ip)
            request.session["auth"] = True
            log.info("login_ok", ip=ip)
            return RedirectResponse(_safe_next(request.query_params.get("next")), status_code=303)
        throttle.record_failure(ip)
        log.warning("login_failed", ip=ip)
        return _render_login(request.query_params.get("next"), error=True)

    @router.post("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    return router


# ── Wiring ───────────────────────────────────────────────────────────────────

def install_security(app, settings) -> None:
    """Attach the phase-3 middleware stack to `app` per settings. Middleware added LAST is
    OUTERMOST, so adding in the order below yields the inbound call order:
        SecurityHeaders -> RateLimit -> [BodyLimit -> Visitor -> FlagRateLimit] -> Session -> AuthGate -> route
    (headers wrap every response incl. 429/401/302; rate-limit throttles before auth so
    login brute-force is capped; session is loaded before the gate reads it)."""
    if settings.auth_enabled:
        if not settings.session_secret or not settings.shared_password_hash:
            raise RuntimeError(
                "auth_enabled=True requires SDTM_RAG_SESSION_SECRET and "
                "SDTM_RAG_SHARED_PASSWORD_HASH to be set (fail-loud, no silent allow-all)."
            )
        app.include_router(build_auth_router(settings))
        app.add_middleware(AuthGateMiddleware)
        app.add_middleware(
            SessionMiddleware,
            secret_key=settings.session_secret,
            session_cookie=settings.session_cookie_name,
            max_age=settings.session_max_age_s,
            same_site="lax",
            https_only=False,  # plain HTTP over LAN (§1); cannot require Secure
        )

    # P2 L2 (public tier / quota_enabled only): BodyLimit -> Visitor -> FlagRateLimit, inside
    # RateLimit and outside Session/AuthGate.
    _install_quota(app, settings)

    if settings.rate_limit_enabled:
        limiter = TokenBucketLimiter(settings.rate_limit_per_min, settings.rate_limit_burst)
        app.add_middleware(
            RateLimitMiddleware,
            limiter=limiter,
            trust_forwarded=settings.rate_limit_trust_forwarded,
        )

    if settings.security_headers_enabled:
        app.add_middleware(SecurityHeadersMiddleware)


# ── Compare error sanitizer (SEC MED, deferred from phase 2) ────────────────

def sanitize_compare_errors(answers, enabled: bool):
    """When sharing (enabled), collapse each per-model error to a generic client-facing
    string — the full upstream text (e.g. 'credit balance too low') already went to the
    server log in compare._one_completion. No-op (returns as-is) on localhost dev so the
    operator keeps the useful diagnostic detail."""
    if not enabled:
        return answers
    for a in answers:
        if a.error:
            a.error = "Model temporarily unavailable."
    return answers
