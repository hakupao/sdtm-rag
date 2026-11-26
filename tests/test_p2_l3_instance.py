"""P2 L3: instance tier (2.1) + public endpoint lockdown (2.3). Contract docs/design/P2_request_context.md
§2.3 / §2.6 / §2.7. Every public refusal has a private positive control on the same request."""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from server import instance, providers, quota
from server.config import PUBLIC_FORCED_OFF, SelectableModel, Settings
from server.llm_config import INTERNAL_GROUPS
from server.main import create_app
from server.request_context import ServiceRefusal

PUBLIC_MODELS = [SelectableModel(id="ds-v4", label="DeepSeek V4 Pro", model="deepseek/deepseek-v4-pro",
                                 verified=False)]
BLOCKED = ["/api/ask_compare", "/api/validate", "/api/validate-study"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("SDTM_RAG_"):
            monkeypatch.delenv(k)


def _paths(tmp_path, data_dir=None):
    data = data_dir or tmp_path / "data"
    data.mkdir(exist_ok=True)
    st = tmp_path / "nostudy"
    return dict(data_dir_override=str(data), study_kb_root=st / "cards",
                study_catalog_path=st / "catalog.json", study_aliases_path=st / "aliases.yml")


def _pub(tmp_path, **kw):
    return Settings(instance="public", selectable_models=PUBLIC_MODELS, **{**_paths(tmp_path), **kw})


def _priv(tmp_path, **kw):
    return Settings(**{**_paths(tmp_path), **kw})


def _fake_rag():
    return SimpleNamespace(collection=SimpleNamespace(count=lambda: 7), structured_lookup_enabled=True,
                           hybrid_enabled=True, hybrid_fusion="rrf", prompt_guardrail_enabled=True,
                           web_search_enabled=True)


def _client(s):
    app = create_app(s)            # no `with` ⇒ lifespan (chroma/RAG build) does not run
    app.state.rag = _fake_rag()
    app.state.llm_router = None
    return TestClient(app)


class _Passed(Exception):
    pass


@pytest.fixture
def past_check_request(monkeypatch):
    """Requests that get past instance.check_request hit this sentinel 418 (no retrieval needed)."""
    def mark(ctx, s):
        raise ServiceRefusal(418, "passed_check_request", "ok")
    monkeypatch.setattr(providers, "check_model", mark)


# ── settings: tier + public study defaults ───────────────────────────────

def test_default_tier_is_private_and_study_switches_unchanged():
    s = Settings()
    assert s.instance == "private"
    assert all(getattr(s, n) is True for n in PUBLIC_FORCED_OFF)


def test_env_selects_public_and_study_switches_default_off(monkeypatch):
    monkeypatch.setenv("SDTM_RAG_INSTANCE", "public")
    s = Settings()
    assert s.instance == "public"
    assert all(getattr(s, n) is False for n in PUBLIC_FORCED_OFF)


def test_unknown_tier_value_is_rejected():
    with pytest.raises(ValueError):
        Settings(instance="staging")


def test_default_dogfood_log_follows_data_dir(tmp_path):
    s = Settings(data_dir_override=str(tmp_path))
    assert s.dogfood_log_path == tmp_path / "dogfood_failures.md"
    assert Settings().dogfood_log_path.parent.name == "data"


# ── startup refusal (public) ─────────────────────────────────────────────

def test_clean_public_settings_start(tmp_path):
    instance.check_startup(_pub(tmp_path))
    assert create_app(_pub(tmp_path)).state.settings.instance == "public"


@pytest.mark.parametrize("switch", PUBLIC_FORCED_OFF)
def test_public_refuses_explicit_study_switch(tmp_path, switch):
    with pytest.raises(RuntimeError, match=switch):
        create_app(_pub(tmp_path, **{switch: True}))


@pytest.mark.parametrize("switch", PUBLIC_FORCED_OFF)
def test_public_refuses_study_switch_from_env(tmp_path, monkeypatch, switch):
    monkeypatch.setenv("SDTM_RAG_" + switch.upper(), "true")
    with pytest.raises(RuntimeError, match=switch):
        create_app(_pub(tmp_path))


@pytest.mark.parametrize("flag", ["rerank_enabled", "pdf_context_enabled"])
def test_public_refuses_rerank_and_pdf_channel(tmp_path, flag):
    with pytest.raises(RuntimeError, match=flag):
        create_app(_pub(tmp_path, **{flag: True}))


@pytest.mark.parametrize("where", ["data_study", "cards", "catalog", "aliases", "docs"])
def test_public_refuses_when_study_data_present(tmp_path, where):
    s = _pub(tmp_path)
    target = {"data_study": s.data_dir / "study", "cards": s.study_kb_root,
              "catalog": s.study_catalog_path, "aliases": s.study_aliases_path,
              "docs": s.dossier_docs_dir}[where]
    if target.suffix:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
    else:
        target.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="study data present"):
        create_app(s)


