"""Instance tier hooks — owned by L3 (P2 steps 2.1 / 2.3).

P2.0 ships no-op defaults (private behaviour). Route registration / startup refusal per tier
lives in main.py + config.py (also L3); these are the request-time hooks router.py calls.
"""
from __future__ import annotations


def tier(request) -> str:
    """"private" | "public". Default reads `settings.instance` if L3 adds that field."""
    s = getattr(request.app.state, "settings", None)
    return getattr(s, "instance", "private")


def check_request(ctx, body) -> None:
    """Reject a request this tier must not serve (e.g. dossier="on" or an internal model group on
    public) by raising request_context.ServiceRefusal. Default: allow everything."""
    pass


def shape_info(request, payload, extra: dict):
    """Final /api/info response. `payload` is the InfoResponse; `extra` = providers.info_fields |
    quota.info_fields. Default: unchanged when there is nothing extra (byte-identical), else the
    payload's JSON with the extra keys merged in."""
    if not extra:
        return payload
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse

    return JSONResponse({**jsonable_encoder(payload), **extra})
