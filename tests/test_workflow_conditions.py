"""两个 Gitea workflow 的静态检查: job / step 的 `if` 条件真值表, 以及公开腿的结构不变量。

workflow 的 job 只在 main 上执行, 分支上跑不了; 这里用一个只覆盖本仓用到的语法子集的求值器, 把每个 `if`
在各种输入下的结果钉成表。求值器按 GitHub Actions 的约定建模: 表达式里没有状态函数
(always / success / failure / cancelled) 时, 隐含 `success() &&` —— job 级带 `needs` 时也一样。
⚠ 这是语义模型, 不是 act_runner 本身: Gitea 对 job 级 `always()`、`vars`、`needs` 的真实行为要在合并后的演练里确认。"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WF_FILES = {"kb-sync": ".gitea/workflows/kb-sync.yml", "sdtm-rag": ".gitea/workflows/sdtm-rag.yml"}
WF = {k: yaml.safe_load((ROOT / v).read_text()) for k, v in WF_FILES.items()}
PUB = yaml.safe_load((ROOT / "deploy/container/compose.public.yml").read_text())
PRIV = yaml.safe_load((ROOT / "deploy/container/compose.yml").read_text())

STATUS_FUNCS = ("always", "success", "failure", "cancelled")
_TOKEN = re.compile(r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<op>&&|\|\||==|!=|\(|\)|,)"
                    r"|(?P<name>[A-Za-z_][\w-]*(?:\.[\w-]+)*))")


class V:
    """表达式里的值: 字符串比较不分大小写; 空串为假, 非空串 (含 'false') 为真。"""

    def __init__(self, v):
        self.v = v

    def _key(self):
        return self.v.lower() if isinstance(self.v, str) else self.v

    def __eq__(self, other):
        return self._key() == (other._key() if isinstance(other, V) else other)

    def __ne__(self, other):
        return not self == other

    def __bool__(self):
        return bool(self.v)

    __hash__ = None


def _fmt(template: V, *args: V) -> V:
    def show(x):
        return {True: "true", False: "false", None: ""}.get(x.v, x.v) if isinstance(x.v, (bool, type(None))) else x.v
    return V(template.v.format(*[show(a) for a in args]))


def evaluate(expr: str, ctx: dict | None = None, status: str = "success") -> bool:
    """status = 之前的步骤 (step 级) 或 needs 里的 job (job 级) 的综合结果: success / failure / cancelled。"""
    assert status in ("success", "failure", "cancelled")
    ctx = ctx or {}
    out, pos, has_status = [], 0, False
    expr = expr.strip()
    if expr.startswith("${{"):
        expr = expr[3:-2]
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            if expr[pos:].strip() == "":
                break
            raise NotImplementedError(f"求值器不认识的写法: {expr[pos:]!r}")
        pos = m.end()
        if m["str"]:
            out.append(f"V({m['str'][1:-1].replace(chr(39) * 2, chr(39))!r})")
        elif m["op"]:
            out.append({"&&": " and ", "||": " or "}.get(m["op"], m["op"]))
        elif expr[pos:].lstrip().startswith("("):
            has_status |= m["name"] in STATUS_FUNCS
            out.append(f"F[{m['name']!r}]")
        else:
            out.append(f"C({m['name']!r})")
    funcs = {"always": lambda: V(True), "success": lambda: V(status == "success"),
             "failure": lambda: V(status == "failure"), "cancelled": lambda: V(status == "cancelled"),
             "format": _fmt}
    src = "".join(out)
    if not has_status:
        src = f"F['success']() and ({src})"
    return bool(eval(src, {"__builtins__": {}}, {"V": V, "F": funcs, "C": lambda k: V(ctx.get(k, ""))}))  # noqa: S307


MAIN, OTHER = {"gitea.ref": "refs/heads/main"}, {"gitea.ref": "refs/heads/feature"}
ON, OFF = {"vars.SDTM_RAG_PUBLIC_DEPLOY": "true"}, {}
CHANGED = {"steps.detect.outputs.result": "changed"}


def _job(wf: str, job: str) -> dict:
    return WF[wf]["jobs"][job]


def _step(wf: str, job: str, name: str) -> dict:
    steps = _job(wf, job)["steps"]
    hits = [s for s in steps if s.get("name") == name or s.get("id") == name] or [
        s for s in steps if s.get("name", "").startswith(name)]
    assert len(hits) == 1, (wf, job, name, len(hits))
    return hits[0]


def _runs(wf: str, job: str) -> str:
    return "\n".join(s.get("run", "") for s in _job(wf, job)["steps"])


# (workflow, job, step 或 None, 上下文, 状态, 期望)。step 用 name 前缀或 id 定位。
KB_SYNC_TABLE = [
    # job private: 只在 main 上跑
    ("kb-sync", "private", None, MAIN, "success", True),
    ("kb-sync", "private", None, OTHER, "success", False),
    # job public: main + 变量开; 私有腿成功 / 失败 / 取消都照跑
    ("kb-sync", "public", None, {**MAIN, **ON}, "success", True),
    ("kb-sync", "public", None, {**MAIN, **ON}, "failure", True),
    ("kb-sync", "public", None, {**MAIN, **ON}, "cancelled", True),
    ("kb-sync", "public", None, {**MAIN, **OFF}, "success", False),
    ("kb-sync", "public", None, {**MAIN, **OFF}, "failure", False),
    ("kb-sync", "public", None, {**MAIN, "vars.SDTM_RAG_PUBLIC_DEPLOY": "false"}, "success", False),
    ("kb-sync", "public", None, {**OTHER, **ON}, "success", False),
    ("kb-sync", "public", None, {**OTHER, **ON}, "failure", False),
    # private 的步骤
    ("kb-sync", "private", "构建候选镜像", CHANGED, "success", True),
    ("kb-sync", "private", "构建候选镜像", {"steps.detect.outputs.result": "same"}, "success", False),
    ("kb-sync", "private", "构建候选镜像", {"steps.detect.outputs.result": "gated"}, "success", False),
    ("kb-sync", "private", "构建候选镜像", CHANGED, "failure", False),
    ("kb-sync", "private", "候选入库并运行 CDISC 闸", CHANGED, "success", True),
    ("kb-sync", "private", "候选入库并运行 CDISC 闸", {}, "success", False),
    ("kb-sync", "private", "候选入库并运行 CDISC 闸", CHANGED, "failure", False),
    # 删镜像: 每条腿建了镜像 (changed) 就在自己结束时删, 成功 / 失败 / 取消都删, 与公开变量无关
    ("kb-sync", "private", "删除候选镜像", {**CHANGED, **OFF}, "success", True),
    ("kb-sync", "private", "删除候选镜像", {**CHANGED, **OFF}, "failure", True),
    ("kb-sync", "private", "删除候选镜像", {**CHANGED, **OFF}, "cancelled", True),
    ("kb-sync", "private", "删除候选镜像", {**CHANGED, **ON}, "success", True),
    ("kb-sync", "private", "删除候选镜像", {**CHANGED, **ON}, "failure", True),
    ("kb-sync", "private", "删除候选镜像", {"steps.detect.outputs.result": "same", **OFF}, "success", False),
    ("kb-sync", "private", "删除候选镜像", {"steps.detect.outputs.result": "gated", **ON}, "failure", False),
    # public 的步骤: 只有 changed 才建候选; 前面任何一步失败, 后面都不跑
    ("kb-sync", "public", "构建候选镜像", CHANGED, "success", True),
    ("kb-sync", "public", "构建候选镜像", {"steps.detect.outputs.result": "gated"}, "success", False),
    ("kb-sync", "public", "检查公开站的 embedding key", CHANGED, "success", True),
    ("kb-sync", "public", "检查公开站的 embedding key", {"steps.detect.outputs.result": "same"}, "success", False),
    ("kb-sync", "public", "检查公开站的 embedding key", CHANGED, "failure", False),
    ("kb-sync", "public", "选基线镜像", CHANGED, "success", True),
    ("kb-sync", "public", "选基线镜像", {}, "success", False),
    ("kb-sync", "public", "选基线镜像", CHANGED, "failure", False),
    ("kb-sync", "public", "公开候选入库并运行 CDISC 闸", CHANGED, "success", True),
    ("kb-sync", "public", "公开候选入库并运行 CDISC 闸", {"steps.detect.outputs.result": "same"}, "success", False),
    ("kb-sync", "public", "公开候选入库并运行 CDISC 闸", CHANGED, "failure", False),  # key 检查或基线失败 → 不入库
    # 公开腿同样: 自己建了镜像才删, 成功 / 失败 / 取消都删
    ("kb-sync", "public", "删除候选镜像", CHANGED, "success", True),
    ("kb-sync", "public", "删除候选镜像", CHANGED, "failure", True),
    ("kb-sync", "public", "删除候选镜像", CHANGED, "cancelled", True),
    ("kb-sync", "public", "删除候选镜像", {"steps.detect.outputs.result": "same"}, "success", False),
    ("kb-sync", "public", "删除候选镜像", {}, "failure", False),  # 还没走到检测就失败: 没建过镜像
]
PUSH = {"gitea.event_name": "push"}
DISPATCH = {"gitea.event_name": "workflow_dispatch", "inputs.deploy": True}
BUILD_ONLY = {"gitea.event_name": "workflow_dispatch", "inputs.deploy": False}
ROLLBACK = {"gitea.event_name": "workflow_dispatch", "inputs.deploy": True, "inputs.tag": "0" * 40}
SWAP = {"steps.kbcheck.outputs.decision": "swap"}
STARTED = {"steps.deploy.outputs.started": "true", "steps.prev.outputs.prev": "a" * 40, "steps.tag.outputs.tag": "b" * 40}
PRE_OK, PRE_BAD = {"steps.pre.outcome": "success"}, {"steps.pre.outcome": "failure"}
DEPLOY_STEPS = ("记录当前线上镜像", "KB 数据对齐检查", "部署", "健康检查")

SDTM_RAG_TABLE = [
    # job deploy: 只在 main
    ("sdtm-rag", "deploy", None, MAIN, "success", True),
    ("sdtm-rag", "deploy", None, OTHER, "success", False),
    # 回滚 (手动填 tag) 时跳过测试与构建
    *[("sdtm-rag", "deploy", st, ctx, "success", want) for st in ("测试", "构建并推送")
      for ctx, want in ((PUSH, True), (DISPATCH, True), (ROLLBACK, False))],
    ("sdtm-rag", "deploy", "构建并推送", PUSH, "failure", False),  # 测试失败 → 不构建
    # 只构建不部署 (deploy=false) 时, 部署类步骤全部跳过
    *[("sdtm-rag", "deploy", st, ctx, status, want) for st in DEPLOY_STEPS
      for ctx, status, want in ((PUSH, "success", True), (DISPATCH, "success", True), (ROLLBACK, "success", True),
                                (BUILD_ONLY, "success", False), (PUSH, "failure", False))],
    ("sdtm-rag", "deploy", "检查 KB 索引新鲜度", SWAP, "success", True),
    ("sdtm-rag", "deploy", "检查 KB 索引新鲜度", {"steps.kbcheck.outputs.decision": "same"}, "success", False),
    ("sdtm-rag", "deploy", "检查 KB 索引新鲜度", SWAP, "failure", False),
    ("sdtm-rag", "deploy", "换数据收尾", SWAP, "success", True),
    ("sdtm-rag", "deploy", "换数据收尾", SWAP, "failure", False),
    ("sdtm-rag", "deploy", "换数据收尾", {"steps.kbcheck.outputs.decision": "forced"}, "success", False),
    ("sdtm-rag", "deploy", "失败时退回换过的 chroma/meta", SWAP, "failure", True),
    ("sdtm-rag", "deploy", "失败时退回换过的 chroma/meta", SWAP, "success", False),
    ("sdtm-rag", "deploy", "失败时退回换过的 chroma/meta", SWAP, "cancelled", False),
    ("sdtm-rag", "deploy", "失败时退回换过的 chroma/meta", {"steps.kbcheck.outputs.decision": "same"}, "failure", False),
    ("sdtm-rag", "deploy", "健康检查失败 → 退回部署前的镜像", STARTED, "failure", True),
    ("sdtm-rag", "deploy", "健康检查失败 → 退回部署前的镜像", STARTED, "success", False),
    ("sdtm-rag", "deploy", "健康检查失败 → 退回部署前的镜像", {**STARTED, "steps.deploy.outputs.started": ""}, "failure", False),
    ("sdtm-rag", "deploy", "健康检查失败 → 退回部署前的镜像", {**STARTED, "steps.prev.outputs.prev": ""}, "failure", False),
    ("sdtm-rag", "deploy", "健康检查失败 → 退回部署前的镜像", {**STARTED, "steps.prev.outputs.prev": "b" * 40}, "failure", False),
    ("sdtm-rag", "deploy", "退出镜像仓库", {}, "failure", True),
    ("sdtm-rag", "deploy", "退出镜像仓库", {}, "cancelled", True),
    # job deploy_public: main + 变量开 + 不是「只构建」; 私有部署 (needs) 失败或取消 → 不跑
    ("sdtm-rag", "deploy_public", None, {**MAIN, **ON, **PUSH}, "success", True),
    ("sdtm-rag", "deploy_public", None, {**MAIN, **ON, **DISPATCH}, "success", True),
    ("sdtm-rag", "deploy_public", None, {**MAIN, **ON, **ROLLBACK}, "success", True),
    ("sdtm-rag", "deploy_public", None, {**MAIN, **ON, **BUILD_ONLY}, "success", False),
    ("sdtm-rag", "deploy_public", None, {**MAIN, **OFF, **PUSH}, "success", False),
    ("sdtm-rag", "deploy_public", None, {**MAIN, "vars.SDTM_RAG_PUBLIC_DEPLOY": "false", **PUSH}, "success", False),
    ("sdtm-rag", "deploy_public", None, {**OTHER, **ON, **DISPATCH}, "success", False),
    ("sdtm-rag", "deploy_public", None, {**MAIN, **ON, **PUSH}, "failure", False),
    ("sdtm-rag", "deploy_public", None, {**MAIN, **ON, **PUSH}, "cancelled", False),
    # 兜底停机: 失败或取消才进 (进了以后由 public-abort 看标记文件决定停不停)
    ("sdtm-rag", "deploy_public", "中断时停掉已被动过的公开实例", {}, "failure", True),
    ("sdtm-rag", "deploy_public", "中断时停掉已被动过的公开实例", {}, "cancelled", True),
    ("sdtm-rag", "deploy_public", "中断时停掉已被动过的公开实例", {}, "success", False),
    # 清理: 成功 / 失败 / 取消都清; 预检没过 (镜像没拉到) 就没有东西可清
    ("sdtm-rag", "deploy_public", "清理临时容器与验收副本", PRE_OK, "success", True),
    ("sdtm-rag", "deploy_public", "清理临时容器与验收副本", PRE_OK, "failure", True),
    ("sdtm-rag", "deploy_public", "清理临时容器与验收副本", PRE_OK, "cancelled", True),
    ("sdtm-rag", "deploy_public", "清理临时容器与验收副本", PRE_BAD, "failure", False),
    ("sdtm-rag", "deploy_public", "清理临时容器与验收副本", {}, "cancelled", False),
    ("sdtm-rag", "deploy_public", "退出镜像仓库", {}, "failure", True),
    ("sdtm-rag", "deploy_public", "退出镜像仓库", {}, "cancelled", True),
    # 没写 if 的步骤 (隐含 success()): 预检失败 → 部署步骤不跑; 预检成功才跑
    ("sdtm-rag", "deploy_public", "临时容器验收，通过后才换正式容器", {}, "success", True),
    ("sdtm-rag", "deploy_public", "临时容器验收，通过后才换正式容器", {}, "failure", False),
    ("sdtm-rag", "deploy_public", "临时容器验收，通过后才换正式容器", {}, "cancelled", False),
]
TABLE = KB_SYNC_TABLE + SDTM_RAG_TABLE


def _expr(wf: str, job: str, step: str | None) -> str:
    node = _job(wf, job) if step is None else _step(wf, job, step)
    return str(node.get("if", "success()"))


@pytest.mark.parametrize("wf,job,step,ctx,status,want", TABLE,
                         ids=[f"{w}/{j}/{s or 'job'}/{st}/{i}" for i, (w, j, s, _, st, _) in enumerate(TABLE)])
def test_if_truth_table(wf, job, step, ctx, status, want):
    assert evaluate(_expr(wf, job, step), ctx, status) is want


def test_truth_table_covers_every_condition_in_both_workflows():
    """两个 workflow 里每个带 `if` 的 job / step 都在表里, 且 (除纯 always() 外) 真假两种结果都钉过。"""
    seen: dict[tuple, set] = {}
    for wf, job, step, _, _, want in TABLE:
        node = _job(wf, job) if step is None else _step(wf, job, step)
        seen.setdefault((wf, job, None if step is None else node.get("name")), set()).add(want)
    n = 0
    for wf, doc in WF.items():
        for job, spec in doc["jobs"].items():
            nodes = [(None, spec)] + [(s.get("name"), s) for s in spec["steps"] if "if" in s]
            for name, node in nodes:
                n += 1
                got = seen.get((wf, job, name))
                assert got, f"表里缺 {wf}/{job}/{name}"
                if str(node["if"]).strip() != "always()":
                    assert got == {True, False}, f"{wf}/{job}/{name} 只钉了 {got}"
    assert n >= 26


def test_evaluator_models_implicit_success_and_status_functions():
    assert evaluate("a.b == 'x'", {"a.b": "X"}) is True  # 不分大小写
    assert evaluate("a.b == 'x'", {"a.b": "x"}, "failure") is False  # 隐含 success()
    assert evaluate("always() && a.b == 'x'", {"a.b": "x"}, "failure") is True
    assert evaluate("failure() || cancelled()", {}, "cancelled") is True
    assert evaluate("failure() || cancelled()", {}, "success") is False
    assert evaluate("(failure() || cancelled()) && s.o == 'true'", {"s.o": "true"}, "failure") is True
    assert evaluate("(failure() || cancelled()) && s.o == 'true'", {}, "failure") is False
    assert evaluate("x != 'workflow_dispatch' || format('{0}', i.d) != 'false'", {"x": "workflow_dispatch", "i.d": False}) is False
    assert evaluate("x != 'workflow_dispatch' || format('{0}', i.d) != 'false'", {"x": "workflow_dispatch", "i.d": True}) is True
    assert evaluate("x != 'workflow_dispatch' || format('{0}', i.d) != 'false'", {"x": "push"}) is True
    assert evaluate("missing.key == ''") is True  # 不存在的属性是空串
    with pytest.raises(NotImplementedError):
        evaluate("!cancelled()")


# ── kb-sync: 两条腿的结构 ────────────────────────────────────────────────
def _mount_sources(compose_service: dict) -> list[str]:
    return [v["source"] for v in compose_service["volumes"]]


def test_kb_sync_has_two_legs_and_public_follows_private():
    jobs = WF["kb-sync"]["jobs"]
    assert list(jobs) == ["private", "public"]
    assert jobs["public"]["needs"] == "private" and "needs" not in jobs["private"]
    assert WF["kb-sync"]["concurrency"]["group"] == WF["sdtm-rag"]["concurrency"]["group"] == "sdtm-rag-deploy"
    assert WF["kb-sync"]["concurrency"]["cancel-in-progress"] is False


def test_kb_sync_each_leg_uses_only_its_own_root_and_env():
    priv, pub = _job("kb-sync", "private")["env"], _job("kb-sync", "public")["env"]
    assert [priv["DATA_ROOT"], priv["ENV_FILE"]] == _mount_sources(PRIV["x-common"])
    assert [pub["DATA_ROOT"], pub["ENV_FILE"]] == _mount_sources(PUB["services"]["api"])
    assert priv["DATA_ROOT"] != pub["DATA_ROOT"] and priv["ENV_FILE"] != pub["ENV_FILE"]
    assert "DATA_ROOT" not in WF["kb-sync"].get("env", {}) and "ENV_FILE" not in WF["kb-sync"].get("env", {})
    # 各腿的脚本里不出现另一条腿的路径字面量 (路径只经由本 job 的 env 进入)
    for mine, other in ((priv, "private"), (pub, "public")):
        text = _runs("kb-sync", "public" if other == "private" else "private")
        assert mine["DATA_ROOT"] not in text and mine["ENV_FILE"] not in text
    assert "sdtm-rag-public/data" not in _runs("kb-sync", "private")


def test_kb_sync_public_leg_guards_are_wired_in_order():
    names = [s.get("name", "checkout") for s in _job("kb-sync", "public")["steps"]]
    order = ["路径一致性断言", "检测", "构建候选镜像", "检查公开站的 embedding key", "选基线镜像",
             "公开候选入库并运行 CDISC 闸", "删除候选镜像"]
    idx = [next(i for i, n in enumerate(names) if n.startswith(o)) for o in order]
    assert idx == sorted(idx) and len(set(idx)) == len(order)
    cand = _step("kb-sync", "public", "公开候选入库并运行 CDISC 闸")["run"]
    assert "--kb-only" in cand and '--prod-image "$BASE_IMAGE"' in cand and '--env-file "$ENV_FILE"' in cand
    cand_env = _step("kb-sync", "public", "公开候选入库并运行 CDISC 闸")["env"]
    assert cand_env["BASE_IMAGE"] == "${{ steps.base.outputs.image }}" and cand_env["BASE_REF"] == "${{ steps.base.outputs.ref }}"
    assert '--prod-image-ref "$BASE_REF"' in cand  # 镜像 ID 之外, 记录里留下可读的标签
    paths = _step("kb-sync", "public", "路径一致性断言")["run"]
    assert "paths-check" in paths and "compose.public.yml" in paths and "--private-compose-file deploy/container/compose.yml" in paths
    base = _step("kb-sync", "public", "选基线镜像")["run"]
    # 公开容器镜像优先; stamp 一律由私有线上镜像去读 (候选基线镜像在配对之前不挂数据根)
    assert 'baseline-image --data-root "$DATA_ROOT" --via-image "$PROD_IMAGE" --images "$PUBLIC_IMAGE" "$PROD_IMAGE"' in base
    assert "docker inspect --type container sdtm-rag-public-api" in base
    # 选出来之后按镜像 ID 交给下一步 (标签在这期间被改指 / 被删也不会换成别的镜像, 不会触发拉取)
    assert base.index('BASE=$(') < base.index("BASE_ID=$(docker image inspect -f '{{.Id}}' \"$BASE\")")
    assert '{ echo "image=$BASE_ID"; echo "ref=$BASE"; } >> "$GITHUB_OUTPUT"' in base and 'echo "image=$BASE"' not in base
    # 人工指定基线: 只经环境变量进脚本 (不拼进命令); 只认本仓镜像仓库里按 commit 打标签、且已在本机的镜像;
    # 只认这一个 (守卫照旧, 不回落到自动选)
    assert _step("kb-sync", "public", "选基线镜像")["env"]["MANUAL_BASE"] == "${{ inputs.public_baseline_image }}"
    assert "${{" not in base
    assert 'baseline-image --data-root "$DATA_ROOT" --via-image "$PROD_IMAGE" --images "$MANUAL_BASE")' in base
    m = re.search(r'\[\[ "\$MANUAL_BASE" =~ (\S+) \]\]', base)
    repo = PUB["services"]["api"]["image"].split(":${", 1)[0]
    assert m and m.group(1) == "^" + re.escape(repo).replace("/", "/").replace("\\-", "-") + ":[0-9a-f]{40}$", m and m.group(1)
    pat = re.compile(m.group(1))
    assert pat.search(f"{repo}:{'a' * 40}") and not pat.search(f"evil.example/x:{'a' * 40}")
    assert not pat.search(f"{repo}:latest") and not pat.search(f"{repo}:{'a' * 40}\nextra")
    assert base.index("=~") < base.index('docker image inspect "$MANUAL_BASE"') < base.index('--images "$MANUAL_BASE"')
    assert "public_baseline_image" in WF["kb-sync"][True]["workflow_dispatch"]["inputs"]
    assert "public_baseline_image" not in _runs("kb-sync", "private") and "MANUAL_BASE" not in _runs("kb-sync", "private")
    assert "key-check" in _step("kb-sync", "public", "检查公开站的 embedding key")["run"]
    # 私有腿不带 kb-only (私有 chroma 里本来就有 study 集合)
    assert "--kb-only" not in _runs("kb-sync", "private")


def test_kb_sync_public_leg_failures_are_red_not_warnings():
    """公开腿的 key 失效、基线选不出、闸不过、集合违规都必须让 job 变红, 不能被降级成告警或吞掉。"""
    for wf in WF.values():
        for job in wf["jobs"].values():
            assert "continue-on-error" not in job
            assert all("continue-on-error" not in s for s in job["steps"])
    for s in _job("kb-sync", "public")["steps"]:
        run = s.get("run", "")
        if s.get("name", "").startswith("删除候选镜像"):
            continue
        assert "::warning::" not in run and "|| true" not in run.replace("2>inspect.err || true", ""), s.get("name")
        assert not re.search(r"kbsync\.py[^\n]*\|\|", run), s.get("name")  # kbsync 的失败不接 ||
    base = _step("kb-sync", "public", "选基线镜像")["run"]
    assert base.count("|| true") == 1
    assert "docker inspect --type container sdtm-rag-public-api" in base.split("|| true")[0].splitlines()[-1]
    # 那个 || true 只为了接住「容器不存在」; 别的 docker 错误紧接着就让步骤失败
    after = base.split("|| true", 1)[1]
    assert "grep -Eqi 'no such (container|object)' inspect.err" in after and "exit 1" in after.split("fi", 1)[0]
    # 整个仓库的 workflow 里, 表达式 ${{ }} 都不直接出现在 run 脚本里的用户输入位置 (inputs.* 只经 env)
    for wf in WF.values():
        for job in wf["jobs"].values():
            assert not [s.get("name") for s in job["steps"] if "${{ inputs." in s.get("run", "")]


def test_kb_sync_legs_share_the_ref_and_fingerprint_steps_verbatim():
    for sid in ("ref", "kb"):
        a, b = _step("kb-sync", "private", sid), _step("kb-sync", "public", sid)
        assert a == b and len(a["run"]) > 200, sid
    a, b = _step("kb-sync", "private", "构建候选镜像"), _step("kb-sync", "public", "构建候选镜像")
    assert a == b and "docker build" in a["run"]  # 每条腿都 build: 第二次命中缓存, 不复用上次运行留下的镜像
    # 每条腿删的是自己建的那个标签 (标签 = KB 指纹前 12 位), 两条腿的写法相同; 不再有「留给另一条腿」的条件
    a, b = _step("kb-sync", "private", "删除候选镜像"), _step("kb-sync", "public", "删除候选镜像")
    assert a == b and a["run"] == 'docker rmi "sdtm-rag-kbcand:${FP:0:12}" || true'
    assert a["env"] == {"FP": "${{ steps.kb.outputs.fp }}"} and "vars." not in a["if"]
    build = _step("kb-sync", "private", "构建候选镜像")
    assert 'sdtm-rag-kbcand:${FP:0:12}' in build["run"] and build["env"] == a["env"]  # 建的和删的是同一个标签


def test_user_supplied_refs_and_tags_are_matched_as_whole_strings():
    """`grep -x` 逐行匹配: 多行输入里有一行合法就放行。本次改到的校验一律用 bash 的整串匹配。"""
    for job in ("private", "public"):
        run = _step("kb-sync", job, "ref")["run"]
        m = re.search(r'\[\[ "\$REF" =~ (\S+) \]\]', run)
        assert m and 'printf \'%s\' "$REF" | grep' not in run, job
        pat = re.compile(m.group(1))
        good = ["kb-2026.11.28", "kb-2026.11.28.2", "a" * 40]
        bad = ["kb-2026.11.28\nx=1", "x\nkb-2026.11.28", "main", "a" * 39, "kb-2026.11.28; rm -rf /", ""]
        assert all(pat.search(g) for g in good) and not any(pat.search(b) for b in bad)
    pre = _step("sdtm-rag", "deploy_public", "pre")["run"]
    m = re.search(r'\[\[ "\$TAG" =~ (\S+) \]\]', pre)
    assert m and "grep -Eqx" not in pre
    pat = re.compile(m.group(1))
    assert pat.search("0" * 40) and not pat.search("0" * 40 + "\ntag=x") and not pat.search("x\n" + "0" * 40)
    assert pre.index("=~") < pre.index("docker pull")


def test_no_expression_is_interpolated_into_any_run_script():
    """`${{ }}` 在 runner 把脚本交给 bash 之前就被替换成文本: 出现在 run 里的任何表达式都是把一段字符串拼进命令。
    两个 workflow 的所有 job 都不允许; 表达式先进 env, 脚本里只引用普通变量。"""
    n = 0
    for name, wf in WF.items():
        for job, spec in wf["jobs"].items():
            for s in spec["steps"]:
                n += 1
                assert "${{" not in s.get("run", ""), (name, job, s.get("name"))
    assert n >= 30


def _run_step(step: dict, env: dict[str, str], tmp_path, interpolate: dict[str, str] | None = None):
    """像 runner 那样执行一个步骤的 run 脚本 (bash -e -o pipefail), 返回 (退出码, 写进 GITHUB_OUTPUT 的各行, 标准输出)。
    interpolate: 旧写法里残留的 `${{ x }}` 在执行前按文本替换 (runner 就是这么做的)。"""
    script = step["run"]
    for k, v in (interpolate or {}).items():
        script = script.replace("${{ " + k + " }}", v)
    out = tmp_path / "github_output"
    out.write_text("")
    r = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script], capture_output=True,
                       text=True, env={"PATH": os.environ["PATH"], "GITHUB_OUTPUT": str(out), **env})
    return r.returncode, out.read_text().splitlines(), r.stdout


SHA = "ab" * 20
GOOD_TAG = "0123456789abcdef0123456789abcdef01234567"


@pytest.mark.skipif(shutil.which("bash") is None, reason="本机没有 bash")
@pytest.mark.parametrize("label,value", [
    ("多行: 第一行合法", GOOD_TAG + "\ntag=evil"),
    ("多行: 第二行合法", "x\n" + GOOD_TAG),
    ("多行: 两行都合法", GOOD_TAG + "\n" + "f" * 40),
    ("结尾换行", GOOD_TAG + "\n"),
    ("开头换行", "\n" + GOOD_TAG),
    ("前导空格", " " + GOOD_TAG),
    ("结尾空格", GOOD_TAG + " "),
    ("结尾制表符", GOOD_TAG + "\t"),
    ("回车结尾", GOOD_TAG + "\r"),
    ("大写", GOOD_TAG.upper()),
    ("混合大小写", "A" + GOOD_TAG[1:]),
    ("39 位", GOOD_TAG[:39]),
    ("41 位", GOOD_TAG + "0"),
    ("7 位短号", GOOD_TAG[:7]),
    ("非十六进制", "g" * 40),
    ("分支名", "main"),
    ("带命令替换", "$(id)" + GOOD_TAG[5:]),
    ("带引号与分号", GOOD_TAG[:30] + '";id;"'),
    ("只有空白", "   "),
])
def test_deploy_tag_input_is_rejected_unless_it_is_exactly_a_commit_sha(tmp_path, label, value):
    """私有部署 job 的「确定要部署的标签」: 这些输入都必须被拒, 并且什么都不写进 GITHUB_OUTPUT (后面的步骤拿不到 tag)。"""
    rc, outputs, stdout = _run_step(_step("sdtm-rag", "deploy", "tag"), {"INPUT_TAG": value, "SHA": SHA}, tmp_path)
    assert rc == 1 and outputs == [], (label, rc, outputs)
    assert "标签必须是 40 位小写 commit SHA" in stdout and "部署标签" not in stdout


@pytest.mark.skipif(shutil.which("bash") is None, reason="本机没有 bash")
@pytest.mark.parametrize("label,value,want", [
    ("合法的 40 位提交号 (回滚)", GOOD_TAG, GOOD_TAG),
    ("空值 (push 或手动留空)", "", SHA),
])
def test_deploy_tag_step_keeps_its_behaviour_for_legitimate_input(tmp_path, label, value, want):
    """只做加固: 合法输入下, 新写法与改之前 (基点 9a8ad43 的写法) 的退出码、GITHUB_OUTPUT、打印的内容逐项相同。"""
    old = {"run": OLD_TAG_STEP_RUN}
    new = _step("sdtm-rag", "deploy", "tag")
    got_old = _run_step(old, {"INPUT_TAG": value}, tmp_path, interpolate={"gitea.sha": SHA})
    got_new = _run_step(new, {"INPUT_TAG": value, "SHA": SHA}, tmp_path)
    assert got_new == got_old == (0, [f"tag={want}"], f"部署标签：{want}\n"), (label, got_old, got_new)


# 改之前的写法 (git show 9a8ad43:.gitea/workflows/sdtm-rag.yml 里该步骤的 run), 留作对照
OLD_TAG_STEP_RUN = """TAG="$INPUT_TAG"
[ -n "$TAG" ] || TAG="${{ gitea.sha }}"
printf '%s' "$TAG" | grep -Eqx '[0-9a-f]{40}' || { echo "标签必须是 40 位小写 commit SHA"; exit 1; }
echo "tag=$TAG" >> "$GITHUB_OUTPUT"
echo "部署标签：$TAG"
"""


@pytest.mark.skipif(shutil.which("bash") is None, reason="本机没有 bash")
def test_old_tag_check_really_was_bypassable_by_multiline_input(tmp_path):
    """对照组: 同样的多行输入, 改之前的写法会放行, 并把多出来的行写进 GITHUB_OUTPUT —— 证明上面的拒绝来自新写法。"""
    rc, outputs, _ = _run_step({"run": OLD_TAG_STEP_RUN}, {"INPUT_TAG": GOOD_TAG + "\ntag=evil"}, tmp_path,
                               interpolate={"gitea.sha": SHA})
    assert rc == 0 and outputs == [f"tag={GOOD_TAG}", "tag=evil"]


def test_private_deploy_job_uses_the_tag_only_through_env():
    """内联的 ${{ steps.tag.outputs.tag }} 都换成了 env 里的 TAG: 用到 tag 的每个步骤, env 里都是同一个表达式。"""
    uses = [s for s in _job("sdtm-rag", "deploy")["steps"] if re.search(r'\$TAG\b|\$\{TAG', s.get("run", ""))
            and s.get("id") != "tag"]
    assert len(uses) >= 5, [s.get("name") for s in uses]
    for s in uses:
        assert s["env"]["TAG"] == "${{ steps.tag.outputs.tag }}", s.get("name")
    names = {s["name"] for s in uses}
    assert {"构建并推送", "部署", "KB 数据对齐检查", "失败时退回换过的 chroma/meta"} <= names
    tag = _step("sdtm-rag", "deploy", "tag")
    assert tag["env"] == {"INPUT_TAG": "${{ inputs.tag }}", "SHA": "${{ gitea.sha }}"}
    assert '[[ "$TAG" =~ ^[0-9a-f]{40}$ ]]' in tag["run"] and "grep" not in tag["run"]
    for job in ("deploy", "deploy_public"):
        login = _step("sdtm-rag", job, "登录镜像仓库")
        assert login["env"]["ACTOR"] == "${{ gitea.actor }}" and '-u "$ACTOR"' in login["run"]


def _base_workflow(name: str) -> dict:
    """基点 9a8ad43 的 workflow 原文, 冻在 fixture 里: CI 的 checkout 深度是 1, 取不到基点提交。
    取得到基点的地方 (本机) 顺带核对 fixture 与 `git show` 逐字相同。"""
    text = (ROOT / "tests/fixtures/workflows" / f"base_9a8ad43_{name}.yml").read_text()
    r = subprocess.run(["git", "show", f"9a8ad43:.gitea/workflows/{name}.yml"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode == 0:
        assert r.stdout == text, "fixture 与基点提交里的 workflow 不一致"
    return yaml.safe_load(text)


def test_private_deploy_job_changed_only_where_intended():
    """私有部署 job 相对基点只改了: 登录步骤的用户名经 env; 标签步骤的校验; 两个步骤里内联的 tag。其余步骤逐字未变。"""
    base = _base_workflow("sdtm-rag")
    old = {s.get("name", "checkout"): s for s in base["jobs"]["deploy"]["steps"]}
    new = {s.get("name", "checkout"): s for s in _job("sdtm-rag", "deploy")["steps"]}
    assert list(old) == list(new)  # 步骤与顺序不变
    changed = sorted(n for n in old if old[n] != new[n])
    assert changed == sorted(["登录镜像仓库", "确定要部署的标签", "构建并推送", "部署"])
    for n in ("构建并推送", "部署"):
        o, nw = old[n], new[n]
        assert o.get("if") == nw.get("if") and o.get("id") == nw.get("id")
        assert o["run"].replace("${{ steps.tag.outputs.tag }}", "$TAG") == nw["run"]  # 脚本只是把内联表达式换成变量
        assert {k: v for k, v in nw["env"].items() if k != "TAG"} == o.get("env", {})
    o, nw = old["登录镜像仓库"], new["登录镜像仓库"]
    assert o["run"].replace("${{ gitea.actor }}", "$ACTOR") == nw["run"]
    assert {k: old["确定要部署的标签"][k] for k in ("id", "name")} == {k: new["确定要部署的标签"][k] for k in ("id", "name")}
    for key in ("if", "runs-on", "timeout-minutes", "outputs"):
        assert base["jobs"]["deploy"].get(key) == _job("sdtm-rag", "deploy").get(key)
    assert base["env"] == WF["sdtm-rag"]["env"] and base[True] == WF["sdtm-rag"][True]  # workflow 级 env 与触发条件不变


def test_kb_sync_private_leg_changed_only_where_intended():
    """kb-sync 私有腿相对基点 (单 job `kbsync`) 只改了「确定 KB ref」的格式校验; 其余步骤逐字未变, 数据根 / env 文件的值不变。"""
    base = _base_workflow("kb-sync")
    old = {s.get("name", "checkout"): s for s in base["jobs"]["kbsync"]["steps"]}
    new = {s.get("name", "checkout"): s for s in _job("kb-sync", "private")["steps"]}
    assert list(old) == list(new)
    assert sorted(n for n in old if old[n] != new[n]) == ["确定 KB ref"]
    assert {k: base["env"][k] for k in ("DATA_ROOT", "ENV_FILE")} == _job("kb-sync", "private")["env"]
    assert base["env"]["KB_REPO"] == WF["kb-sync"]["env"]["KB_REPO"]
    for key in ("if", "runs-on", "timeout-minutes"):
        assert base["jobs"]["kbsync"].get(key) == _job("kb-sync", "private").get(key)
    assert base[True]["schedule"] == WF["kb-sync"][True]["schedule"] and base["concurrency"] == WF["kb-sync"]["concurrency"]


def _bash_accepts(condition: str, var: str, value: str) -> bool:
    """把 workflow 里的 `[[ "$VAR" =~ … ]]` 原样交给 bash 执行 (值经环境变量传入, 与 workflow 相同)。"""
    r = subprocess.run(["bash", "-c", condition], env={**os.environ, var: value}, capture_output=True, text=True)
    assert r.returncode in (0, 1), r.stderr  # 2 = 正则本身写错
    return r.returncode == 0


@pytest.mark.skipif(shutil.which("bash") is None, reason="本机没有 bash")
def test_format_checks_behave_in_real_bash():
    """上一条用 Python 的 re 模拟; 这一条让 bash 自己跑同一行 (两者对换行、锚点的处理不完全相同)。"""
    cases = {
        ("kb-sync", "private", "ref", "REF"): (
            ["kb-2026.11.28", "kb-2026.11.28.2", "a" * 40],
            ["kb-2026.11.28\nx=1", "x\nkb-2026.11.28", "kb-2026.11.28\n", "main", "a" * 39, "a" * 41, "kb-2026.11.28;id", "", " kb-2026.11.28"]),
        ("kb-sync", "public", "ref", "REF"): (["kb-2026.11.28", "b" * 40], ["kb-2026.11.28\nref=x", "kb-2026.11.28\n", ""]),
        ("sdtm-rag", "deploy_public", "pre", "TAG"): (
            ["0" * 40], ["0" * 40 + "\ntag=x", "x\n" + "0" * 40, "0" * 40 + "\n", "0" * 39, "A" * 40, "", "0" * 40 + " "]),
        ("kb-sync", "public", "选基线镜像", "PUBLIC_IMAGE"): (
            ["192.168.100.58/bojiang/sdtm-rag:" + "d" * 40],
            ["docker.io/library/python:3.14", "192.168.100.58/bojiang/sdtm-rag:latest", "sdtm-rag-kbcand:abcdef012345"]),
        ("kb-sync", "public", "选基线镜像", "BASE_ID"): (
            ["sha256:" + "e" * 64], ["192.168.100.58/bojiang/sdtm-rag:" + "c" * 40, "sha256:" + "e" * 63, "", "sha256:" + "e" * 64 + "\nx"]),
        ("kb-sync", "public", "选基线镜像", "MANUAL_BASE"): (
            ["192.168.100.58/bojiang/sdtm-rag:" + "c" * 40],
            ["evil.example/x:" + "c" * 40, "192.168.100.58/bojiang/sdtm-rag:latest", "192.168.100.58/bojiang/sdtm-rag:" + "c" * 40 + "\nx",
             "192x168x100x58/bojiang/sdtm-rag:" + "c" * 40, "x192.168.100.58/bojiang/sdtm-rag:" + "c" * 40, ""]),
    }
    n = 0
    for (wf, job, step, var), (good, bad) in cases.items():
        m = re.search(r'\[\[ "\$' + var + r'" =~ \S+ \]\]', _step(wf, job, step)["run"])
        assert m, (wf, job, step)
        for v in good:
            assert _bash_accepts(m.group(0), var, v), (wf, job, step, v)
        for v in bad:
            assert not _bash_accepts(m.group(0), var, v), (wf, job, step, v)
            n += 1
    assert n >= 20


# ── sdtm-rag: deploy_public 的结构 ────────────────────────────────────────
def test_deploy_public_wires_the_orchestrator_with_public_paths_only():
    job = _job("sdtm-rag", "deploy_public")
    assert job["needs"] == "deploy"
    env = job["env"]
    assert [env["PUBLIC_DATA_ROOT"], env["PUBLIC_ENV_FILE"]] == _mount_sources(PUB["services"]["api"])
    assert env["COMPOSE_PUBLIC"] == "deploy/container/compose.public.yml"
    assert env["COMPOSE_PRIVATE"] == "deploy/container/compose.yml"
    assert env["PUBLIC_DATA_ROOT"] != WF["sdtm-rag"]["env"]["DATA_ROOT"]
    runs = _runs("sdtm-rag", "deploy_public")
    # 私有数据根不进公开 job 的任何命令; 私有 compose 只作为 --private-compose-file 被解析
    assert "$DATA_ROOT" not in runs.replace("$PUBLIC_DATA_ROOT", "") and WF["sdtm-rag"]["env"]["DATA_ROOT"] not in runs
    assert runs.count("$COMPOSE_PRIVATE") == 1 and '--private-compose-file "$COMPOSE_PRIVATE"' in runs
    assert "compose.yml" not in runs.replace("compose.public.yml", "")
    main = _step("sdtm-rag", "deploy_public", "临时容器验收，通过后才换正式容器")["run"]
    for flag in ('--data-root "$PUBLIC_DATA_ROOT"', '--env-file "$PUBLIC_ENV_FILE"', '--compose-file "$COMPOSE_PUBLIC"',
                 '--image "$IMAGE:$TAG"', '--tag "$TAG"', "--touched-file .public_touched"):
        assert flag in main, flag
    assert "deploy-public" in main and "||" not in main and "::warning::" not in main


def test_deploy_public_network_prechecks_are_wired():
    """三道只读预检 (协调方 2026-11-28 裁定): 镜像下限在 workflow 的预检步骤里; 子网与隔离核对在编排里, 这里只看接线。"""
    job = _job("sdtm-rag", "deploy_public")
    env = job["env"]
    main = _step("sdtm-rag", "deploy_public", "临时容器验收，通过后才换正式容器")["run"]
    for flag in ('--isolation-probe "$ISOLATION_PROBE"', '--isolation-lan "$ISOLATION_LAN"', '--isolation-egress "$ISOLATION_EGRESS"'):
        assert flag in main, flag
    assert env["ISOLATION_PROBE"] == "deploy/public-net/isolation_probe.py"  # 隧道那条线的文件 (本分支上还没有)
    target = re.compile(r"[A-Za-z0-9.\-]+:\d{1,5}")
    lan, egress = env["ISOLATION_LAN"].split(), env["ISOLATION_EGRESS"].split()
    assert len(lan) >= 5 and len(egress) >= 2 and all(target.fullmatch(t) for t in lan + egress)
    assert "10.201.8.1:22" in lan and "192.168.100.58:443" in lan  # 公开网桥的网关、局域网里的镜像仓库
    assert all(re.match(r"(10|172|192)\.", t) for t in lan), "内网目标应当都是私有地址"
    assert "api.anthropic.com:443" in egress and not any(re.match(r"\d", t) for t in egress)
    # 镜像下限: 照抄隧道那条线给的写法 (脚本经标准输入送进待部署的镜像; 退出码与输出两样都核对), 排在拉镜像之后
    pre = _step("sdtm-rag", "deploy_public", "pre")["run"]
    assert IMAGE_FLOOR in pre and pre.index("docker pull") < pre.index(IMAGE_FLOOR)


IMAGE_FLOOR = ('out=$(docker run --rm -i --entrypoint python "$IMG" - < deploy/public-net/image_floor_check.py) \\\n'
               '  && [ "$out" = "image-floor: ok" ] || { echo "镜像下限预检未通过"; exit 1; }')


@pytest.mark.skipif(shutil.which("bash") is None, reason="本机没有 bash")
@pytest.mark.parametrize("script_present,docker_rc,docker_out,passes", [
    (True, 0, "image-floor: ok", True),
    (True, 0, "", False),                       # 漏了 -i / 脚本没送进去: python 读到空输入, 退出码 0 但没有那行输出
    (True, 0, "image-floor: ok\nextra", False),  # 输出必须恰好是那一行
    (True, 0, "ok", False),
    (True, 1, "image-floor: ok", False),        # 输出对但退出码非 0
    (True, 1, "", False),                       # 隧道这一步之前的镜像: 脚本以非零退出
    (False, 0, "image-floor: ok", False),       # 脚本文件不存在 (隧道那条线没合进来): 重定向失败, 不放行
])
def test_image_floor_precheck_line_behaves_in_real_bash(tmp_path, script_present, docker_rc, docker_out, passes):
    """把 workflow 里那两行原样交给 bash (与 Gitea 相同的 -e -o pipefail), docker 换成一个按设定回话的替身。
    替身同时核对: 带了 -i、标准输入就是那个脚本、镜像是 $IMG。"""
    (tmp_path / "bin").mkdir()
    fake = tmp_path / "bin" / "docker"
    fake.write_text("#!/bin/sh\n"
                    'case " $* " in *" -i "*) ;; *) echo "no -i" >&2; exit 97;; esac\n'
                    'case " $* " in *" img:1 - "*) ;; *) echo "wrong image/args" >&2; exit 98;; esac\n'
                    '[ "$(cat)" = "FLOOR-SCRIPT" ] || { echo "stdin is not the script" >&2; exit 99; }\n'
                    f"printf '%s' \"$FAKE_OUT\"\nexit {docker_rc}\n")
    fake.chmod(0o755)
    if script_present:
        (tmp_path / "deploy/public-net").mkdir(parents=True)
        (tmp_path / "deploy/public-net/image_floor_check.py").write_text("FLOOR-SCRIPT")
    r = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", IMAGE_FLOOR.replace("\\\n", "") + "\necho REACHED-NEXT-LINE"],
                       cwd=tmp_path, capture_output=True, text=True,
                       env={"PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}", "IMG": "img:1", "FAKE_OUT": docker_out})
    assert r.returncode in (0, 1), r.stderr
    assert ("REACHED-NEXT-LINE" in r.stdout) is passes, (r.returncode, r.stdout, r.stderr)
    assert (r.returncode == 0) is passes
    if not passes:
        assert "镜像下限预检未通过" in r.stdout


def test_deploy_public_has_no_start_or_data_commands_outside_the_orchestrator():
    """workflow 里不直接起停公开容器, 也不直接换 / 退数据: 这些只发生在有单测的编排里。"""
    runs = _runs("sdtm-rag", "deploy_public")
    for banned in ("docker compose", "docker start", "docker restart", " up -d", "restore", "deploy-swap", " swap ", "finish"):
        assert banned not in runs, banned
    cmds = re.findall(r"kbsync\.py\s+([a-z-]+)", runs)
    assert cmds == ["deploy-public", "public-abort", "accept-down"]


def test_deploy_public_abort_runs_before_cleanup_and_shares_the_marker():
    names = [s.get("name", "checkout") for s in _job("sdtm-rag", "deploy_public")["steps"]]
    order = ["公开实例预检", "临时容器验收", "中断时停掉已被动过的公开实例", "清理临时容器与验收副本", "退出镜像仓库"]
    idx = [next(i for i, n in enumerate(names) if n.startswith(o)) for o in order]
    assert idx == sorted(idx)  # 兜底停机在清理之前: 清理失败不会引发停机
    abort = _step("sdtm-rag", "deploy_public", "中断时停掉已被动过的公开实例")
    assert "public-abort" in abort["run"] and "--touched-file .public_touched" in abort["run"]
    assert "cancelled()" in abort["if"] and "failure()" in abort["if"]
    clean = _step("sdtm-rag", "deploy_public", "清理临时容器与验收副本")
    assert "accept-down" in clean["run"] and clean["if"].startswith("always()") and "||" not in clean["run"]


def test_private_deploy_job_does_not_touch_public_paths():
    runs = _runs("sdtm-rag", "deploy")
    for needle in ("sdtm-rag-public", "compose.public.yml", "PUBLIC_", "deploy-public", "--kb-only"):
        assert needle not in runs, needle
