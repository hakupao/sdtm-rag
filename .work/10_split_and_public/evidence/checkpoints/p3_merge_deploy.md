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

## 第二段: fix-ct-cell-format → fix-pc-examples-chunker → defhome-r4 — PASS

- HEAD 核对: `bfbf547` / `b7d2664` / `3fb0837` 均符合。合并 (都 `--no-ff` + `[skip ci]`, 无冲突): `8fe4174` = merge fix-ct-cell-format; `3f86710` = merge fix-pc-examples-chunker; `2b24d53` = merge defhome-r4。
- 本机 @`2b24d53`: `pytest -m "not slow"` 2995 passed / 0 failed / 2 skipped; 合并引入 16 个文件 oidscan CLEAN。
- push: Gitea + GitHub 均 `88a16c6..2b24d53`; 推后 80 s 无新任务。
- 只构建: run 202 / task 331 (tag 空, deploy=false) success; 部署类步骤全 skipped; `deploy_public` (job 440) skipped。
- 测试端口 (`p3_merge_seg2_testport_2b24d53.sh`; NEW=2b24d53 vs 线上 0673fee): 两边 freshness OK f863e45445a6; CDISC 140=140, avg 0.9917=0.9917, 逐题 0 差; study 51=51, avg 0.875=0.875, 逐题 0 差; `/api/ask` ok; `/api/info` 键集相同, 无 tier/providers/quota。
- validator 冒烟 (私有档, 现成 fixture `tests/fixtures/sp5_real_sample/` 的 CDISC pilot dm/ae/cm/ex/lb, 非 DM 附 dm_file, `semantic_review=false`): 5 个域新旧 `/api/validate` 响应除 `generated_at` 外全字段相同。`/api/validate-study` 未做 (需 study 数据, 不临时造)。旧 KB 的 CT 单元格是纯 `Cnnnnn`, 新旧解析结果本应一致, 与此相符。
- 部署: run 203 / task 332 (tag=2b24d53ec7047ed37070b9e53f54995f091fcf76, deploy=true) success。部署前线上 0673fee…; KB 对齐 `decision=same` (f863e45445a6), 不换数据; api/ui = 2b24d53; 健康检查 200。`deploy_public` (job 442) skipped (仓库变量为空); `sdtm-rag-public-api` 仍 Exited。
- 部署后: `check_index_freshness` OK; LAN `/api/health` 200; `/api/info` 形状不变, index_fresh=True, chunk_count=4329。
- 数据未换 (`p3_merge_seg2_snapshot.sh`, 不含 mtime, 部署前后 diff 只有 api/ui 两行镜像): stamp 不变; `meta.yaml` sha256 `abfa9815…` 与 `implicit_relations.json` `c3dbe292…` 不变; chroma 目录 inode/birth 不变, 122 个文件路径集合指纹不变, 非 sqlite/非 .bin 文件内容指纹不变; 数据根无 cand/prev/journal。
- **代码新规则 + 线上 meta 旧规则**: 线上服务读 `/app/data/meta/meta.yaml` (数据根挂载), `model_defhome` 59 条, 无 DOMAIN/POOLID/USUBJID (= 旧规则产物); 仓库 tracked `data/meta/meta.yaml` 为 62 条 (R4 多 3 条), 只供 CI/测试。运行时没有 meta 与代码规则的一致性校验 (meta_store 只检必需键), freshness 只比 chroma 与 KB 指纹, 均 OK; 服务行为 = 旧 meta 的归属 (与部署前相同), 无报错。新规则的 meta 要等下次 kb-sync 候选 (由含 R4 的 main 构建) 换入后才上线。
- 回滚: dispatch tag=0673fee4b8df87b71c67e6da0bc4573bb12e4fea, deploy=true (同指纹, 不换数据)。
- kb-sync 基线镜像 (= 线上镜像) 现已含 CT 解析、PC chunker、R4 三项修复。

复跑: 同第一段, 脚本换成 `p3_merge_seg2_testport_2b24d53.sh` / `p3_merge_seg2_snapshot.sh` (经 `ssh bojiang.local … limactl shell deploy -- bash -s` 喂入)。
