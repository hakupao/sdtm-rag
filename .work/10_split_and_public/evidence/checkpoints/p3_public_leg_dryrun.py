"""公开腿在替身数据根上的实跑 (P3 公开站 KB 更新 + 临时容器验收)。

用临时目录搭「私有数据根」(带 study 集合与 study 目录) 和「公开数据根」(只有 KB + quota.sqlite) 的替身, 目录布局与
生产同构 (deploy-data/{sdtm-rag,sdtm-rag-public}/data)。每一步都经 kbsync.py 的命令行入口 main(argv) 调用;
文件系统子命令在临时目录上真跑, docker / compose 用 tests/ 里带容器状态的假实现 (本机没有 docker, 也不碰虚拟机)。
不读写任何真实数据根。每个场景结束时核对: 私有根逐字节未变、公开根里没有私有内容、临时容器与验收副本已清、
假 docker 记下的不变量违例为空 (换 / 退数据时正式容器必须是停的; 验收副本子命令对数据根只读)。

从仓库根运行:  .venv/bin/python .work/10_split_and_public/evidence/checkpoints/p3_public_leg_dryrun.py
退出码 0 = 全部场景与预期一致。"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from tests.test_kbsync import BASE, NEW, OLD, TS, _chroma, _cols, _meta, _snapshot, ks  # noqa: E402
from tests.test_kbsync_deploy_public import (  # noqa: E402
    EGRESS,
    FORMAL,
    IMG_NEW,
    IMG_OLD,
    LAN,
    NET,
    PROBE_STANDIN,
    TAG_NEW,
    TEMP,
    PublicFake,
)
from tests.test_kbsync_public import CAND, PRIV_MODEL, assert_no_bind_reaches  # noqa: E402

FAILS: list[str] = []
ROWS: list[tuple[str, str, str]] = []


def site(tmp: Path) -> dict:
    base = tmp / "deploy-data"
    priv, pub = base / "sdtm-rag" / "data", base / "sdtm-rag-public" / "data"
    _chroma(priv / "chroma", OLD, "PRIVATE-chroma-with-study")
    _meta(priv / "meta", "private-meta")
    (priv / "study" / "st01").mkdir(parents=True)
    (priv / "study" / "st01" / "catalog.json").write_text("PRIVATE-study")
    _chroma(pub / "chroma", OLD, "public-chroma")
    _meta(pub / "meta", "public-meta")
    (pub / "quota.sqlite").write_text("quota-live")
    env = tmp / "opt" / "sdtm-rag-public" / ".env"
    env.parent.mkdir(parents=True)
    env.write_text("PLACEHOLDER=1\n")
    pm = copy.deepcopy(PRIV_MODEL)
    for svc in pm["services"].values():
        svc["volumes"][0]["source"] = str(priv)
    probe = tmp / "public-net" / "isolation_probe.py"  # 隧道那条线的隔离探测脚本的替身 (judge 在本机真跑)
    probe.parent.mkdir()
    probe.write_text(PROBE_STANDIN)
    return {"priv": priv, "pub": pub, "env": env, "touched": tmp / "touched", "priv_model": pm, "probe": probe}


def fake(s: dict, *, formal, cols=None, image_fp=NEW) -> PublicFake:
    f = PublicFake(s["pub"], s["env"], formal=formal, image_fp=image_fp, cols=cols, priv_model=s["priv_model"])
    f.image_fps.update({"cand:1": NEW, IMG_OLD: OLD, "priv-live:1": NEW})
    f.probe_script = s["probe"].read_bytes()  # 假 docker 会核对: 送进隔离探测容器的就是这个脚本
    f.key_results = [(0, '{"ok": true, "category": "ok", "model": "text-embedding-3-small", "dim": 1536}')] * 4
    return f


def cli(f: PublicFake, *argv: str) -> tuple[int, str]:
    """经命令行入口调用; 返回 (退出码, stdout 最后一行非空内容; stdout 为空时取 stderr 的)。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = ks.main(list(argv), docker=f)
        except SystemExit as e:
            rc = 2 if not isinstance(e.code, int) else e.code
            print(e.code, file=sys.stderr)
        except RuntimeError as e:
            rc = 2
            print(f"RuntimeError: {e}", file=sys.stderr)
    lines = [ln for ln in out.getvalue().splitlines() if ln.strip()] or [
        ln for ln in err.getvalue().splitlines() if ln.strip()]
    return rc, (lines[-1] if lines else "")


