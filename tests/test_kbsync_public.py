"""公开数据根这条腿 (P3): kb-only 两层断言、路径一致性、基线镜像、embedding key 检查、两个数据根互不相通。
文件系统子命令在 tmp 目录上真跑, docker 用 tests/test_kbsync.py 的假实现。"""
from __future__ import annotations

import argparse
import base64
import copy
import json
import re
import sys
import types
from pathlib import Path

import pytest
import yaml

from tests import test_kbsync as _tk
from tests.test_kbsync import (
    NEW,
    OLD,
    TS,
    FakeDocker,
    _chroma,
    _cols,
    _gated_cand,
    _meta,
    _snapshot,
    ks,
)

root = _tk.root  # fixture: 私有布局的单个数据根 (chroma + meta + study/)

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "kbsync"
PUB_MODEL = json.loads((FIX / "compose_config_public.json").read_text())
PRIV_MODEL = json.loads((FIX / "compose_config_private.json").read_text())
PUB_ROOT = "/Volumes/DevSSD/deploy-data/sdtm-rag-public/data"
PUB_ENV = "/opt/sdtm-rag-public/.env"
PRIV_ROOT = "/Volumes/DevSSD/deploy-data/sdtm-rag/data"
CAND = ks.cand_names(NEW)[0]
KB = ks.KB_COLLECTION


def _cand_args(D: Path, *extra: str, base: str = "prod:1"):
    return ks.build_parser().parse_args(
        ["candidate", "--data-root", str(D), "--fp", NEW, "--ts", TS, "--ref", "kb-2026.11.28",
         "--a-commit", "c" * 40, "--prod-image", base, "--cand-image", "cand:1",
         "--env-file", "/opt/pub/.env", *extra])


def _failed_marker(D: Path) -> dict:
    return json.loads((D / f"chroma_failed_{NEW[:12]}_{TS}" / ks.MARKER).read_text())


def _via_cmds(fd: FakeDocker) -> list[str]:
    return [c[c.index("-") + 1] for c in fd.calls if "-i" in c and "-" in c]


# ── 第一层: 候选建完、过闸之前, 集合必须恰为 {sdtm_kb_v1} ────────────────────
def test_kb_only_candidate_with_only_kb_collection_passes(root):
    fd = FakeDocker(root, collections={CAND: _cols(4333)})
    assert ks.candidate(fd, _cand_args(root, "--kb-only")) == 0
    assert ks.is_gated_pass(root, NEW)
    assert fd.col_dirs == [root / CAND]  # 用候选镜像读候选目录本身


def test_kb_only_candidate_with_extra_collection_is_archived_before_gate(root, capsys):
    before = (root / "chroma" / "chroma.sqlite3").read_text()
    fd = FakeDocker(root, collections={CAND: _cols(4333, study_zz=(5, "d1"))})
    assert ks.candidate(fd, _cand_args(root, "--kb-only")) == 1
    assert _failed_marker(root)["reason"] == "kb_only_violation"
    assert (root / f"meta_failed_{NEW[:12]}_{TS}").is_dir()
    assert not (root / CAND).exists() and ks.detect(root, NEW)["result"] == "changed"
    assert (root / "chroma" / "chroma.sqlite3").read_text() == before
    # 评测本身满分: 拦下它的只能是集合断言; 而且在 gate 之前 (gate 一旦 PASS, 标记就写进去了)
    assert "gate" not in _via_cmds(fd) and _via_cmds(fd)[-1] == "fail"
    assert "study_zz" not in capsys.readouterr().out  # 只报计数, 不报集合名


def test_candidate_records_the_baseline_image_tag_next_to_its_id(root):
    fd = FakeDocker(root, collections={CAND: _cols(4333)})
    a = _cand_args(root, "--kb-only", "--prod-image-ref", "registry/sdtm-rag:" + "a" * 40, base="sha256:" + "f" * 64)
    assert ks.candidate(fd, a) == 0
    mk = ks.read_marker(root / CAND)
    assert mk["prod_image"] == "sha256:" + "f" * 64 and mk["prod_image_ref"] == "registry/sdtm-rag:" + "a" * 40
    (root / CAND).rename(root / "moved")
    fd2 = FakeDocker(root, collections={CAND: _cols(4333)})
    assert ks.candidate(fd2, _cand_args(root, "--kb-only")) == 0 and "prod_image_ref" not in ks.read_marker(root / CAND)


def test_without_kb_only_the_same_candidate_passes(root):
    """私有腿 (不带 --kb-only): 同一份含非 KB 集合的候选照常过闸 —— 上一条的拒绝来自 --kb-only, 不是别处。"""
    fd = FakeDocker(root, collections={CAND: _cols(4333, study_zz=(5, "d1"))})
    assert ks.candidate(fd, _cand_args(root)) == 0
    assert fd.col_dirs == []


