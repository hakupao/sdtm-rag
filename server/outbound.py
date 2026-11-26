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


def completion(ctx, purpose: str, llm_router, **kw):
    ctx = _ctx(ctx)
    fn, kw = providers.resolve(ctx, purpose, "completion", llm_router, kw)
    quota.reserve(ctx, purpose, kw)
    resp = None
    try:
        resp = fn(**kw)
        return resp  # noqa: RET504 — finally reads resp
    finally:
        quota.settle(ctx, purpose, getattr(resp, "usage", None))


async def acompletion(ctx, purpose: str, llm_router, **kw):
    """Non-streamed: settle on return. Streamed: the returned iterator settles with the last usage
    chunk it saw when it is exhausted / closed (usage None if it never arrived)."""
    ctx = _ctx(ctx)
    fn, kw = providers.resolve(ctx, purpose, "acompletion", llm_router, kw)
    quota.reserve(ctx, purpose, kw)
    try:
        resp = await fn(**kw)
    except BaseException:
        quota.settle(ctx, purpose, None)
        raise
    if not kw.get("stream"):
        quota.settle(ctx, purpose, getattr(resp, "usage", None))
        return resp
    return _metered(ctx, purpose, resp)


async def _metered(ctx, purpose, stream):
    usage = None
    try:
        async for chunk in stream:
            u = getattr(chunk, "usage", None)
            if u:
                usage = u
            yield chunk
    finally:
        quota.settle(ctx, purpose, usage)


def embedding(ctx, purpose: str, **kw):
    ctx = _ctx(ctx)
    fn, kw = providers.resolve(ctx, purpose, "embedding", None, kw)
    quota.reserve(ctx, purpose, kw)
    resp = None
    try:
        resp = fn(**kw)
        return resp  # noqa: RET504 — finally reads resp
    finally:
        quota.settle(ctx, purpose, getattr(resp, "usage", None))


def web_search(ctx, searcher, query: str):
    """Tavily via WebSearcher. A quota refusal becomes the existing per-search `quota_exceeded`
    status (the model is told and answers without it) instead of killing the stream."""
    ctx = _ctx(ctx)
    try:
        quota.reserve(ctx, "web", {"query": query})
    except ServiceRefusal:
        return [], "quota_exceeded"
    st = "failed"
    try:
        refs, st = searcher.search(query)
        return refs, st
    finally:
        quota.settle(ctx, "web", {"status": st})
