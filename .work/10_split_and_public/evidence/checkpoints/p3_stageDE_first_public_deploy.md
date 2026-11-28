# 公开腿演练阶段 D / E: 第一次公开部署 (run id 219) —— 公开腿在临时容器验收失败, 阶段 E 没有做 (2026-11-28)

方案 = `p3_public_leg_impl.md` §5「阶段 D」「阶段 E」+ `docs/plans/P3_4_tunnel_drill.md` 第 5 步。时间戳是 UTC。先例: `p3_stageC_public_candidate.md`、`p3_stageB_network_isolation.md`、`p3_tunnel_leg_merge_deploy.md`。失败归档 (规则 B): `failures/p3_stageD_public_deploy_attempt_1.md`。

**结论: 阶段 D 的部署运行失败, 没有过 D → E 的闸, 阶段 E 一步都没有做。** 这是 `deploy_public` 第一次真实运行。
- 私有腿成功, 私有站没有被重启, 数据没有变。
- 公开腿走到「临时容器验收」被拒: 没有网络的临时容器里, 公开档的启动自检给免费模型定不了价, 拒绝启动。其后的答题 key 探测、换入、`up --no-start` 都没有走到。
- **公开站与部署前完全相同** (快照机械 diff 为空): 公开容器已创建、从未启动、镜像仍是旧的 `099c2c9`; 线上数据是旧 KB; 候选还在, 没有被换入。
- 没有重跑, 没有回滚, 没有用 `force_data_mismatch`。**变量 `SDTM_RAG_PUBLIC_DEPLOY` 仍是开的。**
- 这个失败会稳定复现 (与镜像新旧无关), 修之前每一次带公开部署的运行都会在同一处变红。

## 授权
主人 2026-11-28 在协调方的待办项上亲自选定 (**经待办项转达的选择**, 不是在本会话里说的):
- 问题一:「可以做第一次公开部署吗（换入新数据、换新镜像，公开容器保持停止）？」→ 主人选「可以」。说明里写的做法: 用线上私有站同一个镜像 `613f048` 跑一次部署工作流; 公开腿依次核对网络隔离 → 没有网络的临时容器验收 → 验证公开站的 Anthropic key 是否有效 (只验有效性, 不答题) → 换入候选 → 用新镜像重建公开容器并保持停止; 私有腿也会跑, 镜像和数据没变, 预期不会重启; 任何一步不过, 公开站保持原样, 停下来汇报。
- 问题二:「部署成功后，可以启动公开容器并做启动后的核对吗（仍没有对外入口）？」→ 主人选「可以，部署成功后接着做」。说明里写的: 启动后核对健康、公开档、索引新鲜度、HTTPS 安全头、全局限流、只信任连接器那一个地址; 删掉公开站 env 文件里那行旧的可信代理设置; 没有连接器、没有隧道、不发布端口。
- **只覆盖**: 派发**一次** `sdtm-rag` (tag = `613f048…`, deploy = true, `force_data_mismatch` 不勾)、`docker start sdtm-rag-public-api`、演练方案第 5 步的只读核对、5a、5b (以及这项工作的收尾文档的 push)。**不覆盖**: 构建新镜像、连接器、token、隧道、Cloudflare 的任何操作。
- 实际用掉的: 那一次派发。问题二的前提 (部署成功) 没有成立, `docker start`、5a、5b 都没有做 —— **问题二的同意没有被使用**。

失败之后协调方的答复 (2026-11-28, **协调方的决定, 不是主人逐条裁定**): 停在这里; 收尾照做; 修法定为「把公开档可选模型的价格固定进代码, 启动自检不依赖联网」, 由协调方另开会话在分支上做。

## 派发之前的只读预检 (07:23Z–07:29Z) —— 五条都满足
| # | 项 | 结论 | 依据 |
|---|---|---|---|
| 1 | tag 非空时各个 job checkout 的是哪个提交 | **main 的当前提交 `0a85a43`**, 不是 tag 对应的提交 | 两个 job 的 checkout 步骤都是 `uses: actions/checkout@v4`, 私有 job 只多一个 `submodules: true`; 整个 workflow 里没有任何 `ref:` 键, 输入的 `tag` 只进 `INPUT_TAG` / `TAG` 两个环境变量 (镜像标签)。Gitea 上 main = `0a85a43`; Gitea main 上 6 个文件的 blob 号与本地 `0a85a43` 逐个相同 (`sdtm-rag.yml` `d67d9d11…`、`kbsync.py` `45ce8d1c…`、`compose.public.yml` `a5d67787…`、`compose.yml` `f7270884…`、`image_floor_check.py` `890f2fbf…`、`isolation_probe.py` `523736d7…`)。运行后的实证见下文 |
| 2 | `deploy_public` 的完整 `if` | 在「手动派发 + tag 有值 + deploy = true + 变量已开」下为真 | 原文 `gitea.ref == 'refs/heads/main' && vars.SDTM_RAG_PUBLIC_DEPLOY == 'true' && (gitea.event_name != 'workflow_dispatch' \|\| format('{0}', inputs.deploy) != 'false')`, 另有 `needs: deploy`。真值表 (`p3_public_leg_if_tables.md`) 里对应的一行「ref=main, 公开变量=true, event_name=workflow_dispatch, 输入.deploy=true, 输入.tag=0000…, 之前的结果 成功 → 执行」; `tests/test_workflow_conditions.py` 165 passed。变量读回 `data` = `true` |
| 3 | 同一个 tag 重新部署会不会重建或重启私有容器 | **不会** | 私有「部署」步骤: KB 对齐是 `same` 时不进 `stop` 分支, 只有 `IMAGE_TAG="$TAG" docker compose -f deploy/container/compose.yml up -d`; 没有 `--force-recreate`、没有 `down`; `docker pull` 在 KB 对齐步骤里, 拉的是同一个标签。`compose.yml` 自 `613f048` 以来没有改动。**比读文本更硬的一条**: 在虚拟机上用同一份 compose 文件、同样的 `IMAGE_TAG` / `APP_DIR` 算出的配置哈希 (`docker compose config --hash '*'`: api `b842d307…`、ui `92b3cb6a…`) 与线上两个容器的 `com.docker.compose.config-hash` 标签逐个相同; 两个容器的镜像 ID = 本地该标签的镜像 ID = 镜像仓库里的摘要 (`sha256:9e1ac10b…`)。compose 版本 v5.7.0 (容器标签里记的也是它) |
| 4 | 镜像 | 本地和镜像仓库里都在; 满足镜像下限; 镜像内 KB 指纹与候选一致 | 本地 `sha256:9e1ac10b…`, `WorkingDir` `/app`; Gitea 包接口对该标签返回 200 (建于 03:16:22Z, 即 run 215 推的那一个)。镜像下限: `docker run --rm -i --entrypoint python <镜像> - < deploy/public-net/image_floor_check.py` 退出码 0, 输出恰为 `image-floor: ok`。镜像内 KB 指纹 `477bac3ce565aa810c38aeb14a35bf22f2c760c13a7e0b5f7d3bcf6ee24e3236`, chromadb `1.5.9`, `PUBLIC_EDGE_LEVEL` = 1 |
| 5 | 基线快照 (`p3_stageC_snapshot.sh`, 存本机) | 与任务给的现状逐项相符 | 下表 |