def test_public_refuses_dogfood_log_outside_data_dir(tmp_path):
    with pytest.raises(RuntimeError, match="dogfood"):
        create_app(_pub(tmp_path, dogfood_log_override=str(tmp_path / "elsewhere.md")))


def test_private_ignores_all_public_startup_rules(tmp_path):
    s = _priv(tmp_path, rerank_enabled=True, pdf_context_enabled=True,
              dogfood_log_override=str(tmp_path / "elsewhere.md"))
    (s.data_dir / "study").mkdir()
    instance.check_startup(s)      # no raise


# ── endpoint set (§2.7) ──────────────────────────────────────────────────

def _route_paths(app):
    return {getattr(r, "path", None) for r in app.routes}


def test_public_registers_exactly_the_allowlisted_api_routes(tmp_path):
    api = {p for p in _route_paths(create_app(_pub(tmp_path))) if p and p.startswith("/api")}
    assert api == {"/api/health", "/api/info", "/api/ask", "/api/ask_stream", "/api/flag"}


@pytest.mark.parametrize("path", BLOCKED)
def test_blocked_endpoint_is_404_on_public_and_routed_on_private(tmp_path, path):
    r = _client(_pub(tmp_path)).post(path, json={"question": "q"})
    assert r.status_code == 404
    r = _client(_priv(tmp_path)).post(path, json={})
    assert r.status_code == 422          # private: route exists, body validation runs


@pytest.mark.parametrize("path", ["/docs", "/openapi.json", "/redoc"])
def test_docs_closed_on_public_open_on_private(tmp_path, path):
    assert _client(_pub(tmp_path)).get(path).status_code == 404
    assert _client(_priv(tmp_path)).get(path).status_code == 200


def test_health_on_public(tmp_path):
    assert _client(_pub(tmp_path)).get("/api/health").json() == {"status": "ok"}


