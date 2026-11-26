"""Provider / model / BYOK hooks — L1 (P2 steps 2.4 / 2.6). Frozen seam: docs/design/P2_request_context.md.

Registry + capability matrix: `server/provider_registry.{py,yaml}`. Custom-base SSRF guard and IP
pinning: `server/provider_registry_net.py`.

BYOK is active on the public tier, and on the private tier only when the instance sets
`byok_enabled` (settings, L3). With it off every hook here reproduces pre-P2 behaviour exactly.

Probe facts (.work/10_split_and_public/evidence/checkpoints/p2_byok_spike.md): a per-call api_key
is carried into Router `fallbacks` ⇒ BYOK calls never go through the Router; they call litellm
directly with the user's key, and an upstream failure never retries on the server key.
"""
from __future__ import annotations

import logging
import re

import structlog
from fastapi import HTTPException

from server.request_context import Credentials, ServiceRefusal, current

log = structlog.get_logger()

# Frozen v1 header names (contract §2.1). Read only here; never logged.
BYOK_KEY_HEADER = "X-LLM-Api-Key"
BYOK_BASE_HEADER = "X-LLM-Api-Base"

# Purposes that carry the user's key. Everything else (route / embedding / hyde / multiquery /
# review / compare / judge / web) is a server-side call and stays on the server key (L2 meters it).
BYOK_PURPOSES = ("answer", "continue", "regen")
CUSTOM = "custom"
_NON_BYOK_ENDPOINTS = frozenset({"ask_compare", "validate"})
_MAX_KEY_LEN = 512
_CUSTOM_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")
# Marker the dossier prompt-cache layout puts in the system prompt (router._DOSSIER_RULES).
_DOSSIER_SYSTEM_MARKER = "研読パッケージ】"


# ── helpers ──────────────────────────────────────────────────────────────

def _settings(request):
    return getattr(getattr(getattr(request, "app", None), "state", None), "settings", None)


def _tier(request) -> str:
    from server import instance

    return instance.tier(request) if request is not None else "private"


def byok_enabled(request) -> bool:
    return _tier(request) == "public" or bool(getattr(_settings(request), "byok_enabled", False))


def _registry(request):
    from server import provider_registry

    return provider_registry.for_settings(_settings(request))


def _note(ctx, capability: str, reason: str, detail: str | None = None) -> None:
    if any(n.get("capability") == capability and n.get("reason") == reason for n in ctx.notes):
        return
    ctx.notes.append({"capability": capability, "reason": reason,
                      **({"detail": detail} if detail else {})})


def _server_model_string(s, model_id: str | None) -> str | None:
    from server.llm_config import _INTERNAL_GROUP_MODEL_FIELDS

    by_id = {m.id: m.model for m in getattr(s, "selectable_models", [])}
    if model_id in by_id:
        return by_id[model_id]
    field = _INTERNAL_GROUP_MODEL_FIELDS.get(model_id)
    return getattr(s, field, None) if field else None


def _caps(ctx):
    """Capabilities of the model this request answers with; None = unknown (keep defaults)."""
    t = ctx.flags.get("byok")
    if t is not None:
        return t["caps"]
    s = _settings(ctx.request)
    if s is None:
        return None
    e = _registry(ctx.request).entry_for_model(_server_model_string(s, ctx.model))
    return e.caps if e is not None else None


def _refuse_model(allowed: list[str], message: str):
    raise ServiceRefusal(422, "model_not_allowed", message, allowed=allowed)


# ── hooks ────────────────────────────────────────────────────────────────

def credentials_from(request):
    """-> Credentials | None. Headers are read only when BYOK is enabled for this instance;
    shape checks happen in check_model (begin() must not raise)."""
    if request is None or not byok_enabled(request):
        return None
    key = (request.headers.get(BYOK_KEY_HEADER) or "").strip()
    if not key:
        return None
    base = (request.headers.get(BYOK_BASE_HEADER) or "").strip() or None
    return Credentials(api_key=key, api_base=base)