预检 5 的基线 (07:24:40Z):

| 侧 | 项 | 值 |
|---|---|---|
| Actions | 运行列表 | 最新是 id 218 (`completed` / `success`), 总数 24; 虚拟机里没有 job 容器, 没有 job 网络 |
| 公开 | 容器 | Id `2a33f280…`, `created` / `running=false` / `started=0001-01-01T00:00:00Z` / 重启 0 次, 镜像 `…:099c2c9…` (`sha256:3886799a…`); 没有发布端口, `unless-stopped`, 只在 `sdtm-rag-public` 网络 |
| 公开 | 数据根 | 上一级只有 `data`; `data` 下 `chroma` `chroma_cand_477bac3ce565` `meta` `meta_cand_477bac3ce565` `quota.sqlite`; journal / guard / prev / failed / accept 都是 0; 线上 stamp `f863e45445a6…` / 4329 |
| 公开 | 各目录的 inode / 内容摘要 (`p3_stageDE_pubdirs.sh`) | `chroma` 50497 / `dabd65645e3d3d9a`; `chroma_cand_477bac3ce565` 56800 / `2d36c96fc0e32d5d`; `meta` 50534 / `5db4931da6ddf8c0`; `meta_cand_477bac3ce565` 56810 / `0ace313802a980cb` |
| 公开 | 网络与隔离 | 网络 Id `eff48d9c…`, `10.201.8.0/24`, 0 个容器; 隔离表 1 张、5 条 `drop`; 巡检定时器 `active` / `enabled`, 隔离单元 `active` / `enabled`; `nftables.service` `disabled` |
| 公开 | env 文件 (只看元数据, 没有读内容) | `600 root:root`。同目录下另有一个协调方留下的旧备份, 未读未动 |
| 私有 | 容器 | `sdtm-rag-api` Id `a9937c62…`, 启动于 `2026-11-28T03:23:47.097798686Z`; `sdtm-rag-ui` Id `e5d92671…`, 启动于 `03:23:57.678917638Z`; 重启都是 0 次; 镜像 `613f048…`; health `healthy`, `/api/health` 200 |
| 私有 | 数据 | stamp `477bac3ce565…` / 4333; `meta.yaml` sha256 `b484d49ef76cc8d5246f68ff2761c49ba70976ca8071fcce78ab922c3078f5c5`; `chroma` 目录 inode 53422、130 个文件; `study` 1557 个文件 |
| 机器 | 内存 / 容器 | 可用 5165 MB (总 7913 MB); 容器 23 个, 运行中 22 个, 非运行的只有公开容器 |

任务清单之外加做的 (都在派发之前):
- **答题 key 探测脚本要用的包在镜像里能 import**: `docker run --rm --network none --entrypoint python <镜像> -c 'import anthropic …'` → `anthropic 0.107.1`。(探测本身这次没有走到。)
- **派发前起了一个只读轮询** (`p3_stageDE_poll.sh`, 约每 4–5 秒一个样本, 落本机文件): 编排的输出是步骤结束时一次性刷出来的 (阶段 C 的发现), 各小步的时刻要靠它。
- 派发前一刻再读一次: 运行列表最新仍是 218 且已完成; Gitea main 仍是 `0a85a43`; 变量仍是 `true`; 本地工作区干净。

## 阶段 D: 派发一次部署 —— run id 219, 私有腿 success, 公开腿 failure
- **07:29:29Z** `POST …/actions/workflows/sdtm-rag.yml/dispatches`, 正文 `{"ref":"main","inputs":{"tag":"613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7","deploy":"true","force_data_mismatch":"false"}}` → HTTP 204。**只派发了这一次。**
- 运行: id **219** (`run_number` 25), `head_sha` = `0a85a43cec0aedcc74715f90f744be2b0e10153c`, 07:29:33Z → 07:30:52Z, `completed` / **`failure`**。
- **checkout 的实证** (预检 1): 两个 job 的 checkout 日志都是 `git checkout --progress --force -B main refs/remotes/origin/main`, 随后 `git log -1 --format=%H` 打印 `0a85a43cec0aedcc74715f90f744be2b0e10153c`。「tag 有值 (而且不等于 main 的头提交) 时 checkout 的仍是 main」这是第一次在真机上见到 (run 216 那次 tag 恰好等于头提交, 区分不出来)。

