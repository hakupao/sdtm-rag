# P3 + 修复分支合并上线私有站 (2026-11-27, 分两段)

主人 2026-11-27 同意「按顺序把这些分支合进 rag main 并 push」(原话:「可以，全部按顺序合」), 上限 4 次部署; 协调方合为两段, 每段部署一次。先例 `p2_deploy.md`。

## 第一段: p3 + fix-p2-seam-date — PASS

- 准备: p3 上 `69e1519` (PC chunker 报告入库 `pc_examples_chunker_report.md`, 清单 v4 改相对路径) [skip ci]。
- 合并 (都 `--no-ff` + `[skip ci]`): `262d4d3` = merge p3 (`5011588`+`69e1519`); `0673fee` = merge `hakupao/fix-p2-seam-date` (`05fc7b5`)。顺带 push 本地既有 `647fb9c` (文档)。
- 本机 @`0673fee`: `pytest -m "not slow"` 2956 passed / 0 failed / 2 skipped; 合并引入的 34 个文件 `scripts/oidscan_evidence.py` CLEAN。
- push: Gitea + GitHub 均 `47a4b0d..0673fee`; 推后 80 s 无新任务 (未自动触发)。
- 只构建: run 199 / task 328 (tag 空, deploy=false) success; CI 测试 2897 passed / 61 skipped; 部署类步骤全 skipped; `deploy_public` (job 435) skipped。镜像 digest `sha256:077d4643…`。
- 测试端口 (`p3_merge_seg1_testport_0673fee.sh`, 1.9 脚本同法 + `/api/info` 键集比对; NEW=0673fee vs 线上 099c2c9, 各用 chroma 副本, 生产 .env):
  两边 freshness OK f863e45445a6; CDISC 140=140, avg 0.9917=0.9917, 逐题 0 差 (非满分 q126/q38, 同既往); study 51=51, avg 0.875=0.875, 逐题 0 差; 新镜像 `/api/ask` ok; `/api/info` 新旧键集相同, 无 tier/providers/quota。
- 部署: run 200 / task 329 (tag=0673fee4b8df87b71c67e6da0bc4573bb12e4fea, deploy=true) success。部署前线上 099c2c9…; KB 对齐 `decision=same` (f863e45445a6), 不换数据; api/ui = 0673fee; 健康检查 200。`deploy_public` (job 437) skipped (仓库/用户级变量均为空 → `SDTM_RAG_PUBLIC_DEPLOY` 未开); `sdtm-rag-public-api` 仍 Exited (未启动)。
- 部署后: `check_index_freshness` OK; LAN `curl http://192.168.100.150:8000/api/health` 200; `/api/info` 无 tier/providers/quota, web_search/federation 在, index_fresh=True, chunk_count=4329。
- 数据未换: chroma 目录 inode/birth 不变 (2026-11-25), stamp (kb_fingerprint f863e454…, total_chunks 4329) 不变, meta 2 个文件 sha256 汇总不变 (`56b5e309…`), 数据根无 cand/prev/journal; 集合 sdtm_kb_v1 4329 / study 两集合条数与部署前一致。注: 我含 mtime 的 chroma 列表指纹变了 —— 容器启动时 chroma 自身改写 `chroma.sqlite3` 与 2 个 HNSW 段文件 (9 个文件 mtime=部署时刻), 非换数据; 下次快照改用不含 mtime 的方式。
- 回滚: dispatch tag=099c2c930ec869e254b2e9052c3d4a6a85d6d539, deploy=true。

复跑:
```sh
# 测试端口 (在 VM 内执行)
cat .work/10_split_and_public/evidence/checkpoints/p3_merge_seg1_testport_0673fee.sh | ssh bojiang.local 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- bash -s'
# 派发 (凭据取自 git credential)
curl -u bojiang:$P -H 'Content-Type: application/json' -X POST https://git.bojiang.org/api/v1/repos/bojiang/sdtm-rag/actions/workflows/sdtm-rag.yml/dispatches \
  -d '{"ref":"main","inputs":{"tag":"<空或40位SHA>","deploy":"false|true","force_data_mismatch":"false"}}'
curl -u bojiang:$P https://git.bojiang.org/api/v1/repos/bojiang/sdtm-rag/actions/runs/<run>/jobs
```

## 第二段: fix-ct-cell-format (bfbf547) → fix-pc-examples-chunker (b7d2664) → defhome-r4 (3fb0837) — 待协调方指示
