# 进度看板 (sdtm-rag)

> **本仓唯一进度状态源**, 只写当前状态; 历史看 git log 与 `docs/evidence/checkpoints/`。
> 2026-11-25 拆仓时从 monorepo `sdtm-pedia/docs/PROGRESS.md` 迁入 Phase 7 行与「近 30 天」段; 原文已原样移到
> `docs/history/progress_phase7_snapshot_2026-11-25.md` (只读历史)。

## 状态总览

| 线 | 状态 | 当前活动 | 下一步 / 阻塞 |
|----|------|----------|---------------|
| **拆仓 (10_split_and_public)** | 🟢 进行中 | P1 1.1–1.8 + R1/R2 完成, 1.9 实现+审查完成, P2 完成; P3 3.1–3.3 完成, p3 + 4 个修复分支 (seam 日期 / CT 解析 / PC chunker / defhome R4) 已合 main 上线私有站 (2b24d53, 2026-11-27, 公开实例未开; 线上数据未换); 两仓公开 (GitHub `hakupao/sdtm-pedia` / `hakupao/sdtm-rag`, 本仓双推 Gitea+GitHub); 生产跑本仓镜像; KB = submodule `vendor/sdtm-pedia` | 等 pedia 新 kb-* tag (kb-sync 基线已含三项修复; 1.9 正例 + 本地「KB 更新」) → 3.4 隧道; 详见 `.work/10_split_and_public/_progress.json` |
| **Phase 7** RAG + KG | 🟢 唯一活跃线 | 生产 = mini Lima 虚拟机里的容器 (2026-11-04 起, 取代 launchd); Neo4j 探索层 2026-11-07 退役; 联邦路由 + study 直查默认开 | 见 `deploy/README.md`、CLAUDE.md Key Paths 各 checkpoint; 历史状态见快照 |

**图例**: ✅ 完成 · 🟢 进行中 · ⏸ 待启动 · 🔴 阻塞

→ 2026-11-25 前的 milestone 时间线: `docs/history/progress_phase7_snapshot_2026-11-25.md`