@pytest.mark.parametrize("cols", [{}, {"other": {"count": 3, "digest": "d"}}])
def test_kb_only_candidate_without_kb_collection_is_violation(root, cols):
    fd = FakeDocker(root, collections={CAND: cols})
    assert ks.candidate(fd, _cand_args(root, "--kb-only")) == 1
    assert _failed_marker(root)["reason"] == "kb_only_violation"


def test_kb_only_candidate_unreadable_collections_fails_closed(root):
    fd = FakeDocker(root, collections={CAND: None})  # 读集合的容器 rc != 0
    assert ks.candidate(fd, _cand_args(root, "--kb-only")) == 1
    assert _failed_marker(root)["reason"] == "kb_only_unreadable"
    assert not ks.is_gated_pass(root, NEW)


# ── 第二层: 换入时线上与换入源都不得有非 KB 集合 ─────────────────────────────
def _swap_args(D: Path, *extra: str):
    return ks.build_parser().parse_args(
        ["deploy-swap", "--data-root", str(D), "--image", "img:1", "--target-fp", NEW, "--ts", TS,
         "--chromadb-version", "1.5.9", *extra])


def test_kb_only_swap_refuses_when_both_sides_hold_the_same_non_kb_collection(root):
    """数据故意选成"两边相同": 私有守卫 (线上 == 换入源) 放行, 只有 kb-only 断言能拦。"""
    _gated_cand(root)
    same = {"chroma": _cols(10, study_zz=(5, "d1")), CAND: _cols(12, study_zz=(5, "d1"))}
    before = _snapshot(root)
    assert ks.deploy_swap(FakeDocker(root, collections=same), _swap_args(root, "--kb-only")) == 1
    assert _snapshot(root) == before
    assert ks.deploy_swap(FakeDocker(root, collections=same), _swap_args(root)) == 0  # 不带 kb-only: 换入


def test_kb_only_swap_allows_clean_roots(root):
    _gated_cand(root)
    fd = FakeDocker(root, collections={"chroma": _cols(4329), CAND: _cols(4333)})
    assert ks.deploy_swap(fd, _swap_args(root, "--kb-only")) == 0
    assert (root / "chroma" / "chroma.sqlite3").read_text() == "cand"


def test_kb_only_swap_refuses_source_without_kb_collection(root):
    _gated_cand(root)
    before = _snapshot(root)
    fd = FakeDocker(root, collections={"chroma": _cols(4329), CAND: {}})
    assert ks.deploy_swap(fd, _swap_args(root, "--kb-only")) == 1
    assert _snapshot(root) == before
    assert ks.deploy_swap(FakeDocker(root, collections={"chroma": _cols(4329), CAND: {}}), _swap_args(root)) == 0


# ── 红线不变量: 一次调用只有一个数据根 ───────────────────────────────────────
def _subcommands() -> dict[str, argparse.ArgumentParser]:
    ap = ks.build_parser()
    return next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction)).choices


# 能指向宿主机路径的参数只有这些; 其中只有 data_root 是数据根
PATH_ARGS = {
    "data_root": "唯一的数据根",
    "env_file": "只读挂给容器的 env 文件",
    "kb_root": "fingerprint: 仓内 KB 目录 (该子命令没有 data_root)",
    "compose_file": "公开 compose 文件 (只解析)",
    "private_compose_file": "私有 compose 文件 (只解析, 取挂载源作比对)",
    "touched_file": "job 工作目录里的标记文件 (只记「正式容器已被动过」, 不是数据)",
    "expect_source": "swap: 期望的换入目录名, 只与算出来的名字比较, 不用来拼路径",
}


def test_no_subcommand_accepts_two_data_roots():
    subs = _subcommands()
    assert len(subs) >= 27, "抽不到子命令时下面的断言会变成永真"
    pathlike = re.compile(r"root|dir|path|file|src|dst|source|dest|from|target_root|mount")
    with_root = 0
    for name, sp in subs.items():
        opts = [a for a in sp._actions if a.option_strings]
        roots = [a for a in opts if a.dest == "data_root"]
        assert len(roots) <= 1, name
        with_root += len(roots)
        for a in roots:
            assert a.nargs is None and a.option_strings == ["--data-root"], name  # 不能一次给多个
        suspicious = {a.dest for a in opts if pathlike.search(a.dest)}
        assert suspicious <= set(PATH_ARGS), (name, suspicious - set(PATH_ARGS))
        if "kb_root" in suspicious:
            assert not roots, name
        assert not [a for a in sp._actions if not a.option_strings and a.dest != "help"], f"{name}: 不要位置参数"
    assert with_root >= 21


