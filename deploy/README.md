# 部署 (容器, mini 虚拟机)

> 2026-11-04 起生产跑在 mini 的 Lima 虚拟机 `deploy` 里的 Docker, 取代 launchd 版 (plist 模板 2026-11
> 已删, 见 git 历史)。运维 (虚拟机 / 端口转发 / 监控 / 日志 / `svc`) 见 lan-services 仓库 README。

## 组成

| 文件 | 作用 |
|------|------|
| `container/Dockerfile` | 构建上下文 = 本仓根 (checkout 须含 submodule: `git submodule update --init --depth 1`); 代码 `/app`, KB `/app/vendor/sdtm-pedia/knowledge_base` (只拷 KB, sdtm-pedia 其余不进镜像) |
| `container/Dockerfile.dockerignore` | 只放镜像需要的目录 |
| `container/compose.yml` | `api` 8000 + `ui` Streamlit 8501 (只转发到 mini 本机); `data/` → `$APP_DIR/data`, `.env` → `$APP_DIR/.env` (只读; `APP_DIR` 缺省 `/app`) |
| `../.gitea/workflows/sdtm-rag.yml` | push main → 测试 → 构建 → 推镜像 → 部署 → 健康检查; checkout `submodules: true` (公开 GitHub 仓, 无需凭据) |
| `../.gitea/workflows/kb-sync.yml` + `kbsync/kbsync.py` | KB→RAG 同步（step 1.9）：手动派发时检测 A 仓的 `kb-*` tag（留空 = 最新的），在生产数据副本上入库并运行 CDISC 闸；详见下文「KB 同步」 |
| `container/compose.public.yml` + `container/compose.tunnel.yml` + `public-net/` | 公开实例、Cloudflare 隧道连接器、网络隔离规则；详见下文「公开实例与隧道」 |
| `deploy.sh` + `.env.service.template` | **遗留** (launchd 时代服务目录同步), 删除候选 |

宿主侧: 数据 `/Volumes/DevSSD/deploy-data/sdtm-rag/data` (chroma / study / 反馈记录); 密钥 虚拟机 `/opt/sdtm-rag/.env` (600)。
两个挂载都设 `create_host_path: false`: 挂载缺失直接起不来, 不会带着空数据「健康」启动。

## 发版

push 到 Gitea `main` (路径过滤见 workflow) → 自动部署, 镜像标签 = commit SHA。

改了 `webchat/`: 发版后让同事 `Cmd+Shift+R` (Win `Ctrl+F5`) 强刷一次 —— 修 `Cache-Control` 之前存进浏览器的
旧条目 (启发式新鲜期实测 ≈3 天) 不回源, 症状是"新控件整排消失", 不是后端问题。回归闸:
`tests/test_webchat_cache_headers.py` 常驻; `tests/test_webchat_cache_browser.py` (真浏览器, 默认 skip) 改前端后手动跑。

## KB 同步 (kb-sync)

目录身份只由 chroma stamp 中的 `kb_fingerprint` 确定（候选目录另加 `kbsync_gate.json`），不使用 SHA。数据根（`deploy-data/sdtm-rag/data`）下的目录如下：

| 目录 | 含义 |
|------|------|
| `chroma/` `meta/` | 生产数据 |
| `chroma_cand_<fp12>/` `meta_cand_<fp12>/` | 通过 kb-sync 闸的候选（marker 中为 `verdict=PASS`），等待部署时换入 |
| `chroma_prev_<fp12>_<ts>/` `meta_prev_*` | 被换下的旧生产数据，用于回滚；部署成功后保留最新 2 份 |
| `chroma_failed_<fp12>_<ts>[_stale]/` `meta_failed_*` | 未通过闸或中途中断的候选，**永不自动删除**（规则 B）；磁盘空间紧张时人工清理 |

