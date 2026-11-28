"""Pinned prices (server/cost.py) and the public startup cost check without network.

Deploy run 219 (2026-11-28): the no-network acceptance container refused to start because the public
model's price came from litellm's online price map. Checkpoint:
.work/10_split_and_public/evidence/checkpoints/public_price_pin.md.
Every public-only rule here has a private control on the same input.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from server import cost, instance, quota
from server.config import SelectableModel, Settings
from server.main import create_app
from tests.conftest import set_public_quota_env

ROOT = Path(__file__).resolve().parents[1]

# Literal on purpose (docs/RULES.md rule 5): USD per 1M tokens (input, output), copied from the
# providers' official pricing pages on 2026-11-28 (URLs in server/cost.py). Changing a price means
# re-reading the page and changing both places.
OFFICIAL = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "deepseek-v4-pro": (1.32, 3.96),
    "text-embedding-3-small": (0.02, 0.0),
}
OFFICIAL_LONG_PROMPT = {"claude-haiku-5-5": (100_000, 0.50, 2.50)}

# The public site's model settings as deployed: they live in the deploy machine's env file, not in
# this repo, so they are repeated here (read there by the coordinator on 2026-11-28, non-secret keys
# only; SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS is set there but its value was not read — 16000 is from
# p3_step3.3.md). DEFAULT / HARD / LIGHT max output are NOT set there: the built-in 128000 applies.
HAIKU = "anthropic/claude-haiku-5-5"
HAIKU_MAX_OUT = 16000
DEPLOYED = dict(default_model=HAIKU, hard_model=HAIKU, light_model=HAIKU, fallback_model=HAIKU,
                fallback_max_output_tokens=16000, embedding_model="text-embedding-3-small")
UNPINNED = "openai/gpt-4o-mini"      # litellm's bundled map prices it; this repo does not pin it


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in list(os.environ):
        # any case: test_p3_4_public_https leaves a lowercase sdtm_rag_* name behind, and a public app
        # refuses case variants that disagree
        if k.upper().startswith("SDTM_RAG_"):
            monkeypatch.delenv(k)
    set_public_quota_env(monkeypatch)
    rates = quota._rates                 # the real one: tests below replace quota._rates
    rates.cache_clear()
    yield
    rates.cache_clear()


def _settings(tmp_path, tier, model, max_out=HAIKU_MAX_OUT, **kw):
    """One selectable model `m1` on top of the deployed public model settings (override with **kw)."""
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    st = tmp_path / "nostudy"
    return Settings(instance=tier, data_dir_override=str(data), study_kb_root=st / "cards",
                    study_catalog_path=st / "catalog.json", study_aliases_path=st / "aliases.yml",
                    selectable_models=[SelectableModel(id="m1", label="M1", model=model, verified=False,
                                                       max_output_tokens=max_out)], **{**DEPLOYED, **kw})


def _startup_error(s):
    try:
        instance.check_startup(s)
    except RuntimeError as e:
        return str(e)
    return None


# ── the table ────────────────────────────────────────────────────────────

def test_pinned_table_is_the_official_prices():
    assert cost._PRICES == OFFICIAL
    assert cost._LONG_PROMPT_PRICES == OFFICIAL_LONG_PROMPT
    assert set(cost._LONG_PROMPT_PRICES) <= set(cost._PRICES)
    # every row belongs to exactly one family, and every family names its provider
    assert cost._PINNED_PROVIDERS == {"claude-": "anthropic", "deepseek-": "deepseek", "text-embedding-": "openai"}
    assert all(sum(k.startswith(f) for f in cost._PINNED_PROVIDERS) == 1 for k in cost._PRICES)


def test_every_builtin_server_model_has_a_pinned_price():
    """Built-in selectable list + the four internal groups + the embedding model + the deployed public
    model. A model added to the built-in config without a price row turns this red; a model added only
    in a deploy env file is caught by the public startup check (the refusal tests below)."""
    s = Settings()
    models = ([m.model for m in s.selectable_models]
              + [s.default_model, s.fallback_model, s.hard_model, s.light_model, s.embedding_model, HAIKU])
    assert len(models) >= 10
    assert [m for m in models if cost.pinned_rates(m, None) is None] == []


@pytest.mark.parametrize("model,pinned", [
    ("claude-opus-5", True), ("anthropic/Claude-Opus-5", True), ("claude-opus-5-20260201", True),
    ("claude-opus-5-5", True), ("claude-haiku-5-5-20261001", True),
    ("claude-opus-5-7", False),           # must not borrow the claude-opus-5 row
    ("claude-haiku-4-5-turbo", False), ("claude-opus-5-2026020", False), ("claude-opus-5-202602011", False),
    ("claude-opus", False), ("gpt-4o-mini", False), ("", False),
    ("claude-sonnet-4-6@20260514", False), ("deepseek-v4-pro-0813", False), ("claude-opus-5-latest", False),
    # first-party prices: the bare id or the row's own provider prefix, no other route
    ("deepseek/deepseek-v4-pro", True), ("DeepSeek/DeepSeek-V4-Pro", True), ("anthropic/claude-haiku-5-5-20261001", True),
    ("bedrock/claude-haiku-5-5", False), ("vertex_ai/claude-opus-5", False), ("openai/claude-haiku-5-5", False),
    ("deepseek/claude-opus-5", False), ("anthropic/deepseek-v4-pro", False),
    ("openrouter/anthropic/claude-haiku-5-5", False), ("/claude-opus-5", False),
    ("text-embedding-3-small", True), ("openai/text-embedding-3-small", True),
    ("azure/text-embedding-3-small", False), ("anthropic/text-embedding-3-small", False),
    ("text-embedding-3-large", False), ("text-embedding-3-small-v2", False),
])
def test_a_pinned_row_matches_the_id_or_a_dated_snapshot_only(model, pinned):
    assert (cost.pinned_rates(model, 0) is not None) is pinned


def test_a_missing_row_is_not_covered_by_a_shorter_key(monkeypatch):
    """Without its own row 'claude-opus-5-5' is unpriced: it does not fall back to 'claude-opus-5'."""
    monkeypatch.delitem(cost._PRICES, "claude-opus-5-5")
    assert cost.pinned_rates("anthropic/claude-opus-5-5", 0) is None
    assert cost.pinned_rates("anthropic/claude-opus-5", 0) == (5.00, 25.00)


# ── tiers ────────────────────────────────────────────────────────────────

def test_haiku_5_5_is_priced_by_prompt_length():
    assert cost.pinned_rates(HAIKU, 100_000) == (0.10, 0.50)
    assert cost.pinned_rates(HAIKU, 100_001) == (0.50, 2.50)
    assert cost.pinned_rates(HAIKU, None) == (0.50, 2.50)          # size unknown: the upper bound
    # a dated snapshot has the same tiers as its base row
    assert cost.pinned_rates("claude-haiku-5-5-20261001", 100_000) == (0.10, 0.50)
    assert cost.pinned_rates("claude-haiku-5-5-20261001", 150_000) == (0.50, 2.50)
    assert cost.pinned_rates("claude-opus-5-5", 900_000) == (4.00, 20.00)   # no tier
    assert cost.pinned_rates("claude-opus-5-5", None) == (4.00, 20.00)
    u = {"prompt_tokens": 100_000, "completion_tokens": 1_000}
    assert cost.estimate_cost(HAIKU, u) == pytest.approx(0.0105)
    u = {"prompt_tokens": 150_000, "completion_tokens": 1_000}
    assert cost.estimate_cost(HAIKU, u) == pytest.approx(0.0775)   # 150000 x 0.50 + 1000 x 2.50


def test_the_meter_reserves_at_the_upper_tier_and_settles_at_the_reported_one(tmp_path):
    s = _settings(tmp_path, "public", HAIKU)
    # an estimated prompt size (reserve, the startup bound): the upper tier, whatever the estimate is
    assert quota._price(s, "claude-haiku-5-5", 60_000, 16_000) == pytest.approx(0.07)     # 0.03 + 0.04
    assert quota._price(s, "claude-haiku-5-5", 1_000, 16_000) == pytest.approx(0.0405)
    assert quota.round_estimate_usd(s, "m1") == pytest.approx(0.07)
    # the provider's usage (settle): the tier that request paid
    assert quota._price(s, "claude-haiku-5-5", 60_000, 16_000, reported=True) == pytest.approx(0.014)
    assert quota._price(s, "claude-haiku-5-5", 100_000, 1_000, reported=True) == pytest.approx(0.0105)
    assert quota._price(s, "claude-haiku-5-5", 100_001, 1_000, reported=True) == pytest.approx(0.0525005)
    assert quota._price(s, "claude-haiku-5-5", 150_000, 1_000, reported=True) == pytest.approx(0.0775)
    # a model without tiers: the same either way
    assert quota._price(s, "claude-opus-5-5", 60_000, 16_000) == pytest.approx(0.56)
    assert quota._price(s, "claude-opus-5-5", 60_000, 16_000, reported=True) == pytest.approx(0.56)


def _ctx(s, tmp_path):
    from types import SimpleNamespace

    app = SimpleNamespace(state=SimpleNamespace(settings=s))
    request = SimpleNamespace(app=app, cookies={}, headers={}, client=SimpleNamespace(host="203.0.113.9"))
    st = quota._ReqState(visitor="v1", ip="203.0.113.9", byok=False, day=quota._day())
    return SimpleNamespace(request=request, tier="public", credentials=None, quota=st, endpoint="ask",
                           model="m1", provider=None)


def test_reserve_and_settle_through_the_store_use_those_tiers(tmp_path):
    """reserve() books the upper tier from the estimated prompt; settle() replaces it with the price
    of the usage the provider reported, at that usage's own tier."""
    s = _settings(tmp_path, "public", HAIKU)
    ctx = _ctx(s, tmp_path)
    store = quota._store(s)
    kw = {"model": "m1", "max_tokens": 16_000, "messages": [{"role": "user", "content": "a" * 3000}]}
    h = quota.reserve(ctx, "answer", kw)
    assert store.spent(quota._day()) == pytest.approx((1004 * 0.50 + 16_000 * 2.50) / 1e6)
    quota.settle(ctx, "answer", h, {"prompt_tokens": 2_000, "completion_tokens": 1_000}, "claude-haiku-5-5")
    assert store.spent(quota._day()) == pytest.approx((2_000 * 0.10 + 1_000 * 0.50) / 1e6)
    h = quota.reserve(ctx, "continue", kw)
    quota.settle(ctx, "continue", h, {"prompt_tokens": 120_000, "completion_tokens": 1_000}, "claude-haiku-5-5")
    assert store.spent(quota._day()) == pytest.approx(0.0007 + (120_000 * 0.50 + 1_000 * 2.50) / 1e6)
    # a stream that ended without usage: the prompt size is still only the estimate => upper tier
    h = quota.reserve(ctx, "continue", kw)
    before = store.spent(quota._day())
    est = (1004 * 0.50 + 16_000 * 2.50) / 1e6
    quota.settle(ctx, "continue", h, None, "claude-haiku-5-5", streamed_text="b" * 300)
    assert store.spent(quota._day()) - (before - est) == pytest.approx((1004 * 0.50 + 150 * 2.50) / 1e6)
    quota.finalize(ctx)