@pytest.mark.parametrize("name", ["../other/chroma", "a/b", "..", "", "x\\y"])
def test_guard_copy_refuses_names_that_can_leave_the_data_root(root, name):
    _chroma(root.parent / "other" / "chroma", OLD, "outside")  # 越界路径真实存在: 拦下它的只能是名字校验
    before = _snapshot(root)
    with pytest.raises(SystemExit):
        ks.guard_copy(root, ["chroma", name], TS)
    assert _snapshot(root) == before


@pytest.fixture
def two_roots(tmp_path):
    """私有根 (含 study 集合与 study 目录) 与公开根 (只有 KB) 并排放在同一个上级目录下, 与生产布局一致。"""
    base = tmp_path / "deploy-data"
    priv, pub = base / "sdtm-rag" / "data", base / "sdtm-rag-public" / "data"
    _chroma(priv / "chroma", OLD, "PRIVATE-chroma-with-study")
    _meta(priv / "meta", "private-meta")
    (priv / "study" / "st01").mkdir(parents=True)
    (priv / "study" / "st01" / "catalog.json").write_text("PRIVATE-study")
    _chroma(pub / "chroma", OLD, "public-chroma")
    _meta(pub / "meta", "public-meta")
    (pub / "quota.sqlite").write_text("quota")
    return priv, pub


def _bind_sources(fd: FakeDocker) -> list[Path]:
    out = []
    for call in fd.calls:
        for i, a in enumerate(call):
            if a == "--mount":
                spec = dict(kv.partition("=")[::2] for kv in call[i + 1].split(","))
                if spec.get("type") == "bind":
                    out.append(Path(spec["src"]))
    return out


def assert_no_bind_reaches(fd: FakeDocker, forbidden: Path, min_mounts: int) -> None:
    """任何容器的 bind 源都不能等于 forbidden、在它之下、或是它的上级 (共同上级目录就是一条通道)。"""
    srcs = _bind_sources(fd)
    assert len(srcs) >= min_mounts, f"只抓到 {len(srcs)} 个挂载, 断言会变成永真"
    bad = [s for s in srcs if s == forbidden or forbidden in s.parents or s in forbidden.parents]
    assert not bad, bad


def test_public_leg_never_mounts_or_touches_the_private_root(two_roots):
    priv, pub = two_roots
    before_priv = _snapshot(priv)
    fd = FakeDocker(pub, collections={CAND: _cols(4333)})
    assert ks.candidate(fd, _cand_args(pub, "--kb-only")) == 0
    fd.cols = {"chroma": _cols(4329), CAND: _cols(4333)}
    assert ks.deploy_swap(fd, _swap_args(pub, "--kb-only")) == 0
    assert ks.restore(pub)["restored"] is True
    assert_no_bind_reaches(fd, priv, min_mounts=20)
    assert _snapshot(priv) == before_priv
    text = "\n".join(f"{k}={v}" for k, v in _snapshot(pub).items())
    assert "PRIVATE" not in text and "study" not in text  # 公开根里没有来自私有根的任何东西


def test_bind_guard_detects_a_common_parent_mount(two_roots):
    """上一条所用断言自身的反例: 挂上两个数据根的共同上级目录, 必须被认出来。"""
    priv, pub = two_roots
    fd = FakeDocker(pub)
    fd.calls.append(["run", "--mount", f"type=bind,src={pub.parent.parent},dst=/x", "img"])
    with pytest.raises(AssertionError):
        assert_no_bind_reaches(fd, priv, min_mounts=1)


# ── 基线镜像: 镜像内 KB 指纹必须等于数据根的 stamp ───────────────────────────
def test_stamp_reports_live_fingerprint(root):
    assert ks.stamp(root) == {"fp": OLD}
    (root / "chroma" / ks.STAMP).unlink()
    assert ks.stamp(root) == {"fp": None}


def test_baseline_prefers_public_container_image_when_it_pairs_with_the_data(root):
    fd = FakeDocker(root)
    fd.image_fps = {"pub:old": OLD, "priv:new": NEW}
    assert ks.baseline_image(fd, str(root), ["pub:old", "priv:new"], "priv:new")[0] == "pub:old"


def test_baseline_skips_an_image_whose_kb_differs_from_the_data(root):
    """公开部署失败停机后, 公开容器的镜像是没通过的新镜像, 与退回的旧数据不配对 —— 不能拿它当基线。"""
    fd = FakeDocker(root)
    fd.image_fps = {"pub:failed-new": NEW, "priv:old": OLD}
    assert ks.baseline_image(fd, str(root), ["pub:failed-new", "priv:old"], "priv:old")[0] == "priv:old"