1. **kb-sync**（**只有手动派发**，没有定时触发）。什么时候派发：pedia 发了新的 `kb-*` tag 之后派发一次；想确认现状时也可以
   派发（指纹没变就是 no-op，不入库、不花 embedding 费用）。怎么派发：Gitea 的 Actions 页面里选 `kb-sync` → 运行工作流，
   `ref` 留空 = 取 A 仓最新的 `kb-*` tag，也可以填某个 tag 或 40 位 commit；`public_baseline_image` 只有公开腿选不出基线镜像
   时才填（见下文「公开实例」）。
   不用 Gitea 的定时触发（2026-11-28 从工作流里去掉；协调方受托代裁）：这台 Gitea 只在「头提交不带跳过标记的 push 到 main」
   时登记定时任务，而且登记之后用的是那一刻的工作流内容和提交，之后带 `[skip ci]` 的 push 不刷新。原先写的每天 03:17 因此
   从来没有被登记、一次也没跑过；留着它，哪一次不带标记的 push 就会让它悄悄登记上，从此每天用旧代码无人值守运行。
   需要自动同步时另行设计（倾向：系统定时器调用手动派发接口，每次用的都是当前 main），不要把 `schedule` 加回工作流
   （`tests/test_workflow_conditions.py` 钉着）。
   派发之后：如果 A 仓 KB 指纹与生产 stamp 相同，或该指纹已有过闸候选，
   则不做任何操作（no-op）。否则，先在本机构建候选镜像（不推送），再复制生产 chroma/meta 作为副本；用**当前生产镜像**
   在副本上运行 CDISC 140 题 retrieval-only 评测，结果作为基线；然后用候选镜像运行 `scripts.ingest --no-backup`
   （只重建 `sdtm_kb_v1`）和 `scripts.build_meta`，再运行同一评测。
   闸条件：候选 stamp 指纹与检测到的指纹一致；两边题号集合相同，且不少于 140 题；逐题 `source_recall` 回退
   （缺题也算回退）不超过 1 题；候选满分题数不低于基线减 1；候选 `summary.source_recall_avg` ≥ 0.95。
   评测崩溃或结果为空时判为 FAIL。
   闸结果只输出计数和题号。但如果某一步（eval、ingest 或 build_meta）以非零状态退出，会输出该步 stderr 的最后 20 行
   （只涉及 CDISC 题集，不含研究数据）。marker 中记录候选镜像的 chromadb 版本；部署时如果目标镜像的 chromadb 版本
   与之不同，则不选用该候选。
2. **「KB 更新」**：在本地升级 submodule 并 push，触发**部署**。如果目标镜像的 KB 指纹与生产 stamp 不同，部署按以下
   顺序换数据：停止服务；在**副本**（`kbsync_guard_<ts>/`，用完即删）上核对候选与生产的非 KB 集合（名称、条数、
   内容摘要）是否一致；通过改名换入候选（journal 记在 `kbsync_swap.json`）；启动服务；健康检查；确认
   `check_index_freshness` 返回 rc=0；最后删除 journal 并执行 prune。
   如果非 KB 集合不一致，说明候选建好后 study 集合发生过变化，此时拒绝换入，需要重新运行 kb-sync。
   换到一半失败时，先按 journal 回退数据，再启动原容器。
   找不到过闸候选或保留副本时，部署失败，**生产保持不变**。
   如果数据根残留 journal（上次 job 被取消或超时），任何部署（包括 force）都会在一开始失败，需要人工执行 `restore`
   （或在确认换入已生效后执行 `finish`）。
3. 人工排查：`python3 deploy/kbsync/kbsync.py --via <镜像> detect|predeploy-check|swap-status --data-root <数据根> ...`
   （job 容器无法访问数据根，所有文件操作都在兄弟容器中执行）。

### 公开实例（P3；仓库变量 `SDTM_RAG_PUBLIC_DEPLOY=true` 时才启用，默认关）

公开数据根 `deploy-data/sdtm-rag-public/data`，目录约定同上表。公开 chroma 只含 `sdtm_kb_v1`，**唯一来源是公开数据根自身**：
kbsync 每次调用只接受一个数据根，复制和改名都在这个数据根之内，没有从私有数据根到公开数据根的数据通道。
本小节讲数据和部署流程（kb-sync 公开腿、`deploy_public`）；入口这一侧（隧道、可信代理、限流、HTTPS、网络隔离、起停连接器）
见下文「公开实例与隧道」。

