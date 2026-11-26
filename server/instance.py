"""Instance tier — owned by L3 (P2 steps 2.1 / 2.3; contract docs/design/P2_request_context.md §2.3/2.6/2.7).

`SDTM_RAG_INSTANCE=private` (default) = pre-P2 behaviour, every hook here is a pass-through.
`public` = the open site: no study data / channels, internal endpoints not registered (main.create_app),
server-key model whitelist = the configured public `selectable_models` ids, trimmed /api/info.
"""
from __future__ import annotations

from server.llm_config import INTERNAL_GROUPS

# §2.7: the only /api routes registered on public. Allowlist ⇒ a new endpoint is closed until added here.
PUBLIC_API_PATHS = frozenset({"/api/health", "/api/info", "/api/ask", "/api/ask_stream", "/api/flag"})

# §2.6: /api/info keys kept on public; every other InfoResponse field is internal and dropped.
PUBLIC_INFO_KEYS = ("top_k", "web_search", "selectable_models", "index_fresh")

# request_scope endpoints that public never registers; refused here too (defence in depth).
_PRIVATE_ONLY_ENDPOINTS = frozenset({"ask_compare", "validate"})


def tier(request) -> str:
    """"private" | "public" (settings.instance on app.state)."""
    s = getattr(request.app.state, "settings", None)
    return getattr(s, "instance", "private")


def check_startup(s) -> None:
    """Refuse to build a public app that could serve study data or an unmetered outbound path.
    RuntimeError (fail-loud, same discipline as maybe_build_dossier). Private: no-op."""
    if s.instance != "public":
        return
    from server.config import PUBLIC_FORCED_OFF

    problems = [f"{name}=true" for name in PUBLIC_FORCED_OFF if getattr(s, name)]
    if s.pdf_context_enabled:
        problems.append("pdf_context_enabled=true (study PDF channel)")
    if s.rerank_enabled:
        # Cohere rerank does not go through the outbound seam (design §1 open item) ⇒ unmetered.
        problems.append("rerank_enabled=true (Cohere rerank bypasses the quota seam)")
    study_paths = [s.data_dir / "study", s.study_kb_root, s.study_catalog_path, s.study_aliases_path,
                   s.dossier_docs_dir, s.dossier_cards_dir]
    present = sorted({str(p) for p in study_paths if p.exists()})
    if present:
        problems.append(f"study data present: {present}")
    data = s.data_dir.resolve()
    log_path = s.dogfood_log_path.resolve()
    if not log_path.is_relative_to(data):
        problems.append(f"dogfood log {log_path} is not under data dir {data}")
    if problems:
        raise RuntimeError("SDTM_RAG_INSTANCE=public refuses to start: " + "; ".join(problems))


def _refuse(status: int, code: str, message: str, **fields):
    from server.request_context import ServiceRefusal

    raise ServiceRefusal(status, code, message, **fields)


def public_model_ids(s) -> list[str]:
    return sorted(m.id for m in s.selectable_models if m.id not in INTERNAL_GROUPS)


def check_request(ctx, body) -> None:
    """Public: refuse what this tier must not serve (ServiceRefusal, §2.3). Private / no ctx: allow."""
    if ctx is None or ctx.tier != "public":
        return
    from server.providers import BYOK_BASE_HEADER

    if ctx.endpoint in _PRIVATE_ONLY_ENDPOINTS:
        _refuse(403, "not_on_this_tier", "该功能在公开站未开放。", feature=ctx.endpoint)
    if getattr(body, "dossier", None) == "on":
        _refuse(403, "not_on_this_tier", "研读包在公开站不可用。", feature="dossier")
    if getattr(body, "corpus", None) in ("study", "both"):
        _refuse(403, "not_on_this_tier", "研究资料库在公开站不可用。", feature="study_corpus")
    request = ctx.request
    if request.headers.get(BYOK_BASE_HEADER) is not None:
        _refuse(400, "custom_base_not_allowed", "公开站不支持自定义 API 地址。")
    model = ctx.model
    if model is None:
        return
    allowed = public_model_ids(request.app.state.settings)
    # Internal groups are never selectable on public. Server-key requests (provider None) must name a
    # public selectable id; BYOK model ids belong to the provider registry (L1 check_model).
    if model in INTERNAL_GROUPS or (ctx.provider is None and model not in allowed):
        _refuse(422, "model_not_allowed", "该模型在公开站不可用。", allowed=allowed)


def shape_info(request, payload, extra: dict):
    """Final /api/info response. Private: unchanged when there is nothing extra (byte-identical), else
    the payload's JSON with the extra keys merged in. Public: allowlisted keys + `tier` + extras."""
    public = tier(request) == "public"
    if not extra and not public:
        return payload
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse

    body = jsonable_encoder(payload)
    if public:
        body = {k: body[k] for k in PUBLIC_INFO_KEYS if k in body} | {"tier": "public"}
    return JSONResponse({**body, **extra})
