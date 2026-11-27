# P3 公开实例 chroma 的 KB 更新流程 — 设计 v0.1 (2026-11-27, 只设计, 未实现)

⚠ 未经独立审查 (本轮任务限定不开子代理, 规则 D 待补)。本轮不改 `server/` `deploy/` `.gitea/` `webchat/`, p3 合并上线内容不变。

## 1. 现状 (已读代码)
- kb-sync (`.gitea/workflows/kb-sync.yml`) 只服务**私有数据根**: `detect` 比生产 stamp, `candidate` 的 `prepare` 复制**私有生产 chroma** (含 study 集合) → `chroma_cand_<fp12>`; 候选含 study 集合, **不能**给公开实例用 (红线)。
- `deploy_public` (`.gitea/workflows/sdtm-rag.yml:252-341`) 已经对公开数据根跑 `predeploy-check`, 但只接受 `same`; 其他结果一律 `::warning::` 跳过, 公开实例保持**旧镜像 + 旧 chroma**, 这一对是自洽的。
- `deploy/kbsync/kbsync.py` 已按 `--data-root` / `--env-file` 参数化, 文件系统子命令 (detect / prepare / gate / predeploy-check / swap / restore / finish / prune) 对任何数据根都通用; `deploy_swap` 的非 KB 集合守卫对公开根是「空 == 空」, 天然通过。
  → **缺的只有两处**: kb-sync 不给公开数据根建候选; `deploy_public` 不会 swap。
- 公开数据根 `/Volumes/DevSSD/deploy-data/sdtm-rag-public/data` (chroma 只含 `sdtm_kb_v1` 4329、`meta/`、`quota.sqlite`); `.env` `/opt/sdtm-rag-public/.env` 含 OPENAI key (embedding 必需)。公开容器现为 stopped; 仓库变量 `SDTM_RAG_PUBLIC_DEPLOY` 未开。
- 预演发现 (`kb_rehearsal_bf33bab.md`): 下一版 KB 在 B 仓 `build_meta` 修好前对**两个实例**都过不了闸; 这与本设计无关, 但决定了演练顺序。

## 2. 方案比较

| # | 方案 | 闸在换入前? | 红线 | 新增维护 | 评价 |
|---|---|---|---|---|---|
| **A1** | **kb-sync 对公开数据根再跑一条** (复制公开 chroma → 只重建 `sdtm_kb_v1` → 140 题闸 → 过闸候选留在公开数据根); `deploy_public` 复用 `predeploy-check`/`deploy-swap`/`restore`/`finish`/`prune` | 是 | 候选派生自 CDISC-only 的公开 chroma, 不经过私有数据; 再加一条「只含 `sdtm_kb_v1`」断言 | kbsync.py 几乎不改; 两个 workflow 加参数化 | **推荐** |
| A2 | 从私有过闸候选复制, 删掉 study 集合后给公开用 | 是 | ✗ chroma 删集合不回收 sqlite 页 / WAL / segment 目录, study 内容可能残留在公开数据根 | 少 (省一次 $0.05 embedding) | 否决: 红线风险换 5 美分 |
| A3 | 公开容器启动时发现 stamp 不一致就自己 ingest | ✗ 先换后验 | 安全 | 少 | 否决: 无闸、每次重启可能花钱、启动慢 |
| A4 | 人工 runbook (P3.3 的做法: VM 内 docker run ingest + 手跑 140 题) | 人工 | 安全 | **每次发版人工 15 分钟** | 违背 §5「1.9 全自动, 人只看闸结果」; 只作 A1 坏掉时的兜底 |
| A5 | 拆目录: KB 集合一个 chroma 目录 (两实例共用同一过闸产物), study 集合另一个目录只挂私有 | 是 | 结构上最干净 | 改 server 读两个 chroma 路径、ingest/kbsync/部署全部改, 迁移生产数据 | 长期最省事, 但改动面大、动生产数据; 列为 P4+ 备选, 本轮不做 |

A1 的额外成本: 每次 KB 发版多一次入库 (~$0.05, ~95 s) + 一次 140 题 (~1 分钟), 在同一 concurrency 组里串行跑, 内存占用与私有候选相同 (1536m, 3.1 余量够)。

## 3. 推荐方案 A1 细节