### `deploy` (job 465, 07:29:32Z → 07:29:55Z, 23 秒) —— success, 与预期一致
| 步骤 | 结论 | 关键日志行 |
|---|---|---|
| checkout | success | `0a85a43cec0aedcc74715f90f744be2b0e10153c` |
| 测试 | skipped | (tag 非空) |
| 登录镜像仓库 / 确定要部署的标签 | success | `部署标签：613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7` |
| 构建并推送 | skipped | |
| 记录当前线上镜像 | success | `部署前线上镜像标签：613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7` |
| KB 数据对齐检查 | success | `Status: Image is up to date for …:613f048…` (摘要 `sha256:9e1ac10b…`) → `{"prod_fp12": "477bac3ce565", "target_fp12": "477bac3ce565", "decision": "same"}` →「镜像 KB 指纹与生产 chroma 一致，不换数据」 |
| 部署 | success | `挂载目标目录：/app`; ` Container sdtm-rag-ui Running` / ` Container sdtm-rag-api Running` / `Waiting` / `Healthy` (compose 对两个容器报的是 `Running`, 不是 `Recreated` / `Started`); 两个容器的运行镜像都是 `…:613f048…` |
| 健康检查 | success | `健康检查通过（172.18.0.1:8000/api/health 返回 200）` |
| 新鲜度 / 换数据收尾 / 两个退回步骤 | skipped | |
| 退出镜像仓库 | success | |

### `deploy_public` (job 466, 07:29:56Z → 07:30:52Z, 56 秒) —— **不是 skipped**; failure
私有腿运行期间它是 `requested` (等待), 私有腿结束 1 秒后开始。

| # | 步骤 | 结论 | 用时 | 关键日志行 |
|---|---|---|---|---|
| 0 | checkout | success | 5 秒 | `0a85a43cec0aedcc74715f90f744be2b0e10153c` |
| 1 | 登录镜像仓库 | success | <1 秒 | |
| 2 | 公开实例预检 (镜像) | success | 7 秒 | `Status: Image is up to date for …:613f048…`; 四条检查 (能 import `server.instance` / 公开档解析为 public / `WorkingDir` = `/app` / 镜像下限) 都没有报错 |
| 3 | 临时容器验收，通过后才换正式容器 | **failure** | 39 秒 | 见下 |
| 4 | 中断时停掉已被动过的公开实例 | success | <1 秒 | `[deploy-public] 正式容器没有被动过，不做任何事` |
| 5 | 清理临时容器与验收副本 | success | <1 秒 | (没有输出: 编排自己在失败时已经清过) |
| 6 | 退出镜像仓库 | success | <1 秒 | |

第 3 步的输出 (`[deploy-public]` 开头的行原样; 这一步的输出是结束时一次性刷出来的, 日志时间戳都是 07:30:50.99Z):
```
[deploy-public] KB 对齐检查：{"prod_fp12": "f863e45445a6", "target_fp12": "477bac3ce565", "decision": "swap", "source_chroma": "chroma_cand_477bac3ce565", "source_meta": "meta_cand_477bac3ce565"}
[deploy-public] 部署前：正式容器 已停止，镜像 192.168.100.58/bojiang/sdtm-rag:099c2c930ec869e254b2e9052c3d4a6a85d6d539
[deploy-public] 公开网络 sdtm-rag-public 的子网是 10.201.8.0/24，与 compose 一致
[deploy-public] 隔离核对：PASS          隔离侧源地址 10.201.8.128 在 10.201.8.0/24 里
[deploy-public] 隔离核对：PASS          10.201.8.1:22: 隔离侧 timeout, 对照侧 open
[deploy-public] 隔离核对：PASS          172.22.0.1:22: 隔离侧 timeout, 对照侧 open
[deploy-public] 隔离核对：PASS          192.168.100.58:443: 隔离侧 timeout, 对照侧 open
[deploy-public] 隔离核对：PASS          192.168.5.15:22: 隔离侧 timeout, 对照侧 open
[deploy-public] 隔离核对：PASS          192.168.5.15:8000: 隔离侧 timeout, 对照侧 open
[deploy-public] 隔离核对：PASS          192.168.5.2:22: 隔离侧 timeout, 对照侧 open
[deploy-public] 隔离核对：PASS          192.168.64.1:22: 隔离侧 timeout, 对照侧 open
[deploy-public] 隔离核对：PASS          api.anthropic.com:443: 外网可达
[deploy-public] 隔离核对：PASS          api.openai.com:443: 外网可达
[deploy-public] 隔离核对：PASS          region1.v2.argotunnel.com:7844: 外网可达
[deploy-public] 隔离核对：结论: PASS
[deploy-public] 网络隔离核对通过
[deploy-public] 临时容器 sdtm-rag-public-accept-api 已启动（数据 = chroma_cand_477bac3ce565 的副本，不联网、无端口）
[deploy-public] sdtm-rag-public-accept-api 未就绪，日志末尾：
  （这里是临时容器日志的末尾 40 行: uvicorn 载入应用的调用栈, 止于 server/main.py create_app → server/instance.py check_startup; 已过编排的脱敏）
RuntimeError: SDTM_RAG_INSTANCE=public refuses to start: selectable model 'haiku-5-5': one answer round reserves $0.700 > free pool / 10 = $0.300 (lower its max_output_tokens)
[deploy-public] 失败：临时容器验收不通过 —— 容器没有进入 healthy 状态；启动报错：RuntimeError: SDTM_RAG_INSTANCE=public refuses to start: selectable model 'haiku-5-5': one answer round reserves $0.700 > free pool / 10 = $0.300 (lower its max_output_tokens)
[deploy-public] 正式容器和正式数据都没有动（公开实例仍是停止状态）。
```

各小步的时刻 (轮询样本 + 日志; 轮询每 4–5 秒一个样本, 所以是区间):

