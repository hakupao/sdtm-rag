# P1 step 1.1 — 去绝对路径 (2026-11-25)

writer: executor (opus) → prompt `subagent_prompts/step_1.1_executor.md`; reviewer: code-reviewer (opus) → `step_1.1_reviewer.md`. **Verdict: PASS-with-fixes**。

## 闸 (主控独立复跑)
- `pytest scripts/tests/test_source_relative.py -o addopts=""` → 16 passed
- 逐题对比 (recall/hits/misses) vs P0 基线: CDISC 现库 0 差 / 迁移副本+KB 挪位 0 差; study 现库 ×2 / 迁移副本 0 差 (脚本见本会话; study 结果在 gitignored `data/study/st01/eval/runs/split10_p1/`)
- writer: 全量 `-m "not slow"` 2603 passed / 2 skipped; reviewer 全量 2606 passed / 2 skipped
- reviewer 变异: `_source_where` 改纯 abs → 11 失败, 改纯 rel → 23 失败 (双兼容被测试钉住)

## 审查处置
| # | 级 | 处置 |
|---|---|---|
| M1 | MED | `sdtm-rag/docker-compose.yml` 旧变量名未修 → **延至 1.5** (该遗留文件在 1.5 删除) |
| M2 | MED | 迁移后不能只回滚镜像 → 写入 deploy/README + **1.2 runbook 必须同时恢复 chroma 副本与旧镜像并演练** |
| L1 | LOW | README 加"先停服务" ✅ |
| L2 | LOW | 脚本 docstring 加"中断即重跑" ✅ |
| L3 | LOW | refuse 时打印符号链接提示 ✅ |
| L4 | LOW | README 加旧 .env 手动改名 ✅ |
| L5 | LOW | main.py 过时注释 ✅ |

## 附注
- Chroma 加载 study 集合时自身会改写 HNSW `data_level0.bin` 与 sqlite 锁行 → 回滚只认 P0 备份 (`/Volumes/DevSSD/backups/sdtm-pedia-pre-split-2026-11/`), 不认"未动过的线上目录"。
- 迁移副本: scratchpad `chroma_migrated` (临时, 1.2 生产迁移在 mini 上现跑, 不搬副本)。
- 留给拆仓阶段: `oidscan_evidence.py` GIT_ROOT/knowledge_base (拆后失效为更多假阳性, fail-safe)、_smoke_batch_b / eval 3 个脚本的 KB 路径。