1. **kb-sync 公开腿**（`kb-sync.yml` 的 `public` job，排在私有腿之后；私有腿失败不挡它，它失败也不影响私有腿）。
   与私有腿走同一段代码（`kbsync.py candidate`），另加：
   - 路径一致性断言：数据根和 env 文件必须就是 `compose.public.yml` 的挂载源，且与私有 compose 的挂载源不重叠；
   - embedding key 检查（公开站用自己的 OpenAI key）：key 无效或额度用尽时 job 失败，日志写明类别；
   - 基线镜像：公开容器的镜像优先，容器不存在时用私有线上镜像；**镜像内 KB 指纹必须等于公开 chroma 的 stamp**，
     否则不用它（基线评测用镜像自带的题集和 KB，不配对会让闸变松）。两个都不配对时 job 失败——手动运行 kb-sync，
     在 `public_baseline_image` 里填一个配对的镜像：只接受本仓镜像仓库里按 commit 打标签的镜像
     （`<镜像仓库>/sdtm-rag:<40 位 SHA>`），且须已在部署机本地；通常是上一次成功部署到公开站的镜像。不在本机的镜像一律不用；
   - `--kb-only`：候选建完、过闸之前，集合必须恰为 `sdtm_kb_v1`，否则以 `kb_only_violation` 归档。
   公开腿任何一步失败，job 都是红的；公开站保持旧镜像和旧数据。失败归档（`chroma_failed_*`）原地保留。
   **候选镜像（与设计 v0.2 第 5 条「只构建一次」的已知出入，协调方接受）**：没有单独的构建 / 清理 job，两条腿需要时各自
   `docker build`、结束时各自删除自己构建的镜像（成功失败都删）。不会出现两条腿用了不同镜像的情况：两条腿是同一次运行、
   同一个提交的 checkout，镜像标签是 KB 指纹的前 12 位——标签相同就意味着仓库提交相同、KB 内容相同，构建出来的镜像内容
   相同（第二次构建通常直接命中层缓存）；两条腿解析到不同的 KB 时指纹不同、标签也不同，各用各的。
   运行被取消、或删除时镜像还被占用的话，候选镜像可能残留，人工清理：`docker images sdtm-rag-kbcand`，再逐个 `docker rmi`。
