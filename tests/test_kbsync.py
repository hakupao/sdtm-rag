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
    (D / "study").mkdir()
    return D


def _snapshot(D: Path) -> dict[str, str]:
    return {str(p.relative_to(D)): (p.read_text() if p.is_file() else "<dir>") for p in sorted(D.rglob("*"))}


def _results(scores: dict[str, float]) -> str:
    return json.dumps({"summary": {}, "results": [{"id": k, "source_recall": v} for k, v in scores.items()]})


def _gated_cand(D: Path, fp: str = NEW, verdict: str = "PASS") -> Path:
    c, m = ks.cand_names(fp)
    d = _chroma(D / c, fp, "cand")
    (d / ks.MARKER).write_text(json.dumps({"fingerprint": fp, "verdict": verdict}))
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


def test_detect_failed_marker_is_not_gated(root):
    _gated_cand(root, verdict="FAIL")
    assert ks.detect(root, NEW)["result"] == "changed"


# ── gate ──────────────────────────────────────────────────────────────────
BASE = {f"q{i}": 1.0 for i in range(1, 6)}


def _prepared(D: Path, cand_scores: dict[str, float], ingest_fp: str = NEW) -> Path:
    ks.prepare(D, NEW, TS)
    c, m = ks.cand_names(NEW)
    d = D / c
    (d / ks.STAMP).write_text(f"{ks.STAMP_KEY}={ingest_fp}\n")
    (d / ks.EVAL_DIR / "baseline.json").write_text(_results(BASE))
    (d / ks.EVAL_DIR / "candidate.json").write_text(_results(cand_scores))
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


def test_prepare_archives_stale_candidate_never_deletes(root):
    _gated_cand(root, verdict="FAIL")
    res = ks.prepare(root, NEW, TS)
    assert res["archived_stale"] == [f"chroma_failed_{NEW[:12]}_{TS}_stale", f"meta_failed_{NEW[:12]}_{TS}_stale"]
    assert (root / res["archived_stale"][0] / "chroma.sqlite3").read_text() == "cand"


def test_gate_one_regression_passes(root):
    _prepared(root, {**BASE, "q3": 0.5})
    mk = ks.gate(root, NEW, 1, TS, {"ref": "kb-2026.11.26"})
    assert mk["verdict"] == "PASS", mk
    assert mk["regressed_ids"] == ["q3"]
    assert ks.is_gated_pass(root, NEW)


def test_gate_two_regressions_fail_and_archive(root):
    _prepared(root, {**BASE, "q3": 0.5, "q4": 0.0})
    mk = ks.gate(root, NEW, 1, TS, {})
    assert mk["verdict"] == "FAIL", mk
    assert mk["regressed_ids"] == ["q3", "q4"]
    c, m = ks.cand_names(NEW)
    assert not (root / c).exists() and not (root / m).exists()
    failed = root / f"chroma_failed_{NEW[:12]}_{TS}"
    assert json.loads((failed / ks.MARKER).read_text())["verdict"] == "FAIL"
    assert (root / f"meta_failed_{NEW[:12]}_{TS}" / "meta.yaml").is_file()
    assert (root / "chroma" / "chroma.sqlite3").read_text() == "prod"


def test_gate_missing_question_counts_as_regression(root):
    cand = dict(BASE)
    cand.pop("q1")
    cand.pop("q2")
    _prepared(root, cand)
    mk = ks.gate(root, NEW, 1, TS, {})
    assert mk["verdict"] == "FAIL" and mk["regressed_ids"] == ["q1", "q2"], mk


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
    j = ks.swap(root, NEW, TS)
    assert (root / "chroma" / "chroma.sqlite3").read_text() == "cand"
    assert (root / "meta" / "meta.yaml").read_text() == "new-meta"
    assert j["prev_chroma"] == f"chroma_prev_{OLD[:12]}_{TS}"
    assert (root / j["prev_chroma"] / "chroma.sqlite3").read_text() == "prod"
    assert (root / j["prev_meta"] / "meta.yaml").read_text() == "old-meta"
    assert ks.swap_status(root) == {"pending": True}
    with pytest.raises(SystemExit):  # 未收尾不许二次换
        ks.swap(root, NEW, TS)
    assert ks.restore(root)["restored"] is True
    assert _snapshot(root) == before
    assert ks.restore(root) == {"restored": False}


def test_restore_after_partial_swap(root):
    # journal 已写, 只改名了第一步就断了
    _gated_cand(root)
    before = _snapshot(root)
    c, m = ks.cand_names(NEW)
    j = {"source_chroma": c, "source_meta": m, "prev_chroma": f"chroma_prev_{OLD[:12]}_{TS}",
         "prev_meta": f"meta_prev_{OLD[:12]}_{TS}"}
    (root / ks.JOURNAL).write_text(json.dumps(j))
    (root / "chroma").rename(root / j["prev_chroma"])
    ks.restore(root)
    assert _snapshot(root) == before