| 事件 | 时刻 (UTC) | 依据 |
|---|---|---|
| 第 3 步开始 | 07:30:12.7 | 日志; 验收副本目录名里的时间戳也是 `073012Z` |
| KB 对齐、红线检查、网络预检、隔离核对 | 07:30:13 – 约 07:30:43 | 这一段里公开数据根上一级一直只有 `data` (07:30:42 的样本还没有验收副本)。隔离侧 7 个内网目标各等满超时, 占了其中大部分 |
| 验收副本建出 (`kbsync_accept_20261128T073012Z`) | 07:30:42 – 07:30:46 之间 | 轮询: 07:30:46 的样本第一次出现 |
| 临时容器已经退出 | 07:30:50 的样本: `exited` | 轮询。从建副本到判失败不超过约 9 秒: 应用在载入阶段就被自检拒绝, 容器直接退出, 没有等健康检查的 180 秒 |
| 第 3 步结束 (失败) | 07:30:51.0 | 日志 |
| 临时容器与验收副本已清 | 07:30:54 的样本 | 轮询: 容器不存在, 上一级只剩 `data` |

整个运行期间 (07:29:03Z – 07:31:40Z, 39 个样本) 公开容器每个样本都是 `created` / `run=false` / 镜像 `099c2c93…` / 同一个 Id; 私有 api 每个样本都是 `running` / 启动于 `03:23:47.097798686Z` / 重启 0 次; 可用内存最低 5040 MB。

### 与预期逐条对照
| 预期 (`p3_public_leg_impl.md` §5 阶段 D 一行) | 实际 |
|---|---|
| 私有 `deploy`: 标签 `613f048…`, KB 对齐 `same`, 不换数据, 健康检查 200; 私有容器 `StartedAt` 不变 | **一致** |
| `deploy_public` 不是 skipped | **一致** |
| 预检 (含镜像下限) | 通过 |
| 路径一致 → KB 对齐 `swap` (换入源 `chroma_cand_477bac3ce565`) → 部署前状态 | 一致 (路径一致时编排不打印, 没有「路径不一致」的行) |
| 「公开网络 … 的子网是 10.201.8.0/24，与 compose 一致」 | 逐字出现 |
| 隔离核对判定行 PASS、隔离侧源地址在 `10.201.8.0/24` 里 → 「网络隔离核对通过」 | 一致: 11 行全 PASS, 源地址 `10.201.8.128` |
| 临时容器启动 | 一致 |
| **验收通过并清理** | **不一致: 验收不通过** (启动自检拒绝启动); 清理做了 |
| 「答题 key 探测通过」 | **没有走到** |
| 换入 → `up --no-start` → 「成功：镜像已更新…公开容器保持停止…」 | **没有走到** |

## 失败的原因 (只读查的; 细节与实测在失败归档)
- 拒绝启动的是公开档的成本自检 (`server/instance.py`): 每个可选模型一轮答题的最坏预留额不得超过免费池的十分之一 (报错里的上限是 0.30, 即免费池 3.0 美元, 与 `server/quota.py` 的默认值一致; 公开站的 env 文件没有读)。
- `claude-haiku-5-5` 不在 `server/cost.py` 写死的价格表里, 价格靠 litellm; litellm 在 import 时联网取在线价格表, 取不到就退回包内自带的旧表 (没有这个模型)。**临时验收容器没有网络**, 于是按回退费率 (输入 5 / 输出 25 美元每百万 token) 估: 60000 × 5 + 16000 × 25 = 0.70 美元 > 0.30。
- 同一个镜像的两次一次性容器对照 (`p3_stageDE_price_probe.py`; 不挂数据、不带 env 文件): `--network none` → 单价 `None` / `None`, 价格表 2764 条, 没有这个模型; 默认网桥 → `0.1` / `0.5`, 价格表 7194 条, 有。有网络时的预留额是 0.014 美元。
- 这段逻辑 (`server/instance.py`、`quota.py`、`cost.py`、`provider_registry.py`、`llm_config.py`, `git diff --stat 099c2c9 613f048` 为空) 和 litellm 的版本 (两边都是 1.88.6) 在旧镜像 `099c2c9` 与 `613f048` 之间没有变: 不是这次镜像带来的回归。3.3 试跑时公开容器有外网, 所以没有暴露。**修之前任何镜像都过不了没有网络的临时验收。**
- 类别: 部署设计与应用启动自检之间的配合问题。不是 key、数据、网络隔离的问题。

## D → E 的闸 —— 没有通过, 阶段 E 没有做
| 闸的条件 | 结果 |
|---|---|
| run 整体 success, 两个 job 都 success | **不满足**: run failure; `deploy` success, `deploy_public` failure |
| 三行日志都在: 隔离核对 PASS 且源地址在公开网段内 / 临时容器验收通过 / 「答题 key 探测通过」 | 第一行在 (PASS, `10.201.8.128`); **后两行不在** |
| 公开容器 `created` 或 `exited`、未运行、镜像是新 tag | `created`、未运行 —— **镜像仍是旧的 `099c2c9`** (没有被重建) |
| 没有 `sdtm-rag-public-accept` 临时容器; 没有 accept 网络 | 满足 |
| 公开数据根上一级只有 `data` | 满足 |
| 数据根里是 `chroma meta quota.sqlite` 加 `chroma_prev_f863e45445a6_<ts>` / `meta_prev_…`; 没有 `kbsync_swap.json` / `kbsync_guard_*` | 没有 journal / guard —— 但也**没有 `*_prev_*`, 两个 `*_cand_*` 还在** (没有换入) |
| 线上 stamp 指纹 `477bac3ce565…` | **不满足**: 仍是 `f863e45445a6…` |
| 私有站镜像与启动时间没变 | 满足 |

checkpoint 点名要记的三件事:
- 临时容器从启动到验收通过用了多久: **没有通过, 无从记**。能说的只有: 没有网络的容器里应用在载入阶段就退出了, 从建副本到判失败不超过约 9 秒。「没有网络的临时容器能否起到 healthy」仍然没有答案 —— 价格这一关过了之后, 后面还有没有别的依赖网络的地方, 不知道。
- 「换入」一段有没有 `readonly` 相关报错: **没有走到换入**。验收副本那一步 (`accept-stage`, 兄弟容器里数据根只读挂载、上一级可写) 做成了: 副本目录在数据根的上一级出现, 之后被清掉, 日志里没有 `readonly` / 权限类报错。
- key 探测容器能否读到只读挂载的 env 文件: **没有走到**。旁证只有一条: 临时验收容器 (同样只读挂载这个 env 文件, 同样是容器里的 root) 读到了里面的可选模型配置 —— 报错里的模型名和算出来的预留额 (对应 16000 的输出上限) 都出自 env 文件; 但那个容器没有去掉 capability, 不能替代 key 探测容器的结论。