def _settled(s, tmp_path, monkeypatch, reported_model, other_rates, prompt_tokens=120_000):
    """USD charged for one answer call reserved on m1 (Haiku 5.5) whose provider reported
    `reported_model` with a `prompt_tokens` prompt and 1,000 output tokens."""
    monkeypatch.setattr(quota, "_rates", lambda model: other_rates)
    ctx = _ctx(s, tmp_path)
    store = quota._store(s)
    kw = {"model": "m1", "max_tokens": 16_000, "messages": [{"role": "user", "content": "a" * 3000}]}
    before = store.spent(quota._day())
    h = quota.reserve(ctx, "answer", kw)
    quota.settle(ctx, "answer", h, {"prompt_tokens": prompt_tokens, "completion_tokens": 1_000}, reported_model)
    quota.finalize(ctx)
    return store.spent(quota._day()) - before


def test_settle_never_charges_less_than_the_reserved_models_pinned_price(tmp_path, monkeypatch):
    """The provider reports a name the table does not know. Whatever the other price sources say,
    the charge is at least the pinned price of the model the call was reserved for."""
    s = _settings(tmp_path, "public", HAIKU)
    haiku_long = (120_000 * 0.50 + 1_000 * 2.50) / 1e6            # 0.0625
    # another source prices the unknown name too low (litellm's map: base tier only) => the pinned price
    assert _settled(s, tmp_path, monkeypatch, "claude-haiku-5-5-latest", (0.10, 0.50)) == pytest.approx(haiku_long)
    # nothing prices it => the fallback rate, which is higher here
    assert _settled(s, tmp_path, monkeypatch, "claude-haiku-5-5-latest", (None, None)) \
        == pytest.approx((120_000 * 5 + 1_000 * 25) / 1e6)
    # a pinned name is charged its own price: a snapshot of the same model, or the Router's fallback model
    assert _settled(s, tmp_path, monkeypatch, "claude-haiku-5-5-20261001", (9.0, 9.0)) == pytest.approx(haiku_long)
    assert _settled(s, tmp_path, monkeypatch, "deepseek-v4-pro", (9.0, 9.0)) \
        == pytest.approx((120_000 * 1.32 + 1_000 * 3.96) / 1e6)
    assert _settled(s, tmp_path, monkeypatch, None, (9.0, 9.0)) == pytest.approx(haiku_long)
    # the floor is the reserved model's price at the tier of the reported usage, not always the upper one
    assert _settled(s, tmp_path, monkeypatch, "claude-haiku-5-5-latest", (0.01, 0.01), prompt_tokens=50_000) \
        == pytest.approx((50_000 * 0.10 + 1_000 * 0.50) / 1e6)