def test_baseline_without_public_container_falls_back_to_private_image(root):
    fd = FakeDocker(root)
    fd.image_fps = {"priv:old": OLD}
    assert ks.baseline_image(fd, str(root), ["", "priv:old"], "priv:old")[0] == "priv:old"


def test_baseline_candidate_never_mounts_the_data_root_before_it_pairs(root):
    """stamp 由可信镜像 (私有线上镜像) 去读; 候选基线镜像只跑不挂任何目录的指纹脚本。"""
    fd = FakeDocker(root)
    fd.image_fps = {"manual:1": OLD}
    assert ks.baseline_image(fd, str(root), ["manual:1"], "priv-live:1")[0] == "manual:1"
    with_mount = [c for c in fd.calls if "--mount" in c]
    assert len(with_mount) == 1 and "priv-live:1" in with_mount[0] and "manual:1" not in with_mount[0]
    assert [c for c in fd.calls if "manual:1" in c and ks.IMAGE_FP_PY in c]


def test_baseline_image_not_on_this_machine_is_never_run(root):
    """不在本机的镜像不能拿来跑 (docker run 会去拉取): 直接跳过。"""
    fd = FakeDocker(root)
    fd.image_fps = {"remote:evil": OLD, "priv:new": NEW}
    fd.absent_images = {"remote:evil"}
    img, _, rows = ks.baseline_image(fd, str(root), ["remote:evil", "priv:new"], "priv:new")
    assert img is None and rows[0] == ("remote:evil", "不在本机")
    assert not [c for c in fd.calls if c[0] == "run" and "remote:evil" in c]


def test_baseline_fails_explicitly_when_no_image_pairs(root, capsys):
    fd = FakeDocker(root)
    fd.image_fps = {"pub:x": NEW, "priv:y": NEW}
    argv = ["baseline-image", "--data-root", str(root), "--via-image", "priv:y", "--images", "pub:x", "priv:y"]
    assert ks.main(argv, docker=fd) == 1
    cap = capsys.readouterr()
    assert cap.out == "" and "没有与数据根 chroma" in cap.err  # stdout 为空: workflow 不会拿到一个镜像名
    fd.image_fps = {"pub:x": OLD, "priv:y": NEW}
    assert ks.main(argv, docker=fd) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "pub:x"


def test_baseline_unknown_fingerprint_or_missing_stamp_never_pairs(root):
    fd = FakeDocker(root)  # 镜像指纹读不出 → unknown
    assert ks.baseline_image(fd, str(root), ["old:1"], "old:1")[0] is None
    (root / "chroma" / ks.STAMP).unlink()
    fd.image_fps = {"a:1": OLD}
    assert ks.baseline_image(fd, str(root), ["a:1"], "a:1")[0] is None


# ── embedding key 检查 ───────────────────────────────────────────────────
def _key_argv():
    return ["key-check", "--image", "cand:1", "--env-file", PUB_ENV]


def test_key_check_ok(root, capsys):
    fd = FakeDocker(root)
    fd.key_results = [(0, 'noise\n{"ok": true, "category": "ok", "model": "text-embedding-3-small", "dim": 1536}')]
    assert ks.main(_key_argv(), docker=fd) == 0
    assert "检查通过" in capsys.readouterr().out
    call = next(c for c in fd.calls if ks.KEY_CHECK_PY in c)
    assert f"type=bind,src={PUB_ENV},dst=/app/.env,readonly" in call  # 用的是公开站的 env 文件, 只读
    assert len(_bind_sources(fd)) == 1  # 不挂任何数据根


@pytest.mark.parametrize("cat", ["key_invalid", "quota_exhausted", "key_forbidden", "model_not_found", "other"])
def test_key_check_failure_is_a_failure_with_a_named_cause(root, capsys, cat):
    fd = FakeDocker(root)
    fd.key_results = [(1, json.dumps({"ok": False, "category": cat, "status": 401, "error_class": "E"}))]
    assert ks.main(_key_argv(), docker=fd) == 1
    out = capsys.readouterr().out
    assert cat in out and ks.KEY_HINTS[cat] in out and PUB_ENV in out
    assert "sk-proj" not in out and len(fd.key_results) == 0  # 只调一次, 不重试


