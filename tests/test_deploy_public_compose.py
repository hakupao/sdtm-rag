"""P3.2: 公开实例 compose / workflow 的失效安全属性 (静态检查, 不需要 docker)。"""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
PUB = yaml.safe_load((ROOT / "deploy/container/compose.public.yml").read_text())
PRIV = yaml.safe_load((ROOT / "deploy/container/compose.yml").read_text())
WF = yaml.safe_load((ROOT / ".gitea/workflows/sdtm-rag.yml").read_text())


def test_public_only_api_and_tier_pinned():
    assert set(PUB["services"]) == {"api"}
    assert PUB["services"]["api"]["environment"]["SDTM_RAG_INSTANCE"] == "public"
    assert PUB["name"] != PRIV["name"]


def test_public_no_host_exposure_or_escape_hatches():
    api = PUB["services"]["api"]
    for k in ("ports", "env_file", "network_mode", "privileged", "cap_add", "profiles"):
        assert k not in api, k
    assert all(v["target"].startswith("/app/") for v in api["volumes"])
    assert "${APP_DIR" not in (ROOT / "deploy/container/compose.public.yml").read_text()


def test_public_mounts_disjoint_from_private_and_literal():
    pub = {v["source"] for v in PUB["services"]["api"]["volumes"]}
    priv = {v["source"] for v in PRIV["x-common"]["volumes"]}
    assert not pub & priv
    assert all("$" not in s for s in pub)  # 路径写死, 漏设变量不会落回私有路径
    assert all(v["bind"]["create_host_path"] is False for v in PUB["services"]["api"]["volumes"])


def test_public_container_name_distinct():
    priv_names = {s["container_name"] for s in PRIV["services"].values()}
    assert PUB["services"]["api"]["container_name"] not in priv_names


def test_public_job_gated_and_separate():
    job = WF["jobs"]["deploy_public"]
    assert job["needs"] == "deploy"
    assert "vars.SDTM_RAG_PUBLIC_DEPLOY == 'true'" in job["if"]
    assert "refs/heads/main" in job["if"]
    runs = "\n".join(s.get("run", "") for s in job["steps"])
    assert "import server.instance" in runs  # 拒绝 P2 前镜像
    assert "Settings().instance == 'public'" in runs
    assert "compose.yml" not in runs.replace("compose.public.yml", "")  # 私有 compose 只经 env 传给路径一致性断言
    assert "inputs.deploy" in job["if"]  # 只构建模式不跑
    # 验收与失败停机在 deploy/kbsync/kbsync.py deploy-public 里 (tests/test_kbsync_deploy_public.py);
    # workflow 只留取消 / 超时的兜底
    assert "kbsync.py deploy-public" in runs
    stop = next(s for s in job["steps"] if "public-abort" in s.get("run", ""))
    assert "cancelled()" in stop["if"] and "failure()" in stop["if"]


def test_public_acceptance_script_checks_tier_and_closed_internals():
    import importlib.util

    spec = importlib.util.spec_from_file_location("kbsync", ROOT / "deploy/kbsync/kbsync.py")
    ks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ks)
    assert 'info.get("tier") != "public"' in ks.ACCEPT_PY and '"/openapi.json"' in ks.ACCEPT_PY
    assert "e.code != 404" in ks.ACCEPT_PY


def test_instance_env_case_variant_conflict_refused():
    from server.config import _check_instance_env

    _check_instance_env({"SDTM_RAG_INSTANCE": "public"})
    _check_instance_env({"SDTM_RAG_INSTANCE": "public", "sdtm_rag_instance": "public"})
    _check_instance_env({})
    with pytest.raises(RuntimeError):
        _check_instance_env({"SDTM_RAG_INSTANCE": "public", "sdtm_rag_instance": "private"})