def check_model(ctx, s) -> None:
    """Validate provider / key / model before any work (contract §2.1 table, §2.3 codes)."""
    request = ctx.request
    headers = getattr(request, "headers", None) or {}
    has_key_hdr = bool((headers.get(BYOK_KEY_HEADER) or "").strip())
    has_base_hdr = bool((headers.get(BYOK_BASE_HEADER) or "").strip())

    if not byok_enabled(request):
        if ctx.provider is not None or has_key_hdr or has_base_hdr:
            # ⛔ never answer a "use my key" request on the server key
            raise ServiceRefusal(403, "not_on_this_tier", "本站未开启自带 key (BYOK)", feature="byok")
        _check_server_model(ctx, s)
        return

    public = ctx.tier == "public"
    if has_base_hdr and (public or ctx.provider != CUSTOM):
        raise ServiceRefusal(400, "custom_base_not_allowed",
                             "自定义地址只在私有站的 custom provider 下可用")
    if ctx.credentials is None:
        if ctx.provider is not None:
            raise ServiceRefusal(400, "byok_key_missing", "选择了 provider 但没有提供 API key",
                                 provider=ctx.provider)
        _check_server_model(ctx, s)
        return
    if ctx.provider is None:
        raise ServiceRefusal(400, "provider_required", "提供了 API key 时必须同时指定 provider")

    from server import quota

    quota.check_byok_probing(ctx)   # N bad keys from this IP today ⇒ 429 (metered tiers)
    key = ctx.credentials.api_key
    if len(key) > _MAX_KEY_LEN or not key.isprintable():
        quota.note_bad_key(ctx)
        raise ServiceRefusal(401, "byok_key_invalid", "API key 格式无效", provider=ctx.provider)
    reg = _registry(request)
    prov = reg.provider(ctx.provider)
    if prov is None or (prov.private_only and public):
        visible = [p.id for p in reg.providers if not (p.private_only and public)]
        raise ServiceRefusal(400, "provider_required", f"未知 provider: {ctx.provider!r}",
                             allowed=visible)

    if prov.custom_base:
        target = _custom_target(ctx, prov)
    else:
        entry = prov.model(ctx.model)
        if entry is None:
            _refuse_model([m.id for m in prov.models], f"{prov.label} 没有模型 {ctx.model!r}")
        target = {"provider": prov.id, "model": entry.model, "api_base": prov.api_base,
                  "max_tokens": entry.max_output_tokens, "caps": entry.caps, "pin": None}
    target["timeout"] = reg.byok_timeout_s
    target["num_retries"] = reg.byok_num_retries
    ctx.flags["byok"] = target


def _custom_target(ctx, prov) -> dict:
    from server.llm_config import known_model_groups
    from server.provider_registry_net import UnsafeBase, validate_custom_base

    model = ctx.model or ""
    if not _CUSTOM_MODEL_RE.match(model) or model in known_model_groups(_settings(ctx.request)):
        _refuse_model([], "custom provider 的模型名无效")
    if not ctx.credentials.api_base:
        raise ServiceRefusal(400, "custom_base_not_allowed", "custom provider 需要自定义地址")
    try:
        pin = validate_custom_base(ctx.credentials.api_base)
    except UnsafeBase as e:
        raise ServiceRefusal(400, "custom_base_not_allowed", str(e)) from None
    return {"provider": prov.id, "model": "openai/" + model, "api_base": pin.url,
            "max_tokens": prov.default_max_output_tokens, "caps": prov.default_caps, "pin": pin}


def _check_server_model(ctx, s) -> None:
    from server.llm_config import known_model_groups

    if ctx.tier == "public":
        from server.instance import public_model_ids

        allowed = public_model_ids(s)   # the ONE public whitelist (L3); same refusal as check_request
        if ctx.model not in allowed:
            _refuse_model(allowed, "该模型在公开站不可用。")
        return
    known = known_model_groups(s)
    if ctx.model not in known:
        # ⛔ 不静默退回 default: 静默退回会让"选了模型 X 却拿到 Y 的答案"完全不可见。
        raise HTTPException(status_code=422,
                            detail=f"unknown model {ctx.model!r}; known: {sorted(known)}")


