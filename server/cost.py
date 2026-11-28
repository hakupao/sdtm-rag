"""Per-call cost estimation: the compare badges (DEPLOY_PLAN §3 T3 / §9) and the quota meter (server/quota.py).

`_PRICES` is the PINNED price table (USD per 1M tokens), copied from each provider's official pricing
page. A model in it is priced from it and from nothing else, with or without network. litellm's price
map is only asked for models that are NOT pinned: litellm fetches that map from GitHub when it is
imported and falls back to the older copy bundled in the wheel when the fetch fails, so the same image
prices a new model differently with and without network (deploy run 219, 2026-11-28: the public
startup check refused in the no-network acceptance container).

An unknown model returns None so the badge shows "—" rather than a wrong number or a crash (§9).
We never fabricate a number for a model we cannot price.
"""
from __future__ import annotations

import re

# USD per 1M tokens, (input, output). Keys are the normalized model id (provider prefix stripped,
# lowercased). Only input and output are pinned: they are the only price items the code uses (usage is
# read as prompt_tokens / completion_tokens). Cache writes cost more than base input (1.25x / 2x) and
# cache reads less; the only prompt-cache path is the study dossier, which is private-only.
#
# Sources, read 2026-11-28:
#   Claude rows   https://platform.claude.com/docs/en/about-claude/pricing ("Model pricing" table,
#                 columns "Base input tokens" / "Output tokens"). The three 4.x rows were first taken
#                 from DEPLOY_PLAN §9 (2026-06) and match the page.
#   deepseek-v4-pro  https://api-docs.deepseek.com/quick_start/pricing ("1M INPUT TOKENS (CACHE MISS)" /
#                 "1M OUTPUT TOKENS", PEAK rate; off-peak is half, so the peak rate never under-prices).
# litellm's online map (1.88.6, same day) has the same numbers; it is a cross-check, not the source.
# A new row needs the provider's official page, not litellm and not an older model's price.
_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),      # prompts up to 100,000 tokens; above: _LONG_PROMPT_PRICES
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "deepseek-v4-pro": (1.32, 3.96),
}

# model -> (threshold, input, output): a request whose prompt is OVER `threshold` tokens pays these
# rates for the whole request, output included (same pricing page, "Long context pricing": "Claude
# Haiku 5.5 (for prompts over 100,000 tokens)"). litellm 1.88.6 carries these rates in its map but
# does not apply them (a 150,000-token prompt comes out at the base rate, 5x too low).
_LONG_PROMPT_PRICES: dict[str, tuple[int, float, float]] = {
    "claude-haiku-5-5": (100_000, 0.50, 2.50),
}

_DATE_SUFFIX = re.compile(r"-\d{8}")


def _normalize(model: str) -> str:
    """Strip a litellm provider prefix and lowercase. 'anthropic/Claude-Sonnet-4-6'
    -> 'claude-sonnet-4-6'. A bare 'gpt-4o' is returned unchanged (lowercased)."""
    return model.split("/", 1)[-1].strip().lower()


def _pinned_key(model: str) -> str | None:
    """The `_PRICES` key for this model: the normalized id itself, or the id minus a '-YYYYMMDD'
    snapshot suffix ('claude-sonnet-4-6-20260514'). Nothing looser: 'claude-opus-5-7' must not borrow
    the 'claude-opus-5' row, and 'claude-haiku-4-5-turbo' must not borrow 'claude-haiku-4-5'."""
    norm = _normalize(model)
    if norm in _PRICES:
        return norm
    for key in _PRICES:
        if norm.startswith(key) and _DATE_SUFFIX.fullmatch(norm[len(key):]):
            return key
    return None


def pinned_rates(model: str, prompt_tokens: int | None) -> tuple[float, float] | None:
    """Pinned (input, output) USD per 1M tokens for a request with `prompt_tokens` prompt tokens, or
    None when the model has no pinned row. `prompt_tokens=None` = the prompt size is not known:
    the highest tier (an upper bound)."""
    key = _pinned_key(model)
    if key is None:
        return None
    long_prompt = _LONG_PROMPT_PRICES.get(key)
    if long_prompt is not None and (prompt_tokens is None or prompt_tokens > long_prompt[0]):
        return long_prompt[1], long_prompt[2]
    return _PRICES[key]


def estimate_cost(model: str, usage: dict | None) -> float | None:
    """Estimate the USD cost of one completion.

    Returns a float, or None when it cannot be priced honestly:
      - no usage / no token counts          -> None  (nothing to price)
      - model in the pinned table           -> exact arithmetic from token counts
      - model in the provider registry      -> its override / price_ref price
      - otherwise litellm.completion_cost   -> its number if > 0
      - all of the above fail               -> None  ("—" in the UI, never a guess)
    """
    if not usage:
        return None
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if prompt_tokens is None and completion_tokens is None:
        return None
    pt = int(prompt_tokens or 0)
    ct = int(completion_tokens or 0)

    pinned = pinned_rates(model, pt)
    if pinned is not None:
        in_rate, out_rate = pinned
        return round(pt / 1_000_000 * in_rate + ct / 1_000_000 * out_rate, 6)

    # provider registry (P2 L1): the file's price override, or litellm's price for the
    # registry's `price_ref` (OpenAI-compatible aliases like openai/qwen3-max).
    from server.provider_registry import registry_cost

    reg = registry_cost(model, pt, ct)
    if reg is not None:
        return reg

    # Not pinned — ask litellm's own price map (online copy, or the bundled one without network) via
    # cost_per_token (model, prompt_tokens, completion_tokens) -> (in_cost, out_cost).
    # It raises for models it doesn't know; we swallow that and return None rather than
    # fabricate a number for a model we cannot price honestly.
    try:
        import litellm

        in_cost, out_cost = litellm.cost_per_token(
            model=model, prompt_tokens=pt, completion_tokens=ct
        )
        total = (in_cost or 0.0) + (out_cost or 0.0)
        if total > 0:
            return round(float(total), 6)
    except Exception:  # noqa: BLE001 — unknown model / litellm internal: degrade to "—"
        pass
    return None
