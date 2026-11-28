# 代码审查: 公开腿实现 (kb-sync 两条腿 + 公开部署先用临时容器验收)

你是独立审查者 (只读, 不改任何文件, 不 push, 不连虚拟机)。仓库: 当前工作目录 (分支 `hakupao/public-kb-leg`, 基点 `9a8ad43`)。
用 `git diff 9a8ad43 -- .gitea deploy tests` 看全部改动 (工作区里可能还有未提交的收尾改动, 以工作区为准)。全程中文。

## 要审的东西
- `deploy/kbsync/kbsync.py` (只用标准库; 在 CI job 容器里运行, 文件系统子命令经 `--via` 在兄弟容器里执行)
- `.gitea/workflows/kb-sync.yml`、`.gitea/workflows/sdtm-rag.yml` (`deploy_public` job)
- `tests/test_kbsync.py`、`tests/test_kbsync_public.py`、`tests/test_kbsync_deploy_public.py`、`tests/test_workflow_conditions.py`、`tests/test_deploy_public_compose.py`
- `deploy/README.md` 的「KB 同步」一节

## 规格 (已裁定, 不要重新设计; 只判断实现是否符合、有没有缺陷)
- `.work/10_split_and_public/evidence/checkpoints/p3_public_kb_update_design.md` (v0.2 修订 + 文末裁定登记 D1–D8 为准)
- `.work/10_split_and_public/evidence/checkpoints/p3_step3.2_compose.md` 文末「M3 裁定」
- 2026-11-28 协调方补充裁定 (受托代裁): ① 正式容器部署前是停止的 (或不存在) → 临时验收通过后换入数据、用新镜像重建容器但**不启动**;
  ② 为换数据已停下正式容器后换入被拒或失败 → 保持停止; ③ kb-sync 公开腿的基线镜像必须与公开 chroma 配对 (镜像内 KB 指纹 == stamp),
  都不配对时明确失败, 手动派发时可用输入参数指定基线; ④ 临时验收里加一次不花钱的答题 key 有效性探测 (只列模型), key 不得出现在日志 / 命令行。
- 仓库规则: `CLAUDE.md`、`docs/RULES.md` 规则 5 / 6 (变异验证; 闸失效的成因 A / B1 / B2 / C / D)。

## 请重点看
1. 逻辑缺陷: `deploy_public` / `public_halt` / `swap_guard` / `accept_spec` / `accept_check` / `baseline_image` / `_probe` 的各分支,
   尤其异常路径 (docker 命令失败、via 抛 RuntimeError、输出解析不了) 会不会落到不该去的分支。
2. 私有腿有没有被无意改变行为 (私有 job 的步骤、`candidate` / `deploy_swap` 不带新参数时的行为)。
3. workflow: 表达式、步骤顺序、shell 片段 (bash -e 下的失败传播、引号、`$(...)` 失败时是否真的让步骤失败)。
4. 测试质量: 有没有恒真断言、数据没有分辨力 (规则 6 成因 D)、假 docker 与真实 docker / compose 行为可能不符而掩盖缺陷的地方。
   可以自己跑: `.venv/bin/python -m pytest tests/test_kbsync.py tests/test_kbsync_public.py tests/test_kbsync_deploy_public.py tests/test_workflow_conditions.py tests/test_deploy_public_compose.py -q -o addopts=""`
   变异脚本: `.work/10_split_and_public/evidence/checkpoints/p3_public_leg_mutations.py` (会临时改文件再还原; 如要跑请只跑这一个, 不要并发)。
5. README 与代码行为是否一致。

## 输出
结论 (PASS / PASS-with-fixes / FAIL) + 按严重度分级的问题清单 (CRITICAL / HIGH / MEDIUM / LOW), 每条给文件与函数名 (不要只给行号)、
触发条件、建议改法。没把握的写成疑问, 不要当成结论。
