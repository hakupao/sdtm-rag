# 进度看板 (sdtm-rag)

> **本仓唯一进度状态源**, 只写当前状态; 历史看 git log 与 `docs/evidence/checkpoints/`。
> 2026-11-25 拆仓时从 monorepo `sdtm-pedia/docs/PROGRESS.md` 迁入 Phase 7 行与「近 30 天」段; 原文已原样移到
> `docs/history/progress_phase7_snapshot_2026-11-25.md` (只读历史)。

## 状态总览

| 线 | 状态 | 当前活动 | 下一步 / 阻塞 |
|----|------|----------|---------------|
| **拆仓 (10_split_and_public)** | 🟢 进行中 | P1 1.1–1.9 + R1/R2 完成 (1.9 私有正例 = 「KB 更新」`kb-2026.11.28` 已上线私有站, 2026-11-28, kb-sync 过闸后换入); P2 完成; P3 3.1–3.3 完成; 3.4 / 3.4b 的配置与代码、公开站的 KB 更新流程 2026-11-28 已合入 main 并重新部署私有站 (线上镜像 613f048, 行为不变); 公开站上线演练的头一段 2026-11-28 做完: 虚拟机里公开网络已重建为固定网段 `10.201.8.0/24`, 隔离规则和每分钟巡检已装, 探测结论 PASS (`.work/10_split_and_public/evidence/checkpoints/p3_stageB_network_isolation.md`); 同日做完阶段 C: 修复分支 `hakupao/pre-switch-fixes` 已合入 main (不触发构建和部署), **公开部署开关 `SDTM_RAG_PUBLIC_DEPLOY` 已打开**, 手动派发一次 kb-sync, 公开腿建出候选并过闸 (138 / 138, avg 0.9917, 4333 条; `.work/10_split_and_public/evidence/checkpoints/p3_stageC_public_candidate.md`); 公开站仍没有上线: 公开容器已创建、从未启动, 隧道没接, 公开线上 chroma 仍是旧 KB (候选等第一次公开部署换入); 两仓公开 (GitHub `hakupao/sdtm-pedia` / `hakupao/sdtm-rag`, 本仓双推 Gitea+GitHub); 生产跑本仓镜像; KB = submodule `vendor/sdtm-pedia` | ⚠ **部署开关开着**: 头提交不带 `[skip ci]`、又命中部署路径过滤的 main push, 以及手动派发 `sdtm-rag` 时没有取消勾选 `deploy`, 都会在私有部署之后带上公开部署并换入公开候选 (只构建不会) —— 只改文档 / 测试的提交必须带 `[skip ci]`; kb-sync 的定时触发已去掉, KB 更新只靠手动派发; 公开站上线演练的后续各步 (每一步都要主人另行同意): 第一次公开部署 (换入候选, 容器保持停止) → 人工启动 → 隧道 (`sdtm.bojiang.org`, 先只放行主人); 不想继续时关变量 (办法见阶段 C 的 checkpoint「回退办法」); 虚拟机下次重启后要重跑隔离探测; 详见 `.work/10_split_and_public/_progress.json` |
| **Phase 7** RAG + KG | 🟢 唯一活跃线 | 生产 = mini Lima 虚拟机里的容器 (2026-11-04 起, 取代 launchd); Neo4j 探索层 2026-11-07 退役; 联邦路由 + study 直查默认开 | 见 `deploy/README.md`、CLAUDE.md Key Paths 各 checkpoint; 历史状态见快照 |

**图例**: ✅ 完成 · 🟢 进行中 · ⏸ 待启动 · 🔴 阻塞

→ 2026-11-25 前的 milestone 时间线: `docs/history/progress_phase7_snapshot_2026-11-25.md`