def resolve(ctx, purpose: str, kind: str, llm_router, kw: dict):
    """-> (callable, kwargs). Server-key calls: unchanged (Router method, or the litellm function
    looked up at call time). BYOK answer calls: litellm directly — never the Router (fallbacks
    would carry the user's key to another provider) — with the user's key and the registry's
    model / base / max_tokens; upstream errors become typed refusals without the upstream text."""
    if ctx is not None and ctx.credentials is not None and ctx.endpoint in _NON_BYOK_ENDPOINTS:
        # compare / validate never use a user key: refuse rather than silently run on the server key
        raise ServiceRefusal(403, "not_on_this_tier", "该功能不支持自带 key (BYOK)", feature="byok")
    if ctx is not None and ctx.credentials is not None and purpose in BYOK_PURPOSES \
            and kind != "embedding":
        target = ctx.flags.get("byok")
        if target is None:   # check_model did not run: fail closed, never the server key
            raise ServiceRefusal(400, "provider_required", "BYOK 请求缺少 provider 校验")
        return _byok_call(ctx, purpose, kind, target, kw)
    if llm_router is not None:
        return getattr(llm_router, kind), kw
    import litellm

    return getattr(litellm, kind), kw


def _byok_call(ctx, purpose, kind, t, kw):
    import litellm

    out = {k: v for k, v in kw.items() if k not in ("model", "api_key", "api_base", "client")}
    out.update(model=t["model"], api_key=ctx.credentials.api_key, max_tokens=t["max_tokens"],
               timeout=t["timeout"], num_retries=t["num_retries"])
    out["api_base"] = t["api_base"]   # always the preset's official base (env *_API_BASE must not win)
    if t["pin"] is not None:
        from server.provider_registry_net import openai_client

        out["client"] = openai_client(t["pin"], ctx.credentials.api_key,
                                      is_async=(kind == "acompletion"), timeout=t["timeout"])
        out["num_retries"] = 0
    if (t["provider"] == "anthropic" and t["caps"].prompt_cache and "messages" in out
            and getattr(_settings(ctx.request), "dossier_prompt_cache", False)):   # kill switch
        out["messages"] = _with_cache_breakpoint(out["messages"])
    provider = t["provider"]

    if kind == "acompletion":
        async def acall(**k):
            client = k.get("client")   # per-call pinned client (custom): closed when the call ends
            try:
                resp = await litellm.acompletion(**k)
            except Exception as e:  # noqa: BLE001
                await _aclose_client(client)
                raise _translate(e, purpose, provider, k, ctx) from None
            if not k.get("stream"):
                await _aclose_client(client)
                return resp
            return _translating_stream(resp, purpose, provider, client, ctx)
        return acall, out

    def call(**k):
        try:
            return litellm.completion(**k)
        except Exception as e:  # noqa: BLE001
            raise _translate(e, purpose, provider, k, ctx) from None
        finally:
            if k.get("client") is not None:
                k["client"].close()
    return call, out


async def _aclose_client(client) -> None:
    if client is not None:
        await client.close()


async def _translating_stream(stream, purpose, provider, client=None, ctx=None):
    try:
        async for chunk in stream:
            yield chunk
    except Exception as e:  # noqa: BLE001
        raise _translate(e, purpose, provider, {}, ctx) from None
    finally:
        try:
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()
        finally:
            await _aclose_client(client)


