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
| M3 | 先上线再验收, 3.4 后验收窗口对外可达 | **3.4 前定** (临时容器先验 / cloudflared 验后再指), 记入 _progress → **2026-11-27 主人裁定: 先用临时容器验, 通过后再换正式容器** (见文末「M3 裁定」) |
| M4 | KB 指纹不一致每次 run 都红 | 改 `::warning::` + 跳过部署/验收 (公开实例不动) |
| L5 | 验收用 assert | 改 `sys.exit` |
| L6 | 只验 import | 预检加 `-e SDTM_RAG_INSTANCE=public` 下 `Settings().instance=='public'` |
| L7 | 8010 端口无用 | 删除 |
| L8 | 测试缺口 | 补 cancelled / inputs.deploy / 禁 env_file·network_mode·privileged·ports / target 字面量 |
| OQ | Gitea `vars.` / `needs.outputs` 支持 | 失败方向安全 (跳过或 TAG 空被 SHA 校验拦); 首次开启时看 run 日志确认 TAG 展开 |


## M3 裁定 (2026-11-27, 主人本人在待办项上选定, 非 bot 代裁)
问题:「公开站每次部署, 新版本对外之前怎么验收?」选项: 先用临时容器验, 通过后再换正式容器 / 先断开隧道, 起新版本验完再接回 / 维持现状, 先上线再验。
主人原话:「先用临时容器验，通过后再换正式容器」。

### 对 3.4 实现的要求 (只写要求, 未实现)
1. **`deploy_public` 流程改为**: 用新镜像另起一个**临时容器** → 在临时容器里做现有的全部验收 (健康 / 档位 `tier=public` / 内部接口关闭 `/openapi.json` 等 404 / `check_index_freshness` rc=0) → **全部通过后**才替换正式容器 (`sdtm-rag-public-api`) → 清理临时容器。验收不过: 正式容器不动, 旧版继续对外; 临时容器清理掉, job 失败并告警。
2. **临时容器的数据**: 用公开数据根的**副本** (chroma 和 meta 各复制一份), 做法参照私有站测试端口的先例 (`checkpoints/step_1.9_testport_36499a7.sh`: 各用 chroma 副本, data/ 只读挂载); **不能**与正式容器共用 `quota.sqlite` (临时容器用自己的空库或副本, 否则验收会写正式的额度计数)。有过闸候选要换入时 (kb-sync swap), 临时容器用的是**候选**的副本, 这样验收覆盖的是「新镜像 + 新数据」这一对。
3. **临时容器不对外**: 不发布宿主端口, 不接隧道 (不加入 cloudflared 所在的网络; 用单独网络或无网络, 验收全部走 `docker exec`), 容器名与正式容器不同, 不能被 cloudflared 按名字解析到。
4. **实现时要核对的点**:
   - 内存: 两实例并跑时 VM available 约 4399M (3.3 实测), 临时容器再加一个 api (上限 1536m); 实现前在 VM 上复核余量 (参照 `p3_step3.1_capacity.md`)。
   - 现有验收不调用 `/api/ask`, 不花公开 key; 若以后在临时容器里加真答题冒烟, 要计入公开站 $ 封顶。
   - 副本的清理: 临时容器与数据副本在成功和失败两条路径上都要清理 (`always()`), 残留副本不能留在公开容器的挂载范围里 (与 D7 失败归档区分开)。

### 与已登记 D2 的衔接 (需实现时协调, 本次不改 D2)
D2 (`p3_public_kb_update_design.md` 裁定登记, bot 受托代裁) 是:「换入后验收失败 → 退回数据后停机; 原本停止的保持停止」。M3 之后验收前移到临时容器, 两者的关系需要实现时理清:
- **D2 适用的范围变窄**: 绝大多数失败 (新镜像起不来、档位不对、数据不新鲜) 会在临时容器阶段拦住, 此时正式容器和正式数据都没动, 不走 D2。D2 只剩「临时容器通过、但替换正式容器 / 换入正式数据之后又失败」这种情况。
- **停机 vs 旧版继续对外**: M3 的精神是「验收不过时旧版继续对外」; D2 在替换之后失败时选的是「退回数据后**停机**」。替换后失败是该退回到旧镜像 + 旧数据继续对外 (与 M3 一致), 还是按 D2 停机, 需要在实现前统一口径。
- **数据换入的时机**: A1 设计里 swap 发生在正式数据根 (改名换目录)。M3 下顺序应为: 临时容器用候选副本验收通过 → 停正式容器 → swap → 用新镜像起正式容器 → 简短复验 (健康 + freshness) → finish。复验失败时按 journal restore 退数据 (D2 前半句不变), 之后起旧镜像还是停机即上一条待定。
- 「原本停止的保持停止」不受影响: 原本停止时, 临时容器验收通过后也不应自动把正式容器拉起, 是否拉起要另定 (目前公开实例就是停止状态)。

### 协调方的建议 (主人尚未裁定)
临时容器验收只覆盖应用本身, 覆盖不到隧道这一层 (真实访客 IP 透传 `CF-Connecting-IP`、`QUOTA_TRUSTED_PROXIES`、Cloudflare 限速 / WAF)。**建议**首次上线时用 Cloudflare Access 只放行主人本人, 由主人经隧道验一次, 验完再放开公开访问。这是建议, 待主人裁定。