### 3.1 kb-sync: 两条腿 (私有 → 公开, 串行)
- 把现有单 job 参数化为 `instance ∈ {private, public}` (两个 job 或 matrix + `max-parallel: 1`, 实现时选更简单的写法), 每条腿自带:
  `DATA_ROOT`、`ENV_FILE`、`CONTAINER` (`sdtm-rag-api` / `sdtm-rag-public-api`)。
- 公开腿门控: 公开数据根存在 (detect 前 `--via` 检查) 且 `vars.SDTM_RAG_PUBLIC_DEPLOY == 'true'` (或单独变量, 见 §5 D4)。
- 两条腿各自 `detect` (比各自 stamp): 私有 same、公开 changed 也能单独补建。⚠ kb-sync 只**建候选**, 换入只发生在部署工作流里: 公开落后时, 要等下一次部署 (任意 push 到 main, 或手动 dispatch 一次 `sdtm-rag` 并把 tag 设为当前线上 SHA) 才会换入。实现时可以加一个「只跑 deploy_public」的 dispatch 入口, 免得为了换公开数据而重部署私有站 (算在 D3 里)。
- **公开腿基线镜像**: 公开容器存在 (含 stopped) 用其镜像, 否则用私有线上镜像。基线只在候选副本上跑, chromadb 迁移只碰副本。
- 候选镜像: 两条腿共用同一 `sdtm-rag-kbcand:<fp12>`, 只 build 一次, 两条腿都结束后再删。

### 3.2 kbsync.py: 只加一道断言
- `gate` (或 `candidate` 收尾) 加 `--kb-only`: 用 `collections()` 读候选副本, 要求集合恰好 `{sdtm_kb_v1}`, 否则 FAIL 归档。公开腿必开; 每次更新都重新断言, 不信任「上次是干净的」。
- 其余函数不改。`prepare` 复制公开 chroma (只有 KB 集合, ingest 会整集合重置), `meta/` 整目录复制后 `build_meta` 覆盖 meta.yaml。

### 3.3 deploy_public: 从「same 或跳过」改为「same / swap / 跳过」
| predeploy-check | 动作 | 公开站状态 |
|---|---|---|
| `same` | 现流程 (up -d → 验收) | 新镜像 |
| `swap` (有过闸公开候选) | stop 公开 → `deploy-swap --kb-only` → up -d → 验收 (健康 / 档位 / openapi 404 / freshness rc=0) → `finish` + `prune --keep 2` | 新镜像 + 新 chroma |
| `missing` / `unknown` | `::warning::` 跳过 (同现状) | 旧镜像 + 旧 chroma (自洽) |
| `journal_pending` | job 失败 (不动) | 保持现状, 人工 restore/finish |
- 失败处理顺序 (swap 之后才失败): **先 `restore` 退数据 → 再按 §5 D2 决定停机或退回旧镜像**; journal 状态无法判断时一律停机不启动 (与私有 job 同一原则)。
- 私有 job 不受影响: `deploy_public` 仍 `needs: deploy`, 失败只影响公开实例。
- 维护成本: swap/restore 的 shell 片段与私有 job 重复约 40 行。实现时抽成 `kbsync.py` 的一个编排子命令 (如 `deploy-swap-public`, 内部调用已有函数) 或一个 composite 脚本, 避免两份 shell 漂移。

### 3.4 本地「KB 更新」流程
不变。推 submodule 升级后: 私有缺过闸候选 → 部署失败 (现状); 公开缺候选 → 只告警跳过, 由第二天 kb-sync 补建, 下次部署再换入。

### 3.5 失败时公开站状态 (总表)
| 失败点 | 公开站 |
|---|---|
| 公开腿 ingest / eval / 闸 FAIL / 混入非 KB 集合 | 不变 (候选归档 `chroma_failed_*`, 不删) |
| deploy_public 预检 missing | 不变 (旧镜像 + 旧 chroma) |
| swap 后健康 / 档位 / freshness 失败 | 数据退回旧 chroma; 镜像按 D2 |
| journal 残留或无法判断 | 停机, 人工处理 |