2. **公开部署**（`sdtm-rag.yml` 的 `deploy_public` job，编排在 `kbsync.py deploy-public`）：
   - **红线检查**：先在副本上读线上公开 chroma 的集合。发现 `sdtm_kb_v1` 以外的集合 → 先看 journal（有残留或判不出就保持
     现状并失败），否则**停掉公开站**并失败——不管这次换不换数据，也不管有没有候选（排在「缺候选就跳过」之前）。
     失败信息会列出发现了哪些集合。原样写出的只有本仓现用的三种写法：`sdtm_kb_v<1–3 位数字>`、`study_st<2–3 位数字>`、
     `study_st<2–3 位数字>_docs`；其余的名字可能带着真实研究的标识，只写指纹（sha256 前 10 位）和长度。
     这是故意偏严的检查：将来正当新增一个 KB 集合也会触发，那时要改 `deploy/kbsync/kbsync.py` 的 `KB_COLLECTION` 及其测试，
     并核对 `server/instance.py` 的 `check_chroma`。处理完之后重新运行 `sdtm-rag` 工作流，再人工 `docker start`。
   - 只读预检，不通过就什么都不动：镜像下限（`deploy/public-net/image_floor_check.py` 经标准输入送进待部署的镜像里执行，
     判据是两条都满足：`server.auth.PUBLIC_EDGE_LEVEL >= 1`；实际调一次「可信代理必须是单主机地址」的检查，写成网段确实被拒。
     合格 = 退出码 0 并且输出恰好是 `image-floor: ok`。标记是镜像自己声明的，所以第二条防「标记在、实现不在」。
     隧道这一步之前的镜像没有这个标记，拒绝；用 tag 回滚到旧镜像时也会被拒。它不是在查响应里有没有 HSTS——
     HSTS 只是这个级别包含的几项之一，各项见下文「公开实例与隧道」）；
     公开网络 `sdtm-rag-public` 的子网必须是 compose 里写定的那个（不是就先做网络重建，见
     `docs/plans/P3_4_tunnel_drill.md` 第 2 步）；网络隔离核对（公开网络里的一次性容器连不上内网、默认网桥上的对照容器
     连得上，由 `deploy/public-net/isolation_probe.py judge` 判定；目标清单在 `sdtm-rag.yml` 的 `ISOLATION_LAN` /
     `ISOLATION_EGRESS`，与演练第 3 步保持一致）。
   - 再用新镜像起一个**临时容器**验收：数据是公开数据根的副本（放在数据根的上一级 `kbsync_accept_<ts>/`，只含 chroma 和
     meta，不含 `quota.sqlite`；有过闸候选要换入时用候选的副本），另一个 compose 项目，**没有网络**（`network_mode: none`，
     不加入公开网络）、无端口；环境变量照抄 compose。验收项：健康、档位 = public、内部接口关闭、`check_index_freshness`、
     集合恰为 `sdtm_kb_v1`。
     容器没有进入 healthy 时（临时容器和正式容器复验都一样），日志末尾 40 行会打进 job 日志，最后一条报错写进失败原因和摘要。
     带出之前过两道（`kbsync.py` 的 `_sanitize_log`，步骤顺序固定，原因写在函数说明里）：key 片段换成 `<已隐去>`；
     从 `study` 起的词按上面红线检查的同一张白名单处理（公开档启动自检发现 study 集合时会把名字列进报错；
     配置项的名字如 `study_docs_enabled` 照常写出）。
     **前提（挡不住的三种情形）**：① 名字里没有 `study` 的集合——只有公开站的 `.env` 把 `SDTM_RAG_STUDY_COLLECTION_NAME` /
     `SDTM_RAG_STUDY_DOCS_COLLECTION_NAME` 配成了别的名字、公开 chroma 里又恰好有这个集合时，启动自检才会列出这样的名字；
     ② 路径里的目录名——启动自检发现研究数据目录时会把路径原样列出来，默认配置下路径里只有代号；③ 名字里带空白、引号、
     括号之类的分隔符（chromadb 不允许）。所以公开站的 `.env` 里不要设 `SDTM_RAG_STUDY_*` 这一组键（集合名和路径都不要）。
   - **换模型时必须同时固定价格**：公开站走服务端 key 的每一个模型——可选模型（公开站 `.env` 的
     `SDTM_RAG_SELECTABLE_MODELS`）、内部四档（`SDTM_RAG_DEFAULT_MODEL` / `FALLBACK_MODEL` / `HARD_MODEL` / `LIGHT_MODEL`）、
     `SDTM_RAG_EMBEDDING_MODEL`——都要在 `server/cost.py` 的固定价格表 `_PRICES` 里有一行，数值取自服务商的官方定价页；
     价格按提示词长度分档的模型，高的那一档写进同一个文件的 `_LONG_PROMPT_PRICES`。公开档不用 litellm 的价格表给这些模型定价
     （litellm 的在线价格表要联网才取得到，临时容器没有网络）。表里没有的，公开档拒绝启动，报错里写明是哪个设置项、哪个模型
     （`fallback_model (SDTM_RAG_FALLBACK_MODEL) = '<模型串>': no pinned price`，可选模型是
     `selectable model '<id>' (<模型串>): no pinned price`）：部署停在临时容器验收，公开站保持不变。
     顺序：先加价格并合并，等带着新价格表的镜像部署到公开站，再改公开站 `.env`——反过来做，正式容器下一次重启时会拒绝启动。
     私有档没有这条要求。
   - **一轮答题的预留上限也看回退档**：每个可选模型「一轮答题的最坏预留额」不得超过免费池的十分之一，算的是它自己和它
     回退到的那一档（`SDTM_RAG_FALLBACK_MODEL` + `SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS`）里较贵的；运行时每次答题也按较贵的
     预留。回退档换成更贵的模型、或把它的输出上限调大，都可能让公开档拒绝启动（报错会指向回退档）。例：回退档是 Haiku 5.5 时，
     输出上限不超过 108,000 才通过。
   - 临时验收通过后做答题 key 的有效性探测：公开网络里的一次性容器，只调 Anthropic 的「列出模型」，不发答题请求；
     key 不进日志和命令行。该接口不产生 token，按此推断不计费（官方文档没有专门的计费条目）；它只验 key 是否有效，
     验不了额度。Anthropic 接口暂时不可用时这一项也会不通过。
   - **预检、临时验收、key 探测任何一项不过**：正式容器和正式数据都不动，旧版继续对外。成功和失败都会清掉临时容器和副本。
   - 验收通过后才动正式容器。镜像 KB 指纹与公开 chroma 不同时：先在副本上做换入核对（`--kb-only`：线上与换入源都
     不得有非 KB 集合），通过后停正式容器 → 换入 → 用新镜像起 → 复验 → 删 journal、prune。
   - 公开 chroma 落后而没有过闸候选：只告警并跳过，公开实例不动（等公开腿建出候选，下一次部署换入）。
   - **动过正式容器之后的任何失败 → 停机**：先停，再看 journal，能退数据就退，保持停止；不自动退回旧镜像，
     也不启动任何东西。日志和摘要会写明停下来的容器是哪个镜像：如果已经换成了没通过的新镜像，**不要直接
     `docker start`**（那会是新镜像配旧数据）；排查后重新运行 `sdtm-rag` 工作流。
   - 临时验收要几分钟。动正式容器之前会重新读一次它的状态，以那一刻为准：验收期间被人工停下的不会被拉起。
   - job 被取消或超时：兜底步骤先结束还在跑的编排进程（连同它起的 docker 子进程：先 SIGTERM，最多等 5 秒，还在就 SIGKILL），
     再只在正式容器已被动过时停掉公开项目；不碰数据。已经退出、只是没被回收的进程（僵尸；runner 的 job 容器里 1 号进程
     不回收孤儿）不算「还在」，判成只剩僵尸时收工前仍补发一次 SIGKILL；判断不了的时候（读不到 `/proc`）按还在处理，照常停机并复查。
   - **部署前就是停止的（或容器不存在）**：照常更新数据和镜像，但**保持停止**。启动需人工，在部署机上执行
     `docker start sdtm-rag-public-api`——首次上线和故障停机后的恢复都走这一步。