def _translate(e: Exception, purpose: str, provider: str, kw: dict, ctx=None) -> Exception:
    """Upstream error -> what the router should see. 401/403 ⇒ byok_key_invalid. Other failures
    on the first answer call ⇒ byok_provider_error (no upstream text: it may echo the key) — except
    a failure with stream_options set, which stays raw so the router's narrow retry runs.
    continue / regen failures stay raw: the router keeps the partial answer / restores round 1."""
    if isinstance(e, ServiceRefusal):
        return e
    status = getattr(e, "status_code", None)
    log.warning("byok_upstream_error", provider=provider, purpose=purpose,
                upstream_status=status, error_type=type(e).__name__)
    if status in (401, 403):
        if ctx is not None:
            from server import quota

            quota.note_bad_key(ctx)
        return ServiceRefusal(401, "byok_key_invalid", "API key 无效或无权限", provider=provider)
    if purpose != "answer" or "stream_options" in kw:
        return e
    return ServiceRefusal(502, "byok_provider_error", "模型服务商返回错误", provider=provider,
                          upstream_status=status)


def _with_cache_breakpoint(messages):
    """BYOK Anthropic + dossier prompt-cache layout: the router only marks cache_control for
    server-configured Anthropic models (`_prompt_cache_capable`), so mark it here — same layout
    (single system block, ephemeral breakpoint). Copies; the router reuses `messages`."""
    if not messages or messages[0].get("role") != "system":
        return messages
    sys_text = messages[0]["content"]
    if not isinstance(sys_text, str) or _DOSSIER_SYSTEM_MARKER not in sys_text:
        return messages
    first = {**messages[0], "content": [{"type": "text", "text": sys_text,
                                         "cache_control": {"type": "ephemeral"}}]}
    return [first, *messages[1:]]


def capability(ctx, name: str, default):
    """Capability gate (contract §2.4). Returns the value to use; a downgrade appends a note that
    reaches `sources.downgrades` / `done.downgrades` / AskResponse.downgrades."""
    if ctx is None:
        return default
    caps = _caps(ctx)
    if name == "web_tools":
        from server import quota

        # the ONE owner of the free-question web policy (key: quota_free_web_enabled)
        if default and ctx.credentials is None and not quota.free_web_allowed(ctx):
            _note(ctx, "web_tools", "free_tier_no_web")
            return False
        if default and caps is not None and not caps.tools:
            _note(ctx, "web_tools", "no_tool_calling")
            return False
        return default
    if name == "vision":
        if default and caps is not None and not caps.vision:
            _note(ctx, "vision", "no_vision")
            return False
        return default
    if name == "dossier_auto":
        need = _registry(ctx.request).dossier_auto_min_context_tokens
        if ctx.credentials is not None:
            # Decision (main session, PLAN D5): BYOK never auto-attaches the dossier; explicit
            # dossier="on" / corpus=study stay allowed (no provider whitelist for study data).
            return False
        if default and caps is not None and caps.context_tokens < need:
            _note(ctx, "dossier_auto", "context_too_small", str(caps.context_tokens))
            return False
        return default
    return default


def info_fields(request) -> dict:
    """/api/info `providers` (contract §2.6). Absent while BYOK is off (private default)."""
    if request is None or not byok_enabled(request):
        return {}
    public = _tier(request) == "public"
    out = []
    for p in _registry(request).providers:
        if p.private_only and public:
            continue
        out.append({"id": p.id, "label": p.label, "byok": True, "base_fixed": not p.custom_base,
                    "models": [{"id": m.id, "label": m.label, "capabilities": m.caps.public()}
                               for m in p.models]})
    return {"providers": out}


# ── log redaction (contract §3: grep the RENDERED line) ─────────────────

