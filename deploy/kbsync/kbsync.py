"""KB→RAG 同步（P1 step 1.9，P3 起同时服务私有与公开两个数据根）：检测、候选入库与 CDISC 闸、部署时换入 chroma+meta、回滚、清理。

只用标准库；在 Gitea job 容器中运行（不打进镜像，也不在 sdtm-rag.yml 的路径过滤范围内）。
job 容器无法访问数据根（runner 的 valid_volumes 只放行 CA），因此：
  - 文件系统子命令（FS_CMDS）只操作本地路径；在生产环境中通过 `--via <镜像>` 在兄弟容器中执行
    （数据根按原路径挂载，本脚本通过 stdin 传入）；
  - 编排子命令（candidate/deploy-swap/image-fp 等）在 job 中调用 docker，其中的文件系统操作同样通过 `--via` 执行。
目录身份由 stamp 中的 kb_fingerprint 确定（候选目录另加 kbsync_gate.json），不使用任何 SHA。

红线不变量：每次调用只接受**一个**数据根（`--data-root`），复制与改名都发生在这个数据根之内，
没有任何子命令能把一个数据根的内容带到另一个数据根。公开数据根的 chroma 只来自公开数据根自身；
公开腿另加 `--kb-only`（集合必须恰为 sdtm_kb_v1）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

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


def _norm(path: str) -> PurePosixPath:
    return PurePosixPath(os.path.normpath(path))


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
    if (data_root / JOURNAL).exists():  # 上次换数据未完成收尾：生产 stamp 不可信，不构建候选
        return {"result": "journal_pending"}
    prod = stamp_fp(data_root / "chroma")
    if prod == fp:
        return {"result": "same"}
    if is_gated_pass(data_root, fp):
        return {"result": "gated", "dir": cand_names(fp)[0]}
    return {"result": "changed", "prod_fp12": fp12(prod) if prod else None}


def stamp(data_root: Path) -> dict:
    """只读：线上 chroma stamp 中的完整指纹（没有 stamp 时为 None）。"""
    return {"fp": stamp_fp(data_root / "chroma")}


def _archive_failed(data_root: Path, fp: str, ts: str, tag: str = "") -> list[str]:
    """把候选（chroma + meta）改名为 *_failed_*，从不删除（规则 B）。"""
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
        raise SystemExit("prepare: 生产 stamp 已是该指纹，无需构建候选")
    if not (data_root / "meta" / "meta.yaml").is_file():
        raise SystemExit("prepare: 生产 meta/meta.yaml 不存在")
    stale = _archive_failed(data_root, fp, ts, "_stale")  # 上次中断留下的候选不复用
    c, m = cand_names(fp)
    shutil.copytree(prod, data_root / c, symlinks=True,
                    ignore=shutil.ignore_patterns(MARKER, EVAL_DIR))
    (data_root / c / EVAL_DIR).mkdir()
    # 复制整个 meta/（除 meta.yaml 外还有 implicit_relations.json 等）；build_meta 只覆盖 meta.yaml
    shutil.copytree(data_root / "meta", data_root / m, symlinks=True)
    return {"candidate": c, "meta": m, "archived_stale": stale}


def _load_avg(path: Path) -> float:
    """读取评测产物自带的 summary.source_recall_avg（run_eval 剔除 out_of_scope 后的唯一统计口径），不自行计算。"""
    avg = (json.loads(path.read_text(encoding="utf-8")).get("summary") or {}).get("source_recall_avg")
    if avg is None:
        raise ValueError(f"{path.name}: 缺少 summary.source_recall_avg")
    return float(avg)


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
    """逐题回退：候选 source_recall 低于基线，或候选缺题（键取并集，缺题不得视为无差异）。"""
    return sorted(k for k in set(base) | set(cand)
                  if k not in cand or (k in base and cand[k] < base[k]))


MIN_QUESTIONS = 140  # CDISC test_set_v3
MIN_AVG = 0.95       # 绝对下限：相对闸无法防止"基线本身已经塌陷"的情况


def gate(data_root: Path, fp: str, max_regressions: int, ts: str, info: dict,
         min_questions: int = MIN_QUESTIONS, min_avg: float = MIN_AVG) -> dict:
    c, _ = cand_names(fp)
    d = data_root / c
    if not d.is_dir():
        raise SystemExit(f"gate: 候选目录不存在 {c}")
    marker = {"fingerprint": fp, "timestamp": ts, "max_regressions": max_regressions,
              "min_questions": min_questions, "min_avg": min_avg, **info}
    reason = None
    got = stamp_fp(d)
    if got != fp:  # 写入的不是检测到的 KB（例如镜像中仍是旧 KB）
        reason = f"fingerprint_mismatch: stamp={fp12(got) if got else None} expected={fp12(fp)}"
    else:
        try:
            base = _load_recall(d / EVAL_DIR / "baseline.json")
            cand = _load_recall(d / EVAL_DIR / "candidate.json")
            cand_avg = _load_avg(d / EVAL_DIR / "candidate.json")
        except (OSError, ValueError, KeyError, TypeError) as e:
            reason = f"eval_unreadable: {e}"
        else:
            reg = regressions(base, cand)
            b_full = sum(v >= 1.0 for v in base.values())
            c_full = sum(v >= 1.0 for v in cand.values())
            marker.update({
                "n_questions": len(set(base) | set(cand)),
                "baseline_full": b_full,
                "candidate_full": c_full,
                "candidate_avg": cand_avg,
                "regressed_ids": reg,
                "improved_ids": sorted(k for k in cand if k in base and cand[k] > base[k]),
            })
            fails = []
            if set(base) != set(cand):
                fails.append(f"id_set_mismatch ({len(set(base) ^ set(cand))} ids)")
            if len(set(base) | set(cand)) < min_questions:
                fails.append(f"n_questions {len(set(base) | set(cand))} < {min_questions}")
            if len(reg) > max_regressions:
                fails.append(f"regressions {len(reg)} > {max_regressions}")
            if c_full < b_full - 1:
                fails.append(f"candidate_full {c_full} < baseline_full {b_full} - 1")
            if cand_avg < min_avg:
                fails.append(f"candidate_avg {cand_avg} < {min_avg}")
            reason = "; ".join(fails) or None
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


def predeploy_check(data_root: Path, target_fp: str | None, chromadb_version: str = "") -> dict:
    """只读：确定部署时 chroma/meta 的处理方式，结果为 journal_pending / same / swap / missing / unknown 之一。

    journal 残留（上次 job 被取消或超时）优先于其他一切情况：此时数据处于换了一半的未知状态，任何决定都不可信。
    候选必须由与目标镜像**相同版本的 chromadb** 构建（见 marker.chromadb），否则不选用（防止跨版本迁移）。"""
    prod = stamp_fp(data_root / "chroma")
    base = {"prod_fp12": fp12(prod) if prod else None}
    if (data_root / JOURNAL).exists():
        return {**base, "decision": "journal_pending"}
    if not target_fp or not FP_RE.fullmatch(target_fp):
        return {**base, "decision": "unknown"}
    base["target_fp12"] = fp12(target_fp)
    if prod == target_fp:
        return {**base, "decision": "same"}
    if is_gated_pass(data_root, target_fp):
        c, m = cand_names(target_fp)
        built = (read_marker(data_root / c) or {}).get("chromadb")
        if chromadb_version not in ("", "unknown") and built == chromadb_version:
            return {**base, "decision": "swap", "source_chroma": c, "source_meta": m}
        base["candidate_skipped"] = f"chromadb {built} != target {chromadb_version or None}"
    prev = _newest_prev(data_root, target_fp)
    if prev:
        return {**base, "decision": "swap", "source_chroma": prev[0], "source_meta": prev[1]}
    return {**base, "decision": "missing"}


def swap(data_root: Path, target_fp: str, ts: str, chromadb_version: str = "", expect_source: str = "") -> dict:
    # journal 残留统一由 predeploy_check 判断（journal_pending），这里不再设置含义相同的第二道闸
    chk = predeploy_check(data_root, target_fp, chromadb_version)
    if chk["decision"] != "swap":
        raise SystemExit(f"swap: 没有可换入的数据 (decision={chk['decision']})")
    if expect_source and chk["source_chroma"] != expect_source:  # 验收过的那一份与现在要换入的不是同一份
        raise SystemExit(f"swap: 换入源变了（验收的是 {expect_source}，现在选出的是 {chk['source_chroma']}），拒绝换入")
    old = stamp_fp(data_root / "chroma")
    old12 = fp12(old) if old else "unknown"
    j = {"ts": ts, "target_fp": target_fp, "old_fp": old,
         "source_chroma": chk["source_chroma"], "source_meta": chk["source_meta"],
         "prev_chroma": f"chroma_prev_{old12}_{ts}", "prev_meta": f"meta_prev_{old12}_{ts}"}
    (data_root / JOURNAL).write_text(json.dumps(j, indent=1), encoding="utf-8")  # 先写 journal，再改动目录
    (data_root / "chroma").rename(data_root / j["prev_chroma"])
    (data_root / "meta").rename(data_root / j["prev_meta"])
    (data_root / j["source_chroma"]).rename(data_root / "chroma")
    (data_root / j["source_meta"]).rename(data_root / "meta")
    return {"swapped": True, **j}


def swap_status(data_root: Path) -> dict:
    return {"pending": (data_root / JOURNAL).is_file()}


def restore(data_root: Path) -> dict:
    """按 journal 逆序撤销 swap；中途中断的状态也能恢复（每一步先检查目录是否存在）。"""
    jp = data_root / JOURNAL
    if not jp.is_file():
        return {"restored": False}
    j = json.loads(jp.read_text(encoding="utf-8"))
    _plain_names([j["source_chroma"], j["source_meta"], j["prev_chroma"], j["prev_meta"]])  # journal 被改过也出不了数据根
    for live, src, prev in (("chroma", j["source_chroma"], j["prev_chroma"]),
                            ("meta", j["source_meta"], j["prev_meta"])):
        L, S, P = data_root / live, data_root / src, data_root / prev
        if L.exists() and not S.exists() and P.exists():
            L.rename(S)
        if P.exists() and not L.exists():
            P.rename(L)
    bad = [n for n in (j["prev_chroma"], j["prev_meta"]) if (data_root / n).exists()]
    bad += [n for n in (j["source_chroma"], j["source_meta"], "chroma", "meta") if not (data_root / n).exists()]
    if stamp_fp(data_root / "chroma") != j.get("old_fp"):
        bad.append("chroma stamp != old_fp")
    if bad:  # 终态不符时保留 journal（下次部署会因 journal_pending 被阻止），并以非零状态退出
        raise SystemExit(f"restore: 终态不符 {bad}，已保留 journal，需要人工处理")
    jp.unlink()
    return {"restored": True, "prod_fp12": fp12(j.get("old_fp") or "") or None}


def _plain_names(names: list[str]) -> list[str]:
    """名字只能是数据根下的一级目录名：带路径分隔符或 .. 的名字可以指到数据根之外。"""
    bad = [n for n in names if not n or n in (".", "..") or "/" in n or "\\" in n]
    if bad:
        raise SystemExit(f"目录名必须是数据根下的一级名字：{bad}")
    return names


def guard_copy(data_root: Path, names: list[str], ts: str) -> dict:
    """集合核对在副本上进行：目标镜像的 chromadb 打开目录时可能迁移 schema，因此不能触碰生产或候选的原件。"""
    _plain_names(names)
    g = data_root / f"kbsync_guard_{ts}"
    g.mkdir()
    for n in names:
        shutil.copytree(data_root / n, g / n, symlinks=True)
    return {"guard_dir": g.name}


def guard_clean(data_root: Path, ts: str) -> dict:
    g = data_root / f"kbsync_guard_{ts}"
    if g.is_dir():
        shutil.rmtree(g)
    return {"cleaned": g.name}


ACCEPT_PREFIX = "kbsync_accept_"


def accept_stage(data_root: Path, ts: str, chroma: str, meta: str) -> dict:
    """公开部署的临时验收容器用的数据副本：放在数据根的**上一级**（不在正式容器的挂载范围内），只含 chroma 与 meta。
    不复制 quota.sqlite：临时容器用自己的空库，验收不会写正式的额度计数。兄弟容器里数据根是只读挂载。"""
    _plain_names([chroma, meta])
    if not TS_RE.fullmatch(ts):
        raise SystemExit(f"accept-stage: 时间戳格式不对 {ts!r}")
    for n in (chroma, meta):
        if not (data_root / n).is_dir():
            raise SystemExit(f"accept-stage: 数据根里没有 {n}")
    stage = data_root.parent / f"{ACCEPT_PREFIX}{ts}"
    (stage / "data").mkdir(parents=True)
    shutil.copytree(data_root / chroma, stage / "data" / "chroma", symlinks=True)
    shutil.copytree(data_root / meta, stage / "data" / "meta", symlinks=True)
    return {"stage_dir": stage.name, "data": str(stage / "data")}


def accept_clean(data_root: Path) -> dict:
    """删掉数据根上一级里所有的验收副本（本次的和以前异常退出留下的）。只认 kbsync_accept_<时间戳> 这一种名字。"""
    pat = re.compile(rf"{ACCEPT_PREFIX}{TS_RE.pattern}")
    removed = []
    for d in sorted(data_root.parent.iterdir()):
        if pat.fullmatch(d.name) and d.is_dir() and not d.is_symlink():
            shutil.rmtree(d)
            removed.append(d.name)
    return {"removed": removed}


def finish(data_root: Path) -> dict:
    jp = data_root / JOURNAL
    if jp.is_file():
        jp.unlink()
        return {"finished": True}
    return {"finished": False}


def prune(data_root: Path, keep: int = 2) -> dict:
    """chroma_prev_* 按时间保留最新的 keep 份（连同配对的 meta_prev_*）；chroma_failed_* 永不处理。"""
    pat = re.compile(rf"chroma_prev_([0-9a-f]{{12}}|unknown)_({TS_RE.pattern})")
    prevs = sorted(((m.group(2), m.group(1), p.name) for p in data_root.iterdir()
                    if (m := pat.fullmatch(p.name))), reverse=True)
    removed = []
    for ts, f12, name in prevs[keep:]:
        for n in (name, f"meta_prev_{f12}_{ts}"):
            if (data_root / n).exists():
                shutil.rmtree(data_root / n)
                removed.append(n)
    for g in sorted(data_root.glob("kbsync_guard_*")):  # 上次 deploy-swap 异常时残留的核对副本
        if g.is_dir():
            shutil.rmtree(g)
            removed.append(g.name)
    return {"kept": [n for _, _, n in prevs[:keep]], "removed": removed}


# ── docker 封装（测试中替换为假实现）────────────────────────────────────────
class Docker:
    def run(self, args: list[str], *, input: bytes | None = None,
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        full = {**os.environ, **env} if env else None
        return subprocess.run(["docker", *args], input=input, capture_output=True, env=full)


STAGE_CMDS = {"accept-stage", "accept-clean"}  # 要写数据根上一级的子命令


def via(docker: Docker, image: str, data_root: str, fs_args: list[str]) -> dict:
    """在兄弟容器中运行本脚本的文件系统子命令（数据根按原路径挂载，脚本通过 stdin 传入）。
    验收副本的两个子命令改挂数据根的直接上一级（可写），数据根本身叠一层只读挂载：它们只能读数据根，不能改它。"""
    mounts = ["--mount", f"type=bind,src={data_root},dst={data_root}"]
    if fs_args[0] in STAGE_CMDS:
        parent = str(_norm(data_root).parent)
        if len(_norm(data_root).parts) < 4:  # 数据根太浅时，"上一级"会是 / 或 /Volumes 这样的位置
            raise RuntimeError(f"数据根 {data_root} 层级太浅，拒绝把它的上一级目录可写挂载")
        mounts = ["--mount", f"type=bind,src={parent},dst={parent}",
                  "--mount", f"type=bind,src={data_root},dst={data_root},readonly"]
    r = docker.run(["run", "-i", "--rm", *mounts, "--entrypoint", "python", image, "-", *fs_args],
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
    """data/ 只读挂载，候选 chroma/meta 以原生路径可写挂载覆盖（bind 源不存在时直接报错，不会写到生产目录）。"""
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

SECRET_RE = re.compile(
    r"sk-[A-Za-z0-9_*\-]{6,}|tvly-[A-Za-z0-9_*\-]{6,}|AIza[A-Za-z0-9_\-]{20,}|eyJ[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-.]+"
    r"|(?i:(?:bearer\s+|basic\s+|x-api-key[\"':=\s]+|api[_-]?key[\"':=\s]+|(?:access_)?token[\"':=\s]+"
    r"|secret[\"':=\s]+|password[\"':=\s]+))[A-Za-z0-9_*\-.+/=]{8,}")


def scrub(text: str) -> str:
    """日志里不留 key 片段（OpenAI 的报错会带打了星号的 key 尾部；也盖住 Bearer / x-api-key / api_key= 这类写法）。"""
    return SECRET_RE.sub("<已隐去>", text)


KEY_HINTS = {
    "quota_exhausted": "OpenAI 账户额度用尽或达到项目上限",
    "key_invalid": "OpenAI key 无效或没有设置",
    "key_forbidden": "OpenAI key 没有权限（项目或模型未放行）",
    "model_not_found": "embedding 模型不存在或该 key 不可用",
    "rate_limited": "OpenAI 限流（不是额度用尽），稍后重跑",
    "setup_error": "镜像里读不到配置或 litellm",
    "no_result": "检查容器没有产出结果（env 文件或镜像不可用）",
    "other": "其他 provider 错误",
}


def classify_failure(text: str) -> str | None:
    """把某一步 stderr 里的 provider 报错归成类别；只返回类别名，不返回报错原文。
    额度用尽与限流在 OpenAI 那边同为 429，必须先判额度（否则会被当成可重试的限流）。"""
    t = text.lower()
    if "insufficient_quota" in t or "exceeded your current quota" in t:
        return "quota_exhausted"
    if "invalid_api_key" in t or "incorrect api key" in t or "authenticationerror" in t:
        return "key_invalid"
    if "ratelimiterror" in t or "rate limit" in t:
        return "rate_limited"
    return None


def candidate(docker: Docker, a: argparse.Namespace) -> int:
    """依次执行 prepare、基线 eval（生产镜像）、候选镜像 ingest 与 build_meta、候选 eval、gate。"""
    D, fp, ts = a.data_root, a.fp, a.ts or now_ts()
    if not FP_RE.fullmatch(fp) or not TS_RE.fullmatch(ts):  # 两者都会进挂载路径
        raise SystemExit("candidate: --fp 必须是 64 位十六进制，--ts 必须形如 20261128T010203Z")
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
            err = r.stderr.decode("utf-8", "replace")
            tail = scrub(err).strip().splitlines()[-20:]
            print(f"[kbsync] {name} rc={r.returncode}\n" + "\n".join(tail))
            reason = f"{name}_rc{r.returncode}"
            cat = classify_failure(err)
            if cat:  # key 无效或额度用尽：明确说出原因，不让它只表现为一个 rc
                print(f"[kbsync] 失败原因归类：{cat}（{KEY_HINTS[cat]}；env 文件 {a.env_file}）")
                reason += f"_{cat}"
            res = via(docker, a.prod_image, D, ["fail", "--data-root", D, "--fp", fp, "--ts", ts,
                                                "--reason", reason])
            print(json.dumps(res))
            return 1
    if a.kb_only:
        # 公开腿：候选建完、过闸之前，集合必须恰为 {sdtm_kb_v1}。不放进 gate：gate 在兄弟容器里跑，调不了 docker。
        # 候选目录刚由候选镜像写出，用同一镜像打开，不存在跨版本迁移。只输出计数，不输出集合名。
        try:
            names = set(collections(docker, a.cand_image, f"{D}/{c}"))
        except (RuntimeError, ValueError, IndexError) as e:
            print(f"[kbsync] kb-only：读不出候选的集合（{type(e).__name__}），按违规处理")
            reason = "kb_only_unreadable"
        else:
            extra = len(names - {KB_COLLECTION})
            reason = None if names == {KB_COLLECTION} else "kb_only_violation"
            print(f"[kbsync] kb-only：{KB_COLLECTION} {'在' if KB_COLLECTION in names else '缺失'}，"
                  f"非 KB 集合 {extra} 个")
        if reason:
            res = via(docker, a.prod_image, D, ["fail", "--data-root", D, "--fp", fp, "--ts", ts,
                                                "--reason", reason])
            print(json.dumps(res))
            return 1
    info = json.dumps({"ref": a.ref, "a_commit": a.a_commit, "image": a.cand_image,
                       "prod_image": a.prod_image, "chromadb": chromadb_version(docker, a.cand_image),
                       **({"prod_image_ref": a.prod_image_ref} if a.prod_image_ref else {})})
    res = via(docker, a.prod_image, D, ["gate", "--data-root", D, "--fp", fp, "--ts", ts,
                                        "--max-regressions", str(a.max_regressions), "--info", info])
    summary = {k: res.get(k) for k in ("verdict", "reason", "n_questions", "baseline_full",
                                       "candidate_full", "candidate_avg", "regressed_ids",
                                       "improved_ids", "chromadb", "archived")}
    print("[kbsync] gate " + json.dumps(summary))
    return 0 if res["verdict"] == "PASS" else 1


# 每个集合输出条数；非 KB 集合另外计算内容摘要 = sha256（按 id 排序的 [id, document, metadata]）。只输出摘要，不输出内容。
COLLECTIONS_PY = """
import chromadb, hashlib, json, sys
c = chromadb.PersistentClient(path=sys.argv[1])
kb = sys.argv[2]
out = {}
for x in c.list_collections():
    col = c.get_collection(x.name)
    n = col.count()
    e = {"count": n}
    if x.name != kb:
        rows = []
        for off in range(0, n, 1000):
            g = col.get(limit=1000, offset=off, include=["documents", "metadatas"])
            k = len(g["ids"])
            rows += zip(g["ids"], g["documents"] or [None] * k, g["metadatas"] or [None] * k)
        h = hashlib.sha256()
        for row in sorted(rows, key=lambda r: r[0]):
            h.update(json.dumps(list(row), sort_keys=True, ensure_ascii=False, default=str).encode())
            h.update(b"\\n")
        e["digest"] = h.hexdigest()
    out[x.name] = e
