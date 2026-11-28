"""「打开公开部署开关之前」那几处修正的变异验证 (docs/RULES.md 规则 5)。跑法 (仓根):

    .venv/bin/python .work/10_split_and_public/evidence/checkpoints/pre_switch_fixes_mutations.py

写法照 p3_step3.4_mutations.py: 每个变异先比对磁盘 sha (与启动时冻结的基线不符即拒跑) → 精确替换一处 (原文须恰好
出现 1 次) → 回读, 必须逐字等于「原文替换后」→ 跑测试 → finally 用启动时冻结的原始字节写回并再比 sha。
判定不只看退出码: 每个变异预登记「应该打红的用例」。killed = 有用例失败、没有 error、打红的用例里有预登记的那条。
退出码非零但不满足这三条记 INVALID, 和 SURVIVED 一样算没通过。
直接改文件: 别人 (或另一趟测试) 同时在用工作区时, 用 PSF_MUT_ROOT 指到仓库的一份副本上跑。
开跑前核对测试导入的 kbsync 就是 ROOT 下的那一份 (防「改的是这份、测的是另一份」)。
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("PSF_MUT_ROOT") or Path(__file__).resolve().parents[4]).resolve()
TESTS = ["tests/test_kbsync.py", "tests/test_kbsync_public.py", "tests/test_kbsync_deploy_public.py"]
KS = "deploy/kbsync/kbsync.py"

NAMES = "test_only_conventional_collection_names_are_printed"
SCRUB = "test_startup_error_is_scrubbed_before_it_is_carried_out"
HIDE_E2E = "test_study_collection_names_in_a_startup_error_are_hidden"
HIDE_CFG = "test_configured_study_collection_name_in_a_startup_error_is_hidden"
HIDE_UNIT = "test_hide_study_names"
VERBATIM = "test_startup_refusal_is_carried_verbatim_into_the_failure_reason"
ZGROUP = "test_only_zombies_left_for_a_whole_group"
ZONE = "test_only_zombies_left_for_a_single_process"
ZPROC = "test_only_zombies_left_refuses_without_a_usable_proc"
ZABORT = "test_abort_does_not_wait_on_zombies_but_still_waits_on_a_live_process"
ALIVE = "test_abort_first_ends_a_deploy_process_that_is_still_alive"

SAFE = 'SAFE_COLLECTION_RE = re.compile(r"study_st[0-9]{2,3}(_docs)?|sdtm_kb_v[0-9]{1,3}")'
LOGS = '        text = _hide_study_names(scrub((logs.stdout + logs.stderr).decode("utf-8", "replace")))\n'
RAW = '(logs.stdout + logs.stderr).decode("utf-8", "replace")'
TOKEN = '''STUDY_NAME_RE = re.compile(r"(?i)(?<![A-Za-z0-9_])study[^\\s'\\"`\\[\\]{}(),;:=<>|/\\\\]+")'''
POLL = "                if _only_zombies_left(pid, pgid, whole):\n                    return True\n"

MUTATIONS = [
    # (编号, 文件, 原文, 改成, 这条变异在验什么, 应该打红的用例名子串)
    # ── LOW-1: 集合名白名单 ──
    ("L1a", KS, SAFE, 'SAFE_COLLECTION_RE = re.compile(r"study_st\\d{2,}(_[a-z0-9]+)*|sdtm_[a-z0-9_]+")',
     "白名单放宽回改之前的写法", NAMES),
    ("L1b", KS, "study_st[0-9]{2,3}(_docs)?|", "study_st[0-9]{2,3}(_[a-z0-9]+)?|", "study 名字放开任意后缀", NAMES),
    ("L1c", KS, "study_st[0-9]{2,3}(_docs)?|", "study_st[0-9]{2,}(_docs)?|", "研究序号不限位数 (长数字串原样写出)", NAMES),
    ("L1d", KS, "|sdtm_kb_v[0-9]{1,3}\")", "|sdtm_[a-z0-9_]+\")", "任意 sdtm_ 开头的名字原样写出", NAMES),
    ("L1e", KS, "|sdtm_kb_v[0-9]{1,3}\")", "|sdtm_kb_v[0-9]{1,}\")", "KB 版本号不限位数", NAMES),
    ("L1f", KS, "study_st[0-9]{2,3}(_docs)?|", "study_st\\d{2,3}(_docs)?|", "数字写回 \\d (别的文字里的数字也认)", NAMES),
    ("L1g", KS, "    if SAFE_COLLECTION_RE.fullmatch(name):\n", "    if SAFE_COLLECTION_RE.match(name):\n",
     "只核对开头 (后面跟着什么都放行)", NAMES),
    # ── LOW-2: 启动报错带出之前先脱敏 ──
    ("L2a", KS, LOGS, f"        text = _hide_study_names({RAW})\n", "容器日志带出之前不脱敏", SCRUB),
    ("L2b", KS, '"\\n".join(tail))\n        # 应用拒绝启动时',
     f'"\\n".join({RAW}.strip().splitlines()[-40:]))\n        # 应用拒绝启动时',
     "失败原因处理过, 但打印的日志末尾是原文", SCRUB),
    # ── LOW-3: 启动报错里的集合名 ──
    ("L3a", KS, LOGS, f"        text = scrub({RAW})\n", "容器日志带出之前不隐去 study 集合名", HIDE_E2E),
    ("L3b", KS, "    return STUDY_NAME_RE.sub(lambda m: _show_collection(m.group(0)), text)\n", "    return text\n",
     "隐名函数什么都不做", HIDE_CFG),
    ("L3c", KS, "    return STUDY_NAME_RE.sub(lambda m: _show_collection(m.group(0)), text)\n",
     '    return STUDY_NAME_RE.sub(lambda m: m.group(0) if m.group(0).startswith("study_st") else "<x>", text)\n',
     "隐名时不走白名单 (study_st 开头的一律放行)", HIDE_UNIT),
    ("L3d", KS, TOKEN, TOKEN.replace("(?i)", ""), "只认小写的 study", HIDE_UNIT),
    ("L3e", KS, TOKEN, TOKEN.replace("|/\\\\]+", "|/\\\\.\\-]+"), "名字取到 . 或 - 就停 (后半截漏出来)", HIDE_E2E),
    ("L3f", KS, TOKEN, TOKEN.replace("(?<![A-Za-z0-9_])", ""), "不看前一个字符 (标识符中间的 study 也被隐去)", HIDE_UNIT),
    ("L3g", KS, LOGS, '        text = "<日志已隐去>"\n', "过度隐去: 整段日志都不带出 (防过度的闸)", VERBATIM),
    # ── _end_process_group: 僵尸不算「还在」 ──
    ("Z1", KS, "                if _only_zombies_left(pid, pgid, whole):\n", "                if True:\n",
     "僵尸判断恒真 (活着的进程被当成已结束)", ZABORT),
    ("Z2", KS, POLL, "", "去掉僵尸排除 (回到改之前: 等满 20 轮并多打一行)", ZABORT),
    ("Z3", KS, '        if state != b"Z" or threads != 1:\n', '        if state != b"Z":\n',
     "不看线程数 (主线程退出、别的线程还在跑的进程被当成已结束)", ZGROUP),
    ("Z4", KS, '        if state != b"Z" or threads != 1:\n', '        if state != b"Z" and threads != 1:\n',
     "单线程的活进程被当成已结束", ZGROUP),
    ("Z5", KS, "        except (IndexError, ValueError):\n            return False\n        if whole and pgrp != pgid:\n",
     "        except (IndexError, ValueError):\n            continue\n        if whole and pgrp != pgid:\n",
     "认不出来的一行被跳过 (当成不相干)", ZGROUP),
    ("Z6", KS, "    return seen > 0\n", "    return True\n", "一个目标都没读到也算「只剩僵尸」", ZGROUP),
    ("Z7", KS, '[Path(f"/proc/{pid}/stat")] if not whole\n', '[Path(f"/proc/{pid}/stat")] if True\n',
     "整组时只看组长 (子进程还活着也算已结束)", ZGROUP),
    ("Z8", KS, "        if whole and pgrp != pgid:\n            continue\n", "",
     "不按组号筛 (别的组的活进程也算进来: 永远判不出「只剩僵尸」)", ZGROUP),
    ("Z9", KS, '        if int(Path("/proc/self/stat").read_bytes().split(None, 1)[0]) != os.getpid():\n            return False\n',
     "", "不核对 /proc 是不是本进程所在的 pid 命名空间", ZPROC),
    ("Z10", KS, "int(f[2]), int(f[17])", "int(f[2]), int(f[16])", "线程数取错字段", ZGROUP),
    ("Z11", KS, "int(f[2]), int(f[17])", "int(f[1]), int(f[17])", "组号取错字段", ZGROUP),
    ("Z12", KS, '            f = raw.rsplit(b")", 1)[1].split()\n', '            f = raw.split(b")", 1)[1].split()\n',
     "从第一个 ) 之后取 (进程名可以冒充状态)", ZGROUP),
    ("Z13", KS, "        except (FileNotFoundError, NotADirectoryError, ProcessLookupError):\n            continue",
     "        except (FileNotFoundError, NotADirectoryError, ProcessLookupError):\n            return True",
     "读不到那个进程就算「只剩僵尸」", ZONE),
    # ── 兜底测试的缺口: 只发 SIGTERM、不升级 SIGKILL ──
    ("T1", KS, "        for sig in (signal.SIGTERM, signal.SIGKILL):\n", "        for sig in (signal.SIGTERM,):\n",
     "兜底只发 SIGTERM, 不升级到 SIGKILL", ALIVE),
    ("T2", KS, "    whole = pgid == pid and pgid != os.getpgrp()\n", "    whole = False\n",
     "只结束组长, 不整组结束 (run 214 那次用过的变异)", ALIVE),
    ("T3", KS, "        for sig in (signal.SIGTERM, signal.SIGKILL):\n", "        for sig in (0,):\n",
     "兜底一个结束信号都不发", ALIVE),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_tests() -> tuple[int, str, list[str], dict[str, str]]:
    for d in ("deploy/kbsync/__pycache__", "tests/__pycache__"):
        shutil.rmtree(ROOT / d, ignore_errors=True)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("GITHUB_STEP_SUMMARY", None)
    r = subprocess.run([sys.executable, "-m", "pytest", *TESTS, "-q", "-o", "addopts=", "-p", "no:cacheprovider",
                        "-W", "ignore", "-rfE"], cwd=ROOT, env=env, capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    summary = lines[-1] if lines else "(no output)"
    failed, why, current = [], {}, None
    for ln in lines:
        if ln.startswith(("FAILED ", "ERROR ")):
            failed.append(ln.split(" ", 1)[1].partition(" - ")[0])
        elif re.fullmatch(r"_{3,} .+ _{3,}", ln):          # 每条失败的详情以「___ 用例名 ___」开头
            current = ln.strip("_ ")
        elif ln.startswith("E ") and current and current not in why:
            why[current] = ln[1:].strip()[:140]             # 该用例的第一条 E 行 = 实际的失败信息
    return r.returncode, summary, failed, why


def verdict_of(rc: int, summary: str, failed: list[str], expected: str) -> str:
    if rc == 0:
        return "SURVIVED"
    if " error" in summary or "failed" not in summary:
        return "INVALID(error)"
    if not any(expected in t for t in failed):
        return "INVALID(wrong test)"
    return "killed"


def main() -> int:
    loaded = subprocess.run([sys.executable, "-c", "from tests.test_kbsync import ks; print(ks.__file__)"], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    assert Path(loaded).resolve() == (ROOT / KS).resolve(), f"测试导入的 kbsync 不是 ROOT 下的那一份: {loaded}"
    files = sorted({m[1] for m in MUTATIONS})
    frozen = {f: (ROOT / f).read_bytes() for f in files}
    base = {f: sha(b) for f, b in frozen.items()}
    assert len({m[0] for m in MUTATIONS}) == len(MUTATIONS), "变异编号重复"
    for f in files:
        print(f"FILE {f} sha256={base[f][:16]}")
    rc, summary, _failed, _why = run_tests()
    print(f"BASELINE rc={rc} {summary}")
    if rc != 0:
        print("基线不绿, 拒跑")
        return 2
    bad = []
    for mid, f, old, new, what, expected in MUTATIONS:
        path = ROOT / f
        assert sha(path.read_bytes()) == base[f], f"{mid}: {f} 与基线不符, 拒跑"
        text = frozen[f].decode("utf-8")
        assert text.count(old) == 1, f"{mid}: 原文出现 {text.count(old)} 次, 须恰好 1 次"
        expected_text = text.replace(old, new)
        try:
            path.write_text(expected_text, encoding="utf-8")
            back = path.read_text(encoding="utf-8")
            assert back == expected_text and sha(back.encode("utf-8")) != base[f], f"{mid}: 变异没打上"
            rc, summary, failed, why = run_tests()
        finally:
            path.write_bytes(frozen[f])
        assert sha(path.read_bytes()) == base[f], f"{mid}: 还原后 sha 不符"
        verdict = verdict_of(rc, summary, failed, expected)
        if verdict != "killed":
            bad.append(mid)
        hit = next((t for t in failed if expected in t), "")
        first = why.get(hit.rsplit("::", 1)[-1], "") if hit else ""
        others = sorted({t.rsplit("::", 1)[-1].split("[")[0] for t in failed if expected not in t})
        print(f"{mid:4} {verdict:19} {what} | {summary} | 预登记: {expected} | {first}"
              + (f" | 同时红的: {', '.join(others)}" if others else ""))
    rc, summary, _failed, _why = run_tests()
    print(f"RESTORED rc={rc} {summary}")
    print(f"{len(MUTATIONS) - len(bad)}/{len(MUTATIONS)} killed" + (f"; 没通过: {bad}" if bad else ""))
    return 1 if bad or rc != 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