# Left boundary: not glued to a word (so `risk-benefit-…` survives), but DO match after a URL-encoded
# byte (`%3Dsk-…`), a repr/JSON escape (`\nsk-…`, `\u003dsk-…`). The sk- tail must contain a digit
# (real keys do; ordinary hyphenated words do not).
_LB = r"(?:(?<![A-Za-z0-9])|(?<=%[0-9A-Fa-f]{2})|(?<=\\[ntrbf])|(?<=\\u[0-9A-Fa-f]{4})|(?<=\\x[0-9A-Fa-f]{2}))"
_SECRET_PATTERNS = [
    re.compile(_LB + r"sk-(?=[A-Za-z_\-]*[0-9])[A-Za-z0-9_\-]{12,}"),   # OpenAI / Anthropic / DeepSeek / Kimi …
    re.compile(_LB + r"AIza[0-9A-Za-z_\-]{20,}"),                       # Google
    re.compile(_LB + r"[0-9a-fA-F]{32}\.[A-Za-z0-9]{16}(?![A-Za-z0-9])"),  # Zhipu GLM (id.secret)
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-~+/=]{12,}"),
    re.compile(r"(?i)((?:x-api-key|x-goog-api-key|api[_-]?key|authorization|x-llm-api-key)"
               r"[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]{8,}"),
]
REDACTED = "[REDACTED]"


def redact_text(text: str, secrets: tuple[str, ...] = ()) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, REDACTED)
    for p in _SECRET_PATTERNS:
        text = p.sub(lambda m: (m.group(1) if m.groups() else "") + REDACTED, text)
    return text


def _secrets() -> tuple[str, ...]:
    ctx = current()
    c = getattr(ctx, "credentials", None)
    return (c.api_key,) if c is not None and c.api_key else ()


def _scrub(v, secrets):
    if isinstance(v, str):
        return redact_text(v, secrets)
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if isinstance(v, dict):
        return {_scrub(k, secrets): _scrub(x, secrets) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return type(v)(_scrub(x, secrets) for x in v)
    r = repr(v)
    clean = redact_text(r, secrets)
    return v if clean == r else clean


def _redact_processor(logger, method_name, event_dict):
    """Render exc_info to text first (the renderer would format it itself, past any scrubbing),
    then scrub every value: the current request's exact key + generic key shapes."""
    if event_dict.get("exc_info"):
        event_dict = structlog.processors.format_exc_info(logger, method_name, event_dict)
    secrets = _secrets()
    return {_scrub(k, secrets): _scrub(v, secrets) for k, v in event_dict.items()}


def log_processors() -> list:
    """structlog processors inserted before the renderer (main.py)."""
    return [_redact_processor]


# ── stdlib logging (litellm / httpx / openai log through `logging`, not structlog) ──

class RedactFilter(logging.Filter):
    """Handler filter: renders the record's message (args merged) and exception text, then scrubs
    them like _redact_processor. On HANDLERS, so records from child loggers (httpcore.http11 …)
    that propagate up are covered too (a logger filter only sees its own records)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            secrets = _secrets()
            msg = record.getMessage()
            record.msg, record.args = redact_text(msg, secrets), None
            if record.exc_info and not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            if record.exc_text:
                record.exc_text = redact_text(record.exc_text, secrets)
            if record.stack_info:
                record.stack_info = redact_text(record.stack_info, secrets)
        except Exception:  # noqa: BLE001 — a logging filter must never break logging
            pass
        return True


_REDACT_FILTER = RedactFilter()
_THIRD_PARTY_LOGGERS = ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "litellm", "httpx",
                        "httpcore", "openai", "anthropic")


def install_log_redaction(public: bool) -> None:
    """Attach RedactFilter to every handler that can emit a third-party record: root's, the
    named loggers', and logging.lastResort (used when root has none). Public: those loggers are
    held at WARNING (litellm/httpx INFO/DEBUG lines carry request detail). Idempotent."""
    handlers = [*logging.getLogger().handlers, logging.lastResort]
    for name in _THIRD_PARTY_LOGGERS:
        lg = logging.getLogger(name)
        handlers += lg.handlers
        if public and lg.getEffectiveLevel() < logging.WARNING:
            lg.setLevel(logging.WARNING)
    for h in handlers:
        if h is not None and _REDACT_FILTER not in h.filters:
            h.addFilter(_REDACT_FILTER)