def test_the_floor_also_holds_for_a_stream_that_ended_without_usage(tmp_path, monkeypatch):
    """No usage: the charge is estimated prompt + 1.5 x streamed tokens. An unknown reported name must
    not bring that below the reserved model's pinned price (upper tier: the prompt size is an estimate)."""
    s = _settings(tmp_path, "public", HAIKU)
    monkeypatch.setattr(quota, "_rates", lambda model: (0.10, 0.50))     # litellm's map: base tier only
    ctx = _ctx(s, tmp_path)
    store = quota._store(s)
    kw = {"model": "m1", "max_tokens": 16_000, "messages": [{"role": "user", "content": "a" * 3000}]}
    before = store.spent(quota._day())
    h = quota.reserve(ctx, "answer", kw)
    quota.settle(ctx, "answer", h, None, "claude-haiku-5-5-latest", streamed_text="b" * 300)
    quota.finalize(ctx)
    charged = store.spent(quota._day()) - before
    assert charged == pytest.approx((1004 * 0.50 + 150 * 2.50) / 1e6)    # not (1004 x 0.10 + 150 x 0.50) / 1e6
    assert charged < (1004 * 0.50 + 16_000 * 2.50) / 1e6                 # and still below the reservation


def test_settle_keeps_the_old_price_chain_when_the_reserved_model_is_not_pinned(tmp_path, monkeypatch):
    monkeypatch.setenv("SDTM_RAG_QUOTA_ENABLED", "true")          # private meters only when asked to
    s = _settings(tmp_path, "private", UNPINNED)
    monkeypatch.setattr(quota, "_rates", lambda model: {"gpt-4o-mini": (1.0, 2.0)}.get(model, (3.0, 4.0)))
    ctx = _ctx(s, tmp_path)
    ctx.tier = "private"
    store = quota._store(s)
    h = quota.reserve(ctx, "answer", {"model": "m1", "max_tokens": 1000, "messages": []})
    assert h is not None, "the meter is off: this test would not be testing settle"
    quota.settle(ctx, "answer", h, {"prompt_tokens": 1_000_000, "completion_tokens": 0}, "gpt-4o-mini")
    assert store.spent(quota._day()) == pytest.approx(1.0)        # the reported name's own price, as before
    quota.finalize(ctx)


