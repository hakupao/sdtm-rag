"""Quota / cost-cap hooks — owned by L2 (P2 steps 2.2 / 2.7).

P2.0 ships no-op defaults. Lifecycle per request (contract §2.4):
  admit(ctx)                      once, after validation, before retrieval; raise ServiceRefusal(429) to refuse
  reserve(ctx, purpose, kw)       before EVERY outbound call (outbound.py); may raise ServiceRefusal
  settle(ctx, purpose, usage)     after every call; usage may be None (failed / aborted / not reported)
                                  and, per the probe, may be litellm-ESTIMATED on an upstream-cut stream
  finalize(ctx)                   exactly once at request end (normal, error, client disconnect);
                                  charge whatever was reserved but never settled
ctx is None outside a request (eval/scripts) ⇒ every hook must be a pass-through for None.
"""
from __future__ import annotations


def admit(ctx) -> None:
    pass


def reserve(ctx, purpose: str, kw: dict) -> None:
    pass


def settle(ctx, purpose: str, usage) -> None:
    pass


def finalize(ctx) -> None:
    pass


def response_fields(ctx) -> dict:
    """Extra keys for AskResponse / SSE `done` (e.g. {"quota": {...}}). Default: none."""
    return {}


def info_fields(request) -> dict:
    """Extra /api/info keys (e.g. `quota`). Default: none."""
    return {}