两份 job 日志只计数的扫描 (存本机后扫; 305 行 / 263 行): 密钥形状 0, JWT 形状 0, `study` 开头的词 0, 带用户名的路径 0, 带取值的 key / token 赋值 0。公开腿日志里带出来的容器日志末尾 40 行只有调用栈和那一行报错。

## 阶段 E —— 没有执行
D → E 的闸没有过, 下面各项**都没有做**: `docker start sdtm-rag-public-api`; `/api/info` 档位、容器内 `check_index_freshness`、`/openapi.json`; 演练方案第 5 步的只读核对 (网络、动态地址段、可信代理、`FORWARDED_ALLOW_IPS`、HSTS、cookie); 5a (全局限流); 5b (删 env 文件里的旧行 —— 没有建备份, 没有动 env 文件, 所以没有行数与权限可记; 文件仍是 `600 root:root`); 隔离复核 (启动后的 3d); 「没有对外入口」的核对。公开容器从未启动, 这些都无从核对。

唯一提前做了的是第 8 项的**静态阅读** (不依赖容器启动, 只读; 结论供以后用):

### 隔离单元相对 `docker.service` 的启动顺序 (静态读, 没有重启任何东西)
- 仓库里的单元文件 (`deploy/public-net/sdtm-rag-public-isolation.service`): `[Unit]` 里只有 `Before=docker.service`; `[Install]` 是 `WantedBy=multi-user.target`; `Type=oneshot` + `RemainAfterExit=yes`。虚拟机上装的那一份与仓库逐字节相同 (sha256 `67d7842f…`; 规则文件 `4565d6f2…` 也相同)。
- 虚拟机上 systemd 实际解析出的关系 (`systemctl show`): 隔离单元 `Before=multi-user.target shutdown.target docker.service`, `enabled` / `active`; `docker.service` 的 `After=` 里有 `sdtm-rag-public-isolation.service`, 而它的 `Requires=` (`sysinit.target system.slice docker.socket`) 和 `Wants=` (`containerd.service network-online.target`) 里**都没有**隔离单元。
- 所以这是**纯顺序关系, 没有硬依赖**: 两个单元在同一次开机里都要启动时, 隔离单元先于 docker; 隔离单元失败 (规则文件写坏、nft 不可用) 时 docker 照样启动、照样拉起容器 —— 这是有意的 (规则出错不该拖垮同机的私有站), 兜底是开机 20 秒后第一次、之后每分钟一次的巡检。
- 规则能不能在 docker 建出网桥之前装进去: 能。`isolation.nft` 按接口**名字** (`iifname` / `oifname "br-sdtmpub"`) 和源网段 (`ip saddr 10.201.8.0/24`) 匹配, 不按接口索引; 按名字匹配不要求装入时接口已经存在。
- **对现在的意义**: 公开容器仍然从未启动 (`started=0001-01-01T00:00:00Z`, `unless-stopped`), 所以「重启后它会不会自己起来、规则是不是先于它装入」这条**现在还没有开始起作用**。它从第一次 `docker start` 成功那一刻起才有实际意义: 那之后虚拟机或 docker 守护进程重启, 公开容器会自己起来, 起来之前规则应当已经装好; 万一隔离单元失败, 容器会在没有隔离的情况下运行最长约 20 秒 (到第一次巡检), 巡检也装不上时它只会停连接器、不会停公开容器。
- 没有验证的: 真的重启一次的实际顺序 (阶段 B 留下的待办, 仍然挂着); docker 被 socket 激活而早于 `multi-user.target` 启动时顺序是否仍然成立 (同一次开机事务里两者都在排队时成立, 这是按 systemd 的一般规则说的, 没有实测)。

## 运行之后: 公开 / 私有两侧前后对比
同一个快照脚本 (`p3_stageC_snapshot.sh`) 在派发之前 (07:24:40Z) 和运行结束之后 (07:31:53Z) 的输出做机械 diff, 去掉带时间和余量的一行之后**没有任何差异**。`p3_stageDE_pubdirs.sh` 的前后输出也没有差异。

| 侧 | 项 | 值 (前 = 后) |
|---|---|---|
| 公开 | 容器 | Id `2a33f280…`, `created` / `running=false` / `started=0001-01-01T00:00:00Z` / 重启 0 次, 镜像 `…:099c2c9…` (`sha256:3886799a…`) —— **仍然从未启动, 镜像没有换** |
| 公开 | 线上数据 | stamp `f863e45445a6…` / 4329; `chroma` inode 50497、清单指纹 `7a91a1360dcc6cf9`、内容摘要 `dabd65645e3d3d9a`; `meta` inode 50534、清单指纹 `c9a94e8bd019b981`、内容摘要 `5db4931da6ddf8c0`; `quota.sqlite` 的 inode / 大小 / mtime |
| 公开 | 候选 | `chroma_cand_477bac3ce565` (inode 56800, 内容摘要 `2d36c96fc0e32d5d`, 4333 条)、`meta_cand_477bac3ce565` (inode 56810, `0ace313802a980cb`) —— **原样, 没有被换入** |
| 公开 | 残留 | journal 0 / guard 0 / prev 0 / failed 0 / accept 0; 没有临时容器, 没有 accept 网络, 没有连接器 |
| 公开 | 网络与隔离 | 网络 Id `eff48d9c…`, `10.201.8.0/24`, 0 个容器; 隔离表 1 张 5 条 `drop`; 定时器与单元 `active` / `enabled`; `nftables.service` `disabled` |
| 私有 | 容器 | api Id `a9937c62…` / ui Id `e5d92671…`; 启动时间 `03:23:47.097798686Z` / `03:23:57.678917638Z`; 重启 0 次; 镜像 `613f048…`; health `healthy`, 200 |
| 私有 | 数据 | stamp `477bac3ce565…` / 4333; `chroma` / `meta` 目录 inode 与文件名清单指纹; `meta.yaml` sha256 `b484d49e…`; `*_prev_*`、`*_failed_*` 原样; `study` 1557 个文件 |
| 机器 | 容器与镜像 | 容器总数 23, 运行中 22, 非运行的只有 `sdtm-rag-public-api`; 镜像总数 36; 没有 job 容器、没有 job 网络残留 |
| Gitea | 变量 | `SDTM_RAG_PUBLIC_DEPLOY` = `true` (没有动) |