print(json.dumps(out))
"""
CHROMADB_VERSION_PY = "import chromadb;print(chromadb.__version__)"


def collections(docker: Docker, image: str, host_dir: str) -> dict[str, dict]:
    # chromadb 无法打开只读目录（实测报 sqlite "readonly database"），因此使用可写挂载。
    # 只用于副本（guard / 验收副本），或刚由同一镜像写出的候选目录（kb-only），不用于线上目录原件
    r = docker.run(["run", "--rm", "--mount", f"type=bind,src={host_dir},dst=/c", "--entrypoint",
                    "python", image, "-c", COLLECTIONS_PY, "/c", KB_COLLECTION])
    if r.returncode != 0:
        raise RuntimeError(f"读取集合失败 {Path(host_dir).name} rc={r.returncode}")
    return json.loads(r.stdout.decode().strip().splitlines()[-1])


# 入库和评测都要用 embedding key。先做一次最小调用，把"key 无效 / 额度用尽"与"入库失败"分开。
# 只输出类别、HTTP 状态和异常类名；不输出报错原文（原文可能带 key 片段）。
KEY_CHECK_PY = """
import json, sys


def classify(exc):
    s = str(exc).lower()
    status = getattr(exc, "status_code", None)
    name = type(exc).__name__
    if "insufficient_quota" in s or "exceeded your current quota" in s:
        cat = "quota_exhausted"  # 与限流同为 429，先判
    elif status == 401 or name == "AuthenticationError" or "invalid_api_key" in s or "incorrect api key" in s:
        cat = "key_invalid"
    elif status == 403 or name == "PermissionDeniedError":
        cat = "key_forbidden"
    elif status == 404 or name == "NotFoundError":
        cat = "model_not_found"
    elif status == 429 or name == "RateLimitError":
        cat = "rate_limited"
    else:
        cat = "other"
    return {"ok": False, "category": cat, "status": status, "error_class": name}