def test_a_row_of_an_unlisted_family_matches_its_bare_id_only(monkeypatch):
    """A price row added without its provider in _PINNED_PROVIDERS must not raise in the meter."""
    monkeypatch.setitem(cost._PRICES, "zz-new-model", (1.0, 2.0))
    assert cost.pinned_rates("zz-new-model", 0) == (1.0, 2.0)
    assert cost.pinned_rates("someone/zz-new-model", 0) is None


def test_the_embedding_model_is_priced_from_the_table(tmp_path, monkeypatch):
    _break_litellm(monkeypatch)
    s = _settings(tmp_path, "public", HAIKU)
    assert quota._price(s, "text-embedding-3-small", 1_000_000, 0) == pytest.approx(0.02)
    usd, model, pt = quota._estimate_parts(s, "embedding", {"model": s.embedding_model, "input": ["a" * 300]})
    assert (model, pt) == ("text-embedding-3-small", 100) and usd == pytest.approx(100 * 0.02 / 1e6)


# ── one answer round: the selectable model, or the group the Router falls back to ──

DS = "deepseek/deepseek-v4-pro"


def test_the_router_fallback_table_is_what_the_meter_reads(tmp_path):
    """The candidates come from llm_config._fallback_map (the table create_router hands the Router):
    an answer group falls back to default-fallback; hard / light / default-fallback / a plain model
    string have no fallback."""
    s = _settings(tmp_path, "public", HAIKU, fallback_model=DS, fallback_max_output_tokens=32000)
    assert quota._call_candidates(s, "m1") == [("m1", HAIKU, 16000), ("default-fallback", DS, 32000)]
    assert quota._call_candidates(s, "default") == [("default", HAIKU, 128000), ("default-fallback", DS, 32000)]
    for name in ("hard", "light", "default-fallback", "text-embedding-3-small", "deepseek/deepseek-chat"):
        assert [g for g, _m, _mo in quota._call_candidates(s, name)] == [name]


