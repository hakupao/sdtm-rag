"""KB→RAG 同步 (P1 step 1.9): 检测 / 候选灌库 + CDISC 闸 / 部署时换 chroma+meta / 回滚 / 清理.

只用标准库; 跑在 Gitea job 容器里 (不进镜像, 也不在 sdtm-rag.yml 路径过滤里)。
job 容器看不到数据根 (runner valid_volumes 只放行 CA), 所以:
  - 文件系统子命令 (detect/prepare/gate/fail/predeploy-check/swap/swap-status/restore/finish/prune)
    只操作本地路径, 生产上用 `--via <镜像>` 在兄弟容器里执行 (数据根按原路径挂进去, 本脚本走 stdin);
  - 编排子命令 (candidate/deploy-swap/image-fp) 在 job 里调 docker, 文件系统动作同样经 `--via`。
目录身份 = stamp 里的 kb_fingerprint (+ 候选的 kbsync_gate.json), 不看任何 SHA。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

KB_COLLECTION = "sdtm_kb_v1"
STAMP = "ingested_at_commit.txt"
STAMP_KEY = "kb_fingerprint"
MARKER = "kbsync_gate.json"
EVAL_DIR = "kbsync_eval"
JOURNAL = "kbsync_swap.json"
FP_RE = re.compile(r"[0-9a-f]{64}")
TS_RE = re.compile(r"\d{8}T\d{6}Z")


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fp12(fp: str) -> str:
    return fp[:12]


def cand_names(fp: str) -> tuple[str, str]:
    return f"chroma_cand_{fp12(fp)}", f"meta_cand_{fp12(fp)}"


def stamp_fp(chroma_dir: Path) -> str | None:
    p = Path(chroma_dir) / STAMP
    if not p.is_file():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        k, sep, v = line.partition("=")
        if sep and k.strip() == STAMP_KEY:
            return v.strip() or None
    return None


def read_marker(chroma_dir: Path) -> dict | None:
    p = Path(chroma_dir) / MARKER
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def is_gated_pass(data_root: Path, fp: str) -> bool:
    c, m = cand_names(fp)
    d = data_root / c
    mk = read_marker(d) or {}
    return (d.is_dir() and (data_root / m / "meta.yaml").is_file() and mk.get("verdict") == "PASS"
            and mk.get("fingerprint") == fp and stamp_fp(d) == fp)


# ── 文件系统子命令 ────────────────────────────────────────────────────────
def detect(data_root: Path, fp: str) -> dict:
    prod = stamp_fp(data_root / "chroma")
    if prod == fp:
        return {"result": "same"}
    if is_gated_pass(data_root, fp):
        return {"result": "gated", "dir": cand_names(fp)[0]}
    return {"result": "changed", "prod_fp12": fp12(prod) if prod else None}


def _archive_failed(data_root: Path, fp: str, ts: str, tag: str = "") -> list[str]:
    """候选 (chroma + meta) 改名为 *_failed_* —— 从不删除 (规则 B)。"""
    moved = []
    suffix = f"{fp12(fp)}_{ts}{tag}"
    for src, kind in zip(cand_names(fp), ("chroma", "meta")):
        s = data_root / src
        if s.exists():
            dst = data_root / f"{kind}_failed_{suffix}"
            s.rename(dst)
            moved.append(dst.name)
    return moved


def prepare(data_root: Path, fp: str, ts: str) -> dict:
    prod = data_root / "chroma"
    if stamp_fp(prod) == fp:
        raise SystemExit("prepare: 生产 stamp 已是该指纹, 无需候选")
    if not (data_root / "meta" / "meta.yaml").is_file():
        raise SystemExit("prepare: 生产 meta/meta.yaml 不存在")
    stale = _archive_failed(data_root, fp, ts, "_stale")  # 上次中断留下的候选不复用
    c, m = cand_names(fp)
    shutil.copytree(prod, data_root / c, symlinks=True,
                    ignore=shutil.ignore_patterns(MARKER, EVAL_DIR))
    (data_root / c / EVAL_DIR).mkdir()
    # 整个 meta/ 复制 (除 meta.yaml 还有 implicit_relations.json 等), build_meta 只覆盖 meta.yaml
    shutil.copytree(data_root / "meta", data_root / m, symlinks=True)
    return {"candidate": c, "meta": m, "archived_stale": stale}


def _load_recall(path: Path) -> dict[str, float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results") or []
    if not results:
        raise ValueError(f"{path.name}: results 为空")
    out: dict[str, float] = {}
    for r in results:
        if r["id"] in out:
            raise ValueError(f"{path.name}: id 重复 {r['id']}")
        out[r["id"]] = float(r["source_recall"])
    return out


def regressions(base: dict[str, float], cand: dict[str, float]) -> list[str]:
    """逐题回退: 候选 source_recall < 基线, 或候选缺题 (键取并集, 少题不许读成无差异)。"""
    return sorted(k for k in set(base) | set(cand)
                  if k not in cand or (k in base and cand[k] < base[k]))


def gate(data_root: Path, fp: str, max_regressions: int, ts: str, info: dict) -> dict:
    c, _ = cand_names(fp)
    d = data_root / c
    if not d.is_dir():
        raise SystemExit(f"gate: 候选目录不存在 {c}")
    marker = {"fingerprint": fp, "timestamp": ts, "max_regressions": max_regressions, **info}
    reason = None
    got = stamp_fp(d)
    if got != fp:  # 灌进去的不是检测到的 KB (如镜像仍是旧 KB)
        reason = f"fingerprint_mismatch: stamp={fp12(got) if got else None} expected={fp12(fp)}"
    else:
        try:
            base = _load_recall(d / EVAL_DIR / "baseline.json")
            cand = _load_recall(d / EVAL_DIR / "candidate.json")
        except (OSError, ValueError, KeyError) as e:
            reason = f"eval_unreadable: {e}"
        else:
            reg = regressions(base, cand)
            marker.update({
                "n_questions": len(set(base) | set(cand)),
                "baseline_full": sum(v >= 1.0 for v in base.values()),
                "candidate_full": sum(v >= 1.0 for v in cand.values()),
                "regressed_ids": reg,
                "improved_ids": sorted(k for k in cand if k in base and cand[k] > base[k]),
            })
            if len(reg) > max_regressions:
                reason = f"regressions {len(reg)} > {max_regressions}"
    marker["verdict"] = "FAIL" if reason else "PASS"
    marker["reason"] = reason
    (d / MARKER).write_text(json.dumps(marker, ensure_ascii=False, indent=1), encoding="utf-8")
    if reason:
        marker["archived"] = _archive_failed(data_root, fp, ts)
    return marker


def fail(data_root: Path, fp: str, ts: str, reason: str) -> dict:
    c, _ = cand_names(fp)
    d = data_root / c
    if d.is_dir() and not read_marker(d):
        (d / MARKER).write_text(json.dumps({"fingerprint": fp, "timestamp": ts, "verdict": "FAIL",
                                            "reason": reason}, ensure_ascii=False), encoding="utf-8")
    return {"verdict": "FAIL", "reason": reason, "archived": _archive_failed(data_root, fp, ts)}


def _newest_prev(data_root: Path, fp: str) -> tuple[str, str] | None:
    pat = re.compile(rf"chroma_prev_{fp12(fp)}_({TS_RE.pattern})")
    hits = sorted(((m.group(1), p.name) for p in data_root.iterdir()
                   if (m := pat.fullmatch(p.name)) and p.is_dir()), reverse=True)
    for ts, name in hits:
        meta = f"meta_prev_{fp12(fp)}_{ts}"
        if stamp_fp(data_root / name) == fp and (data_root / meta / "meta.yaml").is_file():
            return name, meta
    return None


def predeploy_check(data_root: Path, target_fp: str | None) -> dict:
    """只读: 决定部署时 chroma/meta 怎么办。same / swap / missing / unknown。"""
    prod = stamp_fp(data_root / "chroma")
    base = {"prod_fp12": fp12(prod) if prod else None}
    if not target_fp or not FP_RE.fullmatch(target_fp):
        return {**base, "decision": "unknown"}
    base["target_fp12"] = fp12(target_fp)
    if prod == target_fp:
        return {**base, "decision": "same"}
    if is_gated_pass(data_root, target_fp):
        c, m = cand_names(target_fp)
        return {**base, "decision": "swap", "source_chroma": c, "source_meta": m}
    prev = _newest_prev(data_root, target_fp)
    if prev:
        return {**base, "decision": "swap", "source_chroma": prev[0], "source_meta": prev[1]}
    return {**base, "decision": "missing"}


def swap(data_root: Path, target_fp: str, ts: str) -> dict:
    if (data_root / JOURNAL).exists():
        raise SystemExit(f"swap: {JOURNAL} 已存在 (上次换数据未收尾), 先 restore 或 finish")
    chk = predeploy_check(data_root, target_fp)
    if chk["decision"] != "swap":
        raise SystemExit(f"swap: 无可换的数据 (decision={chk['decision']})")
    old = stamp_fp(data_root / "chroma")
    old12 = fp12(old) if old else "unknown"
    j = {"ts": ts, "target_fp": target_fp, "old_fp": old,
         "source_chroma": chk["source_chroma"], "source_meta": chk["source_meta"],
         "prev_chroma": f"chroma_prev_{old12}_{ts}", "prev_meta": f"meta_prev_{old12}_{ts}"}
    (data_root / JOURNAL).write_text(json.dumps(j, indent=1), encoding="utf-8")  # 先记账再动目录
    (data_root / "chroma").rename(data_root / j["prev_chroma"])
    (data_root / "meta").rename(data_root / j["prev_meta"])
    (data_root / j["source_chroma"]).rename(data_root / "chroma")
    (data_root / j["source_meta"]).rename(data_root / "meta")
    return {"swapped": True, **j}


def swap_status(data_root: Path) -> dict:
    return {"pending": (data_root / JOURNAL).is_file()}


def restore(data_root: Path) -> dict:
    """按 journal 倒放 swap; 中途断掉的状态也能收拾 (每步先看在不在)。"""
    jp = data_root / JOURNAL
    if not jp.is_file():
        return {"restored": False}
    j = json.loads(jp.read_text(encoding="utf-8"))
    for live, src, prev in (("chroma", j["source_chroma"], j["prev_chroma"]),
                            ("meta", j["source_meta"], j["prev_meta"])):
        L, S, P = data_root / live, data_root / src, data_root / prev
        if L.exists() and not S.exists() and P.exists():
            L.rename(S)
        if P.exists() and not L.exists():
            P.rename(L)
    jp.unlink()
    return {"restored": True, "prod_fp12": fp12(stamp_fp(data_root / "chroma") or "") or None}


def finish(data_root: Path) -> dict:
    jp = data_root / JOURNAL
    if jp.is_file():
        jp.unlink()
        return {"finished": True}
    return {"finished": False}


def prune(data_root: Path, keep: int = 2) -> dict:
    """chroma_prev_* 按时间留最新 keep 份 (连同配对 meta_prev_*); chroma_failed_* 永不碰。"""
    pat = re.compile(rf"chroma_prev_([0-9a-f]{{12}}|unknown)_({TS_RE.pattern})")
    prevs = sorted(((m.group(2), m.group(1), p.name) for p in data_root.iterdir()
                    if (m := pat.fullmatch(p.name))), reverse=True)
    removed = []
    for ts, f12, name in prevs[keep:]:
        for n in (name, f"meta_prev_{f12}_{ts}"):
            if (data_root / n).exists():
                shutil.rmtree(data_root / n)
                removed.append(n)
    return {"kept": [n for _, _, n in prevs[:keep]], "removed": removed}


# ── docker 包装 (测试替换为假实现) ────────────────────────────────────────
class Docker:
    def run(self, args: list[str], *, input: bytes | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["docker", *args], input=input, capture_output=True)


def via(docker: Docker, image: str, data_root: str, fs_args: list[str]) -> dict:
    """在兄弟容器里跑本脚本的文件系统子命令 (数据根按原路径挂载, 脚本走 stdin)。"""
    r = docker.run(["run", "-i", "--rm", "--mount", f"type=bind,src={data_root},dst={data_root}",
                    "--entrypoint", "python", image, "-", *fs_args],
                   input=Path(__file__).read_bytes())
    out = r.stdout.decode("utf-8", "replace").strip().splitlines()
    if r.returncode not in (0, 1) or not out or not out[-1].startswith("{"):  # rc 1 = verdict FAIL
        err = r.stderr.decode("utf-8", "replace").strip().splitlines()[-5:]
        raise RuntimeError(f"{fs_args[0]} via {image} rc={r.returncode}: {' | '.join(err)}")
    return json.loads(out[-1])


def _workdir(docker: Docker, image: str) -> str:
    r = docker.run(["image", "inspect", "-f", "{{.Config.WorkingDir}}", image])
    return r.stdout.decode().strip() or "/app"


def _app_run(docker: Docker, image: str, data_root: str, fp: str, env_file: str, memory: str,
             cmd: list[str]) -> subprocess.CompletedProcess:
    """data/ 只读, 候选 chroma / meta 以原生路径可写覆盖 (bind 源缺失即报错, 不会落到生产)。"""
    app = _workdir(docker, image)
    c, m = cand_names(fp)
    mounts = [f"type=bind,src={data_root},dst={app}/data,readonly",
              f"type=bind,src={data_root}/{c},dst={app}/data/chroma",
              f"type=bind,src={data_root}/{m},dst={app}/data/meta",
              f"type=bind,src={env_file},dst={app}/.env,readonly"]
    args = ["run", "--rm", "--memory", memory]
    for mt in mounts:
        args += ["--mount", mt]
    return docker.run([*args, image, "python", "-m", *cmd])


EVAL_CMD = ["eval.run_eval", "eval/test_set_v3.yml", "--retrieval-only", "--hybrid", "--structured-lookup"]


def candidate(docker: Docker, a: argparse.Namespace) -> int:
    """prepare → 基线 eval (生产镜像) → 候选镜像 ingest + build_meta → 候选 eval → gate。"""
    D, fp, ts = a.data_root, a.fp, a.ts or now_ts()
    c, _ = cand_names(fp)
    print(f"[kbsync] prepare {c}")
    print(json.dumps(via(docker, a.prod_image, D, ["prepare", "--data-root", D, "--fp", fp, "--ts", ts])))
    out = f"data/chroma/{EVAL_DIR}"
    steps = [("baseline_eval", a.prod_image, [*EVAL_CMD, "--output", f"{out}/baseline.json"]),
             ("ingest", a.cand_image, ["scripts.ingest", "--no-backup"]),
             ("build_meta", a.cand_image, ["scripts.build_meta"]),
             ("candidate_eval", a.cand_image, [*EVAL_CMD, "--output", f"{out}/candidate.json"])]
    for name, img, cmd in steps:
        print(f"[kbsync] {name} ({img})")
        r = _app_run(docker, img, D, fp, a.env_file, a.memory, cmd)
        if r.returncode != 0:
            tail = r.stderr.decode("utf-8", "replace").strip().splitlines()[-20:]
            print(f"[kbsync] {name} rc={r.returncode}\n" + "\n".join(tail))
            res = via(docker, a.prod_image, D, ["fail", "--data-root", D, "--fp", fp, "--ts", ts,
                                                "--reason", f"{name}_rc{r.returncode}"])
            print(json.dumps(res))
            return 1
    info = json.dumps({"ref": a.ref, "a_commit": a.a_commit, "image": a.cand_image,
                       "prod_image": a.prod_image})
    res = via(docker, a.prod_image, D, ["gate", "--data-root", D, "--fp", fp, "--ts", ts,
                                        "--max-regressions", str(a.max_regressions), "--info", info])
    summary = {k: res.get(k) for k in ("verdict", "reason", "n_questions", "baseline_full",
                                       "candidate_full", "regressed_ids", "improved_ids", "archived")}
    print("[kbsync] gate " + json.dumps(summary))
    return 0 if res["verdict"] == "PASS" else 1


COLLECTIONS_PY = ("import chromadb,json,sys;c=chromadb.PersistentClient(path=sys.argv[1]);"
                  "print(json.dumps({x.name:c.get_collection(x.name).count() for x in c.list_collections()}))")


def collections(docker: Docker, image: str, host_dir: str) -> dict[str, int]:
    # chromadb 打不开只读目录 (实测 sqlite "readonly database"), 故可写挂载; 调用方须已停生产
    r = docker.run(["run", "--rm", "--mount", f"type=bind,src={host_dir},dst=/c", "--entrypoint",
                    "python", image, "-c", COLLECTIONS_PY, "/c"])
    if r.returncode != 0:
        raise RuntimeError(f"读集合失败 {Path(host_dir).name} rc={r.returncode}")
    return json.loads(r.stdout.decode().strip().splitlines()[-1])


def non_kb(cols: dict[str, int]) -> dict[str, int]:
    return {k: v for k, v in cols.items() if k != KB_COLLECTION}


def deploy_swap(docker: Docker, a: argparse.Namespace) -> int:
    """部署时换数据 (生产须已停): 非 KB 集合 (名 + 条数) 必须与生产一致, 否则拒换。"""
    D, ts = a.data_root, a.ts or now_ts()
    chk = via(docker, a.image, D, ["predeploy-check", "--data-root", D, "--target-fp", a.target_fp])
    if chk["decision"] != "swap":
        print(f"[kbsync] 不可换: {json.dumps(chk)}")
        return 1
    prod_cols = non_kb(collections(docker, a.image, f"{D}/chroma"))
    src_cols = non_kb(collections(docker, a.image, f"{D}/{chk['source_chroma']}"))
    if prod_cols != src_cols:
        diff = sorted(k for k in set(prod_cols) | set(src_cols) if prod_cols.get(k) != src_cols.get(k))
        print(f"[kbsync] 拒换: 非 KB 集合与生产不一致 ({len(diff)} 个集合不同, 名称/条数), "
              "生产未动 —— 候选建好后 study 集合有变, 请重跑 kb-sync")
        return 1
    print(json.dumps(via(docker, a.image, D, ["swap", "--data-root", D, "--target-fp", a.target_fp,
                                              "--ts", ts])))
    return 0


IMAGE_FP_PY = ("from scripts.kb_freshness import kb_fingerprint;from server.config import settings;"
               "print(kb_fingerprint(settings.kb_root))")


def image_fp(docker: Docker, image: str) -> str:
    """镜像内 KB 指纹; 旧镜像 (无 scripts.kb_freshness) 或任何异常 → 'unknown'。"""
    r = docker.run(["run", "--rm", "--entrypoint", "python", image, "-c", IMAGE_FP_PY])
    out = r.stdout.decode().strip().splitlines()
    return out[-1] if r.returncode == 0 and out and FP_RE.fullmatch(out[-1]) else "unknown"


def local_fp(kb_root: str) -> str:
    import importlib.util
    p = Path(__file__).resolve().parents[2] / "scripts" / "kb_freshness.py"
    spec = importlib.util.spec_from_file_location("kb_freshness", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass 解析注解要查 sys.modules
    spec.loader.exec_module(mod)
    return mod.kb_fingerprint(Path(kb_root))


# ── CLI ──────────────────────────────────────────────────────────────────
FS_CMDS = {"detect", "prepare", "gate", "fail", "predeploy-check", "swap", "swap-status",
           "restore", "finish", "prune"}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--via", metavar="IMAGE", help="文件系统子命令在该镜像的兄弟容器里执行")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def p(name: str, *, data=True, fp=False, ts=False):
        s = sub.add_parser(name)
        if data:
            s.add_argument("--data-root", required=True)
        if fp:
            s.add_argument("--fp", required=True)
        if ts:
            s.add_argument("--ts", default="")
        return s

    p("detect", fp=True)
    p("prepare", fp=True, ts=True)
    g = p("gate", fp=True, ts=True)
    g.add_argument("--max-regressions", type=int, default=1)
    g.add_argument("--info", default="{}")
    p("fail", fp=True, ts=True).add_argument("--reason", required=True)
    p("predeploy-check").add_argument("--target-fp", default="")
    p("swap", ts=True).add_argument("--target-fp", required=True)
    p("swap-status")
    p("restore")
    p("finish")
    p("prune").add_argument("--keep", type=int, default=2)

    c = p("candidate", fp=True, ts=True)
    for k in ("--ref", "--a-commit", "--prod-image", "--cand-image", "--env-file"):
        c.add_argument(k, required=True)
    c.add_argument("--max-regressions", type=int, default=1)
    c.add_argument("--memory", default="1536m")
    d = p("deploy-swap", ts=True)
    d.add_argument("--image", required=True)
    d.add_argument("--target-fp", required=True)
    p("image-fp", data=False).add_argument("--image", required=True)
    p("fingerprint", data=False).add_argument("--kb-root", required=True)
    return ap


def run_fs(a: argparse.Namespace) -> dict:
    D = Path(a.data_root)
    if not D.is_dir():
        raise SystemExit(f"data root 不存在: {D}")
    ts = getattr(a, "ts", "") or now_ts()
    if a.cmd == "detect":
        return detect(D, a.fp)
    if a.cmd == "prepare":
        return prepare(D, a.fp, ts)
    if a.cmd == "gate":
        return gate(D, a.fp, a.max_regressions, ts, json.loads(a.info))
    if a.cmd == "fail":
        return fail(D, a.fp, ts, a.reason)
    if a.cmd == "predeploy-check":
        return predeploy_check(D, a.target_fp)
    if a.cmd == "swap":
        return swap(D, a.target_fp, ts)
    if a.cmd == "swap-status":
        return swap_status(D)
    if a.cmd == "restore":
        return restore(D)
    if a.cmd == "finish":
        return finish(D)
    return prune(D, a.keep)


def main(argv: list[str] | None = None, docker: Docker | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    a = build_parser().parse_args(argv)
    docker = docker or Docker()
    if a.cmd in FS_CMDS:
        if a.via:
            rest = argv[argv.index(a.cmd):]
            res = via(docker, a.via, a.data_root, rest)
        else:
            res = run_fs(a)
        print(json.dumps(res, ensure_ascii=False))
        return 1 if res.get("verdict") == "FAIL" else 0
    if a.cmd == "candidate":
        return candidate(docker, a)
    if a.cmd == "deploy-swap":
        return deploy_swap(docker, a)
    if a.cmd == "image-fp":
        print(image_fp(docker, a.image))
        return 0
    print(local_fp(a.kb_root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