def main():
    try:
        from server.config import settings
        import litellm
        model = settings.embedding_model
    except Exception as exc:
        return {"ok": False, "category": "setup_error", "error_class": type(exc).__name__}
    try:
        r = litellm.embedding(model=model, input=["kbsync key check"])
        dim = len(r.data[0]["embedding"])
    except Exception as exc:
        return classify(exc)
    return {"ok": True, "category": "ok", "model": model, "dim": dim}


if __name__ == "__main__":
    out = main()
    print(json.dumps(out))
    sys.exit(0 if out["ok"] else 1)
"""


def key_check(docker: Docker, image: str, env_file: str, *, retries: int = 2, sleep=time.sleep) -> dict:
    """用 env 文件里的 key 做一次最小 embedding 调用。限流（非额度用尽）时等一会儿重试，其余失败立即返回。"""
    return _probe(docker, image, env_file, KEY_CHECK_PY, transient={"rate_limited"}, retries=retries, sleep=sleep)


# ── 公开实例：compose 模型与路径一致性 ──────────────────────────────────────
PUBLIC_SERVICE = "api"
APP_DATA, APP_ENV = "/app/data", "/app/.env"


def compose_model(docker: Docker, compose_file: str, image_tag: str = "x") -> dict:
    """`docker compose config` 解析后的模型（只读，不创建任何资源）。"""
    r = docker.run(["compose", "-f", compose_file, "config", "--format", "json"], env={"IMAGE_TAG": image_tag})
    if r.returncode != 0:
        tail = r.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise RuntimeError(f"compose config {compose_file} rc={r.returncode}: {' | '.join(tail)}")
    return json.loads(r.stdout.decode("utf-8"))


def _overlap(a: str, b: str) -> bool:
    """相同或互为上下级（按路径分量比较，不按字符串前缀：/x/data 与 /x/data2 不算重叠）。"""
    pa, pb = _norm(a).parts, _norm(b).parts
    n = min(len(pa), len(pb))
    return pa[:n] == pb[:n]


def paths_problems(pub: dict, priv: dict, data_root: str, env_file: str) -> list[str]:
    """公开数据根 / env 文件必须就是公开 compose 里 api 服务的挂载源，且与私有 compose 的任何挂载源都不重叠
    （相同、互为上下级都算重叠）。私有一侧取自私有 compose 文件，本函数不接受第二个数据根。"""
    svc = (pub.get("services") or {}).get(PUBLIC_SERVICE)
    if not svc:
        return [f"公开 compose 没有 {PUBLIC_SERVICE} 服务"]
    problems = []
    mounts = {v.get("target"): v for v in svc.get("volumes") or []}
    for target, want, label in ((APP_DATA, data_root, "数据根"), (APP_ENV, env_file, "env 文件")):
        v = mounts.get(target)
        if not v or v.get("type") != "bind" or not v.get("source"):
            problems.append(f"公开 compose 没有 {target} 的 bind 挂载")
        elif _norm(v["source"]) != _norm(want):
            problems.append(f"{label} {want} 与公开 compose 的 {target} 挂载源 {v['source']} 不一致")
    priv_sources = sorted({v["source"] for sv in (priv.get("services") or {}).values()
                           for v in sv.get("volumes") or [] if v.get("type") == "bind" and v.get("source")})
    if not priv_sources:  # 抽不出私有挂载源时，下面的"不重叠"会变成永真
        problems.append("私有 compose 没有解析出任何 bind 挂载源，无法确认公开根与私有根不同")
    # 数据根的上一级目录放临时验收副本，部署时会被可写挂载：它同样不得碰到私有挂载源
    parent = str(_norm(data_root).parent)
    mine_all = [(data_root, "数据根"), (env_file, "env 文件"), (parent, "数据根的上一级目录")]
    # 公开 api 服务的其他挂载（将来新增的只读挂载也会原样带进临时容器）同样不得指向私有挂载源
    # （公开 compose 里将来若有别的服务，它们的挂载也算）
    mine_all += [(v["source"], f"{name} 服务挂载 {v.get('target')} 的源")
                 for name, sv in (pub.get("services") or {}).items() for v in sv.get("volumes") or []
                 if v.get("type") == "bind" and v.get("source")
                 and not (name == PUBLIC_SERVICE and v.get("target") in (APP_DATA, APP_ENV))]
    for mine, label in mine_all:
        problems += [f"公开{label} {mine} 与私有 compose 的挂载源 {ps} 重叠" for ps in priv_sources
                     if _overlap(mine, ps)]
    return problems


def paths_check(docker: Docker, a: argparse.Namespace) -> int:
    problems = paths_problems(compose_model(docker, a.compose_file), compose_model(docker, a.private_compose_file),
                              a.data_root, a.env_file)
    for pr in problems:
        print(f"[kbsync] 路径不一致：{pr}")
    if problems:
        print("[kbsync] 公开数据根 / env 文件与 compose 对不上，拒绝继续（不读写任何数据）")
        return 1
    print(f"[kbsync] 路径一致：数据根 {a.data_root}，env 文件 {a.env_file}，与私有挂载源不重叠")
    return 0


def image_present(docker: Docker, image: str) -> bool:
    return docker.run(["image", "inspect", image]).returncode == 0


def baseline_image(docker: Docker, data_root: str, images: list[str], via_image: str) -> tuple[str | None, str | None, list]:
    """基线镜像必须与数据根里的 chroma 配对：镜像内 KB 指纹 == chroma stamp。按给定顺序取第一个相等的。
    基线评测用镜像自带的题集和镜像内的 KB；不配对时基线先掉分，逐题回退与满分下限两条相对闸都会被放宽。
    stamp 由 via_image（私有线上镜像）去读：候选基线镜像在被证明配对之前不挂载数据根。
    不在本机的镜像一律不用（不触发拉取）。"""
    fp = via(docker, via_image, data_root, ["stamp", "--data-root", data_root]).get("fp")
    rows = []
    for img in dict.fromkeys(i for i in images if i):
        if not image_present(docker, img):
            rows.append((img, "不在本机"))
            continue
        ifp = image_fp(docker, img)
        rows.append((img, ifp))
        if fp and ifp == fp:
            return img, fp, rows
    return None, fp, rows


def chromadb_version(docker: Docker, image: str) -> str:
    r = docker.run(["run", "--rm", "--entrypoint", "python", image, "-c", CHROMADB_VERSION_PY])
    out = r.stdout.decode().strip().splitlines()
    return out[-1] if r.returncode == 0 and out else "unknown"


def non_kb(cols: dict[str, dict]) -> dict[str, dict]:
    return {k: v for k, v in cols.items() if k != KB_COLLECTION}


def swap_guard(docker: Docker, a: argparse.Namespace, ts: str) -> bool:
    """换入前的只读核对，不改动数据根里的任何线上或候选目录：非 KB 集合（名称、条数、内容摘要）必须与生产一致，
    带 --kb-only 时两边都不得有非 KB 集合。核对在副本上进行（目标镜像的 chromadb 版本可能与写库时的版本不同，
    打开目录就可能触发迁移）；原件在换入前不会被任何 chromadb 打开。"""
    D = a.data_root
    ver = ["--chromadb-version", a.chromadb_version]
    chk = via(docker, a.image, D, ["predeploy-check", "--data-root", D, "--target-fp", a.target_fp, *ver])
    if chk["decision"] != "swap":
        print(f"[kbsync] 无法换入: {json.dumps(chk)}")
        return False
    expect = getattr(a, "expect_source", "")
    if expect and chk["source_chroma"] != expect:
        print(f"[kbsync] 拒绝换入：换入源变了（验收的是 {expect}，现在选出的是 {chk['source_chroma']}）")
        return False
    src = chk["source_chroma"]
    try:  # guard-copy 也放在 try 内：复制到一半失败时同样会清理 kbsync_guard_<ts>
        g = via(docker, a.image, D, ["guard-copy", "--data-root", D, "--ts", ts, "--names", "chroma", src])
        prod_all = collections(docker, a.image, f"{D}/{g['guard_dir']}/chroma")
        src_all = collections(docker, a.image, f"{D}/{g['guard_dir']}/{src}")
        prod_cols, src_cols = non_kb(prod_all), non_kb(src_all)
    finally:
        via(docker, a.image, D, ["guard-clean", "--data-root", D, "--ts", ts])
    if a.kb_only and (prod_cols or src_cols or KB_COLLECTION not in src_all):
        # 公开数据根的主闸：线上与换入源都不得有非 KB 集合（"两边相同"不算通过），换入源必须有 KB 集合
        print(f"[kbsync] 拒绝换入（kb-only）：线上非 KB 集合 {len(prod_cols)} 个，换入源非 KB 集合 {len(src_cols)} 个，"
              f"换入源 {KB_COLLECTION} {'在' if KB_COLLECTION in src_all else '缺失'}；数据未改动，需要人工排查")
        return False
    if prod_cols != src_cols:
        diff = sorted(k for k in set(prod_cols) | set(src_cols) if prod_cols.get(k) != src_cols.get(k))
        print(f"[kbsync] 拒绝换入：非 KB 集合与生产不一致（{len(diff)} 个集合的名称、条数或内容摘要不同），"
              "生产未改动。候选建好后 study 集合有变化，请重新运行 kb-sync")
        return False
    return True


def deploy_swap(docker: Docker, a: argparse.Namespace) -> int:
    """部署时换数据（服务必须已停止）：先做 swap_guard 的核对，通过后才改名换入。"""
    D, ts = a.data_root, a.ts or now_ts()
    if not swap_guard(docker, a, ts):
        return 1
    extra = ["--expect-source", a.expect_source] if getattr(a, "expect_source", "") else []
    print(json.dumps(via(docker, a.image, D, ["swap", "--data-root", D, "--target-fp", a.target_fp, "--ts", ts,
                                              "--chromadb-version", a.chromadb_version, *extra])))
    return 0


def journal_state(docker: Docker, image: str, data_root: str) -> int:
    """供 workflow 的退回步骤使用：0 = 无 journal，3 = journal 存在（数据换了一半或未完全退回），2 = 无法判断。
    无法判断不等于没有 journal：调用方对 2 和 3 同样按"不能改动镜像、不能启动服务"处理。"""
    try:
        res = via(docker, image, data_root, ["swap-status", "--data-root", data_root])
    except (RuntimeError, ValueError) as e:
        print(f"[kbsync] 无法判断 journal 状态: {e}", file=sys.stderr)
        return 2
    if res.get("pending") is True:
        return 3
    return 0 if res.get("pending") is False else 2


IMAGE_FP_PY = ("from scripts.kb_freshness import kb_fingerprint;from server.config import settings;"
               "print(kb_fingerprint(settings.kb_root))")


def image_fp(docker: Docker, image: str) -> str:
    """返回镜像内的 KB 指纹；旧镜像（没有 scripts.kb_freshness）或出现任何异常时返回 'unknown'。"""
    r = docker.run(["run", "--rm", "--entrypoint", "python", image, "-c", IMAGE_FP_PY])
    out = r.stdout.decode().strip().splitlines()
    if r.returncode == 0 and out and FP_RE.fullmatch(out[-1]):
        return out[-1]
    tail = r.stderr.decode("utf-8", "replace").strip().splitlines()[-5:]
    print(f"[kbsync] image-fp {image} rc={r.returncode}: " + " | ".join(tail), file=sys.stderr)
    return "unknown"


def local_fp(kb_root: str) -> str:
    import importlib.util
    p = Path(__file__).resolve().parents[2] / "scripts" / "kb_freshness.py"
    spec = importlib.util.spec_from_file_location("kb_freshness", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass 解析注解时需要查找 sys.modules
    spec.loader.exec_module(mod)
    return mod.kb_fingerprint(Path(kb_root))


# ── 公开部署：先用临时容器验收，通过后才动正式容器（M3）；之后任何失败都停机（D2）──────────
ACCEPT_PROJECT = "sdtm-rag-public-accept"        # 独立的 compose 项目：up / rm 不会碰到正式项目的容器
ACCEPT_CONTAINER = "sdtm-rag-public-accept-api"  # 与正式容器不同名，隧道按名字解析不到它
# 临时服务只从公开 compose 的 api 服务取这些键（白名单）。ports / networks / 别名 / 其他服务一律带不进来
ACCEPT_KEEP = ("image", "environment", "mem_limit", "healthcheck", "command", "entrypoint")

# 与正式容器同一套验收：档位 = public，内部接口关闭。
# 公开档带全局限流（compose 里每个来源每分钟 60 个请求、突发 20，/api/health 不计）：这段脚本一共只发 2 个请求，
# 每次验收只跑一遍；健康状态看的是 docker 的健康检查（打的是 /api/health）。有测试钉住请求数，改这里要留足余量。
ACCEPT_PY = """
import json, sys, urllib.request, urllib.error
base = "http://127.0.0.1:8000"
info = json.load(urllib.request.urlopen(base + "/api/info", timeout=5))
if info.get("tier") != "public":
    sys.exit("tier != public")
