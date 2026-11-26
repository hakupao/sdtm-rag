"""Outbound chokepoint — P2.0 seam (owned by P2.0; frozen v1).

Every server-side paid call (LLM completion / stream, embedding, Tavily) goes through here so that
`providers.resolve` (L1) decides target + kwargs and `quota.reserve/settle` (L2) meter it.
With the default hooks each function is exactly the call it replaced: same callable, same kwargs.

`ctx=None` means "use request_context.current()"; that is None outside a request (eval/scripts).
`purpose` is one of PURPOSES (docs/design/P2_request_context.md §1).
"""
from __future__ import annotations

from server import providers, quota
from server.request_context import RequestContext, ServiceRefusal, current

PURPOSES = ("answer", "continue", "regen", "route", "hyde", "multiquery", "embedding",
            "review", "compare", "judge", "web")


def _ctx(ctx: RequestContext | None) -> RequestContext | None:
    return ctx if ctx is not None else current()


def _settle(ctx, purpose, handle, resp):
    quota.settle(ctx, purpose, handle, getattr(resp, "usage", None), getattr(resp, "model", None))


def completion(ctx, purpose: str, llm_router, **kw):
    ctx = _ctx(ctx)
    fn, kw = providers.resolve(ctx, purpose, "completion", llm_router, kw)
    handle = quota.reserve(ctx, purpose, kw)
    resp = None
    try:
        resp = fn(**kw)
        return resp  # noqa: RET504 — finally reads resp
    finally:
        _settle(ctx, purpose, handle, resp)


async def acompletion(ctx, purpose: str, llm_router, **kw):
    """Non-streamed: settle on return. Streamed: the returned iterator settles with the last usage
    chunk and the last reported model it saw when it is exhausted / closed (None if never seen)."""
    ctx = _ctx(ctx)
    fn, kw = providers.resolve(ctx, purpose, "acompletion", llm_router, kw)
    handle = quota.reserve(ctx, purpose, kw)
    try:
        resp = await fn(**kw)
    except BaseException:
        _settle(ctx, purpose, handle, None)
        raise
    if not kw.get("stream"):
        _settle(ctx, purpose, handle, resp)
        return resp
    return _metered(ctx, purpose, handle, resp)


async def _metered(ctx, purpose, handle, stream):
    usage = model = None
    try:
        async for chunk in stream:
            usage = getattr(chunk, "usage", None) or usage
            model = getattr(chunk, "model", None) or model
            yield chunk
    finally:
        quota.settle(ctx, purpose, handle, usage, model)


def embedding(ctx, purpose: str, **kw):
    ctx = _ctx(ctx)
    fn, kw = providers.resolve(ctx, purpose, "embedding", None, kw)
    handle = quota.reserve(ctx, purpose, kw)
    resp = None
    try:
        resp = fn(**kw)
        return resp  # noqa: RET504 — finally reads resp
    finally:
        _settle(ctx, purpose, handle, resp)


def web_search(ctx, searcher, query: str):
    """Tavily via WebSearcher. A quota refusal becomes the existing per-search `quota_exceeded`
    status (the model is told and answers without it) instead of killing the stream."""
    ctx = _ctx(ctx)
    try:
        handle = quota.reserve(ctx, "web", {"query": query})
    except ServiceRefusal:
        return [], "quota_exceeded"
    st = "failed"
    try:
        refs, st = searcher.search(query)
        return refs, st
    finally:
        quota.settle(ctx, "web", handle, {"status": st}, "tavily")
