# P1 step 1.2 生产切换 — PASS (2026-11-25)

执行位置: mini 192.168.100.150, Lima VM `deploy` (`export LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- ...`)。按 runbook v2 (测试端口先验)。

| 步 | 结果 |
|---|---|
| ① 推 gitea main 20b8983 → CI 部署 | 镜像 `sdtm-rag:20b8983022bea9bd7d7e4aee4137b04e0e503f11` healthy; 旧库 (绝对路径) 下 `s1_vi_section_map entries=171` |
| ② 候选副本 `deploy-data/sdtm-rag/chroma_rel_candidate` 迁移 | dry-run: sdtm_kb_v1 rewrite=4329 outside=0, study 两集合 0; --apply applied=4329 remaining_absolute=0; 复跑 rewrite=0 (幂等) |
| ③ 测试容器 `sdtm-rag-p12test` (不发布端口) 挂候选 | entries=171; CDISC 140q 与 P0 基线 **recall/hits/misses/top5 全 0 差** (`p1_runs/step1.2_prod_candidate_cdisc140.json`); study 48q recall 0.875, 未满分题 id 集合与基线相同 (结果留在容器内未带出, 含 OID) |
| ④ 换目录 | stop api → `data/chroma` → `chroma_pre_rel_20261125` → 候选 → `data/chroma` → start; healthy, entries=171; 测试容器已删 |
| ⑤ 冒烟 | `/api/ask` "What are the valid values for AESEV?" → 1872 字答案, sources 为 KB 相对路径 (`terminology/core/ae.md` 等) |

**回滚** (未触发): `docker stop sdtm-rag-api; mv data/chroma chroma_rel_used; mv chroma_pre_rel_20261125 data/chroma; docker start sdtm-rag-api` — 当前镜像兼容两种库, 不必动镜像。
**保留**: `deploy-data/sdtm-rag/chroma_pre_rel_20261125` (迁移前生产库, 规则 B 不删; P4 收尾时再定去留)。