def deploy(f: PublicFake, s: dict) -> tuple[int, str]:
    orig = ks.time.sleep
    ks.time.sleep = lambda _: None  # 假容器不需要真等健康检查
    try:
        return cli(f, "deploy-public", "--data-root", str(s["pub"]), "--env-file", str(s["env"]),
                   "--compose-file", "deploy/container/compose.public.yml",
                   "--private-compose-file", "deploy/container/compose.yml",
                   "--image", IMG_NEW, "--tag", TAG_NEW, "--touched-file", str(s["touched"]), "--ts", TS,
                   "--isolation-probe", str(s["probe"]), "--isolation-lan", LAN, "--isolation-egress", EGRESS)
    finally:
        ks.time.sleep = orig


def kb_leg(f: PublicFake, s: dict, *, kb_only=True, scores=None) -> list[tuple[str, int, str]]:
    """kb-sync 公开腿的步骤, 顺序与 .gitea/workflows/kb-sync.yml 的 public job 相同。"""
    D = str(s["pub"])
    f.cand_scores = scores or dict(BASE)
    steps = [("paths-check", cli(f, "paths-check", "--data-root", D, "--env-file", str(s["env"]),
                                  "--compose-file", "deploy/container/compose.public.yml",
                                  "--private-compose-file", "deploy/container/compose.yml"))]
    rc, last = cli(f, "--via", "priv-live:1", "detect", "--data-root", D, "--fp", NEW)
    steps.append(("detect", (rc, last)))
    if rc == 0 and json.loads(last)["result"] == "changed":
        steps.append(("key-check", cli(f, "key-check", "--image", "cand:1", "--env-file", str(s["env"]))))
        rc, base = cli(f, "baseline-image", "--data-root", D, "--via-image", "priv-live:1",
                       "--images", IMG_OLD if f.formal() else "", "priv-live:1")
        steps.append(("baseline-image", (rc, base)))
        if rc == 0 and all(r == 0 for _, (r, _) in steps):
            steps.append(("candidate", cli(
                f, "candidate", "--data-root", D, "--fp", NEW, "--ts", TS, "--ref", "kb-2026.11.28",
                "--a-commit", "c" * 40, "--prod-image", base, "--cand-image", "cand:1",
                "--env-file", str(s["env"]), *(["--kb-only"] if kb_only else []))))
    return [(n, rc, last) for n, (rc, last) in steps]


