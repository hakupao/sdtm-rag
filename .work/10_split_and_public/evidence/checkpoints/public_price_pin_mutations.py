"""「公开档可选模型的价格固定进代码」这次修正的变异验证 (docs/RULES.md 规则 5)。跑法 (仓根; 必须指到仓库的一份副本上):

    T=<临时目录>; mkdir -p $T/mut $T/pre && git archive HEAD | tar -x -C $T/mut \\
      && git archive 0a85a43 server/cost.py server/quota.py server/instance.py | tar -x -C $T/pre
    PPP_MUT_ROOT=$T/mut PPP_PREFIX_ROOT=$T/pre .venv/bin/python \\
      .work/10_split_and_public/evidence/checkpoints/public_price_pin_mutations.py

写法照 pre_switch_fixes_mutations.py: 每个变异先比对磁盘 sha (与启动时冻结的基线不符即拒跑) → 精确替换一处 (原文须恰好
出现 1 次) → 回读, 必须逐字等于「原文替换后」→ 跑测试 → finally 用启动时冻结的原始字节写回并再比 sha。
判定不只看退出码: 每个变异预登记「应该打红的用例」。killed = 有用例失败、没有 error、打红的用例里有预登记的那条。
退出码非零但不满足这三条记 INVALID, 和 SURVIVED 一样算没通过。
直接改文件, 所以只在副本上跑: 不设 PPP_MUT_ROOT 就拒跑。开跑前核对测试导入的 server 就是 ROOT 下的那一份。
PRE 是另一种: 把 server/ 的三个文件整个换回修之前的字节 (PPP_PREFIX_ROOT, 取自 0a85a43), 只跑「没有在线价格表」那一条,
必须红, 而且输出里要有 run 219 的那句 `$0.700 > free pool / 10 = $0.300`。
XT 也是另一种: 被改的是测试文件 tests/test_p3_4_public_https.py (撤回「不把环境变量留给后面的测试」的修正), 跑的是那个文件自己,
必须红在文件末尾的守卫用例上。
只重跑其中几个: PPP_MUT_ONLY=C1,PRE (逗号分隔的编号; 写了不存在的编号会拒跑)。
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

if not os.environ.get("PPP_MUT_ROOT"):
    raise SystemExit("先把仓库复制一份, 再用 PPP_MUT_ROOT 指过去 (见文件头); 本脚本不在工作区里直接改文件")
ROOT = Path(os.environ["PPP_MUT_ROOT"]).resolve()
if (ROOT / ".git").exists():  # git archive 出来的副本没有 .git; 有的话就是工作区或某个克隆
    raise SystemExit("PPP_MUT_ROOT 指的目录里有 .git (工作区或克隆), 拒跑: 用 git archive 出来的副本")
PREFIX = Path(os.environ["PPP_PREFIX_ROOT"]).resolve() if os.environ.get("PPP_PREFIX_ROOT") else None
TEST = "tests/test_public_price_pin.py"
XT_TEST = "tests/test_p3_4_public_https.py"
COST, QUOTA, INST = "server/cost.py", "server/quota.py", "server/instance.py"
RUN_219 = "$0.700 > free pool / 10 = $0.300"

TABLE = "test_pinned_table_is_the_official_prices"
BUILTIN = "test_every_builtin_server_model_has_a_pinned_price"
SUFFIX = "test_a_pinned_row_matches_the_id_or_a_dated_snapshot_only"
SHORTER = "test_a_missing_row_is_not_covered_by_a_shorter_key"
TIER = "test_haiku_5_5_is_priced_by_prompt_length"
METER = "test_the_meter_reserves_at_the_upper_tier_and_settles_at_the_reported_one"
STORE = "test_reserve_and_settle_through_the_store_use_those_tiers"
NO_LITELLM = "test_a_pinned_model_is_priced_without_litellm"
REFUSE = "test_public_refuses_a_selectable_model_without_a_pinned_price"
PRIVATE_OK = "test_private_starts_with_the_same_unpinned_model"
FALLBACK = "test_an_unpriced_model_still_meters_at_the_fallback_rate"
OFFLINE = "test_public_cost_check_passes_without_the_online_price_map"
OFFLINE_PRIV = "test_private_is_priced_the_same_without_the_online_price_map"
OFFLINE_NAMES = "test_public_names_the_unpinned_model_without_the_online_price_map"
FLOOR = "test_settle_never_charges_less_than_the_reserved_models_pinned_price"
OLD_CHAIN = "test_settle_keeps_the_old_price_chain_when_the_reserved_model_is_not_pinned"
FLOOR_STREAM = "test_the_floor_also_holds_for_a_stream_that_ended_without_usage"
SETTING = "test_public_refuses_a_server_model_setting_without_a_pinned_price"
BOUND_FB = "test_public_bound_covers_the_fallback_model_and_its_output_cap"
NOT_BOUND = "test_groups_that_never_answer_on_public_are_not_in_the_round_bound"
CANDIDATES = "test_the_router_fallback_table_is_what_the_meter_reads"
DEAREST = "test_a_round_is_reserved_at_its_dearest_candidate"
OFFLINE_FB = "test_public_names_the_unpinned_fallback_setting_without_the_online_price_map"
EMBED = "test_the_embedding_model_is_priced_from_the_table"
XT_GUARD = "test_this_file_leaves_no_sdtm_rag_env_behind"
STREAM = "        actual = min(entry.est, _settle_price(s, model, entry.model, entry.pt, out, reported=False))\n"

HAIKU_ROW = '    "claude-haiku-5-5": (0.10, 0.50),      # prompts up to 100,000 tokens; above: _LONG_PROMPT_PRICES\n'
LONG_ROW = '    "claude-haiku-5-5": (100_000, 0.50, 2.50),\n'
MATCH = "        (k for k in _PRICES if norm.startswith(k) and _DATE_SUFFIX.fullmatch(norm[len(k):])), None)\n"
PROVIDER_IF = "    if key is None or (sep and prefix != _pinned_provider(key)):\n"
LONG_GET = "    long_prompt = _LONG_PROMPT_PRICES.get(key)\n"
FLOOR_IF = "            and pinned_rates(reserved_model, None) is not None:\n"
FLOOR_MAX = "        price = max(price, _price(s, reserved_model, pt, ct, reported=reported))\n"
TIER_IF = "    if long_prompt is not None and (prompt_tokens is None or prompt_tokens > long_prompt[0]):\n"
PINNED = "    pinned = pinned_rates(model, pt if reported else None)\n"
SETTLE = "        actual = _settle_price(s, model, entry.model, *tokens, reported=True)\n"
GATE = "        if pinned_rates(rounds[0][1], None) is None:\n"
SETTING_GATE = "        if pinned_rates(model, None) is None:\n"
FIELDS = '    for field in (*_INTERNAL_GROUP_MODEL_FIELDS.values(), "embedding_model"):\n'
WORST = "        group, model, ct, est = max(rounds, key=lambda r: r[3])\n"
ROUNDS = "        rounds = quota.round_estimates(s, m.id)\n"
FB_UNPINNED = "        if any(pinned_rates(model, None) is None for _g, model, _ct, _usd in rounds):\n"
EST_MAX = "    usd = max(_price(s, m, pt, int(kw.get(\"max_tokens\") or mo or default))\n"
EST_FOR = "              for _g, m, mo in _call_candidates(s, name))\n"
RND_FOR = "            for g, m, mo in _call_candidates(s, model_id)]\n"
FB_ADD = "        out += [(g, *_group_model(s, g)) for entry in _fallback_map(s) for g in entry.get(name, ())]\n"
EMBED_ROW = '    "text-embedding-3-small": (0.02, 0.0),\n'
XT_FIX = "    _absent_now_and_after(monkeypatch, KEY.lower())\n"
PUBLIC_ONLY = '    if s.instance != "public":\n        return\n    from server.config import PUBLIC_FORCED_OFF\n'

MUTATIONS = [
    # (编号, 文件, 原文, 改成, 这条变异在验什么, 应该打红的用例名子串)
    # ── 表里少一行 (任务第 2 条: 加了模型没加价格) ──
    ("C1", COST, HAIKU_ROW, "", "拿掉公开站在用的 haiku-5-5 这一行", OFFLINE),
    ("C2", COST, '    "claude-sonnet-5-5": (2.00, 10.00),\n', "", "拿掉内部四档默认模型 sonnet-5-5 这一行", BUILTIN),
    ("C3", COST, '    "claude-opus-5-5": (4.00, 20.00),\n', "", "拿掉 opus-5-5 (不能被更短的 opus-5 那一行顶上)", BUILTIN),
    ("C4", COST, '    "deepseek-v4-pro": (1.32, 3.96),\n', "", "拿掉回退模型 deepseek-v4-pro 这一行", BUILTIN),
    # ── 价格数值 ──
    ("C5", COST, HAIKU_ROW, HAIKU_ROW.replace("(0.10, 0.50)", "(0.10, 0.05)"), "haiku-5-5 输出价少一位 (低估)", TABLE),
    ("C6", COST, '    "claude-opus-5-5": (4.00, 20.00),\n', '    "claude-opus-5-5": (4.00, 2.00),\n',
     "opus-5-5 输出价写低", TABLE),
    # ── 匹配规则 ──
    ("C7", COST, MATCH, "        (k for k in _PRICES if norm.startswith(k)), None)\n",
     "退回宽松的前缀匹配 (opus-5-7 借用 opus-5 的价)", SUFFIX),
    ("C8", COST, MATCH, MATCH.replace("_DATE_SUFFIX.fullmatch", "_DATE_SUFFIX.match"), "日期后缀只匹配开头 (9 位数字也放行)", SUFFIX),
    ("C13", COST, '_DATE_SUFFIX = re.compile(r"-\\d{8}")', '_DATE_SUFFIX = re.compile(r"[-@]\\d{8}")',
     "后缀放宽到 @YYYYMMDD (审查者的存活变异 X3)", SUFFIX),
    ("C14", COST, PROVIDER_IF, "    if key is None:\n", "不看服务商前缀 (bedrock/… 也按第一方价; 安全审查 LOW-4)", SUFFIX),
    ("C15", COST, PROVIDER_IF, PROVIDER_IF.replace("(sep and prefix != ", "(sep and prefix == "), "前缀判断写反", SUFFIX),
    # ── 分档 ──
    ("C9", COST, LONG_ROW, "", "拿掉 haiku-5-5 超过 10 万 token 的那一档 (低估 5 倍)", TIER),
    ("C10", COST, TIER_IF, TIER_IF.replace("> long_prompt[0]", ">= long_prompt[0]"), "分档边界写成大于等于", TIER),
    ("C11", COST, TIER_IF, TIER_IF.replace("prompt_tokens is None or", "prompt_tokens is not None and"),
     "提示词长度未知时不取高档", TIER),
    ("C12", COST, LONG_ROW, LONG_ROW.replace("0.50, 2.50", "0.50, 0.50"), "高档的输出价写成低档的", TABLE),
    ("C16", COST, LONG_GET, "    long_prompt = _LONG_PROMPT_PRICES.get(_normalize(model))\n",
     "分档表按原始模型名查 (带日期后缀的快照丢掉高档; 审查者的存活变异 X2)", TIER),
    # ── 计量走固定表 ──
    ("Q1", QUOTA, PINNED, "    pinned = None\n", "计量不查固定表 (修之前的行为)", NO_LITELLM),
    ("Q2", QUOTA, PINNED, "    pinned = pinned_rates(model, pt)\n",
     "估算出来的提示词长度也按它自己的档位算 (贴着分档线时预留偏低; 启动自检的上限也跟着按低档)", METER),
    ("Q3", QUOTA, SETTLE, "        actual = _settle_price(s, model, entry.model, *tokens, reported=False)\n",
     "结算时不告诉计价「这是服务商回报的用量」(一律按高档扣, 多扣 5 倍)", STORE),
    ("Q4", QUOTA, PINNED, "    pinned = pinned_rates(model, None)\n", "计价一律按高档 (reported 不起作用)", METER),
    ("Q5", QUOTA, "        actual = min(entry.est, _settle_price(s, model, entry.model, entry.pt, out, reported=False))\n",
     "        actual = min(entry.est, _settle_price(s, model, entry.model, entry.pt, out, reported=True))\n",
     "没有用量的流式结算把估算长度当成回报的用量 (按低档扣)", STORE),
    # ── 结算的下限 (代码审查 MEDIUM: 服务商回报了表里没有的名字) ──
    ("Q6", QUOTA, FLOOR_MAX, "        pass\n", "去掉「不低于所预留模型的固定价」", FLOOR),
    ("Q7", QUOTA, FLOOR_MAX, FLOOR_MAX.replace("max(", "min("), "下限写成上限", FLOOR),
    ("Q8", QUOTA, FLOOR_IF, "            and True:\n", "所预留的模型没有固定价时也套下限 (改变原有的计价链)", OLD_CHAIN),
    ("Q9", QUOTA, FLOOR_MAX, "        price = _price(s, reserved_model, pt, ct, reported=reported)\n",
     "直接改用所预留模型的固定价 (回退费率更高时会少记)", FLOOR),
    # 复核时审查者的三条存活变异 (Y1、Y5、Y2)
    ("Q10", QUOTA, STREAM, "        actual = min(entry.est, _price(s, model or entry.model, entry.pt, out))\n",
     "没有用量的流式结算不套下限", FLOOR_STREAM),
    ("Q11", QUOTA, FLOOR_IF, FLOOR_IF.replace("is not None:", "is not None and reported:"),
     "下限只在有用量的分支生效", FLOOR_STREAM),
    ("Q12", QUOTA, FLOOR_MAX, FLOOR_MAX.replace("reported=reported", "reported=False"),
     "下限一律按高档算 (回报的用量在低档时多记 5 倍)", FLOOR),
    # ── 公开档启动自检 ──
    ("I1", INST, GATE, "        if False:\n", "公开档不再要求固定价格", REFUSE),
    ("I2", INST, GATE, GATE.replace("rounds[0][1]", "m.id"),
     "拿模型的 id 而不是模型串去查固定表 (公开站现在的配置会被拒)", OFFLINE),
    # ── 扩展 (2026-11-28 裁定一): 内部四档 + embedding 的固定价格; 单轮上限覆盖回退模型 ──
    ("I4", INST, SETTING_GATE, "        if False:\n", "内部四档和 embedding 不再要求固定价格", SETTING),
    ("I5", INST, FIELDS, "    for field in _INTERNAL_GROUP_MODEL_FIELDS.values():\n", "embedding 不在检查里", SETTING),
    ("I6", INST, FIELDS, '    for field in ("default_model", "hard_model", "light_model", "embedding_model"):\n',
     "回退档 (fallback_model) 不在检查里", SETTING),
    ("I7", INST, WORST, "        group, model, ct, est = rounds[0]\n", "单轮上限只看可选模型自己, 不看回退模型", BOUND_FB),
    ("I8", INST, ROUNDS, '        rounds = quota.round_estimates(s, m.id) + quota.round_estimates(s, "light")\n',
     "把公开档上不答题的内部档也算进单轮上限 (公开站现在的配置会被拒)", NOT_BOUND),
    ("I9", INST, FB_UNPINNED, "        if False:\n", "回退模型没有固定价格时仍拿回退费率去算上限 (多报一条金额)", OFFLINE_FB),
    ("Q13", QUOTA, EST_FOR, EST_FOR.replace("_call_candidates(s, name))", "_call_candidates(s, name)[:1])"),
     "预留不看回退模型", DEAREST),
    ("Q14", QUOTA, RND_FOR, RND_FOR.replace("_call_candidates(s, model_id)]", "_call_candidates(s, model_id)[:1]]"),
     "启动自检的单轮估算不看回退模型", DEAREST),
    ("Q15", QUOTA, EST_MAX, EST_MAX.replace("usd = max(", "usd = min("), "预留取候选里最便宜的", DEAREST),
    ("Q16", QUOTA, FB_ADD, FB_ADD.replace("(g, *_group_model(s, g))", "(g, _group_model(s, g)[0], out[0][2])"),
     "回退模型沿用可选模型的输出上限 (回退档自己的上限没被算进去)", CANDIDATES),
    ("Q17", QUOTA, FB_ADD, FB_ADD.replace("for g in entry.get(name, ())", "for gs in entry.values() for g in gs"),
     "任何组都当成有回退 (hard / light / 普通模型串也加上回退档)", CANDIDATES),
    ("C17", COST, EMBED_ROW, "", "拿掉 embedding 模型这一行", BUILTIN),
    ("C18", COST, EMBED_ROW, EMBED_ROW.replace("(0.02, 0.0)", "(0.002, 0.0)"), "embedding 价格少一位", TABLE),
    ("C19", COST, '"text-embedding-": "openai"}', '"text-embedding-": "azure"}', "embedding 的服务商前缀写错", SUFFIX),
    ("C20", COST, "    return next((provider for family, provider in _PINNED_PROVIDERS.items() if key.startswith(family)), None)\n",
     "    return _PINNED_PROVIDERS[key.split(\"-\", 1)[0] + \"-\"]\n",
     "服务商查不到时抛异常 (计量里会抛 KeyError)", "test_a_row_of_an_unlisted_family_matches_its_bare_id_only"),
    # 不写成「私有档一律跑」: server.main 在导入时就用默认配置建一次应用, 那样整份测试收集不起来 (判 INVALID)
    ("I3", INST, PUBLIC_ONLY, PUBLIC_ONLY.replace(
        'if s.instance != "public":', 'if s.instance != "public" and "selectable_models" not in s.model_fields_set:'),
     "显式配了可选模型的私有档也跑公开档的启动自检", PRIVATE_OK),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def must(ok: bool, msg: str) -> None:
    """守卫一律走这里, 不写成断言语句: python -O 下断言语句不执行, 守卫就悄悄没了。"""
    if not ok:
        raise SystemExit(f"拒跑 / 中止: {msg}")


def run_tests(select: str | None = None, test: str = TEST) -> tuple[int, str, list[str], dict[str, str], str]:
    for d in ("server/__pycache__", "tests/__pycache__"):
        shutil.rmtree(ROOT / d, ignore_errors=True)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    target = [f"{test}::{select}"] if select else [test]
    r = subprocess.run([sys.executable, "-m", "pytest", *target, "-q", "-o", "addopts=", "-p", "no:cacheprovider",
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
            why[current] = ln[1:].strip()[:150]             # 该用例的第一条 E 行 = 实际的失败信息
    return r.returncode, summary, failed, why, r.stdout


def verdict_of(rc: int, summary: str, failed: list[str], expected: str) -> str:
    if rc == 0:
        return "SURVIVED"
    if " error" in summary or "failed" not in summary:
        return "INVALID(error)"
    if not any(expected in t for t in failed):
        return "INVALID(wrong test)"
    return "killed"


def prefix_run(frozen: dict[str, bytes], base: dict[str, str]) -> bool:
    """PRE: 三个文件整个换回修之前的字节, 只跑 OFFLINE 一条; 必须红, 且输出里有 run 219 的那句。"""
    must(PREFIX is not None, "PRE 需要 PPP_PREFIX_ROOT (见文件头)")
    files = [COST, QUOTA, INST]
    old = {f: (PREFIX / f).read_bytes() for f in files}
    must(all(sha(old[f]) != base[f] for f in files), "PPP_PREFIX_ROOT 里的文件与修之后的相同, 不是修之前的")
    try:
        for f in files:
            (ROOT / f).write_bytes(old[f])
            must((ROOT / f).read_bytes() == old[f], f"PRE: {f} 没换上")
        rc, summary, failed, _why, out = run_tests(OFFLINE)
    finally:
        for f in files:
            (ROOT / f).write_bytes(frozen[f])
    for f in files:
        must(sha((ROOT / f).read_bytes()) == base[f], f"PRE: {f} 还原后 sha 不符")
    ok = rc != 0 and "1 failed" in summary and " error" not in summary \
        and any(OFFLINE in t for t in failed) and RUN_219 in out
    hit = next((ln.strip()[:230] for ln in out.splitlines() if RUN_219 in ln), "")
    print(f"PRE  {'killed' if ok else 'INVALID/SURVIVED':19} 三个文件换回修之前的字节 "
          f"(sha {', '.join(sha(old[f])[:10] for f in files)}) | {summary} | 预登记: {OFFLINE} + 「{RUN_219}」 | {hit}")
    return ok


def crosstalk_run() -> bool:
    """XT: 在测试文件里撤回修正 (换回会把小写键留给后面的测试的旧写法), 跑那个文件; 必须恰好红在守卫用例上。"""
    path = ROOT / XT_TEST
    frozen = path.read_bytes()
    text = frozen.decode("utf-8")
    must(text.count(XT_FIX) == 1, f"XT: 原文出现 {text.count(XT_FIX)} 次, 须恰好 1 次")
    rc0, summary0, _f, _w, _o = run_tests(test=XT_TEST)
    must(rc0 == 0, f"XT: 基线不绿 ({summary0})")
    mutated = text.replace(XT_FIX, "    monkeypatch.delenv(KEY.lower(), raising=False)\n")
    try:
        path.write_text(mutated, encoding="utf-8")
        must(path.read_text(encoding="utf-8") == mutated and mutated != text, "XT: 变异没打上")
        rc, summary, failed, why, _out = run_tests(test=XT_TEST)
    finally:
        path.write_bytes(frozen)
    must(path.read_bytes() == frozen, "XT: 还原后内容不符")
    verdict = verdict_of(rc, summary, failed, XT_GUARD)
    only_guard = len(failed) == 1
    print(f"XT   {verdict if only_guard else 'INVALID(others red)':19} 测试文件撤回串扰修正 | {summary} | 预登记: {XT_GUARD} | "
          f"{why.get(XT_GUARD, '')}")
    return verdict == "killed" and only_guard


def main() -> int:
    # 两种导入方式都核对 (venv 里有指向工作区的可编辑安装): 当前目录在最前 (`python -m pytest` 的方式),
    # 和测试里离线子进程的方式 (PYTHONPATH=ROOT)。
    for how, code, env in (
            ("cwd", "import sys; sys.path.insert(0, '.'); import server.cost as c; print(c.__file__)", None),
            ("PYTHONPATH", "import server.cost as c; print(c.__file__)", {**os.environ, "PYTHONPATH": str(ROOT)})):
        loaded = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True,
                                check=True).stdout.strip()
        must(Path(loaded).resolve() == (ROOT / COST).resolve(), f"导入的 server.cost 不是 ROOT 下的那一份 ({how}): {loaded}")
    ids = [m[0] for m in MUTATIONS] + ["PRE", "XT"]
    only = [x for x in os.environ.get("PPP_MUT_ONLY", "").split(",") if x]
    unknown = sorted(set(only) - set(ids))
    must(not unknown, f"PPP_MUT_ONLY 里有不存在的编号: {unknown}")
    todo = [m for m in MUTATIONS if not only or m[0] in only]
    do_pre = not only or "PRE" in only
    do_xt = not only or "XT" in only
    must(bool(todo) or do_pre or do_xt, "一个变异都没选上")
    files = sorted({m[1] for m in MUTATIONS})
    frozen = {f: (ROOT / f).read_bytes() for f in files}
    base = {f: sha(b) for f, b in frozen.items()}
    must(len(set(ids)) == len(ids), "变异编号重复")
    for f in files:
        print(f"FILE {f} sha256={base[f][:16]}")
    rc, summary, _failed, _why, _out = run_tests()
    print(f"BASELINE rc={rc} {summary}")
    if rc != 0:
        print("基线不绿, 拒跑")
        return 2
    bad = []
    for mid, f, old, new, what, expected in todo:
        path = ROOT / f
        must(sha(path.read_bytes()) == base[f], f"{mid}: {f} 与基线不符, 拒跑")
        text = frozen[f].decode("utf-8")
        must(text.count(old) == 1, f"{mid}: 原文出现 {text.count(old)} 次, 须恰好 1 次")
        expected_text = text.replace(old, new)
        try:
            path.write_text(expected_text, encoding="utf-8")
            back = path.read_text(encoding="utf-8")
            must(back == expected_text and sha(back.encode("utf-8")) != base[f], f"{mid}: 变异没打上")
            rc, summary, failed, why, _out = run_tests()
        finally:
            path.write_bytes(frozen[f])
        must(sha(path.read_bytes()) == base[f], f"{mid}: 还原后 sha 不符")
        verdict = verdict_of(rc, summary, failed, expected)
        if verdict != "killed":
            bad.append(mid)
        hit = next((t for t in failed if expected in t), "")
        first = why.get(hit.rsplit("::", 1)[-1], "") if hit else ""
        others = sorted({t.rsplit("::", 1)[-1].split("[")[0] for t in failed if expected not in t})
        print(f"{mid:4} {verdict:19} {what} | {summary} | 预登记: {expected} | {first}"
              + (f" | 同时红的: {', '.join(others)}" if others else ""))
    n = len(todo)
    if do_pre:
        n += 1
        if not prefix_run(frozen, base):
            bad.append("PRE")
    if do_xt:
        n += 1
        if not crosstalk_run():
            bad.append("XT")
    rc, summary, _failed, _why, _out = run_tests()
    print(f"RESTORED rc={rc} {summary}")
    print(f"{n - len(bad)}/{n} killed" + (f" (全部 {len(ids)} 个里只跑了这 {n} 个)" if only else "")
          + (f"; 没通过: {bad}" if bad else ""))
    return 1 if bad or rc != 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
