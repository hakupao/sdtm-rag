"""Quota / cost-cap hooks — owned by L2 (P2 steps 2.2 / 2.7).

P2.0 ships no-op defaults. Lifecycle per request (design doc §3):
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
"""
from __future__ import annotations


def admit(ctx, body) -> None:
    pass


def reserve(ctx, purpose: str, kw: dict):
    return None  # noqa: RET501 — L2 returns its reservation handle here


def settle(ctx, purpose: str, handle, usage, model) -> None:
    pass


def finalize(ctx) -> None:
    pass


def response_fields(ctx) -> dict:
    """Extra keys for AskResponse / SSE `done` (e.g. {"quota": {...}}). Default: none."""
    return {}


def info_fields(request) -> dict:
    """Extra /api/info keys (e.g. `quota`). Default: none."""
    return {}
