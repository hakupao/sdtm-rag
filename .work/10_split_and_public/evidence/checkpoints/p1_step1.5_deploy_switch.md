# P1 step 1.4/1.5 — B 仓接管生产部署 (2026-11-25) — PASS

- B 提交: 1.4 submodule `vendor/sdtm-pedia` @ ebf0c8a (KB tree 62dfce3 = monorepo HEAD:knowledge_base); 1.5b 审查修复 (APP_DIR 回滚; build-only 开关; 健康检查失败自动退回; ⚑ 默认 data/; -rs; oidscan rc=2 提示; crossref 测试双形; kb_freshness 源路径检查); attempt 1/2 失败归档 (`failures/step_1.4_attempt_1.md`, `step_1.5_ci_attempt_{1,2}.md`)
- CI: run 152/153 FAIL (pdf fixture 顺序) → run 154 FAIL (VM 磁盘满, `docker builder prune -af` 释放 8.19GB) → run 155 build-only **PASS** (测试 2550 passed / 61 skipped; 镜像 `ee41a3c…` 2.36GB)
- 测试端口 (容器 `sdtm-rag-p15test`, 新镜像 /app 布局, chroma 副本, data:ro): S1 entries=171; federation 正常; CDISC 140q 与 P0 基线 recall/hits/misses/top5 **0 差**; study 48q 0.875 未满分题集合相同; /api/ask 正常; /api/flag 200 (写到容器内 /tmp)
- 切换: `/opt/sdtm-rag/.env` → `.env.bak-20261125` 备份; 唯一旧路径键 `SDTM_RAG_DOGFOOD_LOG_OVERRIDE` 注释掉 (未打印值; 24 个有效键); dispatch tag=ee41a3c deploy=true → run 156 **success** (部署 + 健康检查); 线上 `sdtm-rag-api/ui = ee41a3c`, `chroma=/app/data/chroma kb=/app/vendor/sdtm-pedia/knowledge_base`, entries=171
- 生产冒烟: CDISC 题 1704 字 (sources 相对路径); ST01 题 auto→`both` (24 源中 16 张 study 卡), corpus=study → 23/23 study; LAN `http://192.168.100.150:8000/api/health` 200
- 1.6b-gitea: Gitea `bojiang/sdtm-pedia` 无分支保护/镜像; `--force-with-lease` c2d396b → **ebf0c8a**; 10 tag 与 GitHub 一致。monorepo 已 no_push。
- 回滚: Actions 手动 tag=20b8983… (旧镜像, APP_DIR 自动取旧 WorkingDir) + 还原 `.env.bak-20261125`