def test_a_round_is_reserved_at_its_dearest_candidate(tmp_path):
    """Fallback dearer than the selectable model (DeepSeek, 32000 output): the startup bound AND the
    reservation are the fallback's. Fallback = the same model and cap (as deployed): unchanged."""
    s = _settings(tmp_path, "public", HAIKU, fallback_model=DS, fallback_max_output_tokens=32000)
    ds_round = (60_000 * 1.32 + 32_000 * 3.96) / 1e6            # 0.20592
    assert quota.round_estimates(s, "m1") == [
        ("m1", HAIKU, 16000, pytest.approx(0.07)), ("default-fallback", DS, 32000, pytest.approx(ds_round))]
    assert quota.round_estimate_usd(s, "m1") == pytest.approx(ds_round)
    kw = {"model": "m1", "messages": [{"role": "user", "content": "a" * 3000}]}   # no per-call max_tokens
    usd, model, pt = quota._estimate_parts(s, "answer", kw)
    assert (model, pt) == (HAIKU, 1004) and usd == pytest.approx((1004 * 1.32 + 32_000 * 3.96) / 1e6)
    ctx = _ctx(s, tmp_path)
    store = quota._store(s)
    quota.reserve(ctx, "answer", kw)
    assert store.spent(quota._day()) == pytest.approx((1004 * 1.32 + 32_000 * 3.96) / 1e6)
    quota.finalize(ctx)
    deployed = _settings(tmp_path, "public", HAIKU)
    assert quota.round_estimate_usd(deployed, "m1") == pytest.approx(0.07)
    assert quota._estimate_parts(deployed, "answer", kw)[0] == pytest.approx((1004 * 0.50 + 16_000 * 2.50) / 1e6)


def test_private_default_config_reserves_what_it_did_before(tmp_path, monkeypatch):
    """Private with the meter on, built-in models: Sonnet 5.5 at 128000 output is dearer than the
    DeepSeek fallback at 32000, so the reservation is the selectable model's own, as before."""
    monkeypatch.setenv("SDTM_RAG_QUOTA_ENABLED", "true")
    data = tmp_path / "data"
    data.mkdir()
    s = Settings(data_dir_override=str(data))
    kw = {"model": "sonnet-5-5", "messages": [{"role": "user", "content": "a" * 3000}]}
    assert quota._estimate_parts(s, "answer", kw)[0] == pytest.approx((1004 * 2.0 + 128_000 * 10.0) / 1e6)
    for group in ("hard", "light"):                               # no fallback: its own model only
        assert quota._estimate_parts(s, "route", {**kw, "model": group})[0] \
            == pytest.approx((1004 * 2.0 + 128_000 * 10.0) / 1e6)
    assert quota._estimate_parts(s, "answer", {**kw, "model": "default-fallback"})[0] \
        == pytest.approx((1004 * 1.32 + 32_000 * 3.96) / 1e6)


def test_public_bound_covers_the_fallback_model_and_its_output_cap(tmp_path):
    ok = _settings(tmp_path, "public", HAIKU, fallback_model=DS, fallback_max_output_tokens=32000)
    assert _startup_error(ok) is None                              # 0.206 <= 0.30
    big = _settings(tmp_path, "public", HAIKU, fallback_model=DS, fallback_max_output_tokens=100_000)
    err = _startup_error(big)                                      # 0.0792 + 0.396 = 0.475
    assert "selectable model 'm1': one answer round reserves $0.475 > free pool / 10 = $0.300" in err
    assert "its Router fallback 'default-fallback' = deepseek/deepseek-v4-pro, max_output_tokens 100000" in err
    assert "SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS" in err and "lower its max_output_tokens" not in err
    # the selectable model itself is the dearer case: the old wording
    own = _startup_error(_settings(tmp_path, "public", HAIKU, max_out=128_000))
    assert "one answer round reserves $0.350 > free pool / 10 = $0.300 (lower its max_output_tokens)" in own
    # Haiku as its own fallback: the bound is 0.03 + cap x 2.50/M  =>  passes up to 108,000
    assert _startup_error(_settings(tmp_path, "public", HAIKU, fallback_max_output_tokens=100_000)) is None
    assert "$0.330 > free pool / 10" in _startup_error(
        _settings(tmp_path, "public", HAIKU, fallback_max_output_tokens=120_000))


