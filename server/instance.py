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
# Per selectable_models entry on public (drops the litellm `model` string; webchat reads id/label/verified).
PUBLIC_MODEL_KEYS = ("id", "label", "verified", "max_output_tokens")

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
    if s.auth_enabled:
        # Public visitors are anonymous (L2 signed cookie); the login gate would add a /login brute-force
        # surface and a second session cookie.
        problems.append("auth_enabled=true (login gate is private-only)")
    if _is_study_collection(s, s.collection_name):
        problems.append(f"collection_name={s.collection_name!r} is a study collection")
    if s.rerank_enabled:
        # Cohere rerank does not go through the outbound seam (design §1 open item) ⇒ unmetered.
        problems.append("rerank_enabled=true (Cohere rerank bypasses the quota seam)")
    study_paths = [s.data_dir / "study", s.study_kb_root, s.study_catalog_path, s.study_aliases_path,
                   s.dossier_docs_dir, s.dossier_cards_dir]
    present = sorted({str(p) for p in study_paths if p.exists()})
    if present:
        problems.append(f"study data present: {present}")
    problems += _public_cost_problems(s)
    data = s.data_dir.resolve()
    log_path = s.dogfood_log_path.resolve()
    if not log_path.is_relative_to(data):
        problems.append(f"dogfood log {log_path} is not under data dir {data}")
    if problems:
        raise RuntimeError("SDTM_RAG_INSTANCE=public refuses to start: " + "; ".join(problems))


_NO_PINNED_PRICE = ("no pinned price — add the provider's official price to _PRICES in server/cost.py "
                    "(and to _LONG_PROMPT_PRICES when it is priced by prompt length); public does not "
                    "price a server-key model from litellm's price map or from the fallback rate")


def _public_cost_problems(s) -> list[str]:
    """P2.9 (SR9/CR7): the free pool must bound EVERY public model's single answer round — the
    built-in selectable list is the private Claude set at 128K output (one round ≈ $3+).

    Every model the server key can pay for must have a PINNED price (cost._PRICES): the selectable
    models, the four internal Router groups and the embedding model. Without one the meter would
    charge litellm's online price (absent without network) or the fallback rate, neither a checked
    number. The other server-side model settings (expansion / judge / compare / rerank) are not
    checked: nothing on the public tier calls them (checkpoint public_price_pin_ext.md).

    The round bound covers what one answer round can reach: the selectable model and the group the
    Router falls back to, each with its own max_tokens (quota.round_estimates — the same candidates
    reserve books). The other internal groups never answer on public (check_request refuses them)."""
    from server import quota
    from server.cost import pinned_rates
    from server.llm_config import _INTERNAL_GROUP_MODEL_FIELDS

    out = []
    if "selectable_models" not in s.model_fields_set:
        out.append("SDTM_RAG_SELECTABLE_MODELS not set (public must list its free models explicitly)")
    for field in (*_INTERNAL_GROUP_MODEL_FIELDS.values(), "embedding_model"):
        model = getattr(s, field)
        if pinned_rates(model, None) is None:
            out.append(f"{field} (SDTM_RAG_{field.upper()}) = {model!r}: {_NO_PINNED_PRICE}")
    budget = quota._pool_caps(s)["free"] / 10
    answering = [m for m in s.selectable_models if m.id not in INTERNAL_GROUPS]
    if len(answering) != len(s.selectable_models):
        # create_router refuses such ids too (they would merge into the internal group); say it here,
        # where the other problems are listed, and do not estimate through a Router that cannot exist
        clash = sorted(m.id for m in s.selectable_models if m.id in INTERNAL_GROUPS)
        out.append(f"selectable model ids {clash} collide with the Router's internal groups")
        answering = []
    for m in answering:
        if "max_output_tokens" not in m.model_fields_set:
            out.append(f"selectable model {m.id!r} has no explicit max_output_tokens")
        rounds = quota.round_estimates(s, m.id)
        if pinned_rates(rounds[0][1], None) is None:
            out.append(f"selectable model {m.id!r} ({rounds[0][1]}): {_NO_PINNED_PRICE}")
            continue
        if any(pinned_rates(model, None) is None for _g, model, _ct, _usd in rounds):
            continue   # its fallback group has no pinned price: reported above, by setting name
        group, model, ct, est = max(rounds, key=lambda r: r[3])
        if est > budget:
            why = "lower its max_output_tokens" if group == m.id else (
                f"the dearer case is its Router fallback {group!r} = {model}, max_output_tokens {ct}: "
                "lower SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS or use a cheaper fallback model")
            out.append(f"selectable model {m.id!r}: one answer round reserves ${est:.3f} > free "
                       f"pool / 10 = ${budget:.3f} ({why})")
    if not s.security_headers_enabled:
        out.append("security_headers_enabled=false (CSP is required with BYOK keys in the browser)")
    return out


def _is_study_collection(s, name: str) -> bool:
    return name in (s.study_collection_name, s.study_docs_collection_name) or name.startswith("study")


def check_chroma(s, client) -> None:
    """Public: refuse to serve from a chroma that holds any study collection (study data via the index,
    not via data/study). Called from the lifespan once the CDISC engine has opened chroma. Private: no-op."""
    if s.instance != "public":
        return
    found = sorted(c.name for c in client.list_collections() if _is_study_collection(s, c.name))
    if found:
        raise RuntimeError(f"SDTM_RAG_INSTANCE=public refuses to start: study collections in chroma: {found}")


def _refuse(status: int, code: str, message: str, **fields):
    from server.request_context import ServiceRefusal

    raise ServiceRefusal(status, code, message, **fields)


def public_model_ids(s) -> list[str]:
    """The ONE source of the public server-key model whitelist (`allowed` in model_not_allowed). L1's
    check_model must use this too so both refusals carry identical `allowed`."""
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
        body["selectable_models"] = [{k: m[k] for k in PUBLIC_MODEL_KEYS if k in m}
                                     for m in body.get("selectable_models", [])]
    # per-visitor (quota) / per-tier content: never cached by a browser or the tunnel's edge
    return JSONResponse({**body, **extra}, headers={"Cache-Control": "no-store"})