## 4. 实现时要改的文件
| 文件 | 改动 |
|---|---|
| `.gitea/workflows/kb-sync.yml` | 两条腿参数化; 公开腿门控; 候选镜像共享与清理 |
| `.gitea/workflows/sdtm-rag.yml` (`deploy_public`) | 接受 `swap`; 失败先 restore; finish/prune |
| `deploy/kbsync/kbsync.py` | `--kb-only` 断言; (可选) 公开换入编排子命令 |
| `tests/test_kbsync*.py` | `--kb-only` 正反例; 公开根 detect/swap/restore; 规则 5 变异验证 (去掉断言 → 测试必须红) |
| `deploy/README.md`「KB 同步」 | 两实例流程、失败处置、人工兜底 (A4 runbook) |
| `.work/10_split_and_public/PLAN.md` 1.9 | 验收拆为「私有正例」+「公开正例」 |
- 实现须在 B 仓 `build_meta` CT 解析修复 (预演结论) 之后或同批做; 两者都在部署路径过滤内, 推 main 即部署。

## 5. 待用户裁定 (不替用户定)
- **D1 公开闸失败的处理**: 推荐「公开保持旧镜像 + 旧数据, 只告警, 不阻断私有部署」; 备选「公开闸失败也让整次部署失败」。
  附带问题: 现状是公开 chroma 一落后, **所有**公开部署 (含纯代码 / 安全修复) 都被跳过, 直到补建候选。是否接受? 备选: 允许代码修复照常上公开站、chroma 暂时落后 (与私有「不匹配即失败」不一致, 需单独授权)。
- **D2 swap 后验收失败**: (a) 退回数据后停机 (现 3.2「失败一律停机」原则, 最保守); (b) 退回数据 + 退回旧镜像继续对外 (可用性好, 但要写和私有 job 同样复杂的退回逻辑)。
- **D3 1.9 正例的节奏**: pedia 可能在 A1 实现前打 tag。(a) 正例先只验私有; A1 上线后由 kb-sync 补建公开候选, 再由一次部署 (push 或手动 dispatch) 换入并补验 (推荐, 不挡 pedia 发版); (b) 等 A1 实现后两实例一起演练。
- **D4 演练前置**: `SDTM_RAG_PUBLIC_DEPLOY` 未开, 公开容器 stopped。公开 swap 演练需要 (a) 先开变量 (deploy_public 会 `up -d` 起公开容器, 不发布端口、无隧道, 不对外); 或 (b) kb-sync 公开腿用独立变量 (如 `SDTM_RAG_PUBLIC_KBSYNC`) 先跑候选, 换入等 3.4 前再开。
- **D5 修复顺序** (来自预演): B 仓的修复 (CT 写法解析、`_model_defhome` 多文件归属规则、KB 计数锚点测试; 见 `kb_rehearsal_bf33bab.md`), 是否在 pedia 打 tag **之前**先合进 main 并部署 (CT 解析补丁已验证在旧 KB 下 meta.yaml 逐字节不变; `_model_defhome` 的新规则要另外验证)。推荐是。另外 `_model_defhome` 的规则本身也要用户裁定: 变量在多个 model 文件都有定义行时, 归到哪个文件。

## v0.2 修订 (2026-11-27, 独立审查后; 与上文冲突处以本节为准)
审查: `p3_public_kb_update_design_review.md` (`oh-my-claudecode:security-reviewer`, PASS-with-fixes)。顶部「未经独立审查」一句作废。

1. **红线不变量写明**: 公开 chroma 的唯一来源 = 公开数据根自身 (prepare / swap / restore 只在同一数据根内复制和改名); 实现时加测试: kbsync 没有任何子命令同时接受两个数据根。chroma 删除不回收空间在 A1 也存在, 但残留只可能是旧版 CDISC, 不碰红线; `--kb-only` 只查逻辑集合, 物理隔离靠上面这条不变量。
2. **`--kb-only` 改为两层** (替换 §3.2): (a) `candidate` 编排里, 候选 eval 之后、gate 之前, 用候选镜像读候选副本的集合, 必须恰为 `{sdtm_kb_v1}`, 否则 `fail --reason kb_only_violation` 归档 (不能放进 gate: gate 走 `--via`, 兄弟容器调不了 docker, 且 gate PASS 后标记已写); (b) `deploy-swap --kb-only` 对守卫副本上的**线上 chroma 与换入源**都断言 `non_kb == {}` —— 这是主闸, 也覆盖 `chroma_prev_*` 换入源和「公开线上已被污染 / 数据根指错」。
3. **失败路径补状态** (补充 §3.3 / §3.5):
   - 预检记录 `prev_image` 与 `prev_running` (公开容器当前就是 stopped)。数据退回后容器回到 `prev_running`: 原本停止就保持停止, 绝不因「退回」把公开站拉起。
   - 一切退回动作先查 `journal-state`: 0 继续; 2 / 3 停机, 人工处理。
   - job 取消 / 超时: 只停公开容器, 不碰数据; 残留 journal 由下次 `journal_pending` 拦住。`timeout-minutes` 实现时按守卫副本复制 + 集合摘要的实测时间重估。
   - restore 失败: journal 保留 → 下次 deploy_public 与 kb-sync 公开腿都 `journal_pending` 失败; 两条腿分 job (见 5), 私有腿不受牵连。
   - 允许的组合态: 私有 swap 成功 + 公开失败 → 私有 = 新镜像 + 新 chroma, 公开 = 旧数据 + (停机或旧镜像, 按 D2)。