def expect(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        FAILS.append(f"{name}: {detail}")


def scenario(title: str):
    def deco(fn):
        with tempfile.TemporaryDirectory() as tmp:
            s = site(Path(tmp))
            before_priv = _snapshot(s["priv"])
            n0 = len(FAILS)
            outcome = fn(s)
            f = outcome.pop("fake")
            expect(title, _snapshot(s["priv"]) == before_priv, "私有根被改动")
            expect(title, "PRIVATE" not in json.dumps(_snapshot(s["pub"])), "公开根出现私有内容")
            expect(title, f.violations == [], f"不变量违例 {f.violations}")
            expect(title, TEMP not in f.containers, "临时容器没清")
            expect(title, not list(s["pub"].parent.glob(f"{ks.ACCEPT_PREFIX}*")), "验收副本没清")
            if any("--mount" in c for c in f.calls):
                try:
                    assert_no_bind_reaches(f, s["priv"], min_mounts=1)
                except AssertionError as e:
                    expect(title, False, f"挂载碰到私有根 {e}")
            ROWS.append((title, "; ".join(f"{k}={v}" for k, v in outcome.items()),
                         "与预期一致" if len(FAILS) == n0 else "不符"))
        return fn
    return deco


def state(f: PublicFake, s: dict) -> dict:
    c = f.formal()
    return {"正式容器": "不存在" if c is None else f"{'运行' if c['running'] else '停止'}/{'新' if c['image'] == IMG_NEW else '旧'}镜像",
            "线上数据": {OLD: "旧", NEW: "新"}.get(ks.stamp_fp(s["pub"] / "chroma"), "?"),  # 按 stamp 指纹判断
            "journal": "有" if (s["pub"] / ks.JOURNAL).exists() else "无",
            "候选": ks.detect(s["pub"], NEW)["result"] if not (s["pub"] / ks.JOURNAL).exists() else "-"}


@scenario("A1 整条公开腿 (公开容器原本停止): 检测 → key → 基线 → 建候选 → kb-only → 过闸 → 部署换入 → 保持停止")
def _(s):
    f = fake(s, formal="stopped", cols={CAND: _cols(4333), "chroma": _cols(4329), "stage": _cols(4333)})
    steps = kb_leg(f, s)
    expect("A1", [n for n, _, _ in steps] == ["paths-check", "detect", "key-check", "baseline-image", "candidate"], str(steps))
    expect("A1", all(rc == 0 for _, rc, _ in steps), str(steps))
    expect("A1", steps[3][2] == IMG_OLD, f"基线应取公开容器镜像, 实际 {steps[3][2]}")
    expect("A1", ks.is_gated_pass(s["pub"], NEW), "候选没过闸")
    rc, last = deploy(f, s)
    st = state(f, s)
    expect("A1", rc == 0 and st == {"正式容器": "停止/新镜像", "线上数据": "新", "journal": "无", "候选": "same"}, f"{rc} {st}")
    expect("A1", f.starts() == [] and "docker start" in last, f"启动 {f.starts()} / {last}")
    expect("A1", (s["pub"] / "quota.sqlite").read_text() == "quota-live", "quota.sqlite 被动了")
    rc2, last2 = cli(f, "--via", IMG_NEW, "detect", "--data-root", str(s["pub"]), "--fp", NEW)
    expect("A1", json.loads(last2)["result"] == "same", last2)
    return {"fake": f, "kb-sync": "PASS", "deploy rc": rc, **st, "启动次数": len(f.starts())}


@scenario("A2 公开容器原本运行: 临时验收 → 停 → 换入 → 起 → 复验 → 收尾")
def _(s):
    f = fake(s, formal="running", cols={CAND: _cols(4333), "chroma": _cols(4329), "stage": _cols(4333)})
    expect("A2", all(rc == 0 for _, rc, _ in kb_leg(f, s)), "kb-sync 公开腿")
    rc, _last = deploy(f, s)
    st = state(f, s)
    expect("A2", rc == 0 and st == {"正式容器": "运行/新镜像", "线上数据": "新", "journal": "无", "候选": "same"}, f"{rc} {st}")
    ev = f.events
    expect("A2", ev.index("temp:rm") < ev.index("formal:stop") < ev.index("fs:swap") < ev.index("formal:up") < ev.index("fs:finish"), str(ev))
    return {"fake": f, "deploy rc": rc, **st, "启动次数": len(f.starts())}


@scenario("B1 候选混入非 KB 集合: 过闸之前按违规归档, 公开站不变")
def _(s):
    f = fake(s, formal="stopped", cols={CAND: _cols(4333, study_zz=(5, "d1"))})
    steps = kb_leg(f, s)
    failed = s["pub"] / f"chroma_failed_{NEW[:12]}_{TS}"
    reason = json.loads((failed / ks.MARKER).read_text())["reason"] if failed.is_dir() else None
    expect("B1", steps[-1][0] == "candidate" and steps[-1][1] == 1 and reason == "kb_only_violation", f"{steps[-1]} {reason}")
    rc, last = deploy(f, s)  # 没有过闸候选 → 只告警跳过
    st = state(f, s)
    expect("B1", rc == 0 and st["正式容器"] == "停止/旧镜像" and st["线上数据"] == "旧" and st["候选"] == "changed", f"{rc} {st}")
    return {"fake": f, "candidate rc": steps[-1][1], "归档原因": reason, "deploy": "告警跳过", **st}


@scenario("B2 闸不过 (回退 2 题): 归档, 公开站不变; 私有腿不受影响")
def _(s):
    f = fake(s, formal="stopped", cols={CAND: _cols(4333)})
    steps = kb_leg(f, s, scores={**BASE, "q001": 0.0, "q002": 0.0})
    failed = s["pub"] / f"chroma_failed_{NEW[:12]}_{TS}"
    verdict = json.loads((failed / ks.MARKER).read_text())["verdict"] if failed.is_dir() else None
    expect("B2", steps[-1][1] == 1 and verdict == "FAIL", f"{steps[-1]} {verdict}")
    expect("B2", ks.detect(s["priv"], NEW)["result"] == "changed", "私有根的检测被影响")
    return {"fake": f, "candidate rc": steps[-1][1], "verdict": verdict, **state(f, s)}


@scenario("B3 embedding key 无效: 建候选之前明确失败, 不留候选")
def _(s):
    f = fake(s, formal="stopped")
    f.key_results = [(1, '{"ok": false, "category": "key_invalid", "status": 401, "error_class": "AuthenticationError"}')]
    steps = kb_leg(f, s)
    expect("B3", steps[-1][0] == "baseline-image" and steps[2][1] == 1 and "key_invalid" in steps[2][2], str(steps))
    expect("B3", not list(s["pub"].glob("chroma_cand_*")) and not list(s["pub"].glob("chroma_failed_*")), "留下了候选")
    return {"fake": f, "key-check rc": steps[2][1], "原因": "key_invalid", **state(f, s)}


@scenario("B4 没有与公开数据配对的基线镜像: 明确失败, 不建候选")
def _(s):
    f = fake(s, formal="stopped")
    f.image_fps.update({IMG_OLD: NEW})  # 公开容器是「没通过的新镜像」, 数据是旧的
    steps = kb_leg(f, s)
    expect("B4", steps[-1][0] == "baseline-image" and steps[-1][1] == 1, str(steps))
    expect("B4", not list(s["pub"].glob("chroma_cand_*")), "留下了候选")
    return {"fake": f, "baseline-image rc": steps[-1][1], **state(f, s)}


@scenario("B5 路径不一致 (数据根指到私有根): 第一步就拒绝, 不挂载任何目录")
def _(s):
    f = fake(s, formal="stopped")
    rc, last = cli(f, "paths-check", "--data-root", str(s["priv"]), "--env-file", str(s["env"]),
                   "--compose-file", "deploy/container/compose.public.yml",
                   "--private-compose-file", "deploy/container/compose.yml")
    expect("B5", rc == 1 and not any("--mount" in c for c in f.calls), f"{rc} {last}")
    return {"fake": f, "paths-check rc": rc}


def _with_candidate(s, *, formal, cols=None):
    f = fake(s, formal=formal, cols=cols or {CAND: _cols(4333), "chroma": _cols(4329), "stage": _cols(4333)})
    assert all(rc == 0 for _, rc, _ in kb_leg(f, s))
    return f


@scenario("C1 临时容器验收不过 (索引不新鲜): 正式容器与正式数据都不动, 旧版继续对外")
def _(s):
    f = _with_candidate(s, formal="running")
    f.stale.add(TEMP)
    before = _snapshot(s["pub"])
    rc, last = deploy(f, s)
    st = state(f, s)
    expect("C1", rc == 1 and st["正式容器"] == "运行/旧镜像" and _snapshot(s["pub"]) == before, f"{rc} {st}")
    expect("C1", not [e for e in f.events if e.startswith("formal:")] and "旧版继续对外" in last, last)
    return {"fake": f, "deploy rc": rc, **st}


@scenario("C2 答题 key 无效: 验收不过, 正式容器不动")
def _(s):
    f = _with_candidate(s, formal="running")
    f.answer_results = [(1, '{"ok": false, "category": "key_invalid", "status": 401}')]
    rc, last = deploy(f, s)
    st = state(f, s)
    ev = f.events  # 探测排在临时验收通过之后, 走公开网络 (替身会核对)
    expect("C2", rc == 1 and st["正式容器"] == "运行/旧镜像" and ev.index("temp:rm") < ev.index("answer_key")
           and not [e for e in ev if e.startswith("formal:")], f"{rc} {st}")
    return {"fake": f, "deploy rc": rc, **st}


@scenario("C4 公开网络还没有重建 (子网不是 compose 写定的): 网络预检拦下, 什么都没动")
def _(s):
    f = _with_candidate(s, formal="running")
    f.net_subnets = {NET: "172.18.0.0/16"}
    before = _snapshot(s["pub"])
    rc, last = deploy(f, s)
    st = state(f, s)
    expect("C4", rc == 1 and st["正式容器"] == "运行/旧镜像" and _snapshot(s["pub"]) == before and "temp:up" not in f.events, f"{rc} {st}")
    return {"fake": f, "deploy rc": rc, **st}


@scenario("C5 公开网络里的容器连得上内网 (隔离规则没装或失效): 隔离核对拦下, 什么都没动")
def _(s):
    f = _with_candidate(s, formal="running")
    f.iso_lan_state = "open"
    rc, last = deploy(f, s)
    st = state(f, s)
    expect("C5", rc == 1 and st["正式容器"] == "运行/旧镜像" and "temp:up" not in f.events and "answer_key" not in f.events, f"{rc} {st}")
    return {"fake": f, "deploy rc": rc, **st}


@scenario("C3 线上公开数据里发现非 KB 集合 (这次要换数据): 先看 journal → 停站, 不换入, 数据不动")
def _(s):
    f = _with_candidate(s, formal="running")
    f.cols.update({"chroma": _cols(4329, study_zz=(5, "d1")), CAND: _cols(4333, study_zz=(5, "d1"))})
    before = _snapshot(s["pub"])
    rc, _last = deploy(f, s)
    st = state(f, s)
    ev = f.events
    expect("C3", rc == 1 and st["正式容器"] == "停止/旧镜像" and st["线上数据"] == "旧" and _snapshot(s["pub"]) == before
           and "fs:swap" not in ev and "temp:up" not in ev and ev.index("fs:swap-status") < ev.index("formal:stop")
           and f.starts() == [], f"{rc} {st}")
    return {"fake": f, "deploy rc": rc, **st, "启动次数": len(f.starts())}


@scenario("C6 线上公开数据里发现非 KB 集合 (这次不换数据): 同样停站并失败")
def _(s):
    f = fake(s, formal="running", image_fp=OLD, cols={"chroma": _cols(4329, study_zz=(5, "d1")), "stage": _cols(4329)})
    before = _snapshot(s["pub"])
    rc, last = deploy(f, s)
    c = f.formal()
    expect("C6", rc == 1 and c == {"running": False, "image": IMG_OLD} and _snapshot(s["pub"]) == before
           and "temp:up" not in f.events and "KB_COLLECTION" in last, f"{rc} {c} {last[:60]}")
    return {"fake": f, "deploy rc": rc, "正式容器": "停止/旧镜像", "数据": "未改", "启动次数": len(f.starts())}


@scenario("C8 公开数据落后且没有候选 (本来只告警跳过), 但线上数据里有非 KB 集合: 照样停站并失败")
def _(s):
    f = fake(s, formal="running", cols={"chroma": _cols(4329, study_st01=(5, "d1"))})  # 镜像是新 KB, 没有建过候选
    rc, last = deploy(f, s)
    c = f.formal()
    expect("C8", rc == 1 and c == {"running": False, "image": IMG_OLD} and "temp:up" not in f.events, f"{rc} {c}")
    return {"fake": f, "deploy rc": rc, "正式容器": "停止/旧镜像", "启动次数": len(f.starts())}


@scenario("C7 发现非 KB 集合但 journal 状态判不出: 保持现状并失败, 不停站")
def _(s):
    f = fake(s, formal="running", image_fp=OLD, cols={"chroma": _cols(4329, study_zz=(5, "d1"))})
    f.skip_fs.add("swap-status")
    rc, _last = deploy(f, s)
    c = f.formal()
    expect("C7", rc == 1 and c == {"running": True, "image": IMG_OLD} and "formal:stop" not in f.events, f"{rc} {c}")
    return {"fake": f, "deploy rc": rc, "正式容器": "运行/旧镜像 (没有动)"}


@scenario("D1 换入后复验不过: 停机 → 看 journal → 退数据 → 保持停止 (不退回旧镜像, 不启动)")
def _(s):
    f = _with_candidate(s, formal="running")
    f.stale.add(FORMAL)
    rc, _last = deploy(f, s)
    st = state(f, s)
    expect("D1", rc == 1 and st == {"正式容器": "停止/新镜像", "线上数据": "旧", "journal": "无", "候选": "gated"}, f"{rc} {st}")
    expect("D1", len(f.starts()) == 1 and f.events[-1] != "formal:up", str(f.events))
    return {"fake": f, "deploy rc": rc, **st, "启动次数": len(f.starts())}


@scenario("D2 换入中途出错 (journal 残留): 按 journal 退回, 保持停止")
def _(s):
    f = _with_candidate(s, formal="running")
    f.fail_fs = {"swap"}
    rc, _last = deploy(f, s)
    st = state(f, s)
    expect("D2", rc == 1 and st["线上数据"] == "旧" and st["journal"] == "无" and st["正式容器"].startswith("停止") and f.starts() == [], f"{rc} {st}")
    return {"fake": f, "deploy rc": rc, **st, "启动次数": len(f.starts())}


@scenario("D3 原本停止 + 换入后重建容器失败: 退数据, 仍然停止, 从未启动")
def _(s):
    f = _with_candidate(s, formal="stopped")
    f.fail.add("create")
    rc, _last = deploy(f, s)
    st = state(f, s)
    expect("D3", rc == 1 and st["线上数据"] == "旧" and st["journal"] == "无" and f.starts() == [] and st["正式容器"].startswith("停止"), f"{rc} {st}")
    return {"fake": f, "deploy rc": rc, **st, "启动次数": len(f.starts())}


@scenario("D4 退回失败 (journal 保留) → 下一次公开部署与 kb-sync 公开腿都被 journal_pending 拦住; 人工 restore 后恢复")
def _(s):
    f = _with_candidate(s, formal="running")
    f.stale.add(FORMAL)
    f.skip_fs.add("restore")
    rc, _last = deploy(f, s)
    st = state(f, s)
    expect("D4", rc == 1 and st["journal"] == "有" and st["正式容器"].startswith("停止"), f"{rc} {st}")
    f.skip_fs.clear()
    f.stale.clear()
    rc2, _ = deploy(f, s)
    rc3, last3 = cli(f, "--via", IMG_NEW, "detect", "--data-root", str(s["pub"]), "--fp", NEW)
    expect("D4", rc2 == 1 and json.loads(last3)["result"] == "journal_pending" and f.formal()["running"] is False, f"{rc2} {last3}")
    rc4, last4 = cli(f, "--via", IMG_NEW, "restore", "--data-root", str(s["pub"]))  # 人工退回
    st2 = state(f, s)
    expect("D4", rc4 == 0 and st2["线上数据"] == "旧" and st2["journal"] == "无" and st2["候选"] == "gated", f"{rc4} {last4} {st2}")
    return {"fake": f, "首次 rc": rc, "journal 残留时再部署 rc": rc2, "kb-sync 检测": "journal_pending",
            "人工 restore 后": f"数据{st2['线上数据']}/候选 {st2['候选']}", "启动次数": len(f.starts())}


@scenario("D5 job 被取消的兜底 (public-abort): 动过才停, 只停机不碰数据")
def _(s):
    f = _with_candidate(s, formal="running")
    argv = ("public-abort", "--compose-file", "deploy/container/compose.public.yml", "--touched-file", str(s["touched"]))
    rc0, _ = cli(f, *argv)
    untouched_running = f.formal()["running"]
    s["touched"].write_text(FORMAL)
    before = _snapshot(s["pub"])
    rc1, _ = cli(f, *argv)
    expect("D5", rc0 == 0 and untouched_running and rc1 == 0 and f.formal()["running"] is False and _snapshot(s["pub"]) == before, "abort")
    return {"fake": f, "没动过": "不停", "动过": "停机, 数据未改"}


if __name__ == "__main__":
    print("| 场景 | 结果 | 判定 |\n|---|---|---|")
    for title, outcome, verdict in ROWS:
        print(f"| {title} | {outcome} | {verdict} |")
    print(f"\n{len(ROWS)} 个场景, 不符 {len(FAILS)} 处")
    for x in FAILS:
        print("  ✘", x)
    sys.exit(1 if FAILS else 0)