3. **人工兜底**（公开腿坏掉时）：在部署机上用镜像直接重建公开 chroma（挂公开数据根和公开 env 文件运行
   `python -m scripts.ingest --no-backup` 和 `python -m scripts.build_meta`），再手跑 CDISC 140 题对照基线；做法见
   `.work/10_split_and_public/evidence/checkpoints/p3_step3.3.md`。

## 公开实例与隧道

> **状态（2026-11-28）：公开实例已部署并启动，但没有对外入口；演练方案做到第 5 步（含 5a、5b）。**
> 已经做完的：公开网络重建为固定网段 `10.201.8.0/24`（网桥 `br-sdtmpub`），隔离规则（nft 表 `inet sdtm_rag_public_isolation`）
> 和每分钟一次的巡检定时器已装并启用（`.work/10_split_and_public/evidence/checkpoints/p3_stageB_network_isolation.md`）；
> 公开部署开关 `SDTM_RAG_PUBLIC_DEPLOY` **已打开**，kb-sync 公开腿建出过闸的候选（`p3_stageC_public_candidate.md`）；
> 第一次公开部署试了两次：第一次（run id 219）在「临时容器验收」失败（没有网络的临时容器里，公开档的启动自检给免费模型定不了价；
> `p3_stageDE_first_public_deploy.md`），把价格固定进代码之后（`public_price_pin.md`、`public_price_pin_ext.md`）第二次（run id 221）成功：
> 候选已换入、公开容器换成新镜像，随后人工启动并做完第 5 步的核对（`p3_stageDE_second_attempt.md`）。
> **现在**：公开容器 `sdtm-rag-public-api` 运行中（`healthy`，镜像与私有站相同），公开线上 chroma 是 `kb-2026.11.28`；
> 没有发布端口、没有连接器、没有 token、没有隧道——只有虚拟机本机连得到它。它的重启策略是 `unless-stopped`：
> 虚拟机或 docker 重启后会自己起来，重启之后要重跑隔离探测（见本节末尾「网络隔离」一条）。
> 还没有做的：连接器和隧道（第 6 步起）；公开站一次真答题都还没有发过（Anthropic key 只验了有效性，没有验额度）。
> ⚠ 开关开着：头提交不带 `[skip ci]`、又命中部署路径过滤的 main push，以及手动运行 `sdtm-rag` 时没有取消勾选 `deploy`，
> 都会在私有部署之后带上公开部署（公开实例在运行时：临时验收 → key 探测 → 换新镜像 → 复验；这条路还没有在真机上走过）；
> 只改文档或测试的提交必须带 `[skip ci]`。私有站要回滚到这次之前的镜像时先关开关（原因见那份记录的「回滚办法」）。
> 所以本节里凡是讲连接器、隧道、Cloudflare 一侧的内容，描述的都是按演练方案做完之后的样子。
> 「网络隔离」这一条现在成立的范围以阶段 B 的记录为准（只验了 TCP、7 个内网目标；规则先于容器装入的开机顺序还没有验），
> 2026-11-28 公开容器启动之后又探测过一次，结论 PASS。
> 上线后把这段状态说明改掉。

