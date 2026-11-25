# KB tag 升级 + 重组后镜像测试端口验证 (2026-11-25)

- submodule `vendor/sdtm-pedia` ebf0c8a → `kb-2026.11.25` (7819398), 提交 cb5fd06 [skip ci]。KB 零差: `git -C ../sdtm-pedia diff --stat ebf0c8a kb-2026.11.25 -- knowledge_base` 为空; `kb_fingerprint` 前后 f863e454… 一致 → 不重灌。
- 本机闸: `.venv/bin/python -m pytest -m "not slow" -q -o addopts=""` 2610 passed / 0 failed; CDISC 140q retrieval-only vs `p0_runs/cdisc140.json` 逐题 0 差。
- 生产 freshness (mini VM): `limactl shell deploy -- sudo docker exec sdtm-rag-api python -m scripts.check_index_freshness` → OK f863e454 (stamp 含 kb_fingerprint, 1.9 前置满足)。
- build-only: Gitea run 244 (workflow_dispatch tag="" deploy=false) success; 生产未动 (ee41a3c); VM 盘 40%。
- 测试端口 (容器 `sdtm-rag-kbtest`, 镜像 cb5fd06, chroma 副本挂 /cand, data:ro, 不发布端口): healthy; s1_vi_section_map entries=171; chunks=4329; freshness OK。
  - CDISC 140q: recall/hits/misses 0 差, top5 0 差 (vs P0 基线)
  - study 48q: recall 0.875, 未满分 6 题 id 集合与 `data/study/st01/eval/runs/split10_p0/study48.json` 相同
  - `/api/ask` "What are the valid values for AESEV?" → 1846 字, sources 为 KB 相对路径
  - 测试容器与 chroma 副本已删。
- 命令模板同 `p1_step1.5_deploy_switch.md` (测试端口先验)。
- 正式部署 (用户确认): Gitea run 245 (tag=cb5fd06 deploy=true) success; 线上 sdtm-rag-api/ui = cb5fd06, api healthy, freshness OK, entries=171 chunks=4329, 局域网 `curl http://192.168.100.150:8000/api/health` 200。回滚: workflow_dispatch tag=ee41a3c… deploy=true。
