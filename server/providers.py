"""Provider / model / BYOK hooks — owned by L1 (P2 steps 2.4 / 2.5 / 2.6).

P2.0 ships no-op defaults that reproduce pre-P2 behaviour exactly. L1 replaces the bodies; the
signatures are the frozen v1 seam (docs/design/P2_request_context.md §2-3). router.py / rag.py
call only these functions, so L1 never needs to edit them.

Probe facts L1 must design around (.work/10_split_and_public/evidence/checkpoints/p2_byok_spike.md):
per-call api_key/api_base override Router deployments, BUT a per-call api_key is carried into
Router `fallbacks` (a BYOK key for provider A is sent to the fallback provider B) — BYOK calls
must not go through a Router group that has fallbacks.
"""
from __future__ import annotations

from fastapi import HTTPException

# Frozen v1 header names (contract §2.1). Read only here; never logged.
BYOK_KEY_HEADER = "X-LLM-Api-Key"
BYOK_BASE_HEADER = "X-LLM-Api-Base"


def credentials_from(request):
    """-> request_context.Credentials | None. Default: BYOK not supported yet (headers ignored)."""
    return None  # noqa: RET501 — L1 returns Credentials here


def check_model(ctx, s) -> None:
    """Validate ctx.model before any work. Default = the pre-P2 whitelist (422, same detail)."""
    from server.llm_config import known_model_groups

    known = known_model_groups(s)
    if ctx.model not in known:
        # ⛔ 不静默退回 default: 静默退回会让"选了模型 X 却拿到 Y 的答案"完全不可见。
        raise HTTPException(status_code=422,
                            detail=f"unknown model {ctx.model!r}; known: {sorted(known)}")


def resolve(ctx, purpose: str, kind: str, llm_router, kw: dict):
    """-> (callable, kwargs) for one outbound call. kind in {"completion", "acompletion",
    "embedding"}. Default: the Router method when a router is given, else the litellm module
    function (looked up at call time), kwargs untouched — not even api_key=None is added."""
    if llm_router is not None:
        return getattr(llm_router, kind), kw
    import litellm

    return getattr(litellm, kind), kw


def capability(ctx, name: str, default):
    """Capability gate. name in {"web_tools", "vision", "dossier_auto"}; returns the value to use.
    Default: `default` (the pre-P2 decision). L1 returns False + appends to ctx.notes to downgrade."""
    return default


def log_processors() -> list:
    """structlog processors inserted before the renderer (main.py). L1 puts key redaction here.
    Acceptance (contract §3): a test must render a real log line (incl. an exc_info traceback
    from a frame holding the key) through main.py's configured chain and grep it. Default: none."""
    return []


def info_fields(request) -> dict:
    """Extra /api/info keys (contract §2.6, e.g. `providers`). Default: none."""
    return {}