def test_private_ignores_the_fallback_bound(tmp_path):
    s = _settings(tmp_path, "private", HAIKU, fallback_model=DS, fallback_max_output_tokens=100_000)
    assert _startup_error(s) is None
    create_app(s)


def test_groups_that_never_answer_on_public_are_not_in_the_round_bound(tmp_path):
    """default / hard / light keep the built-in 128000 output on the deployed site (0.35 a round at
    Haiku's upper tier). They are not reachable from a public answer round, so they do not refuse."""
    s = _settings(tmp_path, "public", HAIKU)
    assert (s.default_max_output_tokens, s.hard_max_output_tokens, s.light_max_output_tokens) == (128000,) * 3
    assert quota.round_estimate_usd(s, "default") == pytest.approx(0.35)
    assert quota.round_estimate_usd(s, "light") == pytest.approx(0.35)
    assert instance._public_cost_problems(s) == []


# ── every server-key model on public needs a pinned price ───────────────

SERVER_MODEL_FIELDS = ("default_model", "fallback_model", "hard_model", "light_model", "embedding_model")


@pytest.mark.parametrize("field", SERVER_MODEL_FIELDS)
def test_public_refuses_a_server_model_setting_without_a_pinned_price(tmp_path, field):
    s = _settings(tmp_path, "public", HAIKU, **{field: UNPINNED})
    err = _startup_error(s)
    assert err is not None
    assert f"{field} (SDTM_RAG_{field.upper()}) = 'openai/gpt-4o-mini': no pinned price" in err
    assert "server/cost.py" in err and "reserves" not in err
    assert err.count("no pinned price") == 1                       # named once, by its setting


@pytest.mark.parametrize("field", SERVER_MODEL_FIELDS)
def test_private_starts_with_the_same_unpinned_server_model_setting(tmp_path, field):
    s = _settings(tmp_path, "private", HAIKU, **{field: UNPINNED})
    assert _startup_error(s) is None
    create_app(s)


def test_the_literal_field_list_is_every_internal_group_plus_embedding():
    from server.llm_config import _INTERNAL_GROUP_MODEL_FIELDS

    assert sorted(SERVER_MODEL_FIELDS) == sorted([*_INTERNAL_GROUP_MODEL_FIELDS.values(), "embedding_model"])


def test_model_settings_nothing_calls_on_public_are_not_checked(tmp_path):
    """expansion / judge / compare / rerank model settings: no public code path calls them
    (checkpoint public_price_pin_ext.md §3), so an unpinned value there does not refuse startup."""
    s = _settings(tmp_path, "public", HAIKU, expansion_model=UNPINNED, judge_model=UNPINNED,
                  compare_models=[UNPINNED], rerank_model="zz-rerank")
    assert s.expansion_model == UNPINNED and s.judge_model == UNPINNED
    assert _startup_error(s) is None


def test_public_names_colliding_selectable_ids_instead_of_crashing(tmp_path):
    s = _settings(tmp_path, "public", HAIKU)
    bad = s.model_copy(update={"selectable_models": [
        SelectableModel(id="light", label="L", model=HAIKU, verified=False, max_output_tokens=1000)]})
    err = _startup_error(bad)
    assert "selectable model ids ['light'] collide with the Router's internal groups" in err
    # a clashing id next to a valid one: still the listed refusal (RuntimeError), not the ValueError the
    # Router's fallback table raises when it is asked to estimate through such a list
    mixed = s.model_copy(update={"selectable_models": [*s.selectable_models, *bad.selectable_models]})
    err = _startup_error(mixed)
    assert "selectable model ids ['light'] collide with the Router's internal groups" in err
    assert "reserves" not in err


# ── a pinned model never asks litellm ────────────────────────────────────

def _break_litellm(monkeypatch):
    import litellm

    def boom(*a, **k):
        raise AssertionError("a pinned model must not be priced through litellm")
    monkeypatch.setattr(litellm, "cost_per_token", boom)
    monkeypatch.setattr(quota, "_rates", boom)


