"""deploy/kbsync/kbsync.py (step 1.9): 文件系统子命令在 tmp 目录上真跑, docker 用假实现。"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
from pathlib import Path

import pytest

_P = Path(__file__).resolve().parents[1] / "deploy" / "kbsync" / "kbsync.py"
_spec = importlib.util.spec_from_file_location("kbsync", _P)
ks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ks)

OLD = "a" * 64
NEW = "b" * 64
TS = "20261126T010203Z"
CV = "1.5.9"  # chromadb 版本


def _chroma(d: Path, fp: str | None, payload: str = "x") -> Path:
    d.mkdir(parents=True)
    (d / "chroma.sqlite3").write_text(payload)
    if fp:
        (d / ks.STAMP).write_text(f"kb_commit_sha=zzz\n{ks.STAMP_KEY}={fp}\ningested_at=t\n")
    return d


def _meta(d: Path, txt: str = "old-meta") -> Path:
    d.mkdir(parents=True)
    (d / "meta.yaml").write_text(txt)
    return d


@pytest.fixture
def root(tmp_path):
    D = tmp_path / "data"
    _chroma(D / "chroma", OLD, "prod")
    _meta(D / "meta")
    (D / "meta" / "implicit_relations.json").write_text("sib")
    (D / "study").mkdir()
    return D


def _snapshot(D: Path) -> dict[str, str]:
    return {str(p.relative_to(D)): (p.read_text() if p.is_file() else "<dir>") for p in sorted(D.rglob("*"))}


def _results(scores: dict[str, float], avg: float | None = None) -> str:
    if avg is None:
        avg = sum(scores.values()) / len(scores) if scores else 0.0
    return json.dumps({"summary": {"source_recall_avg": avg},
                       "results": [{"id": k, "source_recall": v} for k, v in scores.items()]})


def _gated_cand(D: Path, fp: str = NEW, verdict: str = "PASS", chromadb: str = CV) -> Path:
    c, m = ks.cand_names(fp)
    d = _chroma(D / c, fp, "cand")
    (d / ks.MARKER).write_text(json.dumps({"fingerprint": fp, "verdict": verdict, "chromadb": chromadb}))
    _meta(D / m, "new-meta")
    return d


# ── detect ────────────────────────────────────────────────────────────────
def test_detect_same_is_noop(root):
    assert ks.detect(root, OLD) == {"result": "same"}


def test_detect_changed(root):
    assert ks.detect(root, NEW)["result"] == "changed"


def test_detect_already_gated(root):
    _gated_cand(root)
    assert ks.detect(root, NEW)["result"] == "gated"


def test_detect_journal_pending(root):
    _gated_cand(root)
    (root / ks.JOURNAL).write_text("{}")
    assert ks.detect(root, NEW) == {"result": "journal_pending"}
    assert ks.detect(root, OLD) == {"result": "journal_pending"}


def test_detect_failed_marker_is_not_gated(root):
    _gated_cand(root, verdict="FAIL")
    assert ks.detect(root, NEW)["result"] == "changed"


# ── gate ──────────────────────────────────────────────────────────────────
BASE = {f"q{i:03d}": 1.0 for i in range(1, 141)}


def _prepared(D: Path, cand_scores: dict[str, float], ingest_fp: str = NEW, base=None,
              cand_avg: float | None = None) -> Path:
    ks.prepare(D, NEW, TS)
    c, m = ks.cand_names(NEW)
    d = D / c
    (d / ks.STAMP).write_text(f"{ks.STAMP_KEY}={ingest_fp}\n")
    (d / ks.EVAL_DIR / "baseline.json").write_text(_results(base or BASE))
    (d / ks.EVAL_DIR / "candidate.json").write_text(_results(cand_scores, cand_avg))
    return d


def test_prepare_copies_prod_and_skips_old_gate_files(root):
    (root / "chroma" / ks.MARKER).write_text("{}")
    (root / "chroma" / ks.EVAL_DIR).mkdir()
    (root / "chroma" / ks.EVAL_DIR / "old.json").write_text("{}")
    ks.prepare(root, NEW, TS)
    c, m = ks.cand_names(NEW)
    assert (root / c / "chroma.sqlite3").read_text() == "prod"
    assert not (root / c / ks.MARKER).exists()
    assert list((root / c / ks.EVAL_DIR).iterdir()) == []
    assert (root / m / "meta.yaml").read_text() == "old-meta"


def test_meta_sibling_files_survive_prepare_build_meta_swap_restore(root):
    ks.prepare(root, NEW, TS)
    c, m = ks.cand_names(NEW)
    assert (root / m / "implicit_relations.json").read_text() == "sib"
    (root / m / "meta.yaml").write_text("new-meta")  # = build_meta
    (root / c / ks.STAMP).write_text(f"{ks.STAMP_KEY}={NEW}\n")
    (root / c / ks.MARKER).write_text(json.dumps({"fingerprint": NEW, "verdict": "PASS", "chromadb": CV}))
    ks.swap(root, NEW, TS, CV)
    assert (root / "meta" / "meta.yaml").read_text() == "new-meta"
    assert (root / "meta" / "implicit_relations.json").read_text() == "sib"
    ks.restore(root)
    assert (root / "meta" / "meta.yaml").read_text() == "old-meta"
    assert (root / "meta" / "implicit_relations.json").read_text() == "sib"


def test_prepare_archives_stale_candidate_never_deletes(root):
    _gated_cand(root, verdict="FAIL")
    res = ks.prepare(root, NEW, TS)
    assert res["archived_stale"] == [f"chroma_failed_{NEW[:12]}_{TS}_stale", f"meta_failed_{NEW[:12]}_{TS}_stale"]
    assert (root / res["archived_stale"][0] / "chroma.sqlite3").read_text() == "cand"


def test_gate_one_regression_passes(root):
    _prepared(root, {**BASE, "q003": 0.5})
    mk = ks.gate(root, NEW, 1, TS, {"ref": "kb-2026.11.26"})
    assert mk["verdict"] == "PASS", mk
    assert mk["regressed_ids"] == ["q003"]
    assert ks.is_gated_pass(root, NEW)


def test_gate_two_regressions_fail_and_archive(root):
    _prepared(root, {**BASE, "q003": 0.5, "q004": 0.0})
    mk = ks.gate(root, NEW, 1, TS, {})
    assert mk["verdict"] == "FAIL", mk
    assert mk["regressed_ids"] == ["q003", "q004"]
    c, m = ks.cand_names(NEW)
    assert not (root / c).exists() and not (root / m).exists()
    failed = root / f"chroma_failed_{NEW[:12]}_{TS}"
    assert json.loads((failed / ks.MARKER).read_text())["verdict"] == "FAIL"
    assert (root / f"meta_failed_{NEW[:12]}_{TS}" / "meta.yaml").is_file()
    assert (root / "chroma" / "chroma.sqlite3").read_text() == "prod"


def test_gate_two_partial_regressions_fail_on_threshold_alone(root):
    # 回退发生在非满分题上: 满分地板 / avg 地板都不响, 只有逐题阈值能拦 (防地板掩护阈值变异)
    base = {**BASE, "q003": 0.8, "q004": 0.8}
    _prepared(root, {**base, "q003": 0.5, "q004": 0.5}, base=base)
    mk = ks.gate(root, NEW, 1, TS, {})
    assert mk["verdict"] == "FAIL" and mk["reason"] == "regressions 2 > 1", mk


def test_gate_one_partial_regression_passes(root):
    base = {**BASE, "q003": 0.8}
    _prepared(root, {**base, "q003": 0.5}, base=base)
    assert ks.gate(root, NEW, 1, TS, {})["verdict"] == "PASS"


def test_gate_missing_question_counts_as_regression(root):
    cand = dict(BASE)
    cand.pop("q001")
    cand.pop("q002")
    _prepared(root, cand)
    mk = ks.gate(root, NEW, 1, TS, {})
    assert mk["verdict"] == "FAIL" and mk["regressed_ids"] == ["q001", "q002"], mk
    assert "id_set_mismatch" in mk["reason"], mk


def test_gate_extra_candidate_id_fails_id_set(root):
    _prepared(root, {**BASE, "q999": 1.0})
    mk = ks.gate(root, NEW, 1, TS, {})
    assert mk["verdict"] == "FAIL" and mk["regressed_ids"] == [], mk
    assert mk["reason"].startswith("id_set_mismatch"), mk


def test_gate_too_few_questions_fails(root):
    small = {f"q{i:03d}": 1.0 for i in range(1, 140)}  # 139 题, 零回退
    _prepared(root, dict(small), base=small)
    mk = ks.gate(root, NEW, 1, TS, {})
    assert mk["verdict"] == "FAIL" and mk["reason"] == "n_questions 139 < 140", mk


def test_gate_full_hit_floor(root):
    # 放宽逐题阈值到 5, 2 题跌出满分 → 仍须被满分地板拦下
    _prepared(root, {**BASE, "q003": 0.5, "q004": 0.5})
    mk = ks.gate(root, NEW, 5, TS, {})
    assert mk["verdict"] == "FAIL" and mk["reason"] == "candidate_full 138 < baseline_full 140 - 1", mk


def test_gate_full_hit_floor_boundary_one_passes(root):
    _prepared(root, {**BASE, "q003": 0.5})
    mk = ks.gate(root, NEW, 5, TS, {})
    assert mk["verdict"] == "PASS", mk


def test_gate_absolute_avg_floor(root):
    # 基线本身已塌 (相对闸 0 回退) → 绝对地板 0.95 拦
    low = {k: (0.5 if i < 20 else 1.0) for i, k in enumerate(BASE)}
    _prepared(root, dict(low), base=low, cand_avg=0.94)
    mk = ks.gate(root, NEW, 5, TS, {})
    assert mk["verdict"] == "FAIL" and mk["reason"] == "candidate_avg 0.94 < 0.95", mk


def test_gate_avg_floor_boundary_passes(root):
    _prepared(root, dict(BASE), cand_avg=0.95)
    assert ks.gate(root, NEW, 1, TS, {})["verdict"] == "PASS"


def test_gate_missing_summary_avg_fails_closed(root):
    d = _prepared(root, dict(BASE))
    (d / ks.EVAL_DIR / "candidate.json").write_text(json.dumps({"results": json.loads(_results(BASE))["results"]}))
    mk = ks.gate(root, NEW, 1, TS, {})
    assert mk["verdict"] == "FAIL" and mk["reason"].startswith("eval_unreadable"), mk


def test_gate_empty_candidate_results_fail_closed(root):
    _prepared(root, {})
    mk = ks.gate(root, NEW, 1, TS, {})
    assert mk["verdict"] == "FAIL" and mk["reason"].startswith("eval_unreadable"), mk


def test_gate_fingerprint_mismatch_fails_even_with_perfect_eval(root):
    # 镜像仍是旧 KB → 灌出来的 stamp = 旧指纹; eval 全满分也必须拦
    _prepared(root, dict(BASE), ingest_fp=OLD)
    mk = ks.gate(root, NEW, 1, TS, {})
    assert mk["verdict"] == "FAIL", mk
    assert mk["reason"].startswith("fingerprint_mismatch"), mk


# ── predeploy / swap / restore ────────────────────────────────────────────
def test_predeploy_missing_candidate_fails_without_mutation(root):
    before = _snapshot(root)
    assert ks.predeploy_check(root, NEW)["decision"] == "missing"
    with pytest.raises(SystemExit):
        ks.swap(root, NEW, TS)
    assert _snapshot(root) == before


def test_predeploy_same_and_unknown(root):
    assert ks.predeploy_check(root, OLD)["decision"] == "same"
    assert ks.predeploy_check(root, "")["decision"] == "unknown"
    assert ks.predeploy_check(root, "unknown")["decision"] == "unknown"


def test_swap_order_and_restore_round_trip(root):
    _gated_cand(root)
    before = _snapshot(root)
    j = ks.swap(root, NEW, TS, CV)
    assert (root / "chroma" / "chroma.sqlite3").read_text() == "cand"
    assert (root / "meta" / "meta.yaml").read_text() == "new-meta"
    assert j["prev_chroma"] == f"chroma_prev_{OLD[:12]}_{TS}"
    assert (root / j["prev_chroma"] / "chroma.sqlite3").read_text() == "prod"
    assert (root / j["prev_meta"] / "meta.yaml").read_text() == "old-meta"
    assert ks.swap_status(root) == {"pending": True}
    assert ks.predeploy_check(root, NEW, CV)["decision"] == "journal_pending"
    assert ks.restore(root)["restored"] is True
    assert _snapshot(root) == before
    assert ks.restore(root) == {"restored": False}


def test_leftover_journal_refuses_swap_even_with_valid_prev(root):
    # job 取消/超时留下 journal; 目标指纹有完全合格的 chroma_prev → 仍须拒换, 且原因是 journal
    _chroma(root / f"chroma_prev_{NEW[:12]}_20261101T000000Z", NEW, "prev-new")
    _meta(root / f"meta_prev_{NEW[:12]}_20261101T000000Z", "prev-meta")
    (root / ks.JOURNAL).write_text("{}")
    before = _snapshot(root)
    assert ks.predeploy_check(root, NEW, CV)["decision"] == "journal_pending"
    assert ks.predeploy_check(root, OLD, CV)["decision"] == "journal_pending"  # same 也拦
    assert ks.predeploy_check(root, "", CV)["decision"] == "journal_pending"   # unknown/force 也拦
    with pytest.raises(SystemExit, match="journal_pending"):
        ks.swap(root, NEW, TS, CV)
    assert _snapshot(root) == before


def test_candidate_built_with_other_chromadb_is_not_swapped(root):
    _gated_cand(root, chromadb="1.4.0")
    chk = ks.predeploy_check(root, NEW, CV)
    assert chk["decision"] == "missing" and "chromadb" in chk["candidate_skipped"], chk
    assert ks.predeploy_check(root, NEW, "")["decision"] == "missing"  # 版本未知 = 不选候选
    assert ks.predeploy_check(root, NEW, "1.4.0")["decision"] == "swap"


def test_unknown_chromadb_on_both_sides_is_mismatch(root):
    _gated_cand(root, chromadb="unknown")
    assert ks.predeploy_check(root, NEW, "unknown")["decision"] == "missing"


def test_restore_refuses_and_keeps_journal_on_bad_end_state(root):
    _gated_cand(root)
    j = ks.swap(root, NEW, TS, CV)
    (root / j["prev_chroma"] / ks.STAMP).write_text(f"{ks.STAMP_KEY}={NEW}\n")  # 退回来的不是旧指纹
    with pytest.raises(SystemExit, match="终态不符"):
        ks.restore(root)
    assert (root / ks.JOURNAL).is_file()


def test_restore_after_partial_swap(root):
    # journal 已写, 只改名了第一步就断了
    _gated_cand(root)
    before = _snapshot(root)
    c, m = ks.cand_names(NEW)
    j = {"source_chroma": c, "source_meta": m, "prev_chroma": f"chroma_prev_{OLD[:12]}_{TS}",
         "prev_meta": f"meta_prev_{OLD[:12]}_{TS}", "old_fp": OLD}
    (root / ks.JOURNAL).write_text(json.dumps(j))
    (root / "chroma").rename(root / j["prev_chroma"])
    ks.restore(root)
    assert _snapshot(root) == before


def test_rollback_finds_retained_prev(root):
    _chroma(root / f"chroma_prev_{NEW[:12]}_20261101T000000Z", NEW, "prev-new")
    _meta(root / f"meta_prev_{NEW[:12]}_20261101T000000Z", "prev-meta")
    chk = ks.predeploy_check(root, NEW, CV)
    assert chk["decision"] == "swap" and chk["source_chroma"].startswith("chroma_prev_"), chk
    ks.swap(root, NEW, TS, CV)
    assert (root / "chroma" / "chroma.sqlite3").read_text() == "prev-new"
    ks.finish(root)
    assert ks.swap_status(root) == {"pending": False}


# ── prune ─────────────────────────────────────────────────────────────────
def test_prune_keeps_newest_two_and_spares_failed(root):
    for i in range(1, 5):
        ts = f"2026110{i}T000000Z"
        _chroma(root / f"chroma_prev_{OLD[:12]}_{ts}", OLD)
        _meta(root / f"meta_prev_{OLD[:12]}_{ts}")
    _chroma(root / f"chroma_failed_{NEW[:12]}_20261101T000000Z", NEW)
    res = ks.prune(root, 2)
    names = sorted(p.name for p in root.iterdir())
    assert [n for n in names if n.startswith("chroma_prev_")] == [
        f"chroma_prev_{OLD[:12]}_20261103T000000Z", f"chroma_prev_{OLD[:12]}_20261104T000000Z"]
    assert [n for n in names if n.startswith("meta_prev_")] == [
        f"meta_prev_{OLD[:12]}_20261103T000000Z", f"meta_prev_{OLD[:12]}_20261104T000000Z"]
    assert f"chroma_failed_{NEW[:12]}_20261101T000000Z" in names
    assert len(res["removed"]) == 4


# ── 编排 (假 docker) ──────────────────────────────────────────────────────
class FakeDocker(ks.Docker):
    def __init__(self, D: Path, cand_scores=None, ingest_fp=NEW, collections=None, image_fp_out=None,
                 crash_cmd=None):
        self.D, self.cand_scores, self.ingest_fp = D, cand_scores or dict(BASE), ingest_fp
        self.crash_cmd = crash_cmd
        self.crash_stderr = b"RuntimeError: VARIABLE_INDEX section map"
        self.col_dirs: list[Path] = []
        self.fail_fs: set[str] = set()
        self.cols = collections or {}
        self.image_fp_out = image_fp_out
        self.image_fps: dict[str, str] = {}      # 镜像 → 镜像内 KB 指纹 (优先于 image_fp_out)
        self.absent_images: set[str] = set()     # 不在本机的镜像 (image inspect rc != 0)
        self.key_results: list[tuple[int, str]] = []
        self.compose_models: dict[str, dict] = {}  # compose 文件名 → `compose config --format json` 的结果
        self.calls: list[list[str]] = []
        self.envs: list[dict | None] = []

    def _ok(self, out: str = "", rc: int = 0):
        return subprocess.CompletedProcess([], rc, out.encode(), b"")

    def run(self, args, *, input=None, env=None):
        self.calls.append(args)
        self.envs.append(env)
        if args[:2] == ["image", "inspect"]:
            return self._ok("", 1) if args[-1] in self.absent_images else self._ok("/app\n")
        if args[0] == "compose" and "config" in args:
            name = Path(args[args.index("-f") + 1]).name
            assert env and env.get("IMAGE_TAG"), "compose config 需要 IMAGE_TAG"
            return self._ok(json.dumps(self.compose_models[name])) if name in self.compose_models else self._ok("", 1)
        if "-i" in args and "-" in args:  # --via: 本进程内跑文件系统子命令
            fs = args[args.index("-") + 1:]
            if fs[0] in self.fail_fs:  # 先真跑 (留下半成品), 再报错
                with contextlib.redirect_stdout(io.StringIO()):
                    ks.main(fs)
                return subprocess.CompletedProcess([], 2, b"", b"boom")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                try:
                    rc = ks.main(fs)
                except SystemExit as e:
                    return subprocess.CompletedProcess([], 2, b"", str(e).encode())
            return self._ok(buf.getvalue(), rc)
        if "-c" in args and args[args.index("-c") + 1] == ks.COLLECTIONS_PY:
            src = Path(next(a for a in args if a.startswith("type=bind,src=")).split(",")[1][4:])
            image = args[args.index("-c") - 1]
            # 只许打开副本 (guard 副本 / 公开部署的验收副本); 例外: kb-only 用候选镜像打开它自己刚写出的候选目录
            staged = src.parent.parent.name.startswith(ks.ACCEPT_PREFIX)
            assert src.parent.name.startswith("kbsync_guard_") or staged or (
                src.name.startswith("chroma_cand_") and image == "cand:1"), f"集合核对必须在副本上: {src}"
            self.col_dirs.append(src)
            cols = self.cols["stage" if staged else src.name]
            return self._ok(json.dumps(cols)) if cols is not None else self._ok("", 1)
        if "-c" in args and args[args.index("-c") + 1] == ks.CHROMADB_VERSION_PY:
            return self._ok(CV + "\n")
        if "-c" in args and args[args.index("-c") + 1] == ks.IMAGE_FP_PY:
            image = args[args.index("-c") - 1]
            if image in self.image_fps:
                return self._ok(self.image_fps[image] + "\n")
            return self._ok(self.image_fp_out) if self.image_fp_out else self._ok("", 1)
        if "-c" in args and args[args.index("-c") + 1] == ks.KEY_CHECK_PY:
            rc, out = self.key_results.pop(0)
            return subprocess.CompletedProcess([], rc, out.encode(), b"Incorrect API key provided: sk-proj-****abcd")
        specs = [dict(kv.partition("=")[::2] for kv in args[i + 1].split(",")) for i, a in enumerate(args)
                 if a == "--mount"]
        mounts = {m["dst"]: m["src"] for m in specs}
        assert mounts["/app/data"] == str(self.D)
        assert any(m.endswith("dst=/app/data,readonly") for m in args), args
        chroma, meta = Path(mounts["/app/data/chroma"]), Path(mounts["/app/data/meta"])
        assert chroma.name.startswith("chroma_cand_"), chroma
        cmd = args[args.index("-m") + 1]
        if self.crash_cmd and self.crash_cmd(args):
            return subprocess.CompletedProcess([], 1, b"", self.crash_stderr)
        if cmd == "eval.run_eval":
            out = args[args.index("--output") + 1]
            target = chroma / Path(out).relative_to("data/chroma")
            scores = BASE if "baseline" in out else self.cand_scores
            target.write_text(_results(scores))
        elif cmd == "scripts.ingest":
            assert "--no-backup" in args
            (chroma / ks.STAMP).write_text(f"{ks.STAMP_KEY}={self.ingest_fp}\n")
        elif cmd == "scripts.build_meta":
            (meta / "meta.yaml").write_text("new-meta")
        return self._ok()


def _cand_args(D: Path):
    return ks.build_parser().parse_args(
        ["candidate", "--data-root", str(D), "--fp", NEW, "--ts", TS, "--ref", "kb-2026.11.26",
         "--a-commit", "c" * 40, "--prod-image", "prod:1", "--cand-image", "cand:1",
         "--env-file", "/opt/x/.env"])


def test_candidate_pipeline_pass(root, capsys):
    fd = FakeDocker(root, cand_scores={**BASE, "q002": 0.0})
    assert ks.candidate(fd, _cand_args(root)) == 0
    assert ks.is_gated_pass(root, NEW)
    assert ks.read_marker(root / ks.cand_names(NEW)[0])["chromadb"] == CV
    assert ks.detect(root, NEW)["result"] == "gated"
    assert (root / "chroma" / "chroma.sqlite3").read_text() == "prod"
    assert "q002" in capsys.readouterr().out


def test_candidate_pipeline_old_kb_image_fails(root):
    fd = FakeDocker(root, ingest_fp=OLD)
    assert ks.candidate(fd, _cand_args(root)) == 1
    assert ks.detect(root, NEW)["result"] == "changed"
    assert (root / f"chroma_failed_{NEW[:12]}_{TS}").is_dir()


def test_candidate_eval_crash_fails_and_archives(root):
    # 删 VARIABLE_INDEX.md 实测: 候选 eval 直接崩 rc 1 (不是回退) —— 必须 FAIL + 归档, 生产不动
    before = (root / "chroma" / "chroma.sqlite3").read_text()
    fd = FakeDocker(root, crash_cmd=lambda a: "candidate.json" in " ".join(a))
    assert ks.candidate(fd, _cand_args(root)) == 1
    failed = root / f"chroma_failed_{NEW[:12]}_{TS}"
    assert json.loads((failed / ks.MARKER).read_text())["reason"] == "candidate_eval_rc1"
    assert (root / f"meta_failed_{NEW[:12]}_{TS}").is_dir()
    assert ks.detect(root, NEW)["result"] == "changed"
    assert (root / "chroma" / "chroma.sqlite3").read_text() == before


def _deploy_args(D: Path):
    return ks.build_parser().parse_args(
        ["deploy-swap", "--data-root", str(D), "--image", "img:1", "--target-fp", NEW, "--ts", TS,
         "--chromadb-version", CV])


def _cols(kb: int, **study) -> dict:
    return {"sdtm_kb_v1": {"count": kb}, **{k: {"count": v[0], "digest": v[1]} for k, v in study.items()}}


def test_deploy_swap_refuses_on_non_kb_collection_mismatch(root):
    _gated_cand(root)
    c, _ = ks.cand_names(NEW)
    fd = FakeDocker(root, collections={"chroma": _cols(10, study_x=(5, "d1")), c: _cols(12, study_x=(4, "d1"))})
    before = _snapshot(root)
    assert ks.deploy_swap(fd, _deploy_args(root)) == 1
    assert _snapshot(root) == before


def test_deploy_swap_refuses_on_missing_non_kb_collection(root):
    _gated_cand(root)
    c, _ = ks.cand_names(NEW)
    fd = FakeDocker(root, collections={"chroma": _cols(10, study_x=(5, "d1")), c: _cols(12)})
    before = _snapshot(root)
    assert ks.deploy_swap(fd, _deploy_args(root)) == 1
    assert _snapshot(root) == before


def test_deploy_swap_kb_count_change_is_allowed(root):
    _gated_cand(root)
    c, _ = ks.cand_names(NEW)
    fd = FakeDocker(root, collections={"chroma": _cols(10, study_x=(5, "d1")), c: _cols(12, study_x=(5, "d1"))})
    assert ks.deploy_swap(fd, _deploy_args(root)) == 0
    assert len(fd.col_dirs) == 2 and not list(root.glob("kbsync_guard_*"))  # 副本已清
    assert (root / "chroma" / "chroma.sqlite3").read_text() == "cand"
    assert ks.swap_status(root)["pending"] is True


def test_deploy_swap_refuses_on_same_count_different_content(root):
    _gated_cand(root)
    c, _ = ks.cand_names(NEW)
    fd = FakeDocker(root, collections={"chroma": _cols(10, study_x=(5, "d1")), c: _cols(12, study_x=(5, "d2"))})
    before = _snapshot(root)
    assert ks.deploy_swap(fd, _deploy_args(root)) == 1
    assert _snapshot(root) == before


def test_deploy_swap_guard_copy_failure_leaves_no_guard_dir(root):
    _gated_cand(root)
    c, _ = ks.cand_names(NEW)
    fd = FakeDocker(root, collections={"chroma": _cols(10), c: _cols(12)})
    fd.fail_fs = {"guard-copy"}
    before = _snapshot(root)
    with pytest.raises(RuntimeError):
        ks.deploy_swap(fd, _deploy_args(root))
    assert not list(root.glob("kbsync_guard_*"))
    assert _snapshot(root) == before


def test_prune_cleans_stale_guard_dirs(root):
    (root / "kbsync_guard_20261101T000000Z" / "chroma").mkdir(parents=True)
    _chroma(root / f"chroma_failed_{NEW[:12]}_20261101T000000Z", NEW)
    res = ks.prune(root, 2)
    assert res["removed"] == ["kbsync_guard_20261101T000000Z"]
    assert (root / f"chroma_failed_{NEW[:12]}_20261101T000000Z").is_dir()


def test_journal_state_clear_pending_unknown(root):
    fd = FakeDocker(root)
    assert ks.journal_state(fd, "img:1", str(root)) == 0
    (root / ks.JOURNAL).write_text("{}")
    assert ks.journal_state(fd, "img:1", str(root)) == 3
    fd.fail_fs = {"swap-status"}  # via 失败 = 判不出, 绝不当作 "无 journal"
    assert ks.journal_state(fd, "img:1", str(root)) == 2


def test_image_fp_unknown_for_old_image(root, capsys):
    assert ks.image_fp(FakeDocker(root), "old:1") == "unknown"
    assert "image-fp old:1 rc=1" in capsys.readouterr().err
    assert ks.image_fp(FakeDocker(root, image_fp_out=NEW + "\n"), "new:1") == NEW


def test_local_fingerprint_matches_scripts_kb_freshness(tmp_path):
    from scripts.kb_freshness import kb_fingerprint
    (tmp_path / "a.md").write_text("x")
    assert ks.local_fp(str(tmp_path)) == kb_fingerprint(tmp_path)