这次运行在虚拟机上起过、已经不在的东西: 两个 job 容器; 编排起的一次性容器 (取镜像指纹和 chromadb 版本、KB 对齐、读线上集合的副本、隔离侧与对照侧的探测、建验收副本、读副本的集合); 一个临时验收容器 (`sdtm-rag-public-accept-api`, 没有网络, 起来就退出) 和它的数据副本。我自己起的一次性容器 (都是 `--rm`, 不挂数据、不带 env 文件): 镜像下限 1 个、镜像内指纹与版本 2 个、import 检查 1 个、定价诊断 2 个; 另有 `docker compose config --hash` 一次 (只解析, 不建任何东西)。只读轮询是虚拟机里的一个 shell 循环 (经 ssh 起的), 运行结束后从本机断开; 之后在虚拟机、mini、本机各用 `pgrep` 看过, 没有残留的进程。

## 第一次真实运行, 记下来的几样
- **`deploy_public` 的门控与衔接**: 变量开着时它没有被跳过; `needs: deploy` 下私有腿运行期间它是 `requested`, 私有腿成功后才开始。加上 run 216 (变量未开 → skipped), 这个门控的两个方向都在真机上见过了。
- **tag 有值时 checkout 的是 main**: 见上。合进 main 的那批修正 (失败信息隐名、进程收尾) 在这次运行里。
- **同一个标签重新部署私有站**: compose 对两个容器报 `Running`, 没有重建; 私有腿 23 秒。
- **失败路径第一次真的走了一条**: 「临时验收不过 → 正式容器和正式数据都不动 → 兜底不停机 → 清理」这条路在真机上的表现与 `p3_public_leg_impl.md` §3.3 的表一致。步骤级的 `failure() || cancelled()` (兜底) 和 `always() && steps.pre.outcome == 'success'` (清理) 在前一步失败之后都执行了。
- **启动报错带进失败原因**: 那一行原样进了失败原因和日志 (隧道那条线提的要求); 日志末尾 40 行经过了脱敏, 扫描 0 命中。
- **隔离核对在部署里跑通**: 默认网桥上的对照容器全部 `open`, 隔离侧全部 `timeout`, 外网三个目标可达 —— 与阶段 B 手工跑的结果相同。
- **时间**: 公开腿整个 job 56 秒就失败了, 其中隔离核对约 30 秒。走完全程要多久仍然不知道 (`timeout-minutes: 30` 是估计值)。
- **job 网络占了 `172.18.0.0/16`**: 私有腿健康检查用的网关 (job 容器的默认路由) 是 `172.18.0.1` —— 应当是阶段 B 腾出来的那个网段被 runner 的 job 网络拿去用了 (没有去查网络列表确认)。与公开网络 (`10.201.8.0/24`) 不冲突, 只是记一笔: 这个网段不在 `ISOLATION_LAN` 的目标清单里 (清单里是 `172.22.0.1`), 但规则挡的是整个 `172.16.0.0/12`。

## 发现 (只汇报, 没有改)
1. **公开档的启动自检依赖联网取到的价格表** (本次失败的原因)。它同时意味着: 正式公开容器每次启动也要取得到那份在线价格表, 取不到就拒绝启动 (按代码推的, 没有在正式容器上试过; `unless-stopped` 下大概会反复重启, 同样没有实测)。协调方已定修法 (价格固定进代码), 另开会话做。
2. **`p3_public_leg_impl.md` §7 第 2 条的依据不成立**: 那里写「代码上 lifespan 没有出站调用」; 实际上 import litellm 时就有一次出站 (取价格表), 而且结果会影响启动自检。已在那一条后面加了更正。
3. **变量开着 + 这个问题没修的期间**: 任何带公开部署的运行 (不带 `[skip ci]` 又命中路径过滤的 push、勾着 `deploy` 的手动派发) 都会是「私有部署成功、公开腿变红、公开站不变」。私有站的发版不受影响, 但运行会显示失败。
4. **公开 env 文件所在目录里有一个协调方留下的旧备份**, 未读未动 (协调方答复: 等公开站的 Anthropic key 验证通过后由协调方处理)。
5. 隔离核对占了公开腿失败前一半以上的时间 (7 个内网目标各等满 4 秒超时, 串行)。不是问题, 记一笔: 以后嫌慢可以并行探测。

