"""「打开公开部署开关之前」那几处修正的变异验证 (docs/RULES.md 规则 5)。跑法 (仓根; 必须指到仓库的一份副本上):

    mkdir -p <临时目录>/mut && git archive HEAD | tar -x -C <临时目录>/mut \\
      && rmdir <临时目录>/mut/vendor/sdtm-pedia && ln -s "$PWD/vendor/sdtm-pedia" <临时目录>/mut/vendor/sdtm-pedia
    PSF_MUT_ROOT=<临时目录>/mut .venv/bin/python .work/10_split_and_public/evidence/checkpoints/pre_switch_fixes_mutations.py

写法照 p3_step3.4_mutations.py: 每个变异先比对磁盘 sha (与启动时冻结的基线不符即拒跑) → 精确替换一处 (原文须恰好
出现 1 次) → 回读, 必须逐字等于「原文替换后」→ 跑测试 → finally 用启动时冻结的原始字节写回并再比 sha。
判定不只看退出码: 每个变异预登记「应该打红的用例」。killed = 有用例失败、没有 error、打红的用例里有预登记的那条。
退出码非零但不满足这三条记 INVALID, 和 SURVIVED 一样算没通过。
直接改文件, 所以只在副本上跑: 不设 PSF_MUT_ROOT 就拒跑 (独立审查的建议: 默认改工作区的话, 中途被打断会把半变异态留在工作区里)。
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

if not os.environ.get("PSF_MUT_ROOT"):
    raise SystemExit("先把仓库复制一份, 再用 PSF_MUT_ROOT 指过去 (见文件头); 本脚本不在工作区里直接改文件")
ROOT = Path(os.environ["PSF_MUT_ROOT"]).resolve()
WORKSPACE = Path(__file__).resolve().parents[4]
if ROOT == WORKSPACE:
    raise SystemExit("PSF_MUT_ROOT 指的就是工作区本身, 拒跑")
TESTS = ["tests/test_kbsync.py", "tests/test_kbsync_public.py", "tests/test_kbsync_deploy_public.py",
         "tests/test_workflow_conditions.py"]
KS = "deploy/kbsync/kbsync.py"
KBWF, DEPWF = ".gitea/workflows/kb-sync.yml", ".gitea/workflows/sdtm-rag.yml"

NAMES = "test_only_conventional_collection_names_are_printed"
SCRUB = "test_startup_error_is_scrubbed_before_it_is_carried_out"
HIDE_E2E = "test_study_collection_names_in_a_startup_error_are_hidden"
HIDE_CFG = "test_configured_study_collection_name_in_a_startup_error_is_hidden"
HIDE_UNIT = "test_hide_study_names"
HIDE_WHOLE = "test_a_name_with_a_key_shaped_fragment_is_hidden_whole"
KEY_WHOLE = "test_a_secret_containing_the_word_study_is_scrubbed_whole"
BOTH = "test_sanitize_log_keeps_both_guarantees_in_one_text"
GLUED = "test_stdout_and_stderr_of_the_container_log_are_not_glued_together"
SETTINGS = "test_study_setting_names_match_the_settings_class"
SEES = "test_the_schedule_check_sees_every_way_of_writing_it"
VERBATIM = "test_startup_refusal_is_carried_verbatim_into_the_failure_reason"
ZGROUP = "test_only_zombies_left_for_a_whole_group"
ZONE = "test_only_zombies_left_for_a_single_process"
ZPROC = "test_only_zombies_left_refuses_without_a_usable_proc"
ZABORT = "test_abort_does_not_wait_on_zombies_but_still_waits_on_a_live_process"
ALIVE = "test_abort_first_ends_a_deploy_process_that_is_still_alive"
NOSCHED = "test_no_workflow_has_a_schedule_trigger"
CRON = '  schedule:\n    - cron: "17 3 * * *"\n'

SAFE = 'SAFE_COLLECTION_RE = re.compile(r"study_st[0-9]{2,3}(_docs)?|sdtm_kb_v[0-9]{1,3}")'
LOGS = "        text = _sanitize_log(raw)\n"
SAN = '    return _hide_study_names(SECRET_RE.sub(_KEY_MASK, raw)).replace(_KEY_MASK, "<已隐去>")\n'
JOIN = 'raw = logs.stdout.decode("utf-8", "replace") + "\\n" + logs.stderr.decode("utf-8", "replace")'
TOKEN = '''STUDY_NAME_RE = re.compile(r"(?i)study[^\\s'\\"`\\[\\]{}(),;:=<>|/\\\\]+")'''
WORD = "        return word if word.lower() in STUDY_SETTING_NAMES else _show_collection(word)\n"
KILL = "                    send(signal.SIGKILL)  # 都没了会抛 ProcessLookupError，同样算干净\n"
POLL = "                if _only_zombies_left(pid, pgid, whole):\n" + KILL + "                    return True\n"

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
    ("L2a", KS, LOGS, "        text = _hide_study_names(raw)\n", "容器日志带出之前不脱敏", SCRUB),
    ("L2c", KS, SAN, "    return _hide_study_names(SECRET_RE.sub(_KEY_MASK, raw))\n", "占位符没有换回去 (输出里留着占位符)", SCRUB),
    ("L2b", KS, '"\\n".join(tail))\n        # 应用拒绝启动时',
     '"\\n".join(raw.strip().splitlines()[-40:]))\n        # 应用拒绝启动时',
     "失败原因处理过, 但打印的日志末尾是原文", SCRUB),
    # ── LOW-3: 启动报错里的集合名 ──
    ("L3a", KS, LOGS, "        text = scrub(raw)\n", "容器日志带出之前不隐去 study 集合名", HIDE_E2E),
    ("L3b", KS, "    return STUDY_NAME_RE.sub(show, text)\n", "    return text\n", "隐名函数什么都不做", HIDE_CFG),
    ("L3c", KS, WORD, '        return word if word.lower() in STUDY_SETTING_NAMES or word.startswith("study_st") else "<x>"\n',
     "隐名时不走白名单 (study_st 开头的一律放行)", HIDE_UNIT),
    ("L3d", KS, TOKEN, TOKEN.replace("(?i)", ""), "只认小写的 study", HIDE_UNIT),
    ("L3e", KS, TOKEN, TOKEN.replace("|/\\\\]+", "|/\\\\.\\-]+"), "名字取到 . 或 - 就停 (后半截漏出来)", HIDE_E2E),
    ("L3f", KS, TOKEN, TOKEN.replace("(?i)study", "(?i)(?<![A-Za-z0-9_])study"),
     "要求 study 前面不是字母数字 (粘在别的词 / 颜色码 / 写出来的 \\n 后面的名字漏掉; 审查前的写法)", HIDE_UNIT),
    ("L3g", KS, LOGS, '        text = "<日志已隐去>"\n', "过度隐去: 整段日志都不带出 (防过度的闸)", VERBATIM),
    ("L3h", KS, SAN, "    return _hide_study_names(scrub(raw))\n",
     "先脱敏 (直接用「<已隐去>」) 后隐名 (审查第 1 轮 MEDIUM: 名字被切成两段, 后半段漏出来)", HIDE_WHOLE),
    ("L3n", KS, SAN, "    return scrub(_hide_study_names(raw))\n",
     "先隐名后脱敏 (审查第 2 轮: 值里带 study 的 key 只盖住一部分)", KEY_WHOLE),
    ("L3o", KS, '_KEY_MASK = "\\x00K\\x00"\n', '_KEY_MASK = "<K>"\n', "占位符里有分隔符 (名字又被切成两段)", HIDE_WHOLE),
    ("L3p", KS, SAN, "    return scrub(raw)\n", "新的入口只脱敏、不隐名", BOTH),
    ("L3i", KS, JOIN, 'raw = (logs.stdout + logs.stderr).decode("utf-8", "replace")', "stdout 与 stderr 直接相连", GLUED),
    ("L3j", KS, WORD, "        return _show_collection(word)\n", "配置项的名字也被隐去 (报错里看不出是哪个开关)", HIDE_CFG),
    ("L3k", KS, WORD, "        return word if any(word.lower().startswith(n) for n in STUDY_SETTING_NAMES) else _show_collection(word)\n",
     "以配置项的名字开头就放行 (后面跟着什么都原样写出)", HIDE_UNIT),
    ("L3l", KS, WORD, "        return word if word in STUDY_SETTING_NAMES else _show_collection(word)\n",
     "配置项的名字只认小写 (环境变量写法的被隐去)", HIDE_UNIT),
    ("L3m", KS, '    "study_docs_enabled", "study_docs_seats", "study_id",', '    "study_docs_enabled", "study_docs_seats", "study_id", "study_acme",',
     "配置项名单里多了一个不是配置项的名字", SETTINGS),
    # ── _end_process_group: 僵尸不算「还在」 ──
    ("Z1", KS, POLL, "                if True:\n                    return True\n",
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
    ("Z14", KS, "        except OSError:\n            return False\n        try:\n", "        except OSError:\n            continue\n        try:\n",
     "读的时候报错的进程被跳过 (审查的 M16: 看不见的活进程被当成不相干)", ZGROUP),
    ("Z15", KS, KILL, "", "判成「只剩僵尸」时不补发 SIGKILL (判错时漏掉的进程没人结束)", ZABORT),
    ("Z16", KS, POLL, KILL + POLL, "还没问僵尸就先发 SIGKILL (不给 SIGTERM 留时间)", ZABORT),
    # ── 兜底测试的缺口: 只发 SIGTERM、不升级 SIGKILL ──
    ("T1", KS, "        for sig in (signal.SIGTERM, signal.SIGKILL):\n", "        for sig in (signal.SIGTERM,):\n",
     "兜底只发 SIGTERM, 不升级到 SIGKILL", ALIVE),
    ("T2", KS, "    whole = pgid == pid and pgid != os.getpgrp()\n", "    whole = False\n",
     "只结束组长, 不整组结束 (run 214 那次用过的变异)", ALIVE),
    ("T3", KS, "        for sig in (signal.SIGTERM, signal.SIGKILL):\n", "        for sig in (0,):\n",
     "兜底一个结束信号都不发", ALIVE),
    # ── kb-sync 不留定时触发 ──
    ("W1", KBWF, "on:\n  workflow_dispatch:\n", "on:\n" + CRON + "  workflow_dispatch:\n", "kb-sync 的定时触发被加回来", NOSCHED),
    ("W2", DEPWF, "  workflow_dispatch:\n    inputs:\n      tag:\n", CRON + "  workflow_dispatch:\n    inputs:\n      tag:\n",
     "部署工作流被加上定时触发", NOSCHED),
    ("W3", KBWF, "on:\n  workflow_dispatch:\n", "on:\n  push:\n    branches: [main]\n  workflow_dispatch:\n",
     "kb-sync 多了手动派发以外的触发 (push)", NOSCHED),
    ("W4", KBWF, "on:\n  workflow_dispatch:\n", "on:\n  \"schedule\":\n    - \"cron\": \"17 3 * * *\"\n  workflow_dispatch:\n",
     "定时触发换个写法加回来 (带引号的键)", NOSCHED),
    ("W5", KBWF, "on:\n  workflow_dispatch:\n", "on: {schedule: [{cron: \"17 3 * * *\"}]}\non:\n  workflow_dispatch:\n",
     "重复的 on 键, 带定时的写在前面 (审查的 W2: PyYAML 默认取后一个)", NOSCHED),
    ("W6", "tests/test_workflow_conditions.py", "        if dup:\n", "        if False:\n",
     "测试用的加载器不再拒绝重复的键", SEES),
    ("W7", "tests/test_workflow_conditions.py", '(^|[\\s{,\\[-])[\\"\']?(schedule|cron)', '^\\s*(-\\s*)?[\\"\']?(schedule|cron)',
     "文本检查退回只看行首 (审查前的写法)", SEES),
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
