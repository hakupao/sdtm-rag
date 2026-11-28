# 进度看板 (sdtm-rag)

> **本仓唯一进度状态源**, 只写当前状态; 历史看 git log 与 `docs/evidence/checkpoints/`。
> 2026-11-25 拆仓时从 monorepo `sdtm-pedia/docs/PROGRESS.md` 迁入 Phase 7 行与「近 30 天」段; 原文已原样移到
> `docs/history/progress_phase7_snapshot_2026-11-25.md` (只读历史)。

## 状态总览

| 线 | 状态 | 当前活动 | 下一步 / 阻塞 |
|----|------|----------|---------------|
| **拆仓 (10_split_and_public)** | 🟢 进行中 | P1 1.1–1.9 + R1/R2 完成 (1.9 私有正例 = 「KB 更新」`kb-2026.11.28` 已上线私有站, 2026-11-28); P2 完成; P3 3.1–3.3 完成; 3.4 / 3.4b 的配置与代码、公开站的 KB 更新流程在 main; 公开站上线演练 2026-11-28 做到第 5 步: 公开网络 `10.201.8.0/24` + 隔离规则 + 每分钟巡检 (`.work/10_split_and_public/evidence/checkpoints/p3_stageB_network_isolation.md`) → **公开部署开关 `SDTM_RAG_PUBLIC_DEPLOY` 已打开**, kb-sync 公开腿建出过闸候选 (`p3_stageC_public_candidate.md`) → 第一次公开部署 (run id 219) 在「临时容器验收」失败 (`p3_stageDE_first_public_deploy.md`) → 把公开档走服务端 key 的模型的价格固定进代码, 启动自检不再依赖联网 (`public_price_pin.md`、`public_price_pin_ext.md`), 合入 main → 只构建 (run id 220) → 测试端口验证 (两条检索闸逐题 0 差, 私有档行为与成本估算不变) → 正式部署 (run id 221): **私有站换成镜像 `66cb55d`** (数据不变), **公开站第一次部署做成** (隔离核对 → 没有网络的临时容器验收 → Anthropic key 探测 → 换入候选 → 新镜像) → 人工启动公开容器并做完启动后的核对、5a、5b (`p3_stageDE_second_attempt.md`); **现在: 公开容器运行中 (`healthy`, 镜像 `66cb55d`, 公开线上 chroma = `kb-2026.11.28` / 4333 条), 没有对外入口** (没有发布端口、没有连接器、没有 token、没有隧道); 私有站 = 镜像 `66cb55d` + 指纹 `477bac3ce565` / 4333 条; 两仓公开 (GitHub `hakupao/sdtm-pedia` / `hakupao/sdtm-rag`, 本仓双推 Gitea+GitHub); 生产跑本仓镜像; KB = submodule `vendor/sdtm-pedia` | ⚠ **部署开关开着**: 头提交不带 `[skip ci]`、又命中部署路径过滤的 main push, 以及手动派发 `sdtm-rag` 时没有取消勾选 `deploy`, 都会在私有部署之后带上公开部署 (只构建不会) —— 只改文档 / 测试的提交必须带 `[skip ci]`; 公开容器在运行时的那条部署路径 (临时验收 → key 探测 → 换新镜像 → 复验) 还没有在真机上走过, 下一次带部署的运行就是第一次; 私有站要回滚到 `613f048` 时先关开关; kb-sync 没有定时触发, KB 更新只靠手动派发; 下一步 (每一步都要主人另行同意): 隧道 (`sdtm.bojiang.org`, 演练方案第 6 步起: 连接器 → 先只放行主人 → 隧道验收 → 放开); 公开站还没有发过真答题 (Anthropic key 只验了有效性, 没有验额度); 公开容器现在会在虚拟机 / docker 重启后自己起来, 重启后要立刻重跑隔离探测 (开机时规则先于容器装入的顺序还没有实测); 不想继续时 `docker stop sdtm-rag-public-api` 并关变量 (办法见 `p3_stageDE_second_attempt.md`「回滚办法」); 详见 `.work/10_split_and_public/_progress.json` |
| **Phase 7** RAG + KG | 🟢 唯一活跃线 | 生产 = mini Lima 虚拟机里的容器 (2026-11-04 起, 取代 launchd); Neo4j 探索层 2026-11-07 退役; 联邦路由 + study 直查默认开 | 见 `deploy/README.md`、CLAUDE.md Key Paths 各 checkpoint; 历史状态见快照 |

**图例**: ✅ 完成 · 🟢 进行中 · ⏸ 待启动 · 🔴 阻塞

→ 2026-11-25 前的 milestone 时间线: `docs/history/progress_phase7_snapshot_2026-11-25.md`