def test_key_check_without_result_fails_closed_and_scrubs_stderr(root, capsys):
    fd = FakeDocker(root)
    fd.key_results = [(125, "")]  # 容器没跑起来 (env 文件不存在等)
    assert ks.main(_key_argv(), docker=fd) == 1
    out = capsys.readouterr().out
    assert "no_result" in out and "sk-proj" not in out and "<已隐去>" in out
    fd.key_results = [(1, '{"ok": true, "category": "ok"}')]  # 自称 ok 但 rc != 0: 不信
    assert ks.key_check(fd, "cand:1", PUB_ENV)["category"] == "no_result"
    fd.key_results = [(0, '{"ok": false, "category": "key_invalid"}')]  # rc 0 但自称失败: 不信
    assert ks.key_check(fd, "cand:1", PUB_ENV)["ok"] is False


def test_key_check_retries_only_plain_rate_limit(root):
    slept = []
    rl = (1, '{"ok": false, "category": "rate_limited", "status": 429}')
    fd = FakeDocker(root)
    fd.key_results = [rl, (0, '{"ok": true, "category": "ok", "model": "m", "dim": 3}')]
    assert ks.key_check(fd, "cand:1", PUB_ENV, sleep=slept.append)["ok"] is True
    assert slept == [20]
    fd.key_results = [rl, rl, rl, rl]
    assert ks.key_check(fd, "cand:1", PUB_ENV, sleep=slept.append)["category"] == "rate_limited"
    assert len(fd.key_results) == 1  # 1 + 2 次重试后放弃


def _key_check_ns() -> dict:
    ns: dict = {"__name__": "kbsync_key_check"}
    exec(ks.KEY_CHECK_PY, ns)  # noqa: S102  (仓内常量, 与生产容器里跑的是同一段源码)
    return ns


def _exc(name: str, status: int | None, msg: str) -> Exception:
    return type(name, (Exception,), {"status_code": status})(msg)


@pytest.mark.parametrize("name,status,msg,want", [
    # 额度用尽与限流同为 429 + RateLimitError: 只有报文能区分, 额度必须先判
    ("RateLimitError", 429, "You exceeded your current quota, please check your plan", "quota_exhausted"),
    ("RateLimitError", 429, "error code: insufficient_quota", "quota_exhausted"),
    ("RateLimitError", 429, "Rate limit reached for requests", "rate_limited"),
    ("AuthenticationError", 401, "Incorrect API key provided: sk-proj-****abcd", "key_invalid"),
    ("OpenAIError", None, "The api_key client option must be set", "other"),
    ("AuthenticationError", None, "The api_key client option must be set", "key_invalid"),
    ("PermissionDeniedError", 403, "project does not have access to model", "key_forbidden"),
    ("NotFoundError", 404, "model not found", "model_not_found"),
    ("APIConnectionError", None, "connection error", "other"),
])
def test_key_check_script_classifies_provider_errors(name, status, msg, want):
    res = _key_check_ns()["classify"](_exc(name, status, msg))
    assert res["category"] == want and res["ok"] is False
    assert "sk-" not in json.dumps(res) and msg not in json.dumps(res)  # 报错原文不出现在结果里


def test_key_check_script_main_uses_configured_embedding_model(monkeypatch):
    from server.config import settings

    seen = {}

    def embedding(model, input):
        seen["model"] = model
        return types.SimpleNamespace(data=[{"embedding": [0.0] * 7}])

    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(embedding=embedding))
    ns = _key_check_ns()
    assert ns["main"]() == {"ok": True, "category": "ok", "model": settings.embedding_model, "dim": 7}
    assert seen["model"] == settings.embedding_model

    def boom(model, input):
        raise _exc("RateLimitError", 429, "You exceeded your current quota")

    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(embedding=boom))
    assert _key_check_ns()["main"]()["category"] == "quota_exhausted"


# ── 候选某一步失败时的原因归类 (运行中途 key 失效 / 额度用尽) ─────────────────
@pytest.mark.parametrize("text,want", [
    ("litellm.RateLimitError: RateLimitError: OpenAIException - You exceeded your current quota", "quota_exhausted"),
    ("openai.RateLimitError: Error code: 429 - {'error': {'code': 'insufficient_quota'}}", "quota_exhausted"),
    ("litellm.RateLimitError: Rate limit reached for text-embedding-3-small", "rate_limited"),
    ("litellm.AuthenticationError: OpenAIException - Incorrect API key provided", "key_invalid"),
    ("RuntimeError: VARIABLE_INDEX section map", None),
    ("", None),
])
def test_classify_failure(text, want):
    assert ks.classify_failure(text) == want


