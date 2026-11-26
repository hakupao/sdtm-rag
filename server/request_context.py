"""Per-request context — P2.0 seam (owned by P2.0; frozen v1, see docs/design/P2_request_context.md).

One `RequestContext` per API request, built once by `request_scope` before the endpoint body runs.
router.py passes it explicitly; code that has no request parameter (rag.py embedding / HyDE,
federation.py routing, reviewer.py, compare.py) reaches it through `current()`. Outside a request
(eval/, scripts/, tests that build engines directly) `current()` is None and every hook must pass
the call through unchanged.

Lines extend behaviour only through the hook modules (instance.py L3, providers.py L1, quota.py L2),
never by editing this file.
"""
from __future__ import annotations

import asyncio
import functools
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException


@dataclass(repr=False)
class Credentials:
    """BYOK credentials from request headers. Never logged; repr/str are masked."""

    api_key: str
    api_base: str | None = None

    def __repr__(self) -> str:
        return f"Credentials(api_key=***, api_base={'set' if self.api_base else None})"

    __str__ = __repr__


@dataclass(repr=False)
class RequestContext:
    # ⛔ Never serialise a ctx (dataclasses.asdict / vars / json / log kwargs): repr is masked,
    # but the fields are not — `credentials.api_key` and `request` (headers) would leak.
    endpoint: str                      # "ask" | "ask_stream" | "ask_compare" | "validate"
    request: Any = None                # the Starlette Request (cookies, CF-Connecting-IP, app.state.settings)
    tier: str = "private"              # instance.tier(); L3
    model: str | None = None           # requested model id / group (body.model)
    provider: str | None = None        # requested provider id (body.provider); L1
    credentials: Credentials | None = None   # BYOK; L1 (providers.credentials_from)
    quota: Any = None                  # reservation handle owned by L2 (quota.admit)
    flags: dict = field(default_factory=dict)   # capability flags (L1 may fill)
    notes: list[dict] = field(default_factory=list)  # downgrade notes -> sources/done `downgrades`

    def __repr__(self) -> str:
        return (f"RequestContext(endpoint={self.endpoint!r}, tier={self.tier!r}, "
                f"model={self.model!r}, provider={self.provider!r}, "
                f"byok={self.credentials is not None}, notes={len(self.notes)})")

    __str__ = __repr__


class ServiceRefusal(HTTPException):
    """Typed refusal from a hook (quota exhausted, bad BYOK key, endpoint closed on this tier...).

    It is an HTTPException, so raised before a stream opens FastAPI renders it as
    `{"detail": {"code", "message", ...}}` with `status_code`. Every blanket `except Exception`
    on the request path re-raises it first; after the SSE stream has opened router.py turns it
    into an `error` event carrying the same `detail` fields.
    """

    def __init__(self, status_code: int, code: str, message: str, *,
                 headers: dict[str, str] | None = None, **fields: Any):
        super().__init__(status_code=status_code,
                         detail={"code": code, "message": message, **fields}, headers=headers)


_CURRENT: ContextVar[RequestContext | None] = ContextVar("sdtm_rag_request_context", default=None)


def current() -> RequestContext | None:
    return _CURRENT.get()


def begin(request, body, endpoint: str) -> RequestContext:
    from server import instance, providers

    ctx = RequestContext(
        endpoint=endpoint,
        request=request,
        tier=instance.tier(request),
        model=getattr(body, "model", None),
        provider=getattr(body, "provider", None),
        credentials=providers.credentials_from(request),
    )
    _CURRENT.set(ctx)
    return ctx


def request_scope(endpoint: str, *, streaming: bool = False):
    """Endpoint decorator: build + bind the context, and run `quota.finalize(ctx)` exactly once.

    Non-streaming: finalize when the endpoint returns or raises. Streaming: finalize here only if
    the endpoint raises before returning its StreamingResponse; otherwise the stream wrapper
    (`finalizing`) does it when the stream ends, errors or the client goes away.
    """

    def deco(fn):
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def aw(*args, **kwargs):
                from server import quota

                ctx = begin(kwargs["request"], kwargs.get("body"), endpoint)
                try:
                    out = await fn(*args, **kwargs)
                except BaseException:
                    quota.finalize(ctx)
                    raise
                if not streaming:
                    quota.finalize(ctx)
                return out
            return aw

        @functools.wraps(fn)
        def sw(*args, **kwargs):
            from server import quota

            ctx = begin(kwargs["request"], kwargs.get("body"), endpoint)
            try:
                return fn(*args, **kwargs)
            finally:
                quota.finalize(ctx)
        return sw

    return deco


async def finalizing(agen, ctx: RequestContext):
    """Wrap an SSE async generator so `quota.finalize(ctx)` runs on normal end, error, or client
    disconnect (GeneratorExit / CancelledError, which no `except Exception` sees).

    Order guarantee (v1.1): the inner generator is closed FIRST — that closes the open
    `outbound._metered` stream (router wraps it in `aclosing`) so its `quota.settle` lands —
    and only then `finalize`. Shielded so a cancelled task can still finish the close.
    ⚠ Starlette does not aclose `body_iterator` on disconnect: this finally runs when the
    response's iterator is closed / garbage-collected (prompt under CPython refcounting)."""
    import anyio

    from server import quota

    try:
        async for item in agen:
            yield item
    finally:
        with anyio.CancelScope(shield=True):
            try:
                await agen.aclose()
            finally:
                quota.finalize(ctx)
