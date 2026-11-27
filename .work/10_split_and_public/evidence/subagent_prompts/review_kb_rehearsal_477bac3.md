# 审查派单: kb_rehearsal_477bac3.md + kb_upgrade_bundle_checklist.md v6 (规则 D)

审查者 subagent_type: `oh-my-claudecode:critic` (写作者是主会话 Claude)。以下是原样发出的 prompt。

---

你是独立审查者 (规则 D: 写作者与审查者不同 agent 类型)。请审查一份「KB 入库预演」报告和它更新的升级清单, 用中文回复。你的任务是**找错**, 不是确认。

## 背景 (只给事实, 结论请自己核)
- 仓库: `/Volumes/DevSSD/Project/sdtm-rag` (分支 main, HEAD `efefb7a`, 工作区有未提交的 `.work/` 文档改动, 就是被审对象)。先读仓根 `CLAUDE.md` 和 `docs/RULES.md` (规则 5 / 6)。
- 上游知识库仓 `/Volumes/DevSSD/Project/sdtm-pedia` 的 `d46f8af` 是定稿 KB。本次预演把它入库到临时 chroma, 跑 CDISC 140 题 retrieval 闸, 并在新 KB 下跑 pytest、重算清单数字、核对 gold。
- 被审文件:
  1. `.work/10_split_and_public/evidence/checkpoints/kb_rehearsal_477bac3.md` (预演报告)
  2. `.work/10_split_and_public/evidence/checkpoints/kb_upgrade_bundle_checklist.md` 的「v6 更新」一节 (文件末尾)
  3. `.work/10_split_and_public/_progress.json` 最后一条 log 与 `next_step`
  4. `.work/10_split_and_public/evidence/probes/kb_rehearsal_{meta_stats,gold_chunk_check,gold_variants,apply_anchors,heading_vs_gold}.py` (本轮新增的只读脚本)
  5. `.work/10_split_and_public/evidence/checkpoints/kb_rehearsal_477bac3_runs/` (运行产物)
- 上一轮预演与清单的前文 (同目录 `kb_rehearsal_bf33bab.md`、清单 v1-v5) 是背景, 不是本次审查对象, 但 v6 若与前文裁定矛盾要指出。
- pedia 侧说明 (只读): `/Volumes/DevSSD/Project/sdtm-pedia/.work/10_tier_b_repair/evidence/checkpoints/t4_downstream_notes.md` 末节, 以及 `.../work/t4/kb_heading_diff_kb-2026.11.25_HEAD.txt`、`kb_heading_diff_00a2e93_HEAD.txt`。
- 写作者留下的临时现场 (可直接复用, 零费用): `S=/private/tmp/claude-501/-Volumes-DevSSD-Project-sdtm-rag/8a8d99ca-2885-4316-8e2a-36852b13bd5e/scratchpad/rh2`
  - `$S/kb/knowledge_base` = pedia `d46f8af` 展开; `$S/kb_pre/knowledge_base` = pedia `00a2e93` 展开
  - `$S/base` (旧 KB + 开发 chroma 副本)、`$S/cand` (新 KB 入库后的 chroma 与 meta)、`$S/ctl` (对照组 pytest 树)、`$S/ci` (新 KB pytest 树, 测试原样)、`$S/ci2` (套了锚点的副本)
  - `$S/out/` 下有全部评测 JSON、日志、题集变体