def test_rollback_finds_retained_prev(root):
    _chroma(root / f"chroma_prev_{NEW[:12]}_20261101T000000Z", NEW, "prev-new")
    _meta(root / f"meta_prev_{NEW[:12]}_20261101T000000Z", "prev-meta")
    chk = ks.predeploy_check(root, NEW)
    assert chk["decision"] == "swap" and chk["source_chroma"].startswith("chroma_prev_"), chk
    ks.swap(root, NEW, TS)
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
    def __init__(self, D: Path, cand_scores=None, ingest_fp=NEW, collections=None, image_fp_out=None):
        self.D, self.cand_scores, self.ingest_fp = D, cand_scores or dict(BASE), ingest_fp
        self.cols = collections or {}
        self.image_fp_out = image_fp_out
        self.calls: list[list[str]] = []

    def _ok(self, out: str = "", rc: int = 0):
        return subprocess.CompletedProcess([], rc, out.encode(), b"")

    def run(self, args, *, input=None):
        self.calls.append(args)
        if args[:2] == ["image", "inspect"]:
            return self._ok("/app\n")
        if "-i" in args and "-" in args:  # --via: 本进程内跑文件系统子命令
            fs = args[args.index("-") + 1:]
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                try:
                    rc = ks.main(fs)
                except SystemExit as e:
                    return subprocess.CompletedProcess([], 2, b"", str(e).encode())
            return self._ok(buf.getvalue(), rc)
        if "-c" in args and args[args.index("-c") + 1] == ks.COLLECTIONS_PY:
            src = next(a for a in args if a.startswith("type=bind,src=")).split(",")[1][4:]
            return self._ok(json.dumps(self.cols[Path(src).name]))
        if "-c" in args and args[args.index("-c") + 1] == ks.IMAGE_FP_PY:
            return self._ok(self.image_fp_out) if self.image_fp_out else self._ok("", 1)
        specs = [dict(kv.partition("=")[::2] for kv in args[i + 1].split(",")) for i, a in enumerate(args)
                 if a == "--mount"]
        mounts = {m["dst"]: m["src"] for m in specs}
        assert mounts["/app/data"] == str(self.D)
        assert any(m.endswith("dst=/app/data,readonly") for m in args), args
        chroma, meta = Path(mounts["/app/data/chroma"]), Path(mounts["/app/data/meta"])
        assert chroma.name.startswith("chroma_cand_"), chroma
        cmd = args[args.index("-m") + 1]
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
    fd = FakeDocker(root, cand_scores={**BASE, "q2": 0.0})
    assert ks.candidate(fd, _cand_args(root)) == 0
    assert ks.is_gated_pass(root, NEW)
    assert ks.detect(root, NEW)["result"] == "gated"
    assert (root / "chroma" / "chroma.sqlite3").read_text() == "prod"
    assert "q2" in capsys.readouterr().out


def test_candidate_pipeline_old_kb_image_fails(root):
    fd = FakeDocker(root, ingest_fp=OLD)
    assert ks.candidate(fd, _cand_args(root)) == 1
    assert ks.detect(root, NEW)["result"] == "changed"
    assert (root / f"chroma_failed_{NEW[:12]}_{TS}").is_dir()


def _deploy_args(D: Path):
    return ks.build_parser().parse_args(
        ["deploy-swap", "--data-root", str(D), "--image", "img:1", "--target-fp", NEW, "--ts", TS])


def test_deploy_swap_refuses_on_non_kb_collection_mismatch(root):
    _gated_cand(root)
    c, _ = ks.cand_names(NEW)
    fd = FakeDocker(root, collections={"chroma": {"sdtm_kb_v1": 10, "study_x": 5},
                                       c: {"sdtm_kb_v1": 12, "study_x": 4}})
    before = _snapshot(root)
    assert ks.deploy_swap(fd, _deploy_args(root)) == 1
    assert _snapshot(root) == before


def test_deploy_swap_refuses_on_missing_non_kb_collection(root):
    _gated_cand(root)
    c, _ = ks.cand_names(NEW)
    fd = FakeDocker(root, collections={"chroma": {"sdtm_kb_v1": 10, "study_x": 5},
                                       c: {"sdtm_kb_v1": 12}})
    before = _snapshot(root)
    assert ks.deploy_swap(fd, _deploy_args(root)) == 1
    assert _snapshot(root) == before


def test_deploy_swap_kb_count_change_is_allowed(root):
    _gated_cand(root)
    c, _ = ks.cand_names(NEW)
    fd = FakeDocker(root, collections={"chroma": {"sdtm_kb_v1": 10, "study_x": 5},
                                       c: {"sdtm_kb_v1": 12, "study_x": 5}})
    assert ks.deploy_swap(fd, _deploy_args(root)) == 0
    assert (root / "chroma" / "chroma.sqlite3").read_text() == "cand"
    assert ks.swap_status(root)["pending"] is True


def test_image_fp_unknown_for_old_image(root):
    assert ks.image_fp(FakeDocker(root), "old:1") == "unknown"
    assert ks.image_fp(FakeDocker(root, image_fp_out=NEW + "\n"), "new:1") == NEW


def test_local_fingerprint_matches_scripts_kb_freshness(tmp_path):
    from scripts.kb_freshness import kb_fingerprint
    (tmp_path / "a.md").write_text("x")
    assert ks.local_fp(str(tmp_path)) == kb_fingerprint(tmp_path)