本节讲入口这一侧。公开数据怎么来、公开部署每一步做什么（红线检查、镜像下限、临时容器验收、失败后停机、中断兜底）
见上文「KB 同步」里的「公开实例」小节。

公开站 `sdtm.bojiang.org` 的入口只有 Cloudflare 隧道：访客 → Cloudflare → 连接器容器（cloudflared）→ 公开实例。
公开实例和连接器都不发布宿主端口。上线步骤见 `docs/plans/P3_4_tunnel_owner_steps.md`（主人在 Cloudflare 后台做的部分）
和 `docs/plans/P3_4_tunnel_drill.md`（虚拟机里的部分，含每一步的回退）。

| 项 | 值 | 定义在 |
|----|----|--------|
| docker 网络 | `sdtm-rag-public`，子网 `10.201.8.0/24`，网桥 `br-sdtmpub`，不启用 IPv6 | `container/compose.public.yml` |
| 公开实例 | 容器 `sdtm-rag-public-api`，端口 8000，动态地址（只从 `10.201.8.128/25` 分配） | 同上 |
| 连接器 | 容器 `sdtm-rag-public-cloudflared`，静态地址 `10.201.8.2`，独立 compose 项目 `sdtm-rag-public-tunnel` | `container/compose.tunnel.yml` |
| 可信代理 | `SDTM_RAG_QUOTA_TRUSTED_PROXIES=10.201.8.2`，写在公开实例的 `environment`，压过 `.env` 里的同名键 | `container/compose.public.yml` |
| 全局限流 | 每个访客 IP 每分钟 60 个请求、突发 20；不计 `/`、`/static/*`、`/api/health`。三个 `SDTM_RAG_RATE_LIMIT_*` 键写在公开实例的 `environment` | `container/compose.public.yml` |
| 隧道 token | 虚拟机内 `/opt/sdtm-rag-public/cloudflared/tunnel-token`（属主 `65532:65532`，权限 `400`；所在目录 `root` `700`） | 主人手工放置 |
| 隔离规则 | nft 表 `inet sdtm_rag_public_isolation`，由 systemd 单元在 docker 之前装入；另有每分钟一次的巡检 | `public-net/isolation.nft`、`public-net/sdtm-rag-public-isolation*.{service,timer}` |

子网、连接器地址、可信代理、规则里的网段和网桥名是同一组事实，改一处必须同时改其余几处（`tests/test_deploy_public_tunnel.py` 逐处核对）。
子网选在 `10/8`：虚拟机现有网络占用 `172.17`–`172.31` 各段和 `192.168` 的若干段，docker 自动分配也只用这两段，不会撞上。

- **只信连接器**：公开实例只在连接对端是 `10.201.8.2`、且请求里恰好有一条 `CF-Connecting-IP` 时采信它。
  同一网络里别的地址带这个头来，或者带了两条，都按连接对端计。可信代理必须是单主机地址，写成网段会拒绝启动。
  公开实例的 `FORWARDED_ALLOW_IPS` 置空：uvicorn 默认会采信来自回环的 `X-Forwarded-For` 并改写连接对端，置空后谁的都不信。不要放宽它。
- **限流有两层**（主人 2026-11-28 定）。应用里的一层就是上表的全局限流，按连接器传来的访客 IP 计；它比提问接口自己的限额宽
  （每 IP 每分钟 20 题、突发 6，另有每访客的），正常用户先碰到的是提问限额那条带说明的拒绝，全局这一层只挡对便宜接口的灌水。
  Cloudflare 的一层是主人在后台建的一条限速规则（`/api/` 前缀，同一 IP 10 秒超过 50 次挡 10 秒；免费套餐只能建 1 条、不能限定主机名）。
  要调其中一层时两边一起看：Cloudflare 的阈值要高于应用在 10 秒内会放行的数量（现在是 30）。
  这三个键是 `Settings` 字段，环境变量名不分大小写：公开站的 `.env` 里如果有取值不同的大小写变体，会压过部署配置里的值，
  所以公开档启动时发现这种冲突就拒绝启动（报错只列键名），私有站不做这项检查。
- **首次上线先只放行主人**（主人 2026-11-28 定）：先建 Cloudflare Access 应用，再加路由；隧道层的验收全部通过后才放开。
  撤入口配置时顺序相反：先删路由，再删 Access 应用（路由还在时删 Access 应用 = 对所有人开放）。
