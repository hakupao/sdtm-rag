# 进度看板 (sdtm-rag)

> **本仓唯一进度状态源**, 只写当前状态; 历史看 git log 与 `evidence/checkpoints/`。
> 2026-11-25 拆仓时从 monorepo `sdtm-pedia/docs/PROGRESS.md` 迁入 Phase 7 行与「近 30 天」段; 原文已原样移到
> `docs/history/progress_phase7_snapshot_2026-11-25.md` (只读历史)。

## 状态总览

| 线 | 状态 | 当前活动 | 下一步 / 阻塞 |
|----|------|----------|---------------|
| **拆仓 (10_split_and_public)** | 🟢 进行中 | 本仓已从 monorepo 抽出 (1.3) + 自立 (1.5a/1.5b); 1.4 KB = submodule `vendor/sdtm-pedia` (钉 sdtm-pedia `ebf0c8a`, shallow) | 开 Gitea Actions → 切部署来源; 记录 `.work/10_split_and_public/` |
| **Phase 7** RAG + KG | 🟢 唯一活跃线 | 生产 = mini Lima 虚拟机里的容器 (2026-11-04 起, 取代 launchd); Neo4j 探索层 2026-11-07 退役; 联邦路由 + study 直查默认开 | 见 `deploy/README.md`、CLAUDE.md Key Paths 各 checkpoint; 历史状态见快照 |

**图例**: ✅ 完成 · 🟢 进行中 · ⏸ 待启动 · 🔴 阻塞

→ 2026-11-25 前的 milestone 时间线: `docs/history/progress_phase7_snapshot_2026-11-25.md`