## 回退办法
这次**没有任何东西需要回退**: 公开站与部署前相同, 私有站没有变。下面是任务要求写明的三种做法, 供之后各阶段用。
- **立即下线公开站**: `docker stop sdtm-rag-public-api` (在部署机上)。现在不适用 —— 公开容器从未启动, 没有入口。
- **数据退回旧版**: 现在不适用 —— 没有换入, 线上就是旧版 (`f863e454…`)。换入之后要退的做法 (`p3_public_leg_impl.md` §5 阶段 D 一行): 公开容器停止状态下, 在部署机上用 `kbsync.py --via <镜像> predeploy-check / swap --target-fp <旧指纹> … / finish` 换回 `chroma_prev_*`, 再 `IMAGE_TAG=<旧 tag> docker compose -f compose.public.yml up --no-start api`。不能靠给 `sdtm-rag` 填旧 tag 来只回滚公开站 (同一个 tag 也作用于私有站, 而且旧镜像过不了镜像下限)。
- **停用公开腿和公开部署**: 把变量关掉。`DELETE …/actions/variables/SDTM_RAG_PUBLIC_DEPLOY` (或 `PUT` 同一地址, 正文 `{"value":"false"}`), 再 `GET …/actions/variables` 读回。关掉之后 `deploy_public` 和 kb-sync 的 `public` job 都会被跳过, 候选留在原地。修好之前如果不想每次部署都看到公开腿变红, 可以先关 (要主人或协调方定; 这次按任务要求保持打开)。
- **不想要这份候选**: 两个目录改名成 `*_failed_477bac3ce565_<UTC 时间戳>` (不删), 命令见 `p3_stageC_public_candidate.md`「回退办法」。

## 仍未验证的事项
1. **`deploy_public` 在「临时验收」之后的全部步骤**: 答题 key 探测 (公开站的 Anthropic key **仍然一次都没有被验证过**; 探测容器去掉全部 capability 后能否读到只读挂载的 env 文件; 在隔离规则下能否连上 Anthropic)、换入前置核对、停正式容器、换入 (嵌套只读挂载下的改名)、`up --no-start` 对「已存在、从未启动、镜像不同」的容器是否如预期重建且不启动、`finish` / `prune`、成功摘要。
2. **没有网络的临时容器能否起到 healthy、要多久**: 这次在载入阶段就退出了。价格这一关修掉之后, 后面 (BM25 建索引、其余启动自检、健康检查、`check_index_freshness`) 在没有网络的条件下还有没有别的问题, 不知道。
3. **阶段 E 的全部内容**: 新镜像 + 新数据在正式容器里启动; 档位 / 新鲜度 / 内部接口关闭; 网络与地址段; 可信代理; `FORWARDED_ALLOW_IPS`; HSTS; cookie 的 `Secure`; 全局限流 (5a); 删旧行 (5b); 启动后的隔离复核; 没有对外入口的核对。
4. 修法本身 (由另一个会话做): 修完的镜像在 `--network none` 下能否定价、能否通过启动自检。
5. **其余失败路径**: key 无效、换入被拒、换入后重建失败、退回失败、job 被取消时的兜底 —— 真机上仍然只走过「临时验收不过」这一条。
6. 阶段 B / C 留下的照旧挂着: 规则先于容器装入的开机顺序 (这次只做了静态阅读); 从未启动的容器在 `unless-stopped` 下重启后是否仍不启动; `concurrency` 是否真的让 kb-sync 与部署排队; `always()` 的另一半。
7. **没有独立审查**: 派单要求不起子代理, 这份记录和失败归档都是执行者自己写的 (规则 D 的缺口; 需要的话由协调方另派)。根因有两次对照实测, 快照 diff、日志、轮询样本都可以机械复核, 命令在下面。
8. 「只改公开站 env 也能绕过」(回退费率两个键、每日总额上限) 只是读代码得出的, 没有实测, 也没有被采用。

## 小结 (规则 C)
- **保留下来的做法**: 派发只有一次机会, 所以派发之前把「现在就能查出来的失败」尽量查掉 (镜像下限、镜像内指纹、key 探测要用的包能不能 import), 并把「私有容器会不会被重建」从读文本推进到比对 compose 配置哈希; 派发前起只读轮询, 补上日志里没有的时刻和「公开容器全程没有运行」的直接证据; 派发后先看运行的 `head_sha` 和两个 job 的状态, 不凭返回码判断; 失败之后不重跑、不动现场, 先取快照做机械 diff, 再只读查原因; 日志先落文件、只计数扫描, 再看具体行; 根因用一组对照实测 (同一个镜像、有网 / 无网) 钉住, 不停在「读代码觉得是」。
- **必须补上的缺口**: (1) 派发前的检查漏了最该查的一条 —— 「应用在没有网络的容器里能不能起来」可以用一个不挂数据的一次性容器提前试 (哪怕只是 import 应用、跑启动自检的定价部分), 我只查了 key 探测的包, 没有查应用本身; 这条在设计 checkpoint 里就是点名的未验证事项, 本该是派发前的第一个探测。(2) 设计阶段「没有出站调用」这个判断只看了自己写的代码 (lifespan), 没有看依赖库在 import 时做什么; 「不联网」这类性质要用断网实测来确认, 不能靠读。(3) 替身 docker 的实跑证明的是编排逻辑, 证明不了「应用在那种容器里起得来」, 两者要分开列。
- **关键决策复盘**: (1) 失败后停在现场, 只做了只读诊断 (两个不挂数据的一次性容器), 没有去试「改 env 再派一次」—— 同意只覆盖一次派发, 而且改 env 是花费上限一类的决定。(2) 阶段 E 的静态阅读提前做了 (不依赖部署成功、只读), 其余各项一律没有碰。(3) 修法只列选项和建议, 由协调方定; 本会话没有改代码。

## 结束状态
- 变量 `SDTM_RAG_PUBLIC_DEPLOY` = `true` (**开着**)。
- main = origin/main (Gitea 与 GitHub 相同); 收尾的文档提交带 `[skip ci]`, 其提交号见向协调方的最终汇报。私有站线上镜像仍是 `613f048…`。
- 公开站: 容器已创建、**从未启动** (镜像 `099c2c9`); 线上数据是旧 KB (`f863e454…` / 4329); 过闸候选 (`477bac3ce565` / 4333) 还在数据根里, 等修好之后的第一次公开部署换入。没有连接器, 没有隧道, 没有对外入口。
- 第一次公开部署 (阶段 D) 和启动 (阶段 E) 都还没有完成; 再做需要修好的新镜像, 以及主人的再次同意 (这次的同意只覆盖一次派发)。

