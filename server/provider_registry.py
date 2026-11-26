"""Provider registry loader + capability matrix (P2 L1, PLAN 2.4 / §5).

Data lives in `provider_registry.yaml` (override path: settings `provider_registry_path`).
Capabilities and prices come from litellm's model_cost table unless the file overrides them,
so a new model = a config edit. `capability_matrix()` is the single table the gates read.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).with_name("provider_registry.yaml")
_DEFAULT_MAX_OUTPUT = 8192


@dataclass(frozen=True)
class Caps:
    tools: bool
    vision: bool
    context_tokens: int
    prompt_cache: bool

    def public(self) -> dict:
        """Shape of /api/info `capabilities` (contract §2.6)."""
        return {"tools": self.tools, "vision": self.vision, "context_tokens": self.context_tokens}


@dataclass(frozen=True)
class ModelEntry:
    id: str
    label: str
    model: str
    caps: Caps
    max_output_tokens: int
    price: tuple[float, float] | None    # USD per 1M (input, output); None = ask litellm
    price_ref: str | None


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    api_base: str | None
    private_only: bool
    custom_base: bool
    models: tuple[ModelEntry, ...]
    default_caps: Caps | None = None
    default_max_output_tokens: int = _DEFAULT_MAX_OUTPUT

    def model(self, model_id: str) -> ModelEntry | None:
        return next((m for m in self.models if m.id == model_id), None)


@dataclass(frozen=True)
class Registry:
    providers: tuple[Provider, ...]
    free_tier_model: str
    dossier_auto_min_context_tokens: int
    byok_timeout_s: float
    byok_num_retries: int
    _by_model: dict = field(default_factory=dict, compare=False, repr=False)

    def provider(self, provider_id: str) -> Provider | None:
        return next((p for p in self.providers if p.id == provider_id), None)

    def entry_for_model(self, model: str | None) -> ModelEntry | None:
        """Row for a litellm model string (server-key models resolve through this too).
        Exact string first, then provider-prefix-insensitive (`claude-opus-5` == `anthropic/claude-opus-5`)."""
        if not model:
            return None
        hit = self._by_model.get(model)
        if hit is not None:
            return hit
        bare = model.split("/", 1)[-1]
        return next((e for k, e in self._by_model.items() if k.split("/", 1)[-1] == bare), None)


def _litellm_row(key: str | None) -> dict:
    if not key:
        return {}
    import litellm

    mc = litellm.model_cost
    return mc.get(key) or mc.get(key.split("/", 1)[-1]) or {}


def _caps(raw: dict | None, row: dict) -> Caps:
    raw = raw or {}
    return Caps(
        tools=bool(raw.get("tools", row.get("supports_function_calling") or False)),
        vision=bool(raw.get("vision", row.get("supports_vision") or False)),
        context_tokens=int(raw.get("context_tokens", row.get("max_input_tokens") or 0)),
        prompt_cache=bool(raw.get("prompt_cache", row.get("supports_prompt_caching") or False)),
    )


def _entry(m: dict) -> ModelEntry:
    row = _litellm_row(m.get("price_ref") or m["model"])
    price = m.get("price")
    return ModelEntry(
        id=str(m["id"]), label=str(m.get("label", m["id"])), model=str(m["model"]),
        caps=_caps(m.get("capabilities"), row),
        max_output_tokens=int(m.get("max_output_tokens") or row.get("max_output_tokens")
                              or _DEFAULT_MAX_OUTPUT),
        price=(float(price[0]), float(price[1])) if price else None,
        price_ref=m.get("price_ref"),
    )


def parse(data: dict) -> Registry:
    from server.llm_config import INTERNAL_GROUPS

    providers = []
    by_model: dict[str, ModelEntry] = {}
    for p in data["providers"]:
        models = tuple(_entry(m) for m in p.get("models") or [])
        ids = [m.id for m in models]
        if len(set(ids)) != len(ids):
            raise ValueError(f"provider {p['id']!r}: duplicate model ids")
        clash = set(ids) & set(INTERNAL_GROUPS)
        if clash:
            raise ValueError(f"provider {p['id']!r}: model ids {sorted(clash)} collide with Router groups")
        for m in models:
            by_model.setdefault(m.model, m)
        providers.append(Provider(
            id=str(p["id"]), label=str(p.get("label", p["id"])), api_base=p.get("api_base"),
            private_only=bool(p.get("private_only", False)),
            custom_base=bool(p.get("custom_base", False)), models=models,
            default_caps=_caps(p["capabilities"], {}) if p.get("capabilities") else None,
            default_max_output_tokens=int(p.get("max_output_tokens") or _DEFAULT_MAX_OUTPUT),
        ))
    pids = [p.id for p in providers]
    if len(set(pids)) != len(pids):
        raise ValueError("duplicate provider ids")
    return Registry(
        providers=tuple(providers),
        free_tier_model=str(data["free_tier_model"]),
        dossier_auto_min_context_tokens=int(data["dossier_auto_min_context_tokens"]),
        byok_timeout_s=float(data.get("byok_timeout_s", 120)),
        byok_num_retries=int(data.get("byok_num_retries", 1)),
        _by_model=by_model,
    )


@functools.lru_cache(maxsize=4)
def load(path: str | None = None) -> Registry:
    p = Path(path) if path else DEFAULT_PATH
    return parse(yaml.safe_load(p.read_text(encoding="utf-8")))


def for_settings(s) -> Registry:
    return load(getattr(s, "provider_registry_path", None) or None)


def registry_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    """USD for one call of a registry model (default registry): the file's `price` override, else
    litellm's pricing of `price_ref` (handles tiered rows; covers the OpenAI-compatible aliases
    such as openai/qwen3-max that litellm cannot price under their own name). None = unknown."""
    e = load().entry_for_model(model)
    if e is None:
        return None
    if e.price is not None:
        return round(prompt_tokens / 1e6 * e.price[0] + completion_tokens / 1e6 * e.price[1], 6)
    if not e.price_ref:
        return None
    import litellm

    try:
        i, o = litellm.cost_per_token(model=e.price_ref, prompt_tokens=prompt_tokens,
                                      completion_tokens=completion_tokens)
    except Exception:  # noqa: BLE001 — unpriced: "—", never a guess
        return None
    total = (i or 0.0) + (o or 0.0)
    return round(float(total), 6) if total > 0 else None


def capability_matrix(reg: Registry | None = None) -> list[dict]:
    """The one capability table (PLAN 2.4): provider × model × {tools, vision, context, cache}."""
    reg = reg or load()
    rows = []
    for p in reg.providers:
        for m in p.models:
            rows.append({"provider": p.id, "model_id": m.id, "model": m.model,
                         "tools": m.caps.tools, "vision": m.caps.vision,
                         "context_tokens": m.caps.context_tokens,
                         "prompt_cache": m.caps.prompt_cache})
        if p.default_caps is not None and not p.models:
            c = p.default_caps
            rows.append({"provider": p.id, "model_id": "*", "model": "*", "tools": c.tools,
                         "vision": c.vision, "context_tokens": c.context_tokens,
                         "prompt_cache": c.prompt_cache})
    return rows