- **HTTPS**：公开档的 cookie 一律带 `Secure`（显式关掉会拒绝启动），响应带 `Strict-Transport-Security: max-age=31536000`。
  「只信连接器」的两条和这里的两条合起来就是镜像下限的第 1 级（`server/auth.py` 的 `PUBLIC_EDGE_LEVEL = 1`）；
  公开部署的预检按这个标记拒绝更早的镜像，判法见上文「公开实例」小节。
  这个头由应用自己发，只对 `sdtm.bojiang.org` 生效；不要打开 Cloudflare 的全域 HSTS 和 Always Use HTTPS 开关（会影响同域名的其他子域名）。
  明文跳转用一条只匹配该主机名的重定向规则。私有站不受这些影响（局域网里走 HTTP）。
- **token**：连接器通过 `TUNNEL_TOKEN_FILE` 读只读挂载的文件。不要改成环境变量、命令行参数或 `env_file`，那样 token 会出现在
  `docker inspect` 和 `docker compose config` 的输出里。轮换：后台刷新 token → 覆盖文件 → `up -d --force-recreate`。
- **起停连接器**（compose 文件经标准输入传入，虚拟机上不落文件）：

  ```bash
  ssh bojiang.local 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- docker compose -f - up -d' \
    < deploy/container/compose.tunnel.yml          # 起
  ssh bojiang.local 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- docker stop sdtm-rag-public-cloudflared'   # 立即下线
  ```

  停掉连接器，公开站立即不可达，公开实例本身不受影响。连接器和公开实例的部署互不牵连。
- **网络隔离**：公开网络里的容器访问不了局域网、虚拟机本机、mini 和同机其他容器（目的地址属于私有网段或本机的包一律丢弃），访问公网不受限。
  这**不是**域名白名单：容器被攻破后仍可连任意公网地址（包括主人自己对外的入口：出口公网 IP 上的端口转发、同域名下别的对外子域名）。
  隔离单元和 docker 之间没有硬依赖（规则文件出错不该拖垮私有站）：单元失败时 docker 仍会把容器拉起来。
  兜底是巡检定时器 `sdtm-rag-public-isolation-watch.timer`：每分钟把规则文件整份重装一遍（表被删、被清空、被改动都会恢复），
  连续两次重装不上就停掉连接器（公开站下线）。这时如果表还在，内核里原有的规则仍然有效；如果表已经不在，公开实例处于没有隔离的状态，
  但连接器已停，没有入口。规则缺失到巡检处理之间最长约一分钟。巡检保证的是「内核里的规则 = 规则文件」，
  不验证实际效果，也发现不了定时器自己被停用，所以每次部署后和虚拟机重启后还要跑探测、确认定时器开着
  （`deploy/public-net/isolation_probe.py`：隔离侧和对照侧各跑一遍 `probe`，再 `judge`；完整命令见演练方案第 3 步）。
  对照侧也连不上的目标记「无结论」，不算通过。
  要撤掉规则时先停巡检定时器。不要在虚拟机上启用系统自带的 `nftables.service`（它的配置文件第一句就是清空整个规则集；
  2026-11-28 查到是 `disabled`），也不要手工执行清空整个规则集的命令：docker 的规则和这张表都会消失。
- **改网络定义**（子网、网桥名）：连接器挂在网络上时 compose 无法重建网络。先停并删除连接器，再按演练方案第 2 步重建。

## 回滚

- **自动**：健康检查失败（或换数据后的 freshness 检查失败）时，workflow 先按 journal 退回 chroma/meta，再退回部署前正在运行的镜像（按该镜像的 WorkingDir 挂载）。
- **数据随镜像回滚**：手动指定 `tag=` 回滚时，同样会比较 KB 指纹；指纹不同时，换入保留的 `chroma_prev_<fp12>_*`。
  如果没有匹配的副本，或无法确定旧镜像的指纹（旧镜像没有 `scripts.kb_freshness`），默认部署失败；勾选
  `force_data_mismatch` 后不换数据，照常部署（日志中告警，回答可能基于不匹配的索引）。
  ⚠ force 只对 unknown 和 missing 两种决定生效。如果决定已经是 swap（存在匹配副本），但非 KB 集合核对不通过，
  force **也无效**，部署失败。此时需要人工处理该副本：将其改名移走后，决定变为 missing，才能使用 force。
  人工退回数据：先停止服务，再执行 `kbsync.py --via <镜像> restore --data-root <数据根>`（仅在 journal 仍存在时有效）。
