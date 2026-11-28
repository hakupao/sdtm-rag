# 进度看板 (sdtm-rag)

> **本仓唯一进度状态源**, 只写当前状态; 历史看 git log 与 `docs/evidence/checkpoints/`。
> 2026-11-25 拆仓时从 monorepo `sdtm-pedia/docs/PROGRESS.md` 迁入 Phase 7 行与「近 30 天」段; 原文已原样移到
> `docs/history/progress_phase7_snapshot_2026-11-25.md` (只读历史)。

## 状态总览

| 线 | 状态 | 当前活动 | 下一步 / 阻塞 |
|----|------|----------|---------------|
| **拆仓 (10_split_and_public)** | 🟢 进行中 | P1 1.1–1.9 + R1/R2 完成 (1.9 私有正例 = 「KB 更新」`kb-2026.11.28` 已上线私有站, 2026-11-28, kb-sync 过闸后换入); P2 完成; P3 3.1–3.3 完成; 3.4 / 3.4b 的配置与代码、公开站的 KB 更新流程 2026-11-28 已合入 main 并重新部署私有站 (线上镜像 613f048, 行为不变; 公开站没有上线: 隧道没接, 公开网络没重建, 隔离规则没装, 部署开关关着, 公开容器停止, 公开 chroma 仍是旧 KB); 两仓公开 (GitHub `hakupao/sdtm-pedia` / `hakupao/sdtm-rag`, 本仓双推 Gitea+GitHub); 生产跑本仓镜像; KB = submodule `vendor/sdtm-pedia` | 先处理 `todo_later` 里「开公开部署开关之前必须处理」的各项; 然后公开站上线演练 (每一步都要主人另行同意): 重建公开网络 + 装隔离规则 → 开部署开关 → 公开候选 → 第一次公开部署 → 隧道 (`sdtm.bojiang.org`, 先只放行主人); 详见 `.work/10_split_and_public/_progress.json` |
| **Phase 7** RAG + KG | 🟢 唯一活跃线 | 生产 = mini Lima 虚拟机里的容器 (2026-11-04 起, 取代 launchd); Neo4j 探索层 2026-11-07 退役; 联邦路由 + study 直查默认开 | 见 `deploy/README.md`、CLAUDE.md Key Paths 各 checkpoint; 历史状态见快照 |

**图例**: ✅ 完成 · 🟢 进行中 · ⏸ 待启动 · 🔴 阻塞

→ 2026-11-25 前的 milestone 时间线: `docs/history/progress_phase7_snapshot_2026-11-25.md`