@pytest.mark.parametrize("tier", ["public", "private"])
def test_a_pinned_model_is_priced_without_litellm(tmp_path, monkeypatch, tier):
    _break_litellm(monkeypatch)
    s = _settings(tmp_path, tier, HAIKU)
    assert quota._price(s, HAIKU, 60_000, 16_000, reported=True) == pytest.approx(0.014)
    assert quota.round_estimate_usd(s, "m1") == pytest.approx(0.07)
    assert cost.estimate_cost(HAIKU, {"prompt_tokens": 1000, "completion_tokens": 1000}) == pytest.approx(0.0006)
    assert _startup_error(s) is None


def test_the_deployed_public_config_passes_the_cost_check(tmp_path, monkeypatch):
    _break_litellm(monkeypatch)
    s = _settings(tmp_path, "public", HAIKU)
    assert instance._public_cost_problems(s) == []
    create_app(s)


# ── public refuses a selectable model without a pinned price; private does not ──

def test_public_refuses_a_selectable_model_without_a_pinned_price(tmp_path):
    # litellm can price this one (bundled map), and at 1000 output tokens it is far below the bound:
    # the refusal is about the missing pinned row, not about the amount.
    s = _settings(tmp_path, "public", UNPINNED, max_out=1000)
    err = _startup_error(s)
    assert err is not None and "refuses to start" in err
    assert "selectable model 'm1' (openai/gpt-4o-mini): no pinned price" in err
    assert "server/cost.py" in err and "_PRICES" in err and "_LONG_PROMPT_PRICES" in err
    assert "reserves" not in err            # one clear reason, not also an amount from a guessed rate
    with pytest.raises(RuntimeError, match="no pinned price"):
        create_app(s)


def test_private_starts_with_the_same_unpinned_model(tmp_path):
    s = _settings(tmp_path, "private", UNPINNED, max_out=1000)
    assert _startup_error(s) is None
    create_app(s)


@pytest.mark.parametrize("tier", ["public", "private"])
def test_an_unpriced_model_still_meters_at_the_fallback_rate(tmp_path, monkeypatch, tier):
    """Run time is unchanged on both tiers: a model nothing can price is charged the fallback rate."""
    monkeypatch.setattr(quota, "_rates", lambda model: (None, None))
    s = _settings(tmp_path, tier, HAIKU)
    assert quota._price(s, "zz-unknown", 60_000, 16_000) == pytest.approx(0.70)     # 5 / 25 per MTok
    assert quota._price(s, "zz-unknown", 60_000, 16_000, reported=True) == pytest.approx(0.70)


def test_an_unpinned_model_still_takes_its_price_from_the_old_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(quota, "_rates", lambda model: (1.0, 2.0))
    s = _settings(tmp_path, "private", HAIKU)
    assert quota._price(s, "zz-priced-elsewhere", 1_000_000, 1_000_000) == pytest.approx(3.0)


# ── the failure of run 219: litellm without its online price map ─────────

# Runs in a fresh interpreter with LITELLM_LOCAL_MODEL_COST_MAP=True: litellm then loads the price map
# bundled in the wheel, the same map it falls back to when the fetch fails in a container without
# network. An in-process test cannot show this: litellm reads the map once, at import.
# The probe only calls what the code before this fix also had, so that the mutation run can put the
# old files back and get the old refusal ("$0.700 > free pool / 10 = $0.300") instead of a crash.
_PROBE = r'''
import json, os, sys, tempfile, warnings
warnings.filterwarnings("ignore")
import litellm
from litellm.litellm_core_utils.get_model_cost_map import get_model_cost_map_source_info
import server.config as config                      # load_dotenv runs at import
for k in [k for k in os.environ if k.upper().startswith("SDTM_RAG_")]:
    del os.environ[k]
from server import cost, instance, quota
out = {"map_source": get_model_cost_map_source_info()["source"], "cases": {}}
for name, tier, model, max_out, extra in json.loads(sys.argv[1]):
    bare = model.split("/", 1)[-1]
    for k in [k for k in litellm.model_cost if bare in k]:    # a later wheel may bundle the model
        del litellm.model_cost[k]
    try:
        litellm.cost_per_token(model=model, prompt_tokens=1000, completion_tokens=1000)
        litellm_prices = True
    except Exception:
        litellm_prices = False
    tmp = tempfile.mkdtemp()
    s = config.Settings(
        instance=tier, data_dir_override=os.path.join(tmp, "data"),
        study_kb_root=os.path.join(tmp, "nostudy", "cards"),
        study_catalog_path=os.path.join(tmp, "nostudy", "catalog.json"),
        study_aliases_path=os.path.join(tmp, "nostudy", "aliases.yml"),
        selectable_models=[config.SelectableModel(id="m1", label="M1", model=model, verified=False,
                                                  max_output_tokens=max_out)], **extra)
    os.makedirs(s.data_dir, exist_ok=True)
    try:
        instance.check_startup(s)
        err = None
    except RuntimeError as e:
        err = str(e)
    usage = {"prompt_tokens": 60000, "completion_tokens": 16000}
    out["cases"][name] = {"litellm_prices": litellm_prices, "startup_error": err,
                          "round_estimate": quota.round_estimate_usd(s, "m1"),
                          "reserved_60k_16k": quota._price(s, model, 60000, 16000),
                          "usage_cost_60k_16k": cost.estimate_cost(model, usage)}
print("PROBE_JSON " + json.dumps(out))
'''
_ZZ = "openai/zz-not-pinned-model"
_CASES = [("public_haiku", "public", HAIKU, HAIKU_MAX_OUT, DEPLOYED),
          ("private_haiku", "private", HAIKU, HAIKU_MAX_OUT, DEPLOYED),
          ("public_unpinned", "public", _ZZ, HAIKU_MAX_OUT, DEPLOYED),
          ("private_unpinned", "private", _ZZ, HAIKU_MAX_OUT, DEPLOYED),
          ("public_fallback_unpinned", "public", HAIKU, HAIKU_MAX_OUT, {**DEPLOYED, "fallback_model": _ZZ}),
          ("private_fallback_unpinned", "private", HAIKU, HAIKU_MAX_OUT, {**DEPLOYED, "fallback_model": _ZZ})]