def test_candidate_step_failure_names_the_key_cause_and_hides_key_fragments(root, capsys):
    fd = FakeDocker(root, crash_cmd=lambda a: "scripts.ingest" in a)
    fd.crash_stderr = (b"Traceback...\nlitellm.RateLimitError: RateLimitError: OpenAIException - You exceeded your "
                       b"current quota (key sk-proj-AbCd1234****wxyz)")
    assert ks.candidate(fd, _cand_args(root, "--kb-only")) == 1
    assert _failed_marker(root)["reason"] == "ingest_rc1_quota_exhausted"
    out = capsys.readouterr().out
    assert "quota_exhausted" in out and ks.KEY_HINTS["quota_exhausted"] in out
    assert "sk-proj" not in out and "<已隐去>" in out


def _b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


# 假值都在运行时拼出来: 源码里不出现完整的密钥 / token 形状, 免得密钥扫描器对测试数据报警 (2026-11-28 被报过一次)。
# 拼出来的字符串与之前写死的逐字相同; 改这里时保持「每个假值至少拆成两段」。
_LETTERS = "".join(chr(ord("a") + i) for i in range(16))   # a..p
_DIGITS = "".join(str(i % 10) for i in range(1, 11))        # 1..9 再接 0
FAKE_SECRETS = [
    "sk-" + "proj-AbCd1234****wxyz",
    "sk-" + "ant-" + "api03-AbCdEf123456",
    "tvly-" + "e" * 32,
    "Authorization: " + "Bearer" + " abcdEFGH" + "12345678",
    "x-api-key: " + "abcdefgh" + "12345678",
    "OPENAI_API_KEY=" + "ZZZZzzzz" + "99998888",
    '"api_key": "' + "QQQQqqqq" + '11112222"',
    "AIza" + "Sy" * 18,
    "Authorization: Basic " + base64.b64encode(b"user:password").decode(),
    "access_token=" + "abcd+efgh" + "/ijkl==",
    "password: " + "hunter2" * 2,
    "secret=" + "AAAA/BBBB" + "+CCCC=",
    ".".join(_b64url(part) for part in ('{"a":"' + _LETTERS + '"}', '{"t":"' + _DIGITS + '"}', "signature")),  # JWT 的外形
]
assert len(FAKE_SECRETS) == 13  # 列表被清空时 parametrize 只会变成 1 条 skip, 不会红


@pytest.mark.parametrize("secret", FAKE_SECRETS)
def test_scrub_hides_key_shapes(secret):
    out = ks.scrub(f"Traceback: provider said {secret} is wrong")
    assert "<已隐去>" in out and secret.split()[-1].strip('"') not in out


def test_scrub_leaves_ordinary_diagnostics_alone():
    for text in ("RuntimeError: VARIABLE_INDEX section map", "n_questions 139 < 140", "bind source path does not exist: /opt/x/.env"):
        assert ks.scrub(text) == text


@pytest.mark.parametrize("argv", [
    ["detect", "--data-root", "{D}", "--fp", "../../../etc"],
    ["prepare", "--data-root", "{D}", "--fp", "a" * 63],
    ["guard-clean", "--data-root", "{D}", "--ts", "../x"],
    ["accept-stage", "--data-root", "{D}", "--ts", "20261128T0000", "--chroma", "chroma", "--meta", "meta"],
])
def test_fingerprint_and_timestamp_are_validated_before_they_reach_a_path(root, argv):
    before = _snapshot(root)
    with pytest.raises(SystemExit):
        ks.main([a.replace("{D}", str(root)) for a in argv])
    assert _snapshot(root) == before


def test_candidate_refuses_a_fingerprint_that_is_not_hex(root):
    fd = FakeDocker(root)
    a = _cand_args(root)
    a.fp = "/../../../ab"
    with pytest.raises(SystemExit):
        ks.candidate(fd, a)
    assert fd.calls == []  # 还没有任何容器被起


def test_restore_refuses_a_journal_that_points_outside_the_data_root(root):
    _chroma(root.parent / "outside" / "chroma", NEW, "outside")  # 越界目标真实存在
    (root / ks.JOURNAL).write_text(json.dumps({
        "ts": TS, "target_fp": NEW, "old_fp": OLD, "source_chroma": "x", "source_meta": "y",
        "prev_chroma": "../outside/chroma", "prev_meta": "meta_prev"}))
    before = _snapshot(root)
    with pytest.raises(SystemExit):
        ks.restore(root)
    assert _snapshot(root) == before and (root.parent / "outside" / "chroma").is_dir()


def test_swap_refuses_when_the_source_is_not_the_one_that_was_accepted(root):
    _gated_cand(root)
    before = _snapshot(root)
    with pytest.raises(SystemExit, match="换入源变了"):
        ks.swap(root, NEW, TS, "1.5.9", expect_source="chroma_prev_something")
    assert _snapshot(root) == before
    fd = FakeDocker(root, collections={"chroma": _cols(4329), CAND: _cols(4333)})
    assert ks.deploy_swap(fd, _swap_args(root, "--kb-only")) == 0  # 不指定时照常 (私有路径)