try:
    urllib.request.urlopen(base + "/openapi.json", timeout=5)
    sys.exit("/openapi.json 未关闭")
except urllib.error.HTTPError as e:
    if e.code != 404:
        sys.exit(f"/openapi.json 返回 {e.code}")
print("tier=public, /openapi.json 404")
"""

# 答题 key 的有效性探测：只调「列出模型」（GET /v1/models，不产生 token），不发任何答题请求。
# 接口与错误类型依据 Anthropic 官方文档（api/models/list、api/errors：401 = authentication_error）。
# 只输出类别、HTTP 状态和异常类名；key 只在进程内交给 SDK，不进命令行、不进输出。
ANSWER_KEY_PY = """
import itertools, json, os, sys


def main():
    try:
        from server.config import settings  # 顺带把 .env 读进环境变量
        import anthropic
    except Exception as exc:
        return {"ok": False, "category": "setup_error", "error_class": type(exc).__name__}
    # 公开档用服务端 key 答题时走的是 selectable_models 与内部四组，不只是 default_model：有一个是 Anthropic 就探测
    models = [str(getattr(settings, k, "") or "") for k in ("default_model", "fallback_model", "hard_model", "light_model")]
    models += [str(getattr(m, "model", "") or "") for m in (getattr(settings, "selectable_models", None) or [])]
    if not any(m.startswith("anthropic/") for m in models):
        return {"ok": True, "category": "not_applicable", "providers": sorted({m.split("/", 1)[0] for m in models if m})}
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return {"ok": False, "category": "key_missing"}
    try:
        client = anthropic.Anthropic(api_key=key, max_retries=1, timeout=20.0)
        n = sum(1 for _ in itertools.islice(client.models.list(limit=1), 1))
    except anthropic.AuthenticationError as exc:
        return {"ok": False, "category": "key_invalid", "status": exc.status_code, "error_class": type(exc).__name__}
    except anthropic.PermissionDeniedError as exc:
        return {"ok": False, "category": "key_forbidden", "status": exc.status_code, "error_class": type(exc).__name__}
    except anthropic.RateLimitError as exc:
        return {"ok": False, "category": "rate_limited", "status": exc.status_code, "error_class": type(exc).__name__}
    except anthropic.APIStatusError as exc:
        return {"ok": False, "category": "provider_error", "status": exc.status_code, "error_class": type(exc).__name__}
    except anthropic.APIConnectionError as exc:
        return {"ok": False, "category": "network_error", "error_class": type(exc).__name__}
    except Exception as exc:
        return {"ok": False, "category": "other", "error_class": type(exc).__name__}
    return {"ok": True, "category": "ok", "models": n}


if __name__ == "__main__":
    out = main()
    print(json.dumps(out))
    sys.exit(0 if out["ok"] else 1)
