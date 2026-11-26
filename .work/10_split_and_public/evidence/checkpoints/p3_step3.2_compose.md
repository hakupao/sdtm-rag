# P3.2 公开实例 compose + workflow (2026-11-26, 分支 p3)

## 裁定 (主会话)

- **私有 `compose.yml` 不改**, 公开实例用独立 `deploy/container/compose.public.yml` (项目 `sdtm-rag-public`, 容器
  `sdtm-rag-public-api`, 只起 api)。私有渲染零差异 = 文件未动; workflow 私有 job 只加 `outputs.tag`。
  PLAN 原写"参数化 + workflow docker inspect 去硬编码": 改为分文件, 因为参数化要让私有路径走变量, 漏设即落回私有档/数据 (fail-open)。
- **失效安全**: 档位 `SDTM_RAG_INSTANCE=public` 写在 compose `environment:` (真实环境变量优先, `load_dotenv` 默认不覆盖);
  数据根 `/Volumes/DevSSD/deploy-data/sdtm-rag-public/data`、`.env` `/opt/sdtm-rag-public/.env` 写死, 不取变量;
  **不发布宿主端口** (审查 #7 后去掉原 `127.0.0.1:8010`; 冒烟用 docker exec)。另: lima.yaml 末尾 catch-all `ignore: true`, 非显式端口本来也不转发。
- **workflow `deploy_public` job**: `needs: deploy`, 仓库变量 `SDTM_RAG_PUBLIC_DEPLOY=true` 才跑 (默认关; 3.3 数据根建好后开)。
  预检 (只读): 镜像须能 `import server.instance` (拒 P2 前镜像, 含手动 tag 回滚) + WorkingDir=/app + 公开 chroma 指纹 `same`。
  验收: 容器 healthy → `/api/info.tier==public` → `/openapi.json` 404 → `check_index_freshness`。失败 → 停公开实例 (不自动退回旧镜像)。
- **未决**: 公开 chroma 的 KB 更新流程 (kb-sync 候选是私有数据副本, 含 study 集合, 不能直接用)。现在指纹不一致只告警并跳过 (公开实例不动, 审查 M4)。

## 验证 (复跑命令)

```bash
# 渲染 (VM, 只读)
cat deploy/container/compose.public.yml | ssh bojiang.local 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; \
  limactl shell deploy -- sh -c "cat > /tmp/p3pub.yml; IMAGE_TAG=abc docker compose -f /tmp/p3pub.yml config; docker compose -f /tmp/p3pub.yml config; rm /tmp/p3pub.yml"'
.venv/bin/python -m pytest tests/test_deploy_public_compose.py -q -o addopts=""
.venv/bin/python -m pytest -m "not slow" -q -o addopts=""
```

- 渲染 (首版, 当时含 8010 端口, 已删): ports `host_ip 127.0.0.1 published 8010`; environment `SDTM_RAG_INSTANCE: public`; 无 IMAGE_TAG → `required variable IMAGE_TAG is missing`。
- 首版变异 4/4 被抓 (端口去 127.0.0.1 / 档位改 private / 数据根改私有 / .env 改变量); 修后加变异 2/2 (守卫 `>1`→`>2` / 去 `cancelled()`)。
  ⚠ 变异复跑坑: 同秒同大小的 sed 改回会命中旧 `.pyc`, 须 `rm server/__pycache__/config.*.pyc`。
- 修后: 新测试 6 passed; 全量 pytest 2956 passed, 2 skipped; 真机制复现 (`SDTM_RAG_INSTANCE=public` + .env `sdtm_rag_instance=private`) → `RuntimeError: conflicting ...`。
- 未做 (随 3.3): 同机两实例并跑 + 局域网/mini 无端口可连。

## 审查 (规则 D)

code-reviewer (opus) → **PASS-with-fixes** (H1 / M3 / L4)。处理:

| # | 问题 | 处理 |
|---|---|---|
| H1 | `.env` 小写键 `sdtm_rag_instance=private` 经 pydantic 大小写不敏感匹配覆盖 compose 的 public | `server/config.py` `_check_instance_env`: 大小写变体值冲突 → 拒启动 + 单测 |
| M2 | 取消/超时跳过停机 | 停机 `if` 加 `cancelled()` + 测试 |
| M3 | 先上线再验收, 3.4 后验收窗口对外可达 | **3.4 前定** (临时容器先验 / cloudflared 验后再指), 记入 _progress |
| M4 | KB 指纹不一致每次 run 都红 | 改 `::warning::` + 跳过部署/验收 (公开实例不动) |
| L5 | 验收用 assert | 改 `sys.exit` |
| L6 | 只验 import | 预检加 `-e SDTM_RAG_INSTANCE=public` 下 `Settings().instance=='public'` |
| L7 | 8010 端口无用 | 删除 |
| L8 | 测试缺口 | 补 cancelled / inputs.deploy / 禁 env_file·network_mode·privileged·ports / target 字面量 |
| OQ | Gitea `vars.` / `needs.outputs` 支持 | 失败方向安全 (跳过或 TAG 空被 SHA 校验拦); 首次开启时看 run 日志确认 TAG 展开 |