def test_swap_guard_refuses_a_different_source_than_expected(root):
    _gated_cand(root)
    fd = FakeDocker(root, collections={"chroma": _cols(4329), CAND: _cols(4333)})
    a = _swap_args(root, "--kb-only")
    a.expect_source = "chroma_prev_other"
    assert ks.swap_guard(fd, a, TS) is False and fd.col_dirs == []
    a.expect_source = CAND
    assert ks.swap_guard(fd, a, TS) is True


def test_stage_commands_refuse_a_shallow_data_root(root):
    fd = FakeDocker(root)
    with pytest.raises(RuntimeError, match="层级太浅"):
        ks.via(fd, "img:1", "/data", ["accept-clean", "--data-root", "/data"])
    with pytest.raises(RuntimeError, match="层级太浅"):
        ks.via(fd, "img:1", "/Volumes/x", ["accept-stage", "--data-root", "/Volumes/x"])
    assert fd.calls == []


def test_candidate_step_failure_without_key_cause_keeps_plain_reason(root):
    fd = FakeDocker(root, crash_cmd=lambda a: "scripts.ingest" in a)
    assert ks.candidate(fd, _cand_args(root)) == 1
    assert _failed_marker(root)["reason"] == "ingest_rc1"


# ── 路径一致性: 数据根 / env 文件 == 公开 compose 的挂载源, 且与私有挂载源不重叠 ──
def test_paths_consistent_with_real_compose_models():
    assert ks.paths_problems(PUB_MODEL, PRIV_MODEL, PUB_ROOT, PUB_ENV) == []
    assert ks.paths_problems(PUB_MODEL, PRIV_MODEL, PUB_ROOT + "/", PUB_ENV) == []  # 尾部斜杠不算不一致


def _with_mount(model: dict, target: str, source: str) -> dict:
    m = copy.deepcopy(model)
    for v in m["services"]["api"]["volumes"]:
        if v["target"] == target:
            v["source"] = source
    return m


@pytest.mark.parametrize("data_root,env_file,needle", [
    (PUB_ROOT + "-other", PUB_ENV, "数据根"),
    (PUB_ROOT, "/opt/sdtm-rag/.env", "env 文件"),
    (PRIV_ROOT, PUB_ENV, "数据根"),
])
def test_paths_mismatch_with_public_compose_is_a_problem(data_root, env_file, needle):
    problems = ks.paths_problems(PUB_MODEL, PRIV_MODEL, data_root, env_file)
    assert problems and any(needle in p and "不一致" in p for p in problems)


@pytest.mark.parametrize("shared", [PRIV_ROOT, PRIV_ROOT + "/public", str(Path(PRIV_ROOT).parent)])
def test_paths_public_root_overlapping_private_root_is_a_problem(shared):
    """公开 compose 与 workflow 一起被改成指向私有根 (或其上下级): 两边"一致", 只有与私有 compose 的比对能拦。"""
    pub = _with_mount(PUB_MODEL, "/app/data", shared)
    problems = ks.paths_problems(pub, PRIV_MODEL, shared, PUB_ENV)
    assert problems and all("重叠" in p for p in problems)


def test_paths_stage_parent_overlapping_private_root_is_a_problem():
    """数据根本身与私有根不重叠, 但它的上一级 (验收副本所在, 部署时可写挂载) 是私有根的上级: 也算。"""
    root = str(Path(PRIV_ROOT).parent / "data-public")
    assert not ks._overlap(root, PRIV_ROOT)
    problems = ks.paths_problems(_with_mount(PUB_MODEL, "/app/data", root), PRIV_MODEL, root, PUB_ENV)
    assert len(problems) == 1 and "上一级目录" in problems[0] and "重叠" in problems[0]


def test_paths_any_extra_public_mount_pointing_at_private_data_is_a_problem():
    """将来给公开 api 加一个只读挂载、源在私有根里: 数据根 / env 都对得上, 也要拦 (只读挂载会原样带进临时容器)。"""
    pub = copy.deepcopy(PUB_MODEL)
    pub["services"]["api"]["volumes"].append(
        {"type": "bind", "source": PRIV_ROOT + "/study", "target": "/app/extra", "read_only": True})
    problems = ks.paths_problems(pub, PRIV_MODEL, PUB_ROOT, PUB_ENV)
    assert len(problems) == 1 and "/app/extra" in problems[0] and "重叠" in problems[0]
    pub["services"]["api"]["volumes"][-1]["source"] = "/opt/sdtm-rag-public/ca.pem"
    assert ks.paths_problems(pub, PRIV_MODEL, PUB_ROOT, PUB_ENV) == []
    # 公开 compose 里将来若有第二个服务, 它的挂载也查
    pub["services"]["sidecar"] = {"volumes": [{"type": "bind", "source": PRIV_ROOT, "target": "/data"}]}
    problems = ks.paths_problems(pub, PRIV_MODEL, PUB_ROOT, PUB_ENV)
    assert len(problems) == 1 and "sidecar" in problems[0] and "重叠" in problems[0]