"""
ANSWER_KEY_HINTS = {
    "key_invalid": "公开站的答题 key 无效（Anthropic 返回 401）",
    "key_missing": "公开站的 env 文件里没有 ANTHROPIC_API_KEY",
    "key_forbidden": "公开站的答题 key 没有权限（Anthropic 返回 403）",
    "rate_limited": "Anthropic 限流，探测没有完成（不是 key 无效）",
    "provider_error": "Anthropic 接口返回错误，探测没有完成（不是 key 无效）",
    "network_error": "连不上 Anthropic，探测没有完成（不是 key 无效）",
    "setup_error": "镜像里读不到配置或 anthropic SDK",
    "no_result": "探测容器没有产出结果（env 文件或镜像不可用）",
    "other": "探测出错",
}
PROBE_TRANSIENT = {"rate_limited", "provider_error", "network_error"}


def _probe(docker: Docker, image: str, env_file: str, script: str, *, transient: set[str], retries: int = 2,
           sleep=time.sleep, public_tier: bool = False, network: str = "") -> dict:
    """在一次性容器里跑探测脚本（只挂 env 文件，只读）。结果与退出码对不上时一律按失败处理。
    public_tier：按公开档解析配置（与正式容器一致）；命令行里只有档位，没有任何密钥。
    network：加入指定的 docker 网络（公开部署的答题 key 探测走公开网络，受它的隔离规则约束）。"""
    app = _workdir(docker, image)
    tier = ["-e", "SDTM_RAG_INSTANCE=public"] if public_tier else []
    # 接在公开网络里的一次性容器（隧道那条线的五条约束）：不指定地址、不起名字或别名、去掉全部 capability
    # （默认的 NET_RAW 能在网桥上冒领别人的地址）、key 只经只读挂载的 env 文件传入、--rm 且不监听端口
    tier += [*ONE_OFF_HARDENING, "--network", network] if network else []
    res: dict = {}
    for attempt in range(retries + 1):
        r = docker.run(["run", "--rm", *tier, "--mount", f"type=bind,src={env_file},dst={app}/.env,readonly",
                        "--entrypoint", "python", image, "-c", script])
        out = r.stdout.decode("utf-8", "replace").strip().splitlines()
        try:
            res = json.loads(out[-1])
        except (IndexError, ValueError):
            res = {}
        if not isinstance(res, dict) or "ok" not in res or (res["ok"] is True) != (r.returncode == 0):
            tail = scrub(r.stderr.decode("utf-8", "replace")).strip().splitlines()[-3:]
            res = {"ok": False, "category": "no_result", "rc": r.returncode, "stderr_tail": " | ".join(tail)}
        if res.get("category") not in transient or attempt == retries:
            break
        sleep(20)
    return res


ONE_OFF_HARDENING = ["--cap-drop", "ALL", "--security-opt", "no-new-privileges"]
DRILL = "docs/plans/P3_4_tunnel_drill.md"  # 隧道那条线的演练方案：网络重建是它的第 2 步，隔离规则是第 3 步
TARGET_RE = re.compile(r"[A-Za-z0-9.\-]+:\d{1,5}")


def public_network(model: dict) -> tuple[str, str | None]:
    """公开 compose 里 api 服务所接的那个网络：（docker 网络名，compose 里写定的子网；没写则 None）。"""
    svc = (model.get("services") or {}).get(PUBLIC_SERVICE) or {}
    keys = list(svc.get("networks") or {})
    if len(keys) != 1:
        raise RuntimeError(f"公开 compose 的 api 服务应当只接一个网络，现在是 {len(keys)} 个")
    net = (model.get("networks") or {}).get(keys[0]) or {}
    subnets = [c.get("subnet") for c in ((net.get("ipam") or {}).get("config") or []) if c.get("subnet")]
    return net.get("name") or keys[0], (subnets[0] if len(subnets) == 1 else None)


def network_check(docker: Docker, name: str, want: str | None) -> str | None:
    """只读：公开网络的实际子网必须就是 compose 里写定的那个（可信代理地址、隔离规则都按它写）。通过返回 None。"""
    if not want:
        return "公开 compose 没有给公开网络写定子网（隧道那条线的改动还没有合进来？）"
    r = docker.run(["network", "inspect", name, "-f", "{{range .IPAM.Config}}{{.Subnet}} {{end}}"])
    if r.returncode != 0:
        return f"公开网络 {name} 不存在或查不出；先做网络重建那一步（{DRILL} 第 2 步）"
    got = r.stdout.decode("utf-8", "replace").split()
    if got != [want]:
        return f"公开网络 {name} 的子网是 {got or '空'}，应为 {want}；先做网络重建那一步（{DRILL} 第 2 步）"
    return None


def isolation_check(docker: Docker, image: str, net: str, subnet: str, script: str, lan: list[str],
                    egress: list[str], *, run=subprocess.run) -> str | None:
    """只读：公开网络确实被隔离着。隔离侧 = 公开网络里的一次性容器（不挂数据、不带 env 文件），对照侧 = 默认网桥上的
    一次性容器，用同一批内网目标；结论交给隧道那条线的 isolation_probe.py judge（退出码 0 才算通过）。
    探测脚本不进镜像，经标准输入送进容器。通过返回 None。"""
    path = Path(script)
    if not path.is_file():
        return f"隔离探测脚本 {script} 不存在（它在隧道那条线的改动里，两条线要一起合并）"
    bad = [t for t in (*lan, *egress) if not TARGET_RE.fullmatch(t)]
    if not lan or not egress or bad:
        return f"隔离探测的目标清单不对（内网 {len(lan)} 个、外网 {len(egress)} 个、格式不对的 {len(bad)} 个）"
    body = path.read_bytes()

    def probe(network: str, targets: list[str]) -> dict:
        r = docker.run(["run", "--rm", "-i", *ONE_OFF_HARDENING, "--network", network, "--entrypoint", "python",
                        image, "-", "probe", *targets], input=body)
        out = r.stdout.decode("utf-8", "replace").strip().splitlines()
        if r.returncode != 0 or not out:  # 漏了 -i 时脚本没送进去：退出码 0 但没有输出，同样不算数
            raise RuntimeError(f"隔离探测容器（网络 {network}）rc={r.returncode}，输出 {len(out)} 行")
        obs = json.loads(out[-1])
        if not (isinstance(obs, dict) and isinstance(obs.get("src"), str) and isinstance(obs.get("lan"), dict)
                and isinstance(obs.get("egress"), dict)):
            raise ValueError(f"隔离探测容器（网络 {network}）的输出不是一份观测")
        return obs

    lan_args = [x for t in lan for x in ("--lan", t)]
    try:
        isolated = probe(net, [*lan_args, *[x for t in egress for x in ("--egress", t)]])
        control = probe("bridge", lan_args)
    except (RuntimeError, ValueError) as e:
        return f"隔离探测没有跑成：{type(e).__name__}: {scrub(str(e))}"
    with tempfile.TemporaryDirectory(prefix="isolation-") as tmp:
        fi, fc = Path(tmp) / "isolated.json", Path(tmp) / "control.json"
        fi.write_text(json.dumps(isolated), encoding="utf-8")
        fc.write_text(json.dumps(control), encoding="utf-8")
        j = run([sys.executable, str(path), "judge", "--isolated", str(fi), "--control", str(fc),
                 "--isolated-net", subnet], capture_output=True, text=True)
    for ln in (j.stdout or "").strip().splitlines():
        print(f"[deploy-public] 隔离核对：{ln}")
    if j.returncode != 0:
        meaning = {1: "不隔离或需要的出站被挡", 2: "无结论"}.get(j.returncode, "判定脚本自己出错")
        return f"网络隔离核对没有通过（judge 退出码 {j.returncode}：{meaning}）；见 {DRILL} 第 3 步"
    return None


def accept_spec(model: dict, stage_data: str) -> tuple[dict, list[str]]:
    """由解析后的公开 compose 模型生成临时验收项目：同镜像、同环境变量、同 env 文件，数据换成副本，不联网、不重启。
    返回（compose 模型，被忽略的键名）。可写挂载只允许 /app/data（换成副本）；其他可写挂载会与正式容器共用状态，拒绝。"""
    svc = (model.get("services") or {}).get(PUBLIC_SERVICE)
    if not svc:
        raise RuntimeError(f"公开 compose 没有 {PUBLIC_SERVICE} 服务")
    if (svc.get("environment") or {}).get("SDTM_RAG_INSTANCE") != "public":
        raise RuntimeError("公开 compose 的 api 服务没有 SDTM_RAG_INSTANCE=public")
    vols, has_data = [], False
    for v in svc.get("volumes") or []:
        if v.get("type") != "bind" or not v.get("source") or not v.get("target"):
            raise RuntimeError(f"公开 compose 有非 bind 挂载 {v.get('target')}，临时验收不知道如何隔离它")
        if v["target"] == APP_DATA:
            has_data = True
            vols.append({"type": "bind", "source": stage_data, "target": APP_DATA, "bind": {"create_host_path": False}})
        elif v.get("read_only") is True:
            vols.append({"type": "bind", "source": v["source"], "target": v["target"], "read_only": True,
                         "bind": {"create_host_path": False}})
        else:
            raise RuntimeError(f"公开 compose 的可写挂载 {v['target']} 会让临时容器与正式容器共用状态")
    if not has_data:
        raise RuntimeError(f"公开 compose 没有 {APP_DATA} 挂载")
    out = {k: svc[k] for k in ACCEPT_KEEP if svc.get(k) is not None}
    out.update(container_name=ACCEPT_CONTAINER, network_mode="none", restart="no", volumes=vols)
    known = {*ACCEPT_KEEP, "volumes", "container_name", "restart", "networks"}
    ignored = sorted(k for k, val in svc.items() if k not in known and val is not None)
    return {"name": ACCEPT_PROJECT, "services": {PUBLIC_SERVICE: out}}, ignored


def container_state(docker: Docker, name: str) -> dict | None:
    """容器不存在 → None；查不出来（docker 报别的错）→ 抛异常，调用方不得把它当成"不存在"。"""
    fmt = "{{.State.Running}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}|{{.Config.Image}}"
    r = docker.run(["inspect", "--type", "container", "-f", fmt, name])  # 同名的镜像 / 网络不算
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace").lower()
        if "no such container" in err or "no such object" in err:
            return None
        raise RuntimeError(f"查不出容器 {name} 的状态 rc={r.returncode}")
    lines = r.stdout.decode("utf-8", "replace").strip().splitlines()
    parts = lines[-1].split("|") if lines else []
    if len(parts) != 4 or parts[0] not in ("true", "false"):
        raise RuntimeError(f"容器 {name} 的状态输出无法解析")
    return {"running": parts[0] == "true", "status": parts[1], "health": parts[2], "image": parts[3]}


def accept_check(docker: Docker, name: str, *, tries: int = 60, sleep=time.sleep) -> str | None:
    """对一个正在运行的公开档容器做验收（健康 / 档位 = public / 内部接口关闭 / 索引新鲜度）。通过返回 None，否则返回原因。"""
    healthy = False
    for _ in range(tries):
        st = container_state(docker, name)
        if st is None or st["status"] in ("exited", "dead"):
            break
        if st["health"] == "healthy":
            healthy = True
            break
        sleep(3)
    if not healthy:
        logs = docker.run(["logs", "--tail", "40", name])
        # 带出之前先过两道：scrub 隐去 key 片段；_hide_study_names 隐去不按约定的 study 集合名。
        # 两道都作用在整段日志上，下面打印的日志末尾和失败原因里的那一行用的是同一份
        text = _hide_study_names(scrub((logs.stdout + logs.stderr).decode("utf-8", "replace")))
        tail = text.strip().splitlines()[-40:]
        print(f"[deploy-public] {name} 未就绪，日志末尾：\n" + "\n".join(tail))
        # 应用拒绝启动时（公开档的各项启动自检）最后一条报错带进失败原因，不用翻日志
        errors = [ln.strip() for ln in tail if re.search(r"\b\w*(Error|Exception)\b:", ln)]
        return "容器没有进入 healthy 状态" + (f"；启动报错：{errors[-1][:600]}" if errors else "")
    r = docker.run(["exec", name, "python", "-c", ACCEPT_PY])
    if r.returncode != 0:
        last = scrub(r.stderr.decode("utf-8", "replace")).strip().splitlines()[-1:]
        return "档位 / 内部接口检查不通过：" + (last[0] if last else f"rc={r.returncode}")
    r = docker.run(["exec", name, "python", "-m", "scripts.check_index_freshness"])
    if r.returncode != 0:
        return f"索引新鲜度检查不通过（check_index_freshness rc={r.returncode}）"
    return None


def accept_down(docker: Docker, image: str, data_root: str) -> list[str]:
    """清掉临时验收容器和数据副本。幂等：每次部署开头先扫一遍（上次被杀掉时留下的），验收结束后再清一遍。"""
    problems = []
    docker.run(["rm", "-f", ACCEPT_CONTAINER])
    try:
        if container_state(docker, ACCEPT_CONTAINER) is not None:
            problems.append(f"临时容器 {ACCEPT_CONTAINER} 删不掉")
    except RuntimeError as e:
        problems.append(str(e))
    try:
        via(docker, image, data_root, ["accept-clean", "--data-root", data_root])
    except (RuntimeError, ValueError) as e:
        problems.append(f"验收副本清理失败：{e}")
    return problems


class _HaltError(Exception):
    """正式容器已经被动过之后的失败：一律停机，数据按 journal 处理。"""


def _summary(lines: list[str]) -> None:
    for ln in lines:
        print(f"[deploy-public] {ln}")
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n".join(["### 公开实例部署", *[f"- {ln}" for ln in lines], ""]) + "\n")
        except OSError:
            pass


def public_halt(docker: Docker, a: argparse.Namespace, name: str, image: str, why: str, prev_image: str) -> None:
    """失败后的唯一出路：停掉公开项目的全部容器 → 看 journal → 能退数据就退 → 保持停止。本函数里没有任何启动动作。"""
    D = a.data_root
    # 这个函数本身不能抛异常（它就是最后一道处理）：每一步出错都按「没做成」记，继续往下走
    try:
        docker.run(["compose", "-f", a.compose_file, "stop"], env={"IMAGE_TAG": "x"})
        st = container_state(docker, name)
        stopped = st is None or not st["running"]
        now_image = st["image"] if st else ""
    except Exception:  # noqa: BLE001
        stopped, now_image = False, "?"
    if not stopped:
        data = "没有确认正式容器已停止，数据未做任何退回动作（journal 原样保留）"
    else:
        try:
            js = journal_state(docker, image, D)
        except Exception:  # noqa: BLE001
            js = 2
        if js == 0:
            data = "数据根没有 journal：没有换入，或换入已经收尾（以 chroma stamp 为准）"
        elif js == 3:
            try:
                via(docker, image, D, ["restore", "--data-root", D])
                data = "已按 journal 把 chroma / meta 退回部署前状态"
            except Exception:  # noqa: BLE001
                data = "按 journal 退回数据失败，journal 保留；下一次公开部署和 kb-sync 公开腿都会因 journal_pending 失败"
        else:
            data = "无法判断 journal 状态，没有改动数据"
    if now_image == image and image != prev_image:
        box = f"正式容器现在是镜像 {image}（没有通过的那一版），部署前是 {prev_image or '无'}；不要直接 docker start。"
    elif now_image == "?":
        box = "正式容器的镜像查不出来；确认之前不要 docker start。"
    elif not now_image:
        box = "正式容器现在不存在。"
    else:
        box = f"正式容器仍是镜像 {now_image}（没有被替换）。"
    _summary([
        f"失败：{why}",
        f"公开实例{'已停止' if stopped else '状态不明，请立即人工确认'}（公开站下线，私有实例不受影响）。{data}。",
        box,
        "恢复：排查原因后重新运行 sdtm-rag 工作流（部署成功后公开容器保持停止），再在部署机上执行 "
        f"`docker start {name}`；journal 残留时先按 deploy/README「KB 同步」人工 restore。",
    ])


def live_extra_collections(docker: Docker, image: str, data_root: str, ts: str) -> list[str]:
    """线上公开 chroma 里 KB 之外的集合名（在副本上读，读完删副本；原件不被任何 chromadb 打开）。
    读出了结果之后副本删不掉：只告警，不丢结论（「发现了却因为清理失败而没停站」比留一个副本更糟）。"""
    def clean() -> bool:
        try:
            via(docker, image, data_root, ["guard-clean", "--data-root", data_root, "--ts", ts])
            return True
        except Exception:  # noqa: BLE001
            return False

    try:
        g = via(docker, image, data_root, ["guard-copy", "--data-root", data_root, "--ts", ts, "--names", "chroma"])
        names = set(collections(docker, image, f"{data_root}/{g['guard_dir']}/chroma"))
    except Exception:
        clean()
        raise
    if not clean():
        print(f"::warning::核对用的副本 kbsync_guard_{ts} 没有删掉（在公开数据根里），请人工删除")
    return sorted(names - {KB_COLLECTION})


# 可以原样写进日志的集合名：只有本仓现用的三种写法（server/config.py 的默认值 sdtm_kb_v1 / study_st01 / study_st01_docs；
# 版本号、研究序号可以变）。后缀不放开（任意后缀可以带着真实研究的标识）；数字写成 [0-9] 并限位数（不限长的数字串
# 本身就可能是真实研究的编号，\d 还会认其它文字里的数字）。其余的名字只写指纹和长度
SAFE_COLLECTION_RE = re.compile(r"study_st[0-9]{2,3}(_docs)?|sdtm_kb_v[0-9]{1,3}")


def _show_collection(name: str) -> str:
    if SAFE_COLLECTION_RE.fullmatch(name):
        return name
    return f"<名字不按约定，已隐去：sha256 前 10 位 {hashlib.sha256(name.encode('utf-8')).hexdigest()[:10]}，长 {len(name)}>"


# 容器日志里以 study 开头的词（前面不是字母 / 数字 / 下划线，一直取到空白、引号、括号、逗号等分隔符为止）
STUDY_NAME_RE = re.compile(r"(?i)(?<![A-Za-z0-9_])study[^\s'\"`\[\]{}(),;:=<>|/\\]+")


def _hide_study_names(text: str) -> str:
    """容器日志带出（打进 job 日志、写进失败原因和摘要）之前：以 study 开头的词按 _show_collection 的白名单处理。
    公开档的启动自检会把名字以 study 开头的集合列进报错（server/instance.py 的 check_chroma；check_startup 的
    collection_name 那一条同理），这样的名字可能带着真实研究的标识。按前面的顺序这类报错本来走不到（临时容器用的副本
    刚核对过集合恰为 KB_COLLECTION），但正式容器复验离红线检查隔着几分钟的验收，所以这里再挡一道，不靠那个前提。
    宁可多隐：日志里别的 study 开头的词（比如代码里的标识符）也会被换成指纹。
    挡不住的（前提，README「公开实例」写着）：集合名不以 study 开头——只有公开站把 SDTM_RAG_STUDY_COLLECTION_NAME /
    SDTM_RAG_STUDY_DOCS_COLLECTION_NAME 配成别的名字、公开 chroma 里又恰好有这个集合时才会被列出来；
    以及集合名里带空白 / 引号 / 括号之类的分隔符（chromadb 不允许这样的名字）。"""
    return STUDY_NAME_RE.sub(lambda m: _show_collection(m.group(0)), text)


def live_contaminated_stop(docker: Docker, a: argparse.Namespace, name: str, image: str, extra: list[str]) -> int:
    """红线：线上的公开 chroma 里出现了 KB 以外的集合 —— 不让它继续对外，停站并失败（协调方 2026-11-28 裁定）。
    这是故意偏严的断言：将来正当新增一个 KB 集合也会触发，所以失败信息写明发现了哪些集合、正当新增要改哪里。
    先看 journal：有残留或判不出时保持现状并失败，不做任何动作。本函数只停不起，也不改数据。"""
    shown = "、".join(_show_collection(n) for n in extra[:10]) + (f" 等共 {len(extra)} 个" if len(extra) > 10 else "")
    found = f"线上的公开 chroma 里发现 {KB_COLLECTION} 以外的集合（{len(extra)} 个：{shown}）"
    hint = (f"这是故意偏严的检查：公开数据根只认 {KB_COLLECTION} 这一个集合。如果是研究数据混入：不要启动，先查来源并清理公开数据根。"
            "如果是正当新增的 KB 集合：改 deploy/kbsync/kbsync.py 的 KB_COLLECTION（改成允许的集合清单，kb-only 的几处断言都用它）"
            "和对应测试，并核对 server/instance.py 的 check_chroma。处理完之后重新运行 sdtm-rag 工作流，"
            f"通过后在部署机上 `docker start {name}`。")
    try:
        js = journal_state(docker, image, a.data_root)
    except Exception:  # noqa: BLE001
        js = 2
    if js != 0:
        _summary([f"失败：{found}。",
                  f"数据根的 journal {'有残留' if js == 3 else '状态判不出'}：保持现状，没有停站、没有改数据；请立即人工处理。", hint])
        return 1
    if a.touched_file:
        Path(a.touched_file).write_text(name, encoding="utf-8")
    try:
        docker.run(["compose", "-f", a.compose_file, "stop"], env={"IMAGE_TAG": "x"})
        st = container_state(docker, name)
        stopped = st is None or not st["running"]
    except Exception:  # noqa: BLE001
        stopped = False
    _summary([f"失败：{found}。",
              ("公开实例已停止（公开站下线，私有实例不受影响）；数据没有改动。" if stopped
               else "已尝试停止公开实例，但没有确认它停下来了，请立即人工确认；数据没有改动。"),
              hint])
    return 1


def deploy_public(docker: Docker, a: argparse.Namespace, *, sleep=time.sleep) -> int:
    """公开实例部署。顺序：路径一致性 → 预检决定 → 线上数据的红线检查 → 网络预检 → 临时容器验收（数据副本，不联网）
    → 答题 key 探测 → 换入前置核对 → 才动正式容器（换数据时先停）→ 复验 → 收尾。
    线上公开 chroma 里有 KB 以外的集合：停站并失败。其余检查不过：正式容器和正式数据都不动。
    动过正式容器之后的任何失败：停机，数据按 journal 退回，绝不启动。部署前是停止的：更新数据和镜像，保持停止。"""
    D, ts = a.data_root, a.ts or now_ts()

    def say(msg: str) -> None:
        print(f"[deploy-public] {msg}")

    if a.touched_file:  # 上次运行留下的标记不算数；pid 文件供中断兜底结束本进程（连同它起的 docker 子进程）
        Path(a.touched_file).unlink(missing_ok=True)
        Path(a.touched_file + ".pid").write_text(f"{os.getpid()} {os.getpgrp()}", encoding="utf-8")
    try:
        return _deploy_public(docker, a, D, ts, say, sleep)
    except (RuntimeError, ValueError, KeyError, IndexError, TypeError, OSError) as e:
        if a.touched_file and Path(a.touched_file).is_file():
            # 标记在 = 正式容器已经被动过：不能说「没有动」。正常情况下之后的失败由 public_halt 接住，到这里属意外
            _summary([f"失败：动过正式容器之后出错 —— {type(e).__name__}: {scrub(str(e))}",
                      "正式容器的状态与数据以中断兜底步骤的输出和 journal 为准；确认之前不要 docker start。"])
            return 1
        _summary([f"失败：部署前检查出错 —— {type(e).__name__}: {scrub(str(e))}", "正式容器和正式数据都没有动。"])
        return 1
    finally:
        if a.touched_file:
            Path(a.touched_file + ".pid").unlink(missing_ok=True)


def _deploy_public(docker: Docker, a: argparse.Namespace, D: str, ts: str, say, sleep) -> int:
    pub = compose_model(docker, a.compose_file, a.tag)
    problems = paths_problems(pub, compose_model(docker, a.private_compose_file), D, a.env_file)
    if problems:
        for pr in problems:
            say(f"路径不一致：{pr}")
        say("公开数据根 / env 文件与 compose 对不上，拒绝部署（公开实例未改动）")
        return 1
    svc = pub["services"][PUBLIC_SERVICE]
    name, image = svc["container_name"], svc["image"]
    if image != a.image:
        say(f"compose 解析出的镜像 {image} 与要部署的 {a.image} 不一致，拒绝部署（公开实例未改动）")
        return 1
    for pr in accept_down(docker, image, D):  # 上次运行被取消 / 超时留下的临时容器与副本
        say(f"开工前清理：{pr}")

    fp, cv = image_fp(docker, image), chromadb_version(docker, image)
    chk = via(docker, image, D, ["predeploy-check", "--data-root", D, "--target-fp", fp, "--chromadb-version", cv])
    decision = chk["decision"]
    say(f"KB 对齐检查：{json.dumps(chk, ensure_ascii=False)}")
    if decision == "journal_pending":
        say(f"公开数据根残留 {JOURNAL}（上次换数据未完成收尾）；公开实例未改动。请先停止公开实例，再人工执行 restore"
            "（或在确认换入已生效后执行 finish），见 deploy/README「KB 同步」")
        return 1
    # 部署前状态（查不出来 → 抛异常，由外层按「部署前检查出错」处理；不当作「不存在」）
    prev = container_state(docker, name)
    prev_running = bool(prev and prev["running"])
    prev_image = prev["image"] if prev else ""
    say(f"部署前：正式容器 {'运行中' if prev_running else ('已停止' if prev else '不存在')}，镜像 {prev_image or '无'}")

    # ── 红线检查：线上的公开 chroma 里只能有 KB 集合。发现别的集合就停站 ——
    #    不管这次换不换数据，也不管有没有候选（排在「缺候选就跳过」之前：那正是最常见的「不换数据」）──
    extra = live_extra_collections(docker, image, D, ts)
    if extra:
        return live_contaminated_stop(docker, a, name, image, extra)

    if decision in ("missing", "unknown"):
        # D1：公开 chroma 落后且没有过闸候选 → 只告警，不部署，不让本次运行变红
        print(f"::warning::公开 chroma 与镜像 KB 指纹不一致 ({decision})，且没有过闸的公开候选：跳过公开实例部署，"
              "公开实例未改动。等 kb-sync 公开腿建出候选后，下一次部署会换入")
        _summary([f"跳过：公开 chroma 与镜像 KB 指纹不一致（{decision}），没有过闸的公开候选；公开实例未改动。"])
        return 0
    if decision not in ("same", "swap"):
        say(f"未知决定 {decision}（公开实例未改动）")
        return 1
    swap_it = decision == "swap"

    untouched = "正式容器和正式数据都没有动" + ("，旧版继续对外。" if prev_running else "（公开实例仍是停止状态）。")

    # ── 只读预检：公开网络就是 compose 写定的那个网段，并且确实被隔离着 ──
    net, subnet = public_network(pub)
    bad = network_check(docker, net, subnet)
    if bad is None:
        say(f"公开网络 {net} 的子网是 {subnet}，与 compose 一致")
        bad = isolation_check(docker, image, net, subnet, a.isolation_probe, a.isolation_lan.split(),
                              a.isolation_egress.split())
    if bad:
        _summary([f"失败：部署前的网络预检不通过 —— {bad}", untouched])
        return 1
    say("网络隔离核对通过")

    # ── 临时容器验收：此阶段不碰正式容器，也不写公开数据根 ──
    reason: str | None = None
    try:
        src = (chk["source_chroma"], chk["source_meta"]) if swap_it else ("chroma", "meta")
        staged = via(docker, image, D, ["accept-stage", "--data-root", D, "--ts", ts,
                                        "--chroma", src[0], "--meta", src[1]])
        names = set(collections(docker, image, staged["data"] + "/chroma"))
        if names != {KB_COLLECTION}:
            reason = (f"将要对外的 chroma 集合不是恰为 {KB_COLLECTION}（{KB_COLLECTION} "
                      f"{'在' if KB_COLLECTION in names else '缺失'}，非 KB 集合 {len(names - {KB_COLLECTION})} 个）")
        if reason is None:
            spec, ignored = accept_spec(pub, staged["data"])
            if ignored:
                say(f"临时容器没有带上公开 compose 的这些键：{', '.join(ignored)}")
            with tempfile.NamedTemporaryFile("w", suffix=".json", prefix="accept-", delete=False, encoding="utf-8") as f:
                json.dump(spec, f)
            r = docker.run(["compose", "-p", ACCEPT_PROJECT, "-f", f.name, "up", "-d"])
            os.unlink(f.name)
            if r.returncode != 0:
                tail = scrub(r.stderr.decode("utf-8", "replace")).strip().splitlines()[-3:]
                reason = "临时容器起不来：" + " | ".join(tail)
            else:
                say(f"临时容器 {ACCEPT_CONTAINER} 已启动（数据 = {src[0]} 的副本，不联网、无端口）")
                reason = accept_check(docker, ACCEPT_CONTAINER, sleep=sleep)
    except (RuntimeError, ValueError, KeyError, IndexError, OSError) as e:
        reason = f"临时验收出错：{type(e).__name__}: {scrub(str(e))}"
    finally:
        leftovers = accept_down(docker, image, D)
    for pr in leftovers:
        print(f"::warning::{pr}")
    if reason:
        _summary([f"失败：临时容器验收不通过 —— {reason}", untouched])
        return 1
    say("临时容器验收通过，已清理临时容器与数据副本")

    # ── 答题 key 的有效性探测：临时容器没有网络，所以另起一个一次性容器，接在公开网络里（受隔离规则约束）──
    key = _probe(docker, image, a.env_file, ANSWER_KEY_PY, transient=PROBE_TRANSIENT, sleep=sleep,
                 public_tier=True, network=net)
    cat = key.get("category", "other")
    if not key.get("ok"):
        detail = {k: v for k, v in key.items() if k not in ("ok", "category")}
        _summary([f"失败：答题 key 探测不通过 —— {ANSWER_KEY_HINTS.get(cat, ANSWER_KEY_HINTS['other'])} [{cat}] "
                  f"{json.dumps(detail, ensure_ascii=False)}", untouched])
        return 1
    if cat == "not_applicable":
        print("::warning::公开站配置的答题模型里没有 Anthropic 的，答题 key 没有探测")
    else:
        say("答题 key 探测通过（只列模型，未发答题请求）")

    swap_args = argparse.Namespace(data_root=D, ts=ts, image=image, target_fp=fp, chromadb_version=cv, kb_only=True,
                                   expect_source=chk.get("source_chroma", ""))  # 只换入验收过的那一份
    if swap_it:
        # 能提前做的换入核对先做完：这时拒绝，正式容器还没有被停
        try:
            ok = swap_guard(docker, swap_args, ts)
        except (RuntimeError, ValueError, KeyError, IndexError, TypeError) as e:
            say(f"换入前置核对出错：{type(e).__name__}: {scrub(str(e))}")
            ok = False
        if not ok:
            _summary(["失败：换入前置核对不通过（见上方日志）。", untouched])
            return 1

    # 临时验收要几分钟：动手之前重新读一次状态，以这一刻为准（期间被人停下的，不拉起）
    now = container_state(docker, name)
    if bool(now and now["running"]) != prev_running:
        say(f"验收期间正式容器的状态变了：现在{'运行中' if now and now['running'] else '已停止 / 不存在'}，按现在的状态处理")
    prev_running = bool(now and now["running"])
    prev_image = now["image"] if now else ""

    # ── 从这里开始动正式容器 ──
    if a.touched_file:
        Path(a.touched_file).write_text(name, encoding="utf-8")
    swapped = False
    try:
        def compose(*args: str, tag: str = "x") -> None:
            r = docker.run(["compose", "-f", a.compose_file, *args], env={"IMAGE_TAG": tag})
            if r.returncode != 0:
                tail = scrub(r.stderr.decode("utf-8", "replace")).strip().splitlines()[-3:]
                raise _HaltError(f"docker compose {' '.join(args)} 失败：" + " | ".join(tail))

        if swap_it:
            compose("stop", PUBLIC_SERVICE)
            st = container_state(docker, name)
            if st and st["running"]:
                raise _HaltError("正式容器停不下来，没有换数据")
            if not swap_guard(docker, swap_args, ts):  # 停机之后的主闸（副本上核对，可能要一会儿）
                raise _HaltError("换入被拒绝或失败")
            st = container_state(docker, name)  # 核对期间又被人起来了就不换
            if st and st["running"]:
                raise _HaltError("换入之前正式容器又在运行，没有换数据")
            print(json.dumps(via(docker, image, D, ["swap", "--data-root", D, "--target-fp", fp, "--ts", ts,
                                                    "--chromadb-version", cv, "--expect-source", chk["source_chroma"]])))
            swapped = True
        if prev_running:
            compose("up", "-d", PUBLIC_SERVICE, tag=a.tag)  # 只动 api 服务：同项目里将来若有别的服务，不由这里起停
            st = container_state(docker, name)
            if not st or st["image"] != image:
                raise _HaltError("正式容器没有换成新镜像")
            bad = accept_check(docker, name, sleep=sleep)
            if bad:
                raise _HaltError(f"正式容器复验不通过 —— {bad}")
        else:
            compose("up", "--no-start", PUBLIC_SERVICE, tag=a.tag)  # 只重建，不启动
            st = container_state(docker, name)
            if not st or st["image"] != image or st["running"]:
                raise _HaltError("正式容器没有按预期重建为「新镜像、未启动」")
        if swapped:
            via(docker, image, D, ["finish", "--data-root", D])
    except Exception as e:  # noqa: BLE001  动过正式容器之后，任何意外都按同一条路处理：停机
        why = str(e) if isinstance(e, _HaltError) else f"{type(e).__name__}: {scrub(str(e))}"
        public_halt(docker, a, name, image, why, prev_image)
        return 1
    if swapped:  # finish 之后不能再让本次运行失败（journal 已删，无从退回）
        try:
            say("旧数据副本清理：" + json.dumps(via(docker, image, D, ["prune", "--data-root", D, "--keep", "2"])))
        except Exception:  # noqa: BLE001  部署已经成功，这里出什么错都只告警
            print("::warning::prune 失败（不影响本次部署），请人工清理旧的 chroma_prev_*")
    data = f"数据已换入 {chk['source_chroma']}" if swapped else "数据未变（KB 指纹一致）"
    if prev_running:
        _summary([f"成功：公开实例已换成镜像 {image} 并通过复验；{data}。"])
    else:
        _summary([f"成功：镜像已更新为 {image}，{data}；**公开容器保持停止**（部署前就是停止的，部署不会把它拉起）。",
                  f"启动需人工：在部署机上执行 `docker start {name}`（首次上线和故障后恢复都走这一步）。"])
    return 0


def _proc_kind(pid: int) -> str:
    """这个 pid 现在是什么：deploy（kbsync 的 deploy-public）/ other（别的进程，说明 pid 已被复用）/
    gone（不在了，或已退出但还没被回收——命令行是空的）/ unknown（没有 /proc 的系统，无从核对）。"""
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return "gone" if Path("/proc/self/cmdline").exists() else "unknown"
    if not cmd:
        return "gone"
    return "deploy" if "kbsync" in cmd and "deploy-public" in cmd else "other"


def _only_zombies_left(pid: int, pgid: int, whole: bool) -> bool:
    """信号 0 还发得出去（进程表里还有条目）时再问一句：剩下的是不是都已经退出、只差没人回收（僵尸）。
    runner 的 job 容器里 1 号进程是 sleep，不回收孤儿：被结束的子进程一直以僵尸留在进程表里，对它发信号 0 永远成功。
    看的是整个组（whole）或那一个进程。只在有把握时返回 True：/proc 认得本进程（同一个 pid 命名空间）、读到了至少一个目标、
    并且每一个都是「状态 Z 且线程数为 1」——主线程先退出而别的线程还在跑的进程，状态同样是 Z，线程数大于 1，它还在执行。
    其余情况一律 False，按「还没结束」处理：没有 /proc、一个目标都没读到、有一行认不出来、读的时候被拒绝。
    前提：组里的进程对本进程可见（同一用户；/proc 没有用 hidepid 藏起别人的进程）。"""
    try:
        if int(Path("/proc/self/stat").read_bytes().split(None, 1)[0]) != os.getpid():
            return False
        stats = ([Path(f"/proc/{pid}/stat")] if not whole
                 else [p / "stat" for p in Path("/proc").iterdir() if p.name.isdigit()])
    except (OSError, ValueError, IndexError):
        return False
    seen = 0
    for st in stats:
        try:
            raw = st.read_bytes()
        except (FileNotFoundError, NotADirectoryError, ProcessLookupError):
            continue  # 列出来之后才消失：已经被回收
        except OSError:
            return False
        try:
            # 进程名（第 2 个字段）里可以有 ")"、空格、非 UTF-8 字节：按字节读，从最后一个 ")" 之后取
            f = raw.rsplit(b")", 1)[1].split()
            state, pgrp, threads = f[0], int(f[2]), int(f[17])  # proc(5)：第 3 / 5 / 20 个字段
        except (IndexError, ValueError):
            return False
        if whole and pgrp != pgid:
            continue
        if state != b"Z" or threads != 1:
            return False
        seen += 1
    return seen > 0


def _end_process_group(pid: int, pgid: int, sleep) -> bool:
    """结束还在跑的编排进程。它是自己那个进程组的组长（main() 里 setpgid 过）时整组结束——连同它起的 docker / compose
    子进程，组长已经不在（含已退出但没被回收）也照发，因为组里可能还剩子进程；否则只结束这一个进程。
    不发信号的情况：pid 不合理（<= 1 或就是本进程）；pid 已经被别的进程复用（原来那一组必然已经全部退出）；
    组就是本进程所在的组时不对整组发。返回「没有需要担心的进程了」：信号 0 发不出去了，或者剩下的全是僵尸
    （_only_zombies_left；先发过结束信号才问这一句）。"""
    if pid <= 1 or pid == os.getpid():
        return True
    whole = pgid == pid and pgid != os.getpgrp()
    alive = True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        alive = False
    except PermissionError:
        return True  # 不是我们的进程
    kind = _proc_kind(pid) if alive else "gone"
    if kind == "other":
        return True
    if kind == "gone" and not whole:
        return True

    def send(sig: int) -> None:
        os.killpg(pgid, sig) if whole else os.kill(pid, sig)

    try:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            send(sig)
            for _ in range(10):
                sleep(0.5)
                send(0)  # 都没了会抛 ProcessLookupError
                if _only_zombies_left(pid, pgid, whole):
                    return True
    except ProcessLookupError:
        return True
    return False


def public_abort(docker: Docker, a: argparse.Namespace, *, sleep=time.sleep) -> int:
    """job 被取消 / 超时 / 意外失败时的兜底。先尽力结束可能还活着的 deploy-public 进程（连同它起的 docker 子进程，
    否则它们会在兜底之后继续动正式容器），再看标记：正式容器已被动过才停，不碰数据（残留 journal 由下次预检拦住）。
    结束进程是尽力而为（已经发给 docker 守护进程的操作收不回来），所以停机后隔几秒再确认，发现又起来了就再停。"""
    pid_file = Path(a.touched_file + ".pid")
    if pid_file.is_file():
        try:
            parts = pid_file.read_text(encoding="utf-8").split()
            pid, pgid = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
            if not _end_process_group(pid, pgid, sleep):
                print(f"[deploy-public] deploy-public 进程 {pid} 可能还没有结束（也可能只是没被回收）；下面照常停机并复查")
        except (ValueError, IndexError, PermissionError, OSError) as e:
            print(f"[deploy-public] 结束 deploy-public 进程时出错：{type(e).__name__}")
        pid_file.unlink(missing_ok=True)
    if not Path(a.touched_file).is_file():
        print("[deploy-public] 正式容器没有被动过，不做任何事")
        return 0
    name = Path(a.touched_file).read_text(encoding="utf-8").strip()
    stopped = False
    for _ in range(3):  # 停 → 等几秒 → 确认；还没来得及被结束的 compose up 可能在这之间把它又起来
        docker.run(["compose", "-f", a.compose_file, "stop"], env={"IMAGE_TAG": "x"})
        sleep(3)
        try:
            st = container_state(docker, name) if name else None
            stopped = st is None or not st["running"]
        except RuntimeError:
            stopped = False
        if stopped:
            break
    if stopped:
        print("[deploy-public] 部署中断：公开实例已停止（公开站下线，私有实例不受影响）；本步骤没有改动数据。"
              "排查后重新运行 sdtm-rag 工作流，成功后在部署机上 docker start 公开容器")
        return 0
    print("[deploy-public] 部署中断，且没有确认公开实例已停止，请立即人工确认")
    return 1


# ── CLI ──────────────────────────────────────────────────────────────────
FS_CMDS = {"detect", "stamp", "prepare", "gate", "fail", "predeploy-check", "swap", "swap-status",
           "restore", "finish", "prune", "guard-copy", "guard-clean", *STAGE_CMDS}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--via", metavar="IMAGE", help="在该镜像的兄弟容器中执行文件系统子命令")
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
    p("stamp")
    p("prepare", fp=True, ts=True)
    g = p("gate", fp=True, ts=True)
    g.add_argument("--max-regressions", type=int, default=1)
    g.add_argument("--info", default="{}")
    g.add_argument("--min-questions", type=int, default=MIN_QUESTIONS)
    g.add_argument("--min-avg", type=float, default=MIN_AVG)
    p("fail", fp=True, ts=True).add_argument("--reason", required=True)
    pc = p("predeploy-check")
    pc.add_argument("--target-fp", default="")
    pc.add_argument("--chromadb-version", default="")
    sw = p("swap", ts=True)
    sw.add_argument("--target-fp", required=True)
    sw.add_argument("--chromadb-version", default="")
    sw.add_argument("--expect-source", default="", help="必须换入的目录名（与验收的那一份相同），不同则拒绝")
    p("guard-copy", ts=True).add_argument("--names", nargs="+", required=True)
    p("guard-clean", ts=True)
    st = p("accept-stage", ts=True)
    st.add_argument("--chroma", required=True, help="数据根下要复制的 chroma 目录名")
    st.add_argument("--meta", required=True, help="数据根下要复制的 meta 目录名")
    p("accept-clean")
    p("swap-status")
    p("restore")
    p("finish")
    p("prune").add_argument("--keep", type=int, default=2)

    c = p("candidate", fp=True, ts=True)
    for k in ("--ref", "--a-commit", "--prod-image", "--cand-image", "--env-file"):
        c.add_argument(k, required=True)
    c.add_argument("--max-regressions", type=int, default=1)
    c.add_argument("--memory", default="1536m")
    c.add_argument("--kb-only", action="store_true", help="公开腿：候选集合必须恰为 sdtm_kb_v1")
    c.add_argument("--prod-image-ref", default="", help="--prod-image 是镜像 ID 时，它原来的标签（只记进候选记录）")
    d = p("deploy-swap", ts=True)
    d.add_argument("--image", required=True)
    d.add_argument("--target-fp", required=True)
    d.add_argument("--chromadb-version", required=True)
    d.add_argument("--kb-only", action="store_true", help="公开数据根：线上与换入源都不得有非 KB 集合")
    kc = p("key-check", data=False)
    kc.add_argument("--image", required=True)
    kc.add_argument("--env-file", required=True)
    bl = p("baseline-image")
    bl.add_argument("--images", nargs="+", required=True, help="候选基线镜像，按优先顺序")
    bl.add_argument("--via-image", required=True, help="用来读 stamp 的可信镜像（私有线上镜像）")
    pth = p("paths-check")
    for k in ("--env-file", "--compose-file", "--private-compose-file"):
        pth.add_argument(k, required=True)
    dp = p("deploy-public", ts=True)
    for k in ("--env-file", "--compose-file", "--private-compose-file", "--image", "--tag"):
        dp.add_argument(k, required=True)
    dp.add_argument("--touched-file", default="", help="动正式容器之前写下的标记文件（供取消 / 超时兜底步骤判断）")
    dp.add_argument("--isolation-probe", required=True, help="隔离探测脚本（隧道那条线的 deploy/public-net/isolation_probe.py）")
    dp.add_argument("--isolation-lan", required=True, help="应当被挡住的内网目标 host:port，空格分隔")
    dp.add_argument("--isolation-egress", required=True, help="应当连得上的外网目标 host:port，空格分隔")
    pa = p("public-abort", data=False)
    pa.add_argument("--compose-file", required=True)
    pa.add_argument("--touched-file", required=True)
    p("accept-down").add_argument("--image", required=True)
    p("image-fp", data=False).add_argument("--image", required=True)
    p("chromadb-version", data=False).add_argument("--image", required=True)
    p("journal-state").add_argument("--image", required=True)
    p("fingerprint", data=False).add_argument("--kb-root", required=True)
    return ap


def run_fs(a: argparse.Namespace) -> dict:
    D = Path(a.data_root)
    if not D.is_dir():
        raise SystemExit(f"data root 不存在: {D}")
    ts = getattr(a, "ts", "") or now_ts()
    fp = getattr(a, "fp", None)
    if (fp is not None and not FP_RE.fullmatch(fp)) or not TS_RE.fullmatch(ts):  # 两者都会拼进目录名
        raise SystemExit("--fp 必须是 64 位十六进制，--ts 必须形如 20261128T010203Z")
    if a.cmd == "detect":
        return detect(D, a.fp)
    if a.cmd == "stamp":
        return stamp(D)
    if a.cmd == "prepare":
        return prepare(D, a.fp, ts)
    if a.cmd == "gate":
        return gate(D, a.fp, a.max_regressions, ts, json.loads(a.info), a.min_questions, a.min_avg)
    if a.cmd == "fail":
        return fail(D, a.fp, ts, a.reason)
    if a.cmd == "predeploy-check":
        return predeploy_check(D, a.target_fp, a.chromadb_version)
    if a.cmd == "swap":
        return swap(D, a.target_fp, ts, a.chromadb_version, a.expect_source)
    if a.cmd == "guard-copy":
        return guard_copy(D, a.names, ts)
    if a.cmd == "guard-clean":
        return guard_clean(D, ts)
    if a.cmd == "accept-stage":
        return accept_stage(D, ts, a.chroma, a.meta)
    if a.cmd == "accept-clean":
        return accept_clean(D)
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
    real_docker = docker is None
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
    if a.cmd == "key-check":
        res = key_check(docker, a.image, a.env_file)
        if res.get("ok"):
            print(f"[kbsync] embedding key 检查通过（{res.get('model')}，{res.get('dim')} 维）")
            return 0
        cat = res.get("category", "other")
        detail = {k: v for k, v in res.items() if k not in ("ok", "category")}
        print(f"[kbsync] embedding key 检查失败：{cat}（{KEY_HINTS.get(cat, KEY_HINTS['other'])}；"
              f"env 文件 {a.env_file}）{json.dumps(detail, ensure_ascii=False)}")
        return 1
    if a.cmd == "baseline-image":
        img, fp, rows = baseline_image(docker, a.data_root, a.images, a.via_image)
        for i, ifp in rows:
            print(f"[kbsync] 基线候选 {i}：镜像内 KB 指纹 {fp12(ifp) if FP_RE.fullmatch(ifp) else ifp}", file=sys.stderr)
        if not img:
            print(f"[kbsync] 没有与数据根 chroma（stamp {fp12(fp) if fp else None}）配对的基线镜像，不构建候选。"
                  "处理：手动运行 kb-sync，在 public_baseline_image 填一个镜像内 KB 指纹等于该 stamp 的镜像"
                  "（本仓镜像的完整引用 <镜像仓库>/sdtm-rag:<40 位 commit SHA>，须已在部署机本地；通常是上一次成功部署到"
                  "公开站的那个镜像）；见 deploy/README「KB 同步」", file=sys.stderr)
            return 1
        print(img)
        return 0
    if a.cmd == "paths-check":
        return paths_check(docker, a)
    if a.cmd == "deploy-public":
        if real_docker:  # 真实运行时自成一个进程组：中断兜底可以把本进程连同它起的 docker 子进程一起结束
            try:
                os.setpgid(0, 0)
            except OSError:
                pass
        return deploy_public(docker, a)
    if a.cmd == "public-abort":
        return public_abort(docker, a)
    if a.cmd == "accept-down":
        problems = accept_down(docker, a.image, a.data_root)
        for pr in problems:
            print(f"[deploy-public] 清理：{pr}")
        return 1 if problems else 0
    if a.cmd == "image-fp":
        print(image_fp(docker, a.image))
        return 0
    if a.cmd == "journal-state":
        rc = journal_state(docker, a.image, a.data_root)
        print({0: "clear", 2: "unknown", 3: "pending"}[rc])
        return rc
    if a.cmd == "chromadb-version":
        print(chromadb_version(docker, a.image))
        return 0
    print(local_fp(a.kb_root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
