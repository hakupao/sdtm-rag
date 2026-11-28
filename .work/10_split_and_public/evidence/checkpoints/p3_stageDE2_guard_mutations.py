"""守卫用例 test_this_file_leaves_no_sdtm_rag_env_behind (tests/test_p3_4_public_https.py) 修正后的变异验证 (规则 5)。

只在副本上跑 (深度 1 的克隆或 git archive 出来的目录, 自带 venv): 不设 GUARD_MUT_ROOT 就拒跑, 指到本脚本所在的工作区也拒跑。
  必须用副本自带的 venv: litellm 在导入时会从它的安装位置往上找 .env (LITELLM_MODE 为默认值时); 拿工作区的 venv 去跑副本,
  工作区的 .env 会被读进来, 「副本里没有 .env」这个条件就不成立 (独立审查发现; 那样跑要另设 LITELLM_MODE=PRODUCTION)。
    GUARD_MUT_ROOT=<副本> <副本>/.venv/bin/python <本脚本>              # 副本里没有 .env
    GUARD_MUT_ROOT=<副本> GUARD_MUT_DOTENV=1 <副本>/.venv/bin/python <本脚本>   # 运行期间在副本里放一个只含一行的 .env, 结束时删掉
每条变异: 先比磁盘上的 sha (不符拒跑) → 逐处精确替换 (每处原文须恰好出现 1 次) → 回读确认打上了 → 只跑这个测试文件 →
finally 用冻结的原始字节写回并再比 sha。判定看 summary 行和守卫用例的失败信息, 不只看条数:
  red  = 恰好 1 failed、失败的就是守卫用例、没有 error、失败信息里有预登记的那段文字;
  green = 0 failed 0 error 0 skipped (用来证明「拿掉这条断言, 同一个问题就漏过去」);
  skipped-alone / green-alone = 只选守卫一条时恰好 1 skipped (并且 skip 的原因是预登记的那一句) / 1 passed;
  green-with-skips = 0 failed 0 error, 并且 summary 里恰好是 3 skipped, 1 xfailed (加进去的四条都没有运行)。
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

if not os.environ.get("GUARD_MUT_ROOT"):
    raise SystemExit("先准备一个副本, 再用 GUARD_MUT_ROOT 指过去; 本脚本不在工作区里直接改文件")
ROOT = Path(os.environ["GUARD_MUT_ROOT"]).resolve()
if ROOT in Path(__file__).resolve().parents:
    raise SystemExit("GUARD_MUT_ROOT 指的是本脚本所在的工作区, 拒跑")
REL = "tests/test_p3_4_public_https.py"
GUARD = "test_this_file_leaves_no_sdtm_rag_env_behind"
DOTENV = os.environ.get("GUARD_MUT_DOTENV") == "1"

FIX = "    _absent_now_and_after(monkeypatch, KEY.lower())\n"
LEAK = "    monkeypatch.delenv(KEY.lower(), raising=False)\n"          # 修正之前的写法 (= public_price_pin_mutations.py 的 XT)
A_LAST = ('    assert in_this_file[-1] == request.node.nodeid, (\n'
          '        f"the guard is not the last selected test of this file (a test added after it, or the "\n'
          '        f"order given on the command line): {in_this_file[-1]} would go unchecked")\n')
A_RUNNING = ('    assert not unwatched, (\n'
             '        f"the per-test recorder did not see these tests of this file: {unwatched} (is it still "\n'
             '        "autouse, and not shadowed by a fixture of the same name?)")\n')
A_ALONE = ('    if in_this_file == [request.node.nodeid]:\n'
           '        pytest.skip("selected on its own: no test of this file ran before the guard, nothing to check")\n')
NODEID_W = '    _env_log["watched"].append(request.node.nodeid)\n'
NODEID_L = "    in_this_file = [item.nodeid for item in mine]\n"
BY_NODEID = [NODEID_W, NODEID_L,                       # 守卫和记录夹具里按 nodeid 的每一处 (G15 整体退回按用例名)
             '        _env_log["left_behind"].append((request.node.nodeid, changed))\n',
             "    if in_this_file == [request.node.nodeid]:\n",
             "    assert in_this_file[-1] == request.node.nodeid, (\n",
             "    may_not_run = {item.nodeid for item in mine\n"]
MAY_SKIP = '                   if item.get_closest_marker("skip") or item.get_closest_marker("skipif")\n'
SEEN = "did not see these tests of this file: ['tests/test_p3_4_public_https.py::"
SHADOW = ('class TestMutationShadowsTheRecorder:\n'
          '    @pytest.fixture(autouse=True)\n'
          '    def _record_sdtm_rag_env(self):\n'
          '        yield\n\n'
          '    def test_mutation_leaks_unseen(self):\n'
          '        os.environ["SDTM_RAG_LEFT_BY_A_MUTATION"] = "1"\n\n\n')
# 同名: 类里的用例与模块级的一条用例同名 (审查者第二轮的 A_shadow_same)
SHADOW_SAME = SHADOW.replace("test_mutation_leaks_unseen", "test_image_floor_marker")
MARKED = ('@pytest.mark.skip(reason="mutation")\ndef test_mutation_marked_skip():\n    pass\n\n\n'
          '@pytest.mark.skipif(True, reason="mutation")\ndef test_mutation_marked_skipif():\n    pass\n\n\n'
          '@pytest.mark.xfail(run=False, reason="mutation")\ndef test_mutation_marked_xfail_norun():\n    pass\n\n\n'
          '@pytest.mark.local_data\ndef test_mutation_marked_local_data():\n    pass\n\n\n')
ONLY_GUARD = ["-k", "leaves_no_sdtm_rag_env_behind", "-rs"]
A_CLEAN = '    assert _env_log["left_behind"] == [], "SDTM_RAG_* names a test changed and did not restore"\n'
AUTOUSE = "@pytest.fixture(autouse=True)\ndef _record_sdtm_rag_env(request, _env_log):\n"
NOT_AUTOUSE = "@pytest.fixture\ndef _record_sdtm_rag_env(request, _env_log):\n"
COMPARE = "    if after != before:\n"
GUARD_DEF = f"def {GUARD}(request, _env_log):\n"
DIRECT_LEAK = ('def test_mutation_writes_os_environ_directly():\n'
               '    os.environ["SDTM_RAG_LEFT_BY_A_MUTATION"] = "1"\n\n\n')
FIRST_DEF = "def test_image_floor_marker():\n"          # 文件里第一条用例: 这时模块级夹具 engines 还没有建起来
DIRECT_DROP = ('def test_mutation_removes_a_name_the_dotenv_brought():\n'
               '    os.environ.pop("SDTM_RAG_AUTH_ENABLED")\n\n\n')

MUTATIONS = [
    # (编号, [(原文, 改成), ...], 在验什么, 预期, 失败信息里须有的文字)
    ("G1", [(FIX, LEAK)], "把原来那处泄漏原样放回去", "red", "sdtm_rag_quota_trusted_proxies"),
    ("G2", [(FIX, LEAK), (A_CLEAN, "")], "泄漏放回去 + 拿掉「没有留下东西」的断言 → 漏过去", "green", ""),
    ("G3", [(FIX, LEAK), (COMPARE, "    if False:\n")], "泄漏放回去 + 记录夹具不再比较前后 → 漏过去", "green", ""),
    ("G4", [(AUTOUSE, NOT_AUTOUSE)], "记录夹具不再自动生效", "red", SEEN),
    ("G5", [(FIX, LEAK), (AUTOUSE, NOT_AUTOUSE), (A_RUNNING, "")],
     "泄漏放回去 + 记录夹具不生效 + 拿掉「记录夹具在运行」的断言 → 漏过去", "green", ""),
    ("G6", [(A_CLEAN, A_CLEAN + "\n\ndef test_mutation_added_after_the_guard():\n    pass\n")],
     "守卫后面又加了一条用例", "red", "the guard is not the last selected test"),
    ("G7", [(A_CLEAN, A_CLEAN + "\n\ndef test_mutation_added_after_the_guard():\n    pass\n"), (A_LAST, "")],
     "守卫后面加了用例 + 拿掉「守卫是最后一条」的断言 → 仍被「每条用例都被记录到」抓住 (两条断言在这一情形上重叠; "
     "第一条留着是为了失败信息说对原因)", "red", SEEN + "test_mutation_added_after_the_guard']"),
    ("G7b", [(A_CLEAN, A_CLEAN + "\n\ndef test_mutation_added_after_the_guard():\n    pass\n"), (A_LAST, ""), (A_RUNNING, "")],
     "守卫后面加了用例 + 两条断言都拿掉 → 漏过去", "green", ""),
    ("G8", [(GUARD_DEF, DIRECT_LEAK + GUARD_DEF)], "另一种泄漏: 用例直接写 os.environ (大写名)", "red",
     "SDTM_RAG_LEFT_BY_A_MUTATION"),
]
MUTATIONS += [
    # 独立审查之后加的 (审查者的 M15 / 单独选中守卫)
    ("G10", [(GUARD_DEF, SHADOW + GUARD_DEF)], "类里一个同名的空夹具把记录夹具遮掉, 类里的用例泄漏", "red",
     SEEN + "TestMutationShadowsTheRecorder::test_mutation_leaks_unseen']"),
    ("G11", [(GUARD_DEF, SHADOW + GUARD_DEF), (A_RUNNING, "")],
     "同上 + 拿掉「每条用例都被记录到」的断言 → 漏过去", "green", ""),
    ("G12", [], "(不改文件) 只选守卫一条: 没有东西可查 → skip, 不是通过", "skipped-alone",
     "selected on its own: no test of this file ran before the guard", ONLY_GUARD),
    ("G13", [(A_ALONE, "")], "拿掉「单独选中就 skip」→ 只选守卫一条时空过", "green-alone", "", ONLY_GUARD),
]
MUTATIONS += [
    # 第二轮审查之后加的 (同名盲区 / 带 skip 类标记的用例不该让守卫红)
    ("G14", [(GUARD_DEF, SHADOW_SAME + GUARD_DEF)], "遮掉记录夹具的类里, 泄漏的用例与模块级的一条用例同名", "red",
     SEEN + "TestMutationShadowsTheRecorder::test_image_floor_marker']"),
    ("G15", [(GUARD_DEF, SHADOW_SAME + GUARD_DEF)] + [(ln, ln.replace("nodeid", "name")) for ln in BY_NODEID],
     "同上 + 记录与比对退回按用例名 → 同名的那条漏过去", "green", ""),
    ("G16", [(GUARD_DEF, MARKED + GUARD_DEF)],
     "加四条不会真正运行的用例 (skip / skipif / xfail(run=False) / local_data): 守卫不该红", "green-with-skips", ""),
    ("G17", [(GUARD_DEF, MARKED + GUARD_DEF), (MAY_SKIP, "                   if item.get_closest_marker(\"skipif\")\n")],
     "同上 + 不再把带 skip 标记的用例排除 → 守卫误报红 (证明排除那一段在起作用)", "red",
     SEEN + "test_mutation_marked_local_data', 'tests/test_p3_4_public_https.py::test_mutation_marked_skip']"),
]
if DOTENV:   # 只有副本里有 .env 时才有名字可删
    MUTATIONS.append(("G9", [(FIRST_DEF, DIRECT_DROP + FIRST_DEF)],
                      "反方向: engines 建起来之前的一条用例把 .env 带来的名字删掉不还原", "red", "'removed'"))

def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def must(ok: bool, msg: str) -> None:
    if not ok:
        raise SystemExit("ABORT " + msg)


def run(extra: list[str] | None = None) -> tuple[int, str, list[str], str, str]:
    p = subprocess.run([sys.executable, "-m", "pytest", REL, "-q", "-o", "addopts=", "-p", "no:cacheprovider", "-rfE",
                        *(extra or [])],
                       cwd=ROOT, capture_output=True, text=True, env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"})
    out = p.stdout + p.stderr
    summary = next((ln for ln in reversed(out.splitlines()) if re.search(r"\b(passed|failed|error|skipped)\b", ln)), "(没有 summary 行)")
    failed = re.findall(r"^(?:FAILED|ERROR) \S+::(\S+)", out, flags=re.M)
    why = " ".join(ln[1:].strip() for ln in out.splitlines() if ln.startswith("E "))   # 断言信息 + 它后面列出的名字
    return p.returncode, summary.strip(), failed, why, out


def main() -> int:
    path = ROOT / REL
    frozen = path.read_bytes()
    base = sha(frozen)
    text = frozen.decode("utf-8")
    where = subprocess.run([sys.executable, "-c", "import server, tests.test_p3_4_public_https as m; print(server.__file__); print(m.__file__)"],
                           cwd=ROOT, capture_output=True, text=True, check=True,
                           env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}).stdout.split()
    must(all(ROOT in Path(w).resolve().parents for w in where), f"导入的不是副本里的那一份: {where}")
    must(ROOT in Path(sys.prefix).resolve().parents, "解释器不是副本自带的 venv (见文件头: 别处的 venv 会把别处的 .env 带进来)")
    dotenv = ROOT / ".env"
    must(not dotenv.exists(), "副本里已经有 .env, 拒跑 (本脚本只接受自己放的那一个)")
    print(f"ROOT 是副本 | {REL} sha256={base[:16]} | 条件: {'副本里放一个只含一行 SDTM_RAG_AUTH_ENABLED=false 的 .env' if DOTENV else '没有 .env'}")
    bad = []
    try:
        if DOTENV:
            dotenv.write_text("SDTM_RAG_AUTH_ENABLED=false\n")
        rc, summary, failed, _, _ = run()
        print(f"BASELINE rc={rc} {summary}")
        must(rc == 0 and not failed, "基线不绿")
        for mid, edits, what, expect, needle, *rest in MUTATIONS:
            extra = rest[0] if rest else None
            must(sha(path.read_bytes()) == base, f"{mid}: 变异前磁盘上的文件不是基线")
            mutated = text
            for old, new in edits:
                must(mutated.count(old) == 1, f"{mid}: 原文出现 {mutated.count(old)} 次, 须恰好 1 次: {old[:50]!r}")
                mutated = mutated.replace(old, new)
            try:
                path.write_text(mutated, encoding="utf-8")
                must(path.read_text(encoding="utf-8") == mutated and (mutated != text or not edits), f"{mid}: 变异没打上")
                rc, summary, failed, why, out = run(extra)
            finally:
                path.write_bytes(frozen)
            must(sha(path.read_bytes()) == base, f"{mid}: 还原后内容不符")
            if expect == "red":
                ok = rc != 0 and failed == [GUARD] and "error" not in summary and needle in why
            elif expect == "skipped-alone":
                ok = rc == 0 and re.match(r"1 skipped, \d+ deselected", summary) is not None and needle in out
            elif expect == "green-with-skips":   # 0 failed 0 error; 被标记的那几条确实没有运行 (skipped / xfailed 都有)
                ok = rc == 0 and not failed and "error" not in summary and "3 skipped, 1 xfailed" in summary
            elif expect == "green-alone":
                ok = rc == 0 and re.match(r"1 passed, \d+ deselected", summary) is not None
            else:
                ok = rc == 0 and not failed and "error" not in summary and "skipped" not in summary
            if not ok:
                bad.append(mid)
            print(f"{mid} {'OK ' if ok else 'BAD'} 预期 {expect:13} | {what} | {summary} | 红的: {failed} | {why[:330]}")
    finally:
        if DOTENV and dotenv.exists():
            dotenv.unlink()
    rc, summary, failed, _, _ = run()
    print(f"RESTORED rc={rc} {summary} | sha256={sha(path.read_bytes())[:16]} | .env 还在: {dotenv.exists()}")
    print(f"{len(MUTATIONS) - len(bad)}/{len(MUTATIONS)} 与预期一致" + (f"; 不一致: {bad}" if bad else ""))
    return 1 if bad or rc != 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