def test_paths_public_env_equal_to_private_env_is_a_problem():
    pub = _with_mount(PUB_MODEL, "/app/.env", "/opt/sdtm-rag/.env")
    assert any("env 文件" in p and "重叠" in p for p in ks.paths_problems(pub, PRIV_MODEL, PUB_ROOT, "/opt/sdtm-rag/.env"))


def test_paths_sibling_directories_do_not_overlap():
    assert not ks._overlap("/x/sdtm-rag/data", "/x/sdtm-rag-public/data")
    assert not ks._overlap("/x/data", "/x/data2")
    assert ks._overlap("/x/data", "/x/data/") and ks._overlap("/x", "/x/data") and ks._overlap("/x/data/a", "/x/data")


def test_paths_unparseable_models_fail_closed():
    assert ks.paths_problems({"services": {}}, PRIV_MODEL, PUB_ROOT, PUB_ENV)
    empty_priv = {"services": {"api": {"volumes": []}}}
    assert any("私有 compose" in p for p in ks.paths_problems(PUB_MODEL, empty_priv, PUB_ROOT, PUB_ENV))
    no_data = copy.deepcopy(PUB_MODEL)
    no_data["services"]["api"]["volumes"] = [v for v in no_data["services"]["api"]["volumes"] if v["target"] != "/app/data"]
    assert any("/app/data" in p for p in ks.paths_problems(no_data, PRIV_MODEL, PUB_ROOT, PUB_ENV))


def _paths_argv(data_root=PUB_ROOT, env_file=PUB_ENV):
    return ["paths-check", "--data-root", data_root, "--env-file", env_file,
            "--compose-file", "deploy/container/compose.public.yml",
            "--private-compose-file", "deploy/container/compose.yml"]


def test_paths_check_cli(root, capsys):
    fd = FakeDocker(root)
    fd.compose_models = {"compose.public.yml": PUB_MODEL, "compose.yml": PRIV_MODEL}
    assert ks.main(_paths_argv(), docker=fd) == 0
    assert ks.main(_paths_argv(data_root=PRIV_ROOT), docker=fd) == 1
    assert "拒绝继续" in capsys.readouterr().out
    assert not _bind_sources(fd)  # 只解析 compose, 不挂载任何目录
    fd.compose_models = {"compose.yml": PRIV_MODEL}  # 公开 compose 解析失败
    with pytest.raises(RuntimeError):
        ks.main(_paths_argv(), docker=fd)


def test_compose_fixtures_match_the_compose_files():
    """fixture 是在部署机上 `docker compose config --format json` 的真实输出 (只读采集)。compose 文件改了挂载 /
    环境变量 / 容器名之后须重新采集:
      cat deploy/container/compose.public.yml | ssh <mini> '... limactl shell deploy -- \\
        sudo env IMAGE_TAG=abc docker compose -f - config --format json' > tests/fixtures/kbsync/compose_config_public.json
    (私有: compose.yml, IMAGE_TAG=x, 存为 compose_config_private.json)"""
    for fname, model in (("compose.public.yml", PUB_MODEL), ("compose.yml", PRIV_MODEL)):
        src = yaml.safe_load((ROOT / "deploy/container" / fname).read_text())
        assert model["name"] == src["name"]
        assert set(model["services"]) == set(src["services"])
        for svc, want in src["services"].items():
            got = model["services"][svc]
            assert got["container_name"] == want["container_name"]
            mounts = [(v["source"], v["target"].replace("${APP_DIR:-/app}", "/app"), bool(v.get("read_only")))
                      for v in want["volumes"]]
            assert [(v["source"], v["target"], bool(v.get("read_only"))) for v in got["volumes"]] == mounts
            assert (got.get("environment") or {}) == (want.get("environment") or {})
            assert got["image"].rsplit(":", 1)[0] == want["image"].split(":${", 1)[0]
    assert PUB_MODEL["services"]["api"]["volumes"][0]["source"] == PUB_ROOT
    assert PUB_MODEL["services"]["api"]["volumes"][1]["source"] == PUB_ENV