4. **路径一致性断言** (新增): deploy_public 预检和 kb-sync 公开腿都断言 `PUBLIC_DATA_ROOT` / `ENV_FILE` 与 `docker compose -f compose.public.yml config` 解析出的挂载源一致, 且公开根 ≠ 私有根; 不一致即失败。误用私有 `.env` 不涉红线 (挂载的仍是公开根), 属成本隔离。
5. **两条腿 = 两个 job** (替换 §3.1「实现时选」): `public` job `needs: private` + `if: always()`, 私有腿失败不挡公开腿; 候选镜像构建条件改为「任一腿 changed」, 构建与删除放独立 job / 步骤, 删除加 `always()`。
6. **§4 更正**: 部署路径过滤 (`sdtm-rag.yml:10-25`) 含 `scripts/**` 与 `.gitea/workflows/sdtm-rag.yml`, **不含** `deploy/kbsync/**` 和 `kb-sync.yml`。`kbsync.py` 从 checkout 运行、不在镜像里, 改了不需部署, 下次 workflow 运行即生效; 只改 `tests/` 不跑 CI, 必须本机跑。所以: CT 解析修复 (`scripts/`) 推 main 会部署; A1 里改 `sdtm-rag.yml` 的部分会部署, 只改 `kb-sync.yml` / `kbsync.py` 的部分不会。
7. **A2 否决理由调整主次**: 主理由 = 引入私有根 → 公开根的数据通道, 破坏单一来源不变量; sqlite / WAL / segment 残留 (与 chromadb 版本有关) 为次要理由。
8. **新增方案 A1'**: 公开候选从**空目录全新入库** (基线在复制出的旧副本上跑, 候选写新目录), 物理文件只有一版 KB, 不会因多次重置越积越大。embedding 成本与 A1 相同 (ingest 本来就整集合重算)。见 D6。
9. **meta/ 来源** (补 §3.2): 公开根 `meta/` 只由 P3.3 的 `build_meta` 生成; `implicit_relations.json` server 不读; prepare 只在同根内复制 → 安全。
10. **§4 文件清单补**: `tests/test_deploy_public_compose.py` (`test_public_job_gated_and_separate` 检查 deploy_public 结构, 须同步改); 一致性断言与两 job 隔离的测试; `kb-sync.yml` / `kbsync.py` 文件头注释 (现写只服务私有根); `docs/PROGRESS.md`; `_progress.json` `decisions_p3.open`。

### 新增待裁定点
- **D2 补充子问题**: 公开站部署前就是停止状态时, 失败后「退回」= 保持停止 (本节第 3 条的默认), 还是视为「退回到旧镜像并启动」?
- **D6** 公开候选: 复制公开 chroma 后重置 (A1, 与私有腿同一代码路径) vs 空目录全新入库 (A1', 物理上更干净, 但候选构建与私有腿分叉)。
- **D7** 公开根里的 `chroma_failed_*` / `chroma_prev_*` / `kbsync_eval` 都在公开容器挂载范围内: 原地保留 (与私有一致), 还是移到公开容器挂载之外的归档目录、失败归档保留几份?
- **D8** 两条腿的隔离: 本节第 5 条的两 job 方案是否接受 (推荐), 或保持单 job 串行 (失败互相牵连)。
