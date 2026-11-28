import sys
sys.path.insert(0, ".")
from tests import test_workflow_conditions as t
groups = {}
for wf, job, step, ctx, status, want in t.TABLE:
    node = t._job(wf, job) if step is None else t._step(wf, job, step)
    key = (wf, job, "(job)" if step is None else node.get("name"))
    groups.setdefault(key, (t._expr(wf, job, step), []))[1].append((ctx, status, want))
ST = {"success": "成功", "failure": "失败", "cancelled": "取消"}
def short(ctx):
    out = []
    for k, v in ctx.items():
        k = k.replace("steps.", "").replace(".outputs.", ".").replace("gitea.", "").replace("vars.SDTM_RAG_PUBLIC_DEPLOY", "公开变量").replace("inputs.", "输入.")
        v = {True: "true", False: "false"}.get(v, v) if isinstance(v, bool) else v
        v = v.replace("refs/heads/", "") if isinstance(v, str) else v
        if isinstance(v, str) and len(v) == 40: v = v[:4] + "…"
        out.append(f"{k}={v}")
    return ", ".join(out) or "—"
print("# `if` 条件真值表 (由 tests/test_workflow_conditions.py 的 TABLE 生成, 该表每一行都是一个通过的测试)\n")
print("「之前的结果」= step 级指前面步骤的综合结果, job 级指 needs 里的 job。没写状态函数的表达式隐含 `success() &&`。\n")
cur = None
for (wf, job, step), (expr, rows) in groups.items():
    if (wf, job) != cur:
        cur = (wf, job); print(f"\n## {wf}.yml / job `{job}`\n")
    print(f"**{step}** — `{expr}`\n")
    print("| 输入 | 之前的结果 | 执行? |\n|---|---|---|")
    for ctx, status, want in rows:
        print(f"| {short(ctx)} | {ST[status]} | {'是' if want else '否'} |")
    print()