## 请独立核实 (每条给出你自己跑的命令和输出要点)
1. **闸的结论**: 用 `deploy/kbsync/kbsync.py` 的 `regressions` / `_load_recall` / `_load_avg` 和 `gate()` 里的五项判据, 对 `$S/out/baseline.json` 与 `$S/out/candidate.json` 重算。报告说的回退题、满分题数、avg、「余量为零」是否成立? 入库到仓库的 `kb_rehearsal_477bac3_runs/*.json` 与 `$S/out/` 的是否同一份结果?
2. **候选是否真的跑在新 KB 上**: stamp 指纹、KB 指纹 (`kbsync.py fingerprint --kb-root`)、KB 树哈希 (`GIT_OPTIONAL_LOCKS=0 git -C /Volumes/DevSSD/Project/sdtm-pedia rev-parse d46f8af:knowledge_base`)。
3. **回退题的归类**: 报告把唯一的回退归为 gold 漂移。请自己看该题在基线 / 候选里的命中与未命中、新旧 KB 的相应章节, 判断归类对不对, 有没有被漏掉的第二个原因。
4. **pytest 分类**: 读 `$S/out/pytest_ctl.log`、`pytest_new.log`、`pytest_new_anchored.log`。失败个数与分类是否如报告所写? 有没有不属于「随 KB 升级才改的锚点」的失败被归错? `kb_rehearsal_apply_anchors.py` 打的替换是否把某条断言改弱了 (规则 6 的成因 A / B / D)? 你可以另开一份副本自己验证, 但不要改 `$S/ci`、`$S/ci2`。
5. **清单 v6 的数字**: 抽查至少 10 个数字, 用 `probes/` 里的脚本或你自己的办法重算 (chunk 数、各类数、`model_defhome` 条数与增删改清单、图计数、ct_codes、覆盖率、超长 chunk、单元格计数等)。指出任何对不上的。
6. **gold**:
   - 节级 gold 全量重算和 pedia 两份标题清单的交叉核对: 是否真的只有报告列的那些失效? 请至少用一种与写作者不同的办法复核。
   - fact 级核对的结论;
   - q39 加 `domains/FA/assumptions.md` 后「能召回」的证据是否充分 (看 `$S/out/cand_q39only_r1.json`、`_r2.json`、`cand_goldnext_r1.json`);
   - q117 / q120 裁定的新 fact 在 `$S/kb/knowledge_base` 里是否逐字存在;
   - 报告对 q76 给出的两种做法: 对 kb-sync 机制的描述 (基线 / 候选各用哪份镜像、题集、KB) 是否与 `deploy/kbsync/kbsync.py` 和 `.gitea/workflows/` 的实际行为一致? 「做法 B 0 回退」的实测是否成立 (`$S/out/base_q76dual.json`、`cand_q76dual.json`、`test_set_v3_q76dual.yml`)? 有没有第三种更好的做法或被忽略的风险?
7. **可复跑性与规则**: 报告里的命令是否能照着复跑 (挑 2-3 条零费用的实际跑一下)? 有没有写了「实测」却没给命令的? 长效文档里有没有引行号 (RULES 不建议)? 有没有与任务范围冲突的动作 (见下)。
8. **遗漏**: 对照下面的任务要求, 有没有该做没做、或做了没写清楚的。

任务要求 (写作者收到的): 钉版本取 KB 并记录指纹与树哈希; 隔离入库 + 140 题闸逐题对比; 新 KB 下 pytest 全部失败逐个归类, 清单外的失败要查到根因; 重算清单全部数字 (计数锚点、PC 6 条期望、R4 映射 75 条、Variable / ModelChapter 等); gold: 用 pedia 两份标题清单重新对照节级 gold, fact 级静态核对重做, q39 实测, q117 / q120 新 fact 逐字核对; 产物是 `.work/` 下文档, 本地提交不 push。不许改 `server/ scripts/ deploy/ .gitea/ webchat/ eval/ tests/ data/`, 不许写 pedia 仓, 不 push / 部署 / 升级 submodule。

## 约束
- **只读**: 不改仓库里任何文件 (包括被审文件), 不写 pedia 仓 (对它的 git 命令一律带 `GIT_OPTIONAL_LOCKS=0`), 不动 `data/`。需要落盘的东西写到 `$S/../review_477bac3/` (自己建)。
- 费用: 静态核对与 pytest 零费用。如果要重跑 140 题评测 (每趟只有 140 个问句的 embedding, 费用可忽略), 最多 2 趟, 且只能在 `$S/base` 或 `$S/cand` 里用 `--output` 写到你自己的目录; **不要重跑 ingest**。
- 在代码树里跑命令时用 `/Volumes/DevSSD/Project/sdtm-rag/.venv/bin/python`, 并设置 `SDTM_RAG_KB_ROOT_OVERRIDE`。zsh 不会对变量自动拆词, 命令参数逐个写。
- 不要 git commit / push。

## 输出格式
1. 结论: PASS / PASS-with-fixes / FAIL。
2. 已核实成立的要点 (每条附你跑的命令)。
3. 问题表: 编号、严重度 (MAJOR / MINOR)、问题、证据、建议改法。
4. 你没有核实、只是读过的部分, 单独列出。
