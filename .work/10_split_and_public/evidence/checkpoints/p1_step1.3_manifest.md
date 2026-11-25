# P1 step 1.3 — B 仓 (sdtm-rag) 路径映射 manifest

> 状态: **已完成** (2026-11-25). 源 = monorepo `main` @ edce7f3; 产物 = `/Volumes/DevSSD/Project/sdtm-rag` (main @ f9c4d01, 771 commits). 仅路径, 无 study OID.

## 方法
- `git clone --no-local` → scratch; 删 11 个 tag; `git filter-repo --refs main --filename-callback <显式字典>` (字典 = 下表规则作用于 `git log --all --name-only` 全部历史路径, 未命中 → 丢弃); `git remote remove origin`; `gc --prune=now --aggressive`; `mv` 到终路径 (无 remote, 仅 `refs/heads/main`).
- 改名闭包: `git log main -M --name-status` 全部 4898 个 R 记录中, 跨 B/A 边界的 0 个 (in 0 / out 0); 无 C(copy) 记录; 同 basename D+A 启发式扫描 0 命中 → 无需额外旧名.
- 冲突检查: 1230 源路径中 308 个目标有 2 个源, 全部为 `branches/07_rag_kg/X` ↔ `sdtm-rag/X | milestones/07_rag_kg/X` 跨时代对; 逐 commit 检查两时代目录从不共存. HEAD 冲突 0; `sdtm-rag/docs/` 只有 `cypher_cookbook.md`, 与 `docs/{design,history,worklog,superpowers}` 无重叠.

## 映射规则

| source | target | HEAD files | historical paths |
|---|---|---|---|
| `branches/07_rag_kg/sdtm-rag/**` | `**` | 0 | 397 |
| `sdtm-rag/**` | `**` | 701 | 703 |
| `branches/07_rag_kg/**` (非 sdtm-rag) | `docs/history/07_rag_kg/**` | 0 | 31 |
| `milestones/07_rag_kg/**` | `docs/history/07_rag_kg/**` | 32 | 32 |
| `.work/05_rag_kg/**` | `docs/history/05_rag_kg/**` | 1 | 1 |
| `.gitea/**` | `.gitea/**` | 1 | 1 |
| `.githooks/**` | `.githooks/**` | 2 | 2 |
| `docs/superpowers/**` (B 子集, 见下) | 同路径 | 58 | 58 |
| `docs/DESIGN_RAG_KG.md` | `docs/design/DESIGN_RAG_KG.md` | 1 | 1 |
| `.work/meta/study_rag_handoff_2026-08-04.md` | `docs/history/handoffs/` 同名 | 1 | 1 |
| `.work/meta/verified_spotcheck_handoff_2026-09-04.md` | `docs/history/handoffs/` 同名 | 1 | 1 |
| `.work/meta/workflow_events_handoff_2026-08-26.md` | `docs/history/handoffs/` 同名 | 1 | 1 |
| `.work/meta/worklog/phase_07_rag_kg.md` | `docs/worklog/phase_07_rag_kg.md` | 1 | 1 |

合计: HEAD 800 文件, 历史源路径 1230.

## docs/superpowers 划分
- **留 A (不进 B, 5)**: `plans/2026-04-18-phase6.5-claude-v2-expansion.md`, `plans/2026-04-27-sdtm-release-website.md`, `specs/2026-04-18-phase6.5-claude-v2-expansion-design.md`, `specs/2026-04-27-sdtm-release-website-design.md`, `specs/2026-04-29-website-motion-design.md`
- **双方都留**: `plans/2026-07-21-repo-restructure-v3.md`, `specs/2026-07-21-repo-restructure-v3-design.md`
- **进 B (58)**: 其余全部 = 29 plans (28 RAG + restructure-v3) + 27 specs (26 RAG + restructure-v3) + 2 RETROSPECTIVE (`2026-07-24-sp7-kg-viewer-ux-RETROSPECTIVE.md`, `2026-08-07-crowding-gold-RETROSPECTIVE.md`). 历史上无已删除的 superpowers 文件.

## 未进 B (留 A, 1.6 处理)
- `.work/meta/worklog/phase_07_release.md` (Release 线, 非 RAG)
- monorepo 根 `.gitignore` / CLAUDE.md / MANIFEST / PROGRESS / AGENT_GUIDE / retrospective.md (共享元文档, 拆分属 1.6)

## 验证摘要 (复跑命令见 executor 报告)
- V1 HEAD blob 逐一致: mapped 800 / B HEAD 800 / identical 800 / missing 0 / differ 0 / extra 0
- V2 771 commits, 最早 2026-04-16; `--follow` 3 样本均追到首个 A 提交
- V3 历史路径命中 `data/study/|data/chroma|\.env$|dogfood_failures` = 0
- V4 size-pack 8.72 MiB (.git 9.1M)
- V5 pytest `-m "not slow"`: 2584 passed / 2 skipped / 3 failed / 16 errors; 19 项全部为 data/study 符号链接造成 (STUDY_DATA_ROOT 未 resolve 的路径比较 17; `git check-ignore` 拒绝穿越符号链接 rc=128 2); 移动路径导致的失败 0. 2584+19 = 2603 = 基线 passed 数
- 旁注: chroma PersistentClient 打开 override 目录会刷新 `chroma.sqlite3` 与 study_st01/study_st01_docs 的 hnsw 文件 mtime; 集合计数不变 (4329/959/125)
- 旁注 (1.5 用): `.gitignore` 的 `data/study/` 尾斜杠不忽略符号链接形式的 data/study
