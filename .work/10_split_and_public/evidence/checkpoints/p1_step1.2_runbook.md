# P1 step 1.2 生产切换 runbook (待用户确认后执行)

前提: 本地 main 已含 33ac656 (双兼容代码, 新旧 chroma 都能起)。所有 `docker compose` 命令在 mini VM 上、compose 文件所在仓库目录执行;
`C="docker compose -f sdtm-rag/deploy/container/compose.yml"`; 数据宿主路径 `/Volumes/DevSSD/deploy-data/sdtm-rag/data`。

## ① 上线兼容版代码 (不动 chroma)
1. 推 main 到 gitea → Actions 自动构建+部署 (路径过滤命中 `sdtm-rag/server/**`)
2. 验证: Actions 健康检查绿; `docker logs sdtm-rag-api | grep s1_vi_section_map` → `entries=171`
3. 记下新镜像 tag = 新提交完整 SHA; 旧镜像 tag = `f9d6370...` (完整 SHA 见 `git rev-parse f9d6370`)

## ② 迁移生产 chroma
4. 备份: `cp -a /Volumes/DevSSD/deploy-data/sdtm-rag/data/chroma /Volumes/DevSSD/deploy-data/sdtm-rag/chroma_pre_rel_20261125` (备份放 data 挂载**之外**)
5. 停 api (Chroma 不支持双进程写): `$C stop api`
6. dry run: `IMAGE_TAG=<新SHA> $C run --rm --no-deps api python -m scripts.migrate_source_relative /Volumes/DevSSD/Project/sdtm-pedia/sdtm-rag/data/chroma --kb-root /Volumes/DevSSD/Project/sdtm-pedia/knowledge_base`
   - 期望: `sdtm_kb_v1 rewrite=4329 outside_root=0`; study 两集合 rewrite=0。不符 → 停, 归档 failures/, 不 apply
7. 同命令加 `--apply`; 再跑一次 dry run 期望 rewrite=0 (幂等)

## ③ 起服验证
8. `IMAGE_TAG=<新SHA> $C up -d api`; 健康检查 `curl -s localhost:8000/api/health`
9. `docker logs sdtm-rag-api | grep s1_vi_section_map` → `entries=171`
10. 浏览器问 1 道 CT 码题 (如 "What are the valid values for AESEV?") + 1 道 ST01 题, 引用正常

## 回滚 (M2: 迁移后的 chroma 配旧镜像会起不来 → 必须两样一起恢复)
- `$C stop api` → `rm -rf .../data/chroma && cp -a .../chroma_pre_rel_20261125 .../data/chroma` → Actions `workflow_dispatch` tag=<旧SHA> (或 `IMAGE_TAG=<旧SHA> $C up -d api`)
- 演练: 在 ③ 通过后, 用**新镜像 + 备份 chroma** 起一次 (验证兼容版吃旧库), 再切回迁移后库; 不实际回到旧镜像 (旧镜像+旧库 = 现状已证)

---
## v2 修订 (2026-11-25, 执行时) — 按 lan-services 规约改为"测试端口先验"
发现: 服务在 mini (192.168.100.150) 的 Lima 虚拟机 `deploy` 里 (`export LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- sudo docker ...`), 不是 .58 (.58 = Gitea+Caddy)。lan-services 约定: **切换线上服务前先在虚拟机里用测试端口验证 + 备好回滚**; 不读 .env 值; mini 上不放项目源码。

1. 代码上线走常规路径: 推 gitea main → CI 构建+部署 (CI 自带健康检查; 双兼容已本地验证) — 不动 chroma
2. VM 内: `cp -a data/chroma → deploy-data/sdtm-rag/chroma_rel_candidate` (data 挂载之外), 在**候选副本**上跑迁移 (新镜像 `docker run --rm`)
3. 测试容器 (新镜像, 测试端口, 只在 VM 内) 挂候选 chroma (`SDTM_RAG_CHROMA_DIR_OVERRIDE`) → 健康 + S1 entries=171 + 容器内跑 CDISC 140q retrieval-only, 逐题对比 P0 基线
4. 通过后换目录: `docker stop sdtm-rag-api` → `mv data/chroma ../chroma_pre_rel_20261125` → `mv ../chroma_rel_candidate data/chroma` → `docker start sdtm-rag-api` (停机数秒)
5. 回滚 = 反向换目录 (新镜像吃新旧两种库, **不必回滚镜像**); 旧镜像回滚只在同时换回 chroma_pre_rel 时才允许 (M2)
