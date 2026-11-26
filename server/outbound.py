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


async def acompletion(ctx, purpose: str, llm_router, *, refund_open_error: bool = False, **kw):
    """Non-streamed: settle on return. Streamed: the returned iterator settles with the last usage
    chunk and the last reported model it saw when it is exhausted / closed (None if never seen),
    plus the text it streamed (quota.settle prices a usage-less stream by that, not max_tokens).
    A stream whose open fails is charged its prompt only — or nothing with refund_open_error=True
    (router's narrow stream_options retry: the immediate re-open is the one that counts)."""
    ctx = _ctx(ctx)
    fn, kw = providers.resolve(ctx, purpose, "acompletion", llm_router, kw)
    handle = quota.reserve(ctx, purpose, kw)
    try:
        resp = await fn(**kw)
    except Exception:
        if refund_open_error:
            quota.settle(ctx, purpose, handle, {"prompt_tokens": 0, "completion_tokens": 0}, None)
        else:
            quota.settle(ctx, purpose, handle, None, None,
                         streamed_text="" if kw.get("stream") else None)
        raise
    except BaseException:   # cancelled (timeout / disconnect) while opening
        quota.settle(ctx, purpose, handle, None, None,
                     streamed_text="" if kw.get("stream") else None)
        raise
    if not kw.get("stream"):
        _settle(ctx, purpose, handle, resp)
        return resp
    return _metered(ctx, purpose, handle, resp)


def _streamed_text(chunk, out: list) -> None:
    """Everything the provider generated in this chunk: content, reasoning and tool-call args."""
    for ch in getattr(chunk, "choices", None) or []:
        d = getattr(ch, "delta", None)
        if d is None:
            continue
        for attr in ("content", "reasoning_content"):
            t = getattr(d, attr, None)
            if isinstance(t, str) and t:
                out.append(t)
        for tc in getattr(d, "tool_calls", None) or []:
            fn = getattr(tc, "function", None)
            for attr in ("name", "arguments"):
                t = getattr(fn, attr, None)
                if isinstance(t, str) and t:
                    out.append(t)


async def _metered(ctx, purpose, handle, stream):
    usage = model = None
    streamed: list[str] = []
    try:
        async for chunk in stream:
            usage = getattr(chunk, "usage", None) or usage
            model = getattr(chunk, "model", None) or model
            _streamed_text(chunk, streamed)
            yield chunk
    finally:
        quota.settle(ctx, purpose, handle, usage, model, streamed_text="".join(streamed))
        close = getattr(stream, "aclose", None)   # release the provider stream too, if closable
        if close is not None:
            await close()


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