## 复跑命令
```sh
R=<本仓根>; cd $R; OUT=<本机临时目录>; C=.work/10_split_and_public/evidence/checkpoints
VM()  { ssh <mini 主机> "export PATH=/opt/homebrew/bin:\$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- $*"; }
VMS() { ssh <mini 主机> 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- bash -s'; }
TAG=613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7; IMG=192.168.100.58/bojiang/sdtm-rag:$TAG
# Gitea API (账号与口令取自 git credential, 经标准输入交给 curl, 不进命令行、不写进任何文件; 下面用占位符)
API=https://git.bojiang.org/api/v1/repos/bojiang/sdtm-rag
# 预检 1: 远端文件与本地逐 blob 比较; workflow 里没有 ref:
for f in .gitea/workflows/sdtm-rag.yml deploy/kbsync/kbsync.py deploy/container/compose.public.yml deploy/container/compose.yml deploy/public-net/image_floor_check.py deploy/public-net/isolation_probe.py; do
  curl -s -u <账号>:$P "$API/contents/$f?ref=main"; git rev-parse HEAD:$f; done        # 接口返回的 sha 与本地 blob 号相同
curl -s -u <账号>:$P "$API/branches/main"; grep -n -A3 "uses: actions/checkout" .gitea/workflows/sdtm-rag.yml; grep -n "ref:" .gitea/workflows/sdtm-rag.yml
# 预检 2
.venv/bin/python -m pytest tests/test_workflow_conditions.py -q -o addopts="" -p no:cacheprovider      # 165 passed
curl -s -u <账号>:$P "$API/actions/variables/SDTM_RAG_PUBLIC_DEPLOY"
# 预检 3: compose 配置哈希 vs 线上容器的标签
git diff --stat 613f048 HEAD -- deploy/container/compose.yml                                            # 空
VM "sudo env IMAGE_TAG=$TAG APP_DIR=/app docker compose -f - config --hash '*'" < deploy/container/compose.yml
VM "sudo docker inspect sdtm-rag-api sdtm-rag-ui --format '{{.Name}} {{index .Config.Labels \"com.docker.compose.config-hash\"}} {{.Image}}'"
# 预检 4
VM "sudo docker image inspect $IMG --format '{{.Id}} {{.RepoDigests}} {{.Config.WorkingDir}}'"
curl -s -u <账号>:$P "https://git.bojiang.org/api/v1/packages/bojiang/container/sdtm-rag/$TAG"
out=$(VM "sudo docker run --rm -i --entrypoint python $IMG -" < deploy/public-net/image_floor_check.py); echo "rc=$? [$out]"   # rc=0 [image-floor: ok]
VM "sudo docker run --rm --entrypoint python $IMG -c 'from scripts.kb_freshness import kb_fingerprint;from server.config import settings;print(kb_fingerprint(settings.kb_root))'"
VM "sudo docker run --rm --network none --entrypoint python $IMG -c 'import anthropic; print(anthropic.__version__)'"
# 预检 5 / 运行之后: 快照与目录指纹 (只读), 前后 diff
VMS < $C/p3_stageC_snapshot.sh > $OUT/snap_pre.txt;  VMS < $C/p3_stageDE_pubdirs.sh > $OUT/pubdirs_pre.txt
VMS < $C/p3_stageC_snapshot.sh > $OUT/snap_post.txt; VMS < $C/p3_stageDE_pubdirs.sh > $OUT/pubdirs_post.txt
diff <(grep -v '^\[T\]' $OUT/snap_pre.txt) <(grep -v '^\[T\]' $OUT/snap_post.txt); diff $OUT/pubdirs_pre.txt $OUT/pubdirs_post.txt   # 都为空
# 运行期间的只读轮询 (后台; 运行结束后手工结束)
VMS < $C/p3_stageDE_poll.sh > $OUT/poll.txt &
# —— 下面这一条会改状态, 需要主人同意; 这次只执行了一次 ——
curl -s -u <账号>:$P -H 'Content-Type: application/json' -X POST "$API/actions/workflows/sdtm-rag.yml/dispatches" \
  -d '{"ref":"main","inputs":{"tag":"613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7","deploy":"true","force_data_mismatch":"false"}}'      # 204
# 运行结果与日志 (run id 219; job 465 = deploy, 466 = deploy_public)
curl -s -u <账号>:$P "$API/actions/runs/219"; curl -s -u <账号>:$P "$API/actions/runs/219/jobs"
curl -s -u <账号>:$P "$API/actions/jobs/465/logs" > $OUT/job_465.log; curl -s -u <账号>:$P "$API/actions/jobs/466/logs" > $OUT/job_466.log
grep -nE 'git log -1|^.{29}[0-9a-f]{40}$|部署标签|decision|Container sdtm-rag|健康检查通过|\[deploy-public\]|refuses to start' $OUT/job_465.log $OUT/job_466.log
grep -cE '<密钥形状, 口径同 p3_tunnel_leg_merge_deploy.md「推送前检查」>|eyJ[A-Za-z0-9_-]{8,}\.|study[_-]?[a-z0-9]|/Users/|/home/' $OUT/job_465.log $OUT/job_466.log   # 0 / 0
# 失败原因的对照实测 (一次性容器, 不挂数据、不带 env 文件)
VM "sudo docker run --rm -i --network none --cap-drop ALL --entrypoint python $IMG -" < $C/p3_stageDE_price_probe.py    # None None / 2764 / False
VM "sudo docker run --rm -i --cap-drop ALL --entrypoint python $IMG -" < $C/p3_stageDE_price_probe.py                   # 0.1 0.5 / 7194 / True
# 隔离单元的启动顺序 (静态读)
grep -nE 'Before=|After=|WantedBy=|Requires=|Wants=' deploy/public-net/sdtm-rag-public-isolation.service; grep -nE 'iifname|oifname|iif |oif ' deploy/public-net/isolation.nft
VM "systemctl show -p Before,After,Wants,Requires,WantedBy,UnitFileState,ActiveState sdtm-rag-public-isolation.service"
VM "systemctl show -p After,Wants,Requires docker.service"
```