@pytest.fixture(scope="module")
def offline():
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("SDTM_RAG_")}
    env.update(LITELLM_LOCAL_MODEL_COST_MAP="True", PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-c", _PROBE, json.dumps(_CASES)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("PROBE_JSON ")]
    assert len(lines) == 1, r.stdout[-2000:]
    out = json.loads(lines[0].removeprefix("PROBE_JSON "))
    assert out["map_source"] == "local"          # the bundled map, not the online one
    assert set(out["cases"]) == {c[0] for c in _CASES}
    # the scenario itself: litellm cannot price any of these models here
    assert [c["litellm_prices"] for c in out["cases"].values()] == [False] * len(_CASES)
    return out["cases"]


def test_public_cost_check_passes_without_the_online_price_map(offline):
    c = offline["public_haiku"]
    assert c["startup_error"] is None
    assert c["round_estimate"] == pytest.approx(0.07)       # pinned upper tier, not the fallback 0.70
    assert c["reserved_60k_16k"] == pytest.approx(0.07)
    assert c["usage_cost_60k_16k"] == pytest.approx(0.014)  # 60000 x 0.10 + 16000 x 0.50


def test_private_is_priced_the_same_without_the_online_price_map(offline):
    c = offline["private_haiku"]
    assert c["startup_error"] is None
    assert c["round_estimate"] == pytest.approx(0.07)
    assert c["reserved_60k_16k"] == pytest.approx(0.07)
    assert c["usage_cost_60k_16k"] == pytest.approx(0.014)


def test_public_names_the_unpinned_model_without_the_online_price_map(offline):
    err = offline["public_unpinned"]["startup_error"]
    assert "selectable model 'm1' (openai/zz-not-pinned-model): no pinned price" in err
    assert "reserves" not in err


def test_public_names_the_unpinned_fallback_setting_without_the_online_price_map(offline):
    err = offline["public_fallback_unpinned"]["startup_error"]
    assert "fallback_model (SDTM_RAG_FALLBACK_MODEL) = 'openai/zz-not-pinned-model': no pinned price" in err
    assert "reserves" not in err


def test_private_starts_with_an_unpinned_fallback_without_the_online_price_map(offline):
    c = offline["private_fallback_unpinned"]
    assert c["startup_error"] is None
    # the reservation covers the fallback group too: it is unpriced, so the fallback RATE decides
    assert c["reserved_60k_16k"] == pytest.approx(0.07)           # _price on the model string: Haiku
    assert c["round_estimate"] == pytest.approx(0.70)             # the round: max(Haiku 0.07, unpriced 0.70)


def test_private_keeps_the_fallback_rate_without_the_online_price_map(offline):
    c = offline["private_unpinned"]
    assert c["startup_error"] is None
    assert c["reserved_60k_16k"] == pytest.approx(0.70)     # 60000 x 5 + 16000 x 25, as before
    assert c["usage_cost_60k_16k"] is None                  # the badge shows "—", as before