def test_flag_on_public_writes_under_data_dir(tmp_path):
    s = _pub(tmp_path)
    r = _client(s).post("/api/flag", json={"question": "q", "answer": "a", "note": "n"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert s.dogfood_log_path.parent == s.data_dir and "**Q:** q" in s.dogfood_log_path.read_text()


def test_flag_on_public_keeps_field_size_limit(tmp_path):
    r = _client(_pub(tmp_path)).post("/api/flag", json={"note": "x" * 2001})
    assert r.status_code == 422


# ── /api/info (§2.6) ─────────────────────────────────────────────────────

def test_info_public_shape_has_no_internal_fields(tmp_path):
    body = _client(_pub(tmp_path)).get("/api/info").json()
    assert set(body) == {"tier", "top_k", "web_search", "selectable_models", "index_fresh"}
    assert body["tier"] == "public"
    assert [m["id"] for m in body["selectable_models"]] == ["ds-v4"]


def test_info_public_merges_hook_extras(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "info_fields", lambda request: {"providers": []})
    monkeypatch.setattr(quota, "info_fields", lambda request: {"quota": {"byok": False}})
    body = _client(_pub(tmp_path)).get("/api/info").json()
    assert body["providers"] == [] and body["quota"] == {"byok": False} and body["tier"] == "public"


def test_info_private_shape_unchanged(tmp_path):
    body = _client(_priv(tmp_path)).get("/api/info").json()
    assert "tier" not in body
    assert {"collection_name", "chunk_count", "fallback_model", "compare_models", "judge_model",
            "index_freshness_reason", "federation", "dossier_gate", "dossier_auto_attach_models",
            "dossier_prompt_cache", "default_model"} <= set(body)


# ── request checks (§2.3) on /api/ask and /api/ask_stream ────────────────

ENDPOINTS = ["/api/ask", "/api/ask_stream"]


def _detail(r):
    return r.json()["detail"]


@pytest.mark.parametrize("path", ENDPOINTS)
def test_dossier_on_rejected_on_public(tmp_path, past_check_request, path):
    r = _client(_pub(tmp_path)).post(path, json={"question": "q", "model": "ds-v4", "dossier": "on"})
    assert r.status_code == 403
    assert _detail(r)["code"] == "not_on_this_tier" and _detail(r)["feature"] == "dossier"
    r = _client(_priv(tmp_path)).post(path, json={"question": "q", "model": "opus-5", "dossier": "on"})
    assert r.status_code == 418


@pytest.mark.parametrize("path", ENDPOINTS)
@pytest.mark.parametrize("dossier", ["auto", "off"])
def test_dossier_auto_off_pass_on_public(tmp_path, past_check_request, path, dossier):
    r = _client(_pub(tmp_path)).post(path, json={"question": "q", "model": "ds-v4", "dossier": dossier})
    assert r.status_code == 418


@pytest.mark.parametrize("path", ENDPOINTS)
@pytest.mark.parametrize("corpus", ["study", "both"])
def test_study_corpus_rejected_on_public(tmp_path, past_check_request, path, corpus):
    r = _client(_pub(tmp_path)).post(path, json={"question": "q", "model": "ds-v4", "corpus": corpus})
    assert r.status_code == 403 and _detail(r)["feature"] == "study_corpus"
    r = _client(_priv(tmp_path)).post(path, json={"question": "q", "model": "opus-5", "corpus": corpus})
    assert r.status_code == 418


@pytest.mark.parametrize("path", ENDPOINTS)
@pytest.mark.parametrize("corpus", ["auto", "cdisc"])
def test_cdisc_corpus_passes_on_public(tmp_path, past_check_request, path, corpus):
    r = _client(_pub(tmp_path)).post(path, json={"question": "q", "model": "ds-v4", "corpus": corpus})
    assert r.status_code == 418


@pytest.mark.parametrize("path", ENDPOINTS)
@pytest.mark.parametrize("group", INTERNAL_GROUPS)
def test_internal_group_rejected_on_public(tmp_path, past_check_request, path, group):
    r = _client(_pub(tmp_path)).post(path, json={"question": "q", "model": group})
    assert r.status_code == 422
    assert _detail(r) == {"code": "model_not_allowed", "message": _detail(r)["message"],
                          "allowed": ["ds-v4"]}
    r = _client(_priv(tmp_path)).post(path, json={"question": "q", "model": group})
    assert r.status_code == 418


@pytest.mark.parametrize("path", ENDPOINTS)
def test_internal_group_rejected_on_public_even_with_provider(tmp_path, past_check_request, path):
    r = _client(_pub(tmp_path)).post(path, json={"question": "q", "model": "hard", "provider": "openai"})
    assert r.status_code == 422 and _detail(r)["code"] == "model_not_allowed"


@pytest.mark.parametrize("path", ENDPOINTS)
def test_model_omitted_is_default_group_and_rejected_on_public(tmp_path, past_check_request, path):
    r = _client(_pub(tmp_path)).post(path, json={"question": "q"})
    assert r.status_code == 422 and _detail(r)["code"] == "model_not_allowed"


@pytest.mark.parametrize("path", ENDPOINTS)
def test_unknown_model_is_model_not_allowed_on_public(tmp_path, past_check_request, path):
    r = _client(_pub(tmp_path)).post(path, json={"question": "q", "model": "opus-5"})
    assert r.status_code == 422 and _detail(r)["allowed"] == ["ds-v4"]


@pytest.mark.parametrize("path", ENDPOINTS)
def test_public_model_passes(tmp_path, past_check_request, path):
    r = _client(_pub(tmp_path)).post(path, json={"question": "q", "model": "ds-v4"})
    assert r.status_code == 418


@pytest.mark.parametrize("path", ENDPOINTS)
def test_byok_model_id_is_left_to_providers_on_public(tmp_path, past_check_request, path):
    r = _client(_pub(tmp_path)).post(path, json={"question": "q", "model": "gpt-x", "provider": "openai"})
    assert r.status_code == 418


@pytest.mark.parametrize("path", ENDPOINTS)
def test_custom_base_header_rejected_on_public(tmp_path, past_check_request, path):
    h = {providers.BYOK_BASE_HEADER: "https://example.invalid/v1"}
    r = _client(_pub(tmp_path)).post(path, json={"question": "q", "model": "ds-v4"}, headers=h)
    assert r.status_code == 400 and _detail(r)["code"] == "custom_base_not_allowed"
    r = _client(_priv(tmp_path)).post(path, json={"question": "q", "model": "opus-5"}, headers=h)
    assert r.status_code == 418


@pytest.mark.parametrize("path", ENDPOINTS)
def test_private_unknown_model_keeps_old_string_detail(tmp_path, path):
    r = _client(_priv(tmp_path)).post(path, json={"question": "q", "model": "nope"})
    assert r.status_code == 422 and isinstance(_detail(r), str) and "unknown model" in _detail(r)


# ── check_request unit (defence in depth + pass-through) ─────────────────

def _ctx(tier, endpoint="ask", model=None, provider=None, headers=None, s=None):
    req = SimpleNamespace(headers=headers or {}, app=SimpleNamespace(state=SimpleNamespace(settings=s)))
    return SimpleNamespace(tier=tier, endpoint=endpoint, model=model, provider=provider, request=req)


def test_check_request_passes_none_ctx():
    instance.check_request(None, SimpleNamespace(dossier="on", corpus="study"))


@pytest.mark.parametrize("endpoint", ["ask_compare", "validate"])
def test_check_request_refuses_private_only_endpoints_on_public(endpoint):
    with pytest.raises(ServiceRefusal) as e:
        instance.check_request(_ctx("public", endpoint), None)
    assert e.value.status_code == 403 and e.value.detail["feature"] == endpoint
    instance.check_request(_ctx("private", endpoint), None)