- **只构建不部署**: 手动运行 workflow, tag 留空、取消勾选 deploy → 只构建+推送镜像, 用于切换前在测试端口验证。
- **.env**: ⚑ 记录默认写 `data/dogfood_failures.md` (挂载卷内), 无需 `SDTM_RAG_DOGFOOD_LOG_OVERRIDE`; 旧 `.env` 里若有指向旧绝对路径的该键, 注释掉即可 (新旧镜像都不受影响)。

Actions 页面手动运行 `sdtm-rag` 工作流, `tag` 填已有镜像的完整 commit SHA → 跳过测试与构建, 直接部署该版本。

跨 step 1.5a 边界: 之前 (monorepo 时代) 的镜像 WorkingDir = `/Volumes/DevSSD/Project/sdtm-pedia/sdtm-rag`, 代码按
`__file__` 找 `data/` `.env`, KB 打在镜像内同一绝对路径下。部署步骤 pull 后取
`APP_DIR=$(docker image inspect -f '{{.Config.WorkingDir}}' <镜像>)` (空则 `/app`) 传给 compose, 挂载目标随之切换,
新旧镜像都能挂对。手工回滚同理: `APP_DIR=<WorkingDir> IMAGE_TAG=<sha> docker compose -f deploy/container/compose.yml up -d`。

⚠ chroma 的 `source` 元数据在 step 1.2 (2026-11) 已改写为 KB 相对路径。回滚到 1.2 之前的镜像须**同时**恢复迁移前的
chroma 副本 (旧代码只按绝对路径过滤 → 启动失败); 备份 `/Volumes/DevSSD/backups/sdtm-pedia-pre-split-2026-11/`。

## 启动失败常见原因

- KB 与 chroma 对不上 → S1 VARIABLE_INDEX section 映射为空 → lifespan 预热 raise (有意: 旧版本同样错配会静默退化成纯 cosine)。
  旧索引先停服务, 再 `.venv/bin/python -m scripts.migrate_source_relative <chroma_dir> --kb-root <旧前缀> --apply`
  (`<旧前缀>` = 索引里 `source` 实际存的绝对 KB 根, 如 `/Volumes/DevSSD/Project/sdtm-pedia/knowledge_base`, **不是**新 KB 位置)。
  `python -m scripts.check_index_freshness` 会抽样报出这类索引 (BAD SOURCE PATHS)。
- 画面 PDF 旁路 (`SDTM_RAG_PDF_CONTEXT_ENABLED`, 默认 false) 开着而 pdftoppm / 页索引 / PDF 缺失或 sha256 不符 ⇒ 启动失败; 键见 `.env.example` 末节。
- 公开档报 `… no pinned price` (前面是可选模型的 id, 或 `fallback_model (SDTM_RAG_FALLBACK_MODEL)` 这样的设置项) ⇒ 那个模型在
  `server/cost.py` 的 `_PRICES` 里没有价格; 按上文「公开实例」里「换模型时必须同时固定价格」那一条补上 (私有档不检查这一项)。
- 公开档报 `one answer round reserves $… > free pool / 10` ⇒ 一轮答题的最坏预留额超了: 报错括号里写明是可选模型自己
  (调低它的 `max_output_tokens`) 还是回退档 (调低 `SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS` 或换便宜的回退模型)。
- `.env` 写了旧变量名 `SDTM_RAG_KB_ROOT` / `SDTM_RAG_CHROMA_DIR` → 静默不生效, 须用 `*_OVERRIDE`; 路径类覆盖须是容器内路径 (`/app/...`)。

## 其他

- KG 查看器产物 2026-11-25 起在 `viewer/dist/kg_viewer.html` (原仓根 `kg_viewer.html`; 由 `scripts/build_kg_viewer.py` 生成, 不进镜像)。
  lan-services 的 Caddy 拷的是这个文件 —— 那边的源路径须同步改成 `viewer/dist/kg_viewer.html`。
- 登录门口令哈希 + session secret: `.venv/bin/python -m scripts.gen_password_hash`。
- Neo4j 探索层 2026-11-07 退役 (dump 在 dev `~/Backups/neo4j-retired-20261107/`); 原安装步骤见本文件 git 历史。
