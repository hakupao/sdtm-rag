# 隧道 + 公开腿两条分支合并进 main, 私有站重新部署 (2026-11-28)

本文件随各步完成续写。时间戳是 UTC。先例: `p3_merge_deploy.md`、`kb_update_2026.11.28.md`。

## 授权
主人 2026-11-28 在协调方的待办项上亲自选定 (**经待办项转达的选择**, 不是在本会话里说的):
- 问题:「把这两条分支合进 rag main、push，并重新部署一次私有站（行为不变），可以吗？」
- 主人选的 (原话):「可以」; 该选项的说明是「做法同前两次：先只构建、测试端口验证，再部署；公开部署开关保持关闭」。
- 只覆盖: 合并、push、私有站的构建与部署、一次 kb-sync 空跑核对。**不覆盖**: 重建公开网络、装隔离规则、开变量、公开部署、启动公开容器、建隧道。

协调方在执行中的三项裁定 (受托代裁, 不是主人逐条裁定):
1. 公开腿分支也用 squash 合并 (任务原写 `--no-ff`): 它的提交 `a6f987d` 里留档的提示词有两行含本机用户名的绝对路径, 最新的树里也还在 → 压成一个提交, 合并后的树里把这两行换成占位写法。
2. 合并后才红的 4 条测试由本会话修, 只改测试, 纳入独立安全审查 (下文「合并后才红的 4 条测试」)。
3. 基点 fixture 的说明放同目录 README, 不动 fixture 正文。

## 第 0 步: 起点
| 项 | 结果 |
|---|---|
| 本仓 | main = origin/main = `9a8ad43`, 工作区干净 |
| 分支 HEAD | `hakupao/public-tunnel` = `9d21808`, `hakupao/public-kb-leg` = `1265aa6`, 与任务给的一致; 两条的 merge-base 都是 `9a8ad43` |
| 线上 | api / ui = 镜像 `f798709…`; `sdtm-rag-public-api` Exited, 镜像 `099c2c9…`; 公开网络子网 `172.18.0.0/16` (没有重建) |
| 私有数据根 | `chroma` `meta` + `*_prev_f863e45445a6_20261127T164455Z` + `*_failed_c5ef769965fd_20261126T051433Z`; 无 cand / journal |
| Gitea | 最近一次运行是 212; 仓库变量为空 (`SDTM_RAG_PUBLIC_DEPLOY` 未开); 最近 30 次运行里没有定时触发的 kb-sync |
| pedia | 最新的 `kb-*` tag 仍是 `kb-2026.11.28` |

## 第 1 步: 合并 (三个提交, 都带 `[skip ci]`)
| 提交 | 内容 | 核对 |
|---|---|---|
| `319654c` | `hakupao/public-tunnel` 的 squash (19 个文件) | `git diff 319654c hakupao/public-tunnel` 为空 |
| `781521d` | `hakupao/public-kb-leg` 的 squash (26 个文件) | 相对分支的补丁只差两处 (见下); 红线闸 CLEAN |
| `e50a9f8` | 整合: 快照文件、4 条测试的修正、裁定登记 | 见下 |

提交信息都是自己写的, 没有用 git 预填的 squash 信息 (那里面有原分支全部提交的标题)。两条分支留在本地, 没有删。

- **冲突**: 只有 `deploy/README.md` (与预查一致), 两边都是纯新增。处理: 公开腿的「### 公开实例」小节留在「## KB 同步」一节末尾 (它自己声明的位置), 隧道的「## 公开实例与隧道」作为紧随其后的独立一节。相对基点 115 增 0 删 (隧道 62 + 公开腿 53); 隧道的两处新增 (组成表 1 行 + 61 行) 和公开腿的 53 行都逐字在; 基点各行按原顺序都在。
- **两行路径**: `subagent_prompts/review_public_leg_round3.md` 第 23、30 行的本机绝对路径换成「另一条线的子工作区」的占位写法, 在提交**之前**改的 (先提交再改, 路径仍会留在历史里)。相对分支 `2 增 2 删`, 没有动别的行。
- **快照文件**: 合并后的 `deploy/container/compose.public.yml` 在部署机上只读渲染 (文件经标准输入传入, 虚拟机上不落文件), 输出与分支带来的 `tests/fixtures/kbsync/compose_config_public_tunnel.json` **逐字节相同** (sha256 `cc30f9f1…`), 然后覆盖到 `compose_config_public.json` (原 `09b4eed7…`)。
- **共享文件**: `_progress.json` (状态; `decisions_p3.owner_2026_11_28` = 主人本人选的各条; `decisions_2026_11_27_delegated.public_leg_impl_2026_11_28` / `merge_2026_11_28` = 协调方受托代裁的各条; `M3_suggestion_pending` 已由主人裁定, 挪走)、`PLAN.md` (1.9 验收拆两半; 3.4 / 3.4b 现状; §6 补「并行分支合并前」)、`docs/PROGRESS.md`、`CLAUDE.md` (「KB 更新」路由词补公开站一句; Key Paths 加一行; 80 行)。

## 合并后才红的 4 条测试 (两条分支各自全绿, 合到一起才红)
覆盖快照之后的第一趟本机全量: **2 failed** / 3540 passed / 2 skipped。又在「深度 1 的克隆 + 独立 venv、没有 `data/`」里 (= CI 的条件) 跑了一趟: **4 failed** / 3479 passed / 61 skipped。4 条都是测试自身的问题, 不是产品代码的问题。

| 测试 | 为什么分支上是绿的 | 为什么合并后红 |
|---|---|---|
| `test_kbsync_deploy_public.py::test_compose_without_a_pinned_subnet_stops_the_deploy`、`::test_public_network_is_read_from_the_compose_model` | 公开腿分支上 `compose_config_public.json` 是隧道合入前的 compose 的解析结果, 测试顺手拿它当「没有写定子网的 compose」 | **同一个快照文件有两种用途**: 另一条测试 (`test_compose_fixtures_match_the_compose_files`) 要求它等于当前 compose 的解析结果。合并后 compose 写定了子网, 快照必须换 (公开腿的集成备注也这样要求), 一换这两条就红; 不换则那一条红 |
| `test_workflow_conditions.py::test_private_deploy_job_changed_only_where_intended`、`::test_kb_sync_private_leg_changed_only_where_intended` | 子工作区有完整历史, `git show 9a8ad43:…` 取得到 | **CI 的 checkout 深度是 1** (run 211 日志里 `fetch … --depth=1`), 取不到基点提交, `check=True` 直接报错。本机有完整历史, 所以合并后本机也看不出来, 只有浅克隆能复现 |

不修的后果: 只构建会在测试步骤失败; 以后每一次私有部署也会被测试步骤挡住。

修法 (只改测试, 协调方裁定):
- 前两条: 用 `_unpinned()` 从快照里去掉 `ipam` 段, 表示隧道合入前的形状。`_unpinned` 用 `pop` 取 `ipam` 并断言去掉的子网就是 `SUBNET`: 没有可去的东西时报错, 不会「什么都没去掉却照样通过」。
- 后两条: 基点的两个 workflow 原文冻成 `tests/fixtures/workflows/base_9a8ad43_{sdtm-rag,kb-sync}.yml` (与 `git show` 逐字节相同; 说明在同目录 `README.md`)。初版是「取得到基点时顺带核对与 `git show` 相同」; 独立审查指出这样在 CI 里 fixture 与 workflow 被一起改会漏检 (MEDIUM-1), 改成把基点的 git blob 号写死在测试里 (`BASE_BLOBS`), 每次都核对, 不依赖历史。

修正后的检出能力 (变异都在临时副本里做, 每次先核对变异确实打上了; 第一次做 M4 时替换的原文写错、变异没打上, 被这一步核对拦下, 那一趟的「通过」没有采用):

| 变异 | 深度 1 的副本 (= CI) | 说明 |
|---|---|---|
| 只改 workflow (私有 deploy job 的健康检查 `seq 1 60` → `seq 1 5`) | 红: 步骤清单断言 `['健康检查', …] == ['构建并推送', …]` | 原测试要抓的就是这个 |
| workflow 与 fixture 同步改 (同上) | 红: `fixture 与基点提交里的 workflow 不一致: f2374be0…` | **同一个变异在初版写法 (`e50a9f8`) 下是 2 passed (漏检)** |
| fixture 只改注释里一个字 | 红: 同上的 blob 断言 | |
| 全部还原 | 2 passed | |
| 快照去掉 `ipam` / `network_check` 去掉「没写定子网」分支 / `public_network` 一律返回 None / 两个子网时取第一个 | 都红 | 审查者做的 (M7–M10) |

以后的做法 (已写进 `PLAN.md` §6 与 `_progress.json` 的 `todo_later`): **并行分支合并之前, 先把它们试合到一起, 在深度 1 的克隆 + 独立 venv 里跑一遍全量测试。**

## 第 2 步: 本机验收 + 独立审查
- 本机 `pytest -m "not slow"`: `5556687` 上 **3542 passed / 0 failed / 2 skipped** (两个 skip 都是要 playwright 的真浏览器闸); 修正前是 2 failed (上节)。其后两处测试改动 (僵尸判断 `613f048`、假密钥改写 `27da769`) 当时各只跑了相关文件; 收尾时在 `27da769` (其后只有文档提交) 上又跑了一趟全量: **3542 passed / 0 failed / 2 skipped**。「用真实隔离探测脚本」那条 (`test_isolation_check_with_the_real_probe_script`, 合并前是 skip) 现在真的运行并通过。
- CI 同款 (深度 1 的全新克隆 + 独立 venv, 无 `data/`): `e50a9f8` 上 3483 passed / 0 failed / 61 skipped; 4 条修正过的测试用 `-rA` 看都是 PASSED, 不是 SKIPPED。
- 主仓 `data/`: 运行前后对比 2090 个文件的大小与修改时间, 以及备份目录之外 1725 个文件的 sha256。**只有 `data/chroma` 下 9 个文件的修改时间变了**, 其中 `chroma.sqlite3` 和 2 个 `data_level0.bin` 内容有变、大小不变 (chromadb 打开索引时自己改写, 与 `p3_merge_deploy.md` 记的现象相同)。只读核对: 三个集合 4333 / 959 / 125 条, stamp `477bac3ce565…` / 4333, `check_index_freshness` OK。`data/study`、`data/meta` 0 变化。收尾那趟全量之后又拿最初的记录比了一次 (中间共跑过六趟全量和若干单文件): 结果相同 —— 仍然只有 `data/chroma` 下那 9 个文件的修改时间变了, 0 个文件大小变化, 内容有变的仍是 `chroma.sqlite3` 和 2 个 `data_level0.bin`; 三个集合 4333 / 959 / 125 条, freshness OK。
- **独立审查 (规则 D)**: `oh-my-claudecode:security-reviewer` (opus), 只读; 任务书 `subagent_prompts/review_tunnel_leg_merge.md`。范围: (A) 公开腿分支上没被独立审查过的部分; (B) 合并结果 (冲突、squash 是否忠实、快照、4 条测试的修正、两条线的接缝、共享文件); (C) 私有站行为不变; 外加推送前内容检查。
  结论 **PASS-with-fixes**: CRITICAL 0 / HIGH 0 / MEDIUM 2 / LOW 6。「没有发现会阻止 push 或私有站重新部署的问题。」审查者自己做了 20 多处变异 (红线检查 9 处里 8 处被抓; `server/auth.py` 私有档 4 处全被抓)。

| # | 意见 | 处置 |
|---|---|---|
| MEDIUM-1 | CI 浅克隆下基点 fixture 的完整性没有检查: workflow 与 fixture 同步改, 4 passed | **已改** (blob 号写死), 上节变异表 |
| MEDIUM-2 | 三个提交都带 `[skip ci]` 却改了会触发部署的路径, 请确认 Gitea 认这个标记 | 有意为之, 是任务与先例的做法: 带标记 push → 手动只构建 → 测试端口 → 部署。Gitea 认标记的依据: `p3_merge_deploy.md` 两段与 `kb_update_2026.11.28.md` 共三次带标记的 push, 之后都没有被触发的运行。这次 push 后照样观察 |
| LOW-1 | 红线停站的失败信息里, 集合名「原样显示」的白名单偏宽 (`study_st<数字>_<任意小写后缀>` 会原样打出) | 没有改 (产品代码, 不在这次合并的范围); 已上报协调方, 记入 `todo_later` |
| LOW-2 | 没有测试钉住「启动报错带出之前先脱敏」: 去掉脱敏, 303 passed。现有代码确实先脱敏 (测试缺口, 不是泄漏) | 同上 |
| LOW-3 | 启动报错原样带出时可能带出集合名; 现在走不到 (此前已要求集合恰为 `sdtm_kb_v1`) | 同上 |
| LOW-4 | 红线检查只在部署时跑, 且排在几道前置检查之后 | 已知的设计取舍 (`p3_public_leg_impl.md` §8), 不改 |
| LOW-5 | 进度文件引用了还不存在的本文件 | 本文件随同一次 push 提交 |
| LOW-6 | `deploy/README.md` 说镜像下限拒绝的是「没有公开档的 HSTS」的镜像; 实际判据是 `PUBLIC_EDGE_LEVEL >= 1` + 单主机可信代理检查。两个相邻小节互相没有引用 | 没有改 (不扩大合并的改动面); 记入 `todo_later` |

审查者确认过、没有问题的: 两个 squash 忠实 (对公开腿用的是逐补丁比较 `diff <(git diff 9a8ad43 hakupao/public-kb-leg) <(git diff 319654c 781521d)`, 只差 README 的上下文和那两行路径); README 冲突处理; 快照与 compose 一致; 两条线的接缝 (脚本路径、probe / judge 的命令行、镜像下限的判法与输出、网段常量、隔离目标清单与演练第 3 步); 私有档 (HSTS 只在公开档; cookie 的 `Secure` 私有档不变; 大小写变体检查只在公开档; `_resolve_ip` 只在对端是可信代理时走到); 私有 deploy job 与 kb-sync 私有腿在两种合法输入下与基点等价; 变量未开时两个公开 job 一定跳过; 新增行与提交信息里没有用户名 / home 路径 / 真名 / 邮箱 / 真实密钥。
审查者下不了结论的: Gitea 对 `[skip ci]` 与 `needs` + `always()` 的真实行为、runner 的 shell、私有站 `.env` 的内容、默认网桥上的对照容器能否连到各内网目标。

## 推送前检查 (第一次 push; 范围 = `9a8ad43..5556687`)
逐提交扫 `git log -p` 的新增行 (10322 行, 53 个文件) 和 4 条提交信息 —— 不只扫净 diff, 净 diff 看不到「先加后删」的内容。
| 口径 | 新增行 | 提交信息 |
|---|---|---|
| home 路径 (`/Users/<名>`、`/home/<名>`) | 0 | 0 |
| 本机账号名、真名 / 作者名、提交者邮箱原值 | 0 | 0 |
| 邮箱 (`noreply@anthropic.com` 与示例域除外) | 0 | 0 |
| 密钥形状 (`sk-` / `tvly-` / `ghp_` / `github_pat_` / `AKIA` / `xox*-` / `PRIVATE KEY` / `Bearer …`) | 5 行 | 0 |
| JWT 形状 (隧道 token 的外形) | 6 行 | 0 |
| 口令赋值形状、`curl -u 名:字面量` | 2 行 | 0 |
- 密钥 / JWT / 口令赋值形状的 13 行都是脱敏与 key 探测测试里的假值 (`sk-invalid-0000…`、`sk-ant-api03-ShouldNeverLeak` 之类; JWT 解码出来是 `{"a":"abcdefghijklmnop"}`、`fake-for-test`), 独立审查者也解码核对过。
- 另有一处与某个本地口令的片段偶然重合, 已核实不是泄漏 (重合的是测试里的通用示例串, 同样的串在已公开的基点树里早就有)。
- 含本机路径的旧提交 `a6f987d`、`9b7e0aa`、`5021cc3` 以及两条分支的 HEAD 都不是 main 的祖先。4 个待推送提交都带 `[skip ci]`。
- 以上命中报给协调方确认后才 push。不拦截、只计数 (净 diff): 内网 / 公开网段地址 154 行, `bojiang` 52 行, 不含用户名的机器路径 65 行。

## 第 3 步: push (第一次)
- `git push origin main` (非强推): Gitea 与 GitHub 都是 `9a8ad43..5556687`; 两个远端的 main = `5556687e162c3de268f07f4aa95cfb146d7d7998`。
- 推后观察 90 秒 (30 / 60 / 90 秒各看一次运行列表): 没有被这次 push 触发的运行, 最新仍是 212。

## 第 4 步 attempt 1: 只构建 run 214 —— 测试步骤失败 (规则 B: `failures/p3_tunnel_leg_merge_build_attempt_1.md`)
- run 214 / job 455 (tag 空, deploy=false, head `5556687`): checkout → **测试 failure** (1 failed / 3482 passed / 61 skipped) → 构建、部署类步骤全部 skipped; `deploy_public` (job 456) skipped。没有镜像, 线上没变, 没有重试。
- 失败的是公开腿带来的 `test_abort_first_ends_a_deploy_process_that_is_still_alive`。之前预判的 4 条在真实 CI 里都通过。
- **第三种「合并后才红」: 只在 Linux runner 里红。** CI 的 job 容器 1 号进程是 `/bin/sleep 3600`, 不回收孤儿进程; 兜底把进程组结束之后, 子进程已经死了但停在僵尸状态, `kill(pid, 0)` 对僵尸仍然成功, 测试把它当成「还活着」。macOS 会回收, 所以本机和浅克隆模拟 (都在 macOS 上) 测不出来; 公开腿的测试合并前从没有在 Linux runner 里跑过。
- 修法 (只改这一条测试, 协调方裁定): `alive()` 里把僵尸 (`/proc/<pid>/stat` 状态 `Z`) 算作已结束; 没有 `/proc` 的系统上读不到就算「不是僵尸」, 行为与改之前相同。
- 在与 CI 相同的镜像 (`docker.gitea.com/runner-images:ubuntu-latest`, 1 号进程 `/bin/sleep`, 按 workflow 的命令装依赖) 里的验证:

| 做法 | 结果 |
|---|---|
| 原测试 (`5556687`) | 1 failed, 报错与 run 214 相同 |
| 换上修后的测试 (容器内外 sha256 相同) | 1 passed |
| 变异: `_end_process_group` 只结束组长、不整组结束 (`whole = False`; 改完用 `cmp` 确认打上了) | 1 failed, 「编排进程起的子进程还活着」 —— 子进程真的还在跑时照样抓得住 |
| 还原 (sha256 与仓库相同), 合并带来的 8 个测试文件 | 648 passed |

- **独立审查 (窄范围, 同一位审查者)**: `oh-my-claudecode:security-reviewer`, 任务书 `subagent_prompts/review_tunnel_leg_merge_round2.md`。结论 **PASS**: 没有削弱检出能力; 没有 `/proc` 的系统上不起作用, 行为与改之前相同。它在 macOS 的副本里实测: 修后的测试 1 passed; `whole = False` 变异 1 failed (5.43 秒, 等满了); 完全不发信号的变异 1 failed; 解析逻辑用构造的 stat 行验证 (进程名含 `)`、空格、没有括号都不误判)。它进不了 Linux 容器, 僵尸那半边的实测只有上表。
  - 两条可选建议没有采纳 (这次提交的就是在 runner 镜像里验证过的那个版本): 只在线程数为 1 时才算已结束 (防「主线程成僵尸、其他线程还在跑」; 测试里的子进程是单线程的 `time.sleep`, 走不到); 按字节读 stat (进程名不是合法 UTF-8 时 `read_text` 会抛错, 后果是测试变红而不是误通过)。
  - 它另外发现一个**改之前就有**的缺口: 把兜底改成「只发 SIGTERM、不升级到 SIGKILL」, 这条测试仍然通过 (子进程不忽略 SIGTERM)。记入 `todo_later`。
- 以后的做法 (已记入 `_progress.json` 的 `todo_later`): **涉及进程、信号、文件系统语义的测试, 合并前在 runner 镜像里跑一遍。**

## 第 3 步 (续): 第二次 push
- 提交 `613f048` (只改那一条测试 + 失败归档 + checkpoint 续写, 带 `[skip ci]`)。推送前检查 (范围 `5556687..613f048`, 138 行新增): 用户名 / home 路径 / 邮箱 / 真名 / 口令原值 0; 密钥形状 2 行, 都是本文件「推送前检查」一节里列举口径名称与已放行假值名称的那两行自己。
- `git push origin main` (非强推): Gitea 与 GitHub 都是 `5556687..613f048`; 两个远端的 main = `613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7`。推后 90 秒没有被触发的运行。

## 第 4 步 attempt 2: 只构建 run 215 —— success
- run 215 / job 457 (tag 空, deploy=false, head `613f048`): checkout / 测试 / 登录 / 确定标签 / 构建并推送 success; 部署类步骤全 skipped; `deploy_public` (job 458) skipped。镜像 `613f048…` digest `sha256:9e1ac10b41642c1484e074ac8de68930e190a899a5627f7be98ec0e3a95078c0`。
- CI 测试: **3483 passed / 0 failed / 61 skipped**。与 run 214 整份对照 (`-q` 不打印每条测试的名字, 所以按测试点阵逐位比): 3542 位里只有 1 位不同 (第 1292 位 `F` → `.`, 就是那一条); `SKIPPED` 行 59 行逐行相同。没有别的只在 Linux runner 上红的测试被这次修正掩盖或带出。
- **标签步骤在两种合法输入下的真实输出** (对照 `p3_public_leg_impl.md` §3.4 的改前改后表: 两种合法输入下三样逐项相同):

| 输入 | 改之后 (这次) | 改之前 (上一次上线) |
|---|---|---|
| tag 留空 (只构建) | run 215: `部署标签：613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7` (= 这次运行的提交), 后续「构建并推送」用这个标签成功 | run 211: `部署标签：f798709476b75bfb8959cd1d0ca4b252cc122c5e` |
| 合法的 40 位提交号 (正式部署) | run 216: `部署标签：613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7` (= 填的值), 测试与构建 skipped, 后续步骤用这个标签部署成功 | run 212: `部署标签：f798709476b75bfb8959cd1d0ca4b252cc122c5e` |

## 第 4 步: 测试端口验证 —— PASS (`p3_tunnel_leg_merge_testport_613f048.sh` + `p3_tunnel_leg_merge_testport_ratelimit.sh`)
新镜像 `613f048` (镜像 ID `sha256:9e1ac10b…`) 对线上镜像 `f798709` (`sha256:8d1ce749…`), 各用线上 chroma 的一份副本, 线上 meta 与生产 `.env` 只读挂载; 不发布端口。

| 判据 | 新镜像 | 线上镜像 (对照) |
|---|---|---|
| freshness | OK, `477bac3ce565…`, 4333 条 | 同 |
| 容器里读到的数据 (防挂错) | 集合 4333 / 959 / 125; `model_defhome` 75, EPOCH → `model/02` | 同 |
| CDISC 140 题 | 138 满分 / avg 0.9917, 非满分 q38、q126 | 同; **逐题 recall 0 差** |
| study 51 条 | avg 0.875, 满分 45 | 同; **逐题 recall 0 差** |
| `/api/ask` (真答题) | 200 | 200 |
| `/api/info` | 19 个键, 无 tier / providers / quota | 键集相同 |

- `top5_sources` 不同的题数 (不是判据, 如实记录): CDISC 1 题, study 3 题, recall 都不变。同一份索引两趟之间的波动, `kb_update_2026.11.28.md`「发现」第 1 条记录过同类现象 (那次 CDISC 侧用的是不同的索引, 这次是同一份索引的两个副本, 说明 CDISC 侧也有这种波动)。预登记判据 (recall 相差不超过 1 题) 满足。
- **私有档行为不变**:
  - 生产 `.env` 下两边读到的开关相同: `auth_enabled=False`, `rate_limit_enabled=True`, `security_headers_enabled=True`, 限额未开。
    - **更正 (规则 6 成因 A, 抽取端取空)**: 脚本那一趟打印的 `'tier': None` 不是「档位未设」—— 我用了一个猜的属性名 (`instance_tier`) 加 `getattr(…, None)`, 两个镜像里都没有这个属性, 取到的是空值, 什么都证明不了。真实的属性是 `settings.instance`。补测 (新旧镜像各 `docker run --rm --network none`, 只读挂生产 `.env`, 不起服务): 两边都是 `instance = 'private'`; 线上容器里 `auth._is_public(settings)` = False。脚本里的取法已改成 `settings.instance` (取不到会直接报错)。
    - 私有档的旁证 (第一趟就有): `/openapi.json` 与 `/docs` 两边都是 200 (公开档会是 404), `/api/info` 没有 `tier` 键。
  - 响应头: 13 个探测 (首页、静态文件、health、info、openapi、docs、不存在的路径、GET / POST login、422、flag、带伪造的 `X-Forwarded-Proto` / `CF-Connecting-IP` 的请求、真答题) 新旧**逐项相同** (状态码、响应头名集合、除 date / content-length / etag / last-modified 外各头的值)。探测数与每个响应的头数有下限断言, 不是空比较。
  - HSTS: 新旧都是 0 次。新镜像出现过的全部响应头名: accept-ranges、cache-control、connection、content-length、content-security-policy、content-type、date、etag、last-modified、referrer-policy、server、x-content-type-options、x-frame-options。
  - cookie: **新旧都是 0 条 `Set-Cookie`, 真机上无 cookie 可比** —— 私有站生产配置下登录门和限额都没开, 根本不发 cookie。「私有档 cookie 不带 `Secure`」的依据是单测 (`test_session_cookie_secure_follows_tier`、`test_private_visitor_cookie_not_secure_by_default`) 和审查者对这两处做的变异 (都被抓)。
  - 限流: 私有站生产 `.env` 里限流**本来就开着** (新旧都是每分钟 30 / 突发 10, 不采信转发头), 不是这次合并带来的; 公开档新加的那组取值 (60 / 20) 只写在 `compose.public.yml` 里。条件对等的测量 (两边都空闲 75 秒后各连发 40 个 `/api/info`, 正反顺序各一轮): 四次都是前 10 个 200、后 30 个 429; 429 的响应头名、`retry-after: 2`、正文 `Too Many Requests` 新旧相同。
    - 第一趟脚本里的连发 (`R` 段) 得到 200 的个数是新 10 / 旧 7。原因在我的脚本: 两边连发前的空闲时间不同 (新的那边多等了旧的那边答题的时间, 桶回满了), 那组数不能用来比较, 所以补了上面这一趟。
  - 大小写变体: 同一对取值不同的变量 (`SDTM_RAG_RATE_LIMIT_BURST` / `sdtm_rag_rate_limit_burst`) —— 直接调 `_check_public_env_case_variants` 会拒绝 (`public tier: conflicting case variants …`, 证明这对变量正是那道检查要拦的); 带着它按生产 env (私有档) 启动新镜像, 照常 healthy, `/api/info` 19 个键。
- 线上不受影响: 验证前后线上容器镜像与启动时间不变; 临时容器与副本已清 (脚本有出错清理)。

## 第 5 步: 正式部署 —— run 216 / job 459 success
- 派发: tag = `613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7`, deploy=true, 没有用 `force_data_mismatch`。只构建与部署之间没有 push。
- 日志: 部署前线上镜像 `f798709…`; KB 对齐 `{"prod_fp12": "477bac3ce565", "target_fp12": "477bac3ce565", "decision": "same"}`, 不换数据; 健康检查 200; 测试、构建、新鲜度、换数据收尾、两个退回步骤都 skipped。
- `deploy_public` (job 460) **skipped** (仓库变量为空)。
- 部署后: api / ui = `613f048…`, api healthy; 容器内 `check_index_freshness` OK (`477bac3ce565…`); 局域网 `/api/health` 200, `/api/info` 19 个键、无 tier / providers / quota、`chunk_count` 4333、`index_fresh` True, 响应头里没有 HSTS; 容器里 `server.auth.PUBLIC_EDGE_LEVEL` = 1 (镜像下限标记在线上镜像里了)。
- 快照 (`p3_tunnel_leg_merge_snapshot.sh`, 不含 mtime): 合并前、部署前两次无差异; 部署前 → 部署后只差 api / ui 两行镜像。
  - 私有数据没变: stamp `477bac3ce565…` / 4333; `meta.yaml` `b484d49ef76c`、`implicit_relations.json` `c3dbe292a00b`; chroma 与 meta 目录 inode 不变, 130 个文件的文件名清单指纹不变; `*_prev_*`、`*_failed_*` 原样; 没有 journal / guard / cand。
  - 公开侧没变: `sdtm-rag-public-api` 的容器 Id、镜像 `099c2c9…` (镜像 ID `sha256:3886799a…`)、状态 exited、StartedAt / FinishedAt、重启次数都不变; 公开网络 Id 不变, 子网仍是 `172.18.0.0/16`, 0 个容器; 没有连接器容器; 隔离规则表 0 张; 公开数据根 (9 个文件) 的文件名 / inode / 大小 / mtime 清单指纹不变 (`57bde78cb564aa66`), 最新的 mtime 仍是 2026-11-26。没有读公开数据根里任何文件的内容, 没有碰 `/opt/sdtm-rag-public/`。

## 第 6 步: kb-sync 空跑核对 (公开腿演练的阶段 A) —— 与预期一致
- 手动派发 kb-sync (工作流在 main = `613f048` 上运行; `ref`、`public_baseline_image` 都留空); 派发前仓库变量为空, pedia 最新的 `kb-*` tag 仍是 `kb-2026.11.28`。run 217 success, 约 30 秒。
- `private` (job 461) success: KB ref `kb-2026.11.28` → A 仓提交 `b2bd837…`, 指纹 `477bac3ce565`, 线上镜像 `613f048…`; 检测 `{"result": "same"}` →「no-op：生产 chroma 已是该 KB 指纹」; 构建候选镜像 / 候选入库并运行 CDISC 闸 / 删除候选镜像 都 skipped。没有入库, 没有 embedding 费用。
- `public` (job 462) **skipped**。
- 之后的快照与部署后那一份无差异: 线上 api 没有被重启 (启动时间不变); 私有数据、公开容器、公开网络、公开数据根都不变; 没有候选镜像残留。
- 这是两 job 版的 kb-sync 和私有腿改过的「确定 KB ref」第一次在这台 Gitea 上真实运行。

## 回滚办法
- 手动运行 `sdtm-rag` 工作流: `tag=f798709476b75bfb8959cd1d0ca4b252cc122c5e`, deploy=true。KB 指纹相同 (`477bac3ce565`), 预检会判 same, 不换数据; 私有 `deploy` job 不做镜像下限检查, 旧镜像可以回滚; `deploy_public` 变量未开, 会跳过。
- ⚠ 变量打开之后就不能这样回滚了: 同一个 tag 也作用于公开站, 而 `f798709` 过不了镜像下限 (`p3_public_leg_impl.md` §8)。
- 本仓回退: 对 `319654c`、`781521d`、`e50a9f8`、`5556687`、`613f048` 做 `git revert` (带 `[skip ci]`), 再走只构建 → 测试端口 → 部署。kb-sync 工作流从 main 的 checkout 运行, revert 之后下一次运行即回到单 job 的写法。

## 收尾阶段的一处测试改写 (协调方要求; 不经过 CI)
密钥扫描器对已推送的提交 `781521d` 报了两处 (JWT 形状、Bearer 形状), 是 `tests/test_kbsync_public.py::test_scrub_hides_key_shapes` 的参数化假值, 不是真密钥 (协调方核对过: 本机 `.env` 里的真实密钥在已推送内容里 0 命中)。已推送的历史不改。
- 改法: 这个 parametrize 的 13 个假值改成运行时拼接 (`FAKE_SECRETS`; JWT 那一条用 base64 现算), 断言没有动。源码里不再有完整的密钥 / token 形状。
- 核对: `p3_tunnel_leg_merge_scrub_equiv.py` 用 AST 取出 `613f048` 里的字面量求值, 与导入当前模块得到的参数逐个比较 → 13 个逐字相同, 顺序相同。本机 `tests/test_kbsync_public.py` 89 passed (其中这条 13 个用例)。
- 独立审查 (同一位审查者, 第三次窄范围; 任务书 `subagent_prompts/review_tunnel_leg_merge_round3.md`): **PASS**。它没有用我的脚本, 自己在两个副本里真实导入改前、改后的模块逐个比较: 13 个参数逐字相同、顺序相同; `pytest --collect-only` 的用例 id 改前改后相同 (全文件 89 条, 这条 13 个); 新名字 (`_b64url`、`FAKE_SECRETS`) 不与别处冲突; 参数列表里已经没有完整的密钥 / token 形状。它建议加一行个数断言 (列表被清空时 parametrize 只变成 1 条 skip, 不会红) —— 已加 (`assert len(FAKE_SECRETS) == 13`), 加完本机该文件 89 passed。它没法确认的: 改写后能不能过那个外部扫描器。
- 推送前检查发现我第一版改写把 JWT 里原先编码着的示例串写成了明文, 新带出一处与某个本地口令片段的偶然重合 (不是泄漏, 同类情形见上文「推送前检查」)。还没有推送, 就把那一段也改成运行时生成 (`_LETTERS`、`_DIGITS`), 并重做了未推送的本地提交 (没有强推); 最终的测试提交是 `27da769`。同一位审查者对 `27da769` 复核: **PASS** (13 个参数仍逐字相同; 用例 id 不变; 把列表删短一个, 个数断言在收集阶段报错; 源码里已没有 JWT 形状)。重合消失 (该文件 0 命中)。
- 文件里还有两处带星号的打码形态假值没有动 (这次没有被报; 不在「只改这一处」的范围), 其它测试文件里完整形状的假密钥也没有处理, 记入 `todo_later`。

## 仍未验证的事项
1. **收尾阶段那处测试改写没有经过 CI**, 下次构建时才会跑 (本机该文件全部通过)。
2. 公开侧的一切都还没有真实运行过: `deploy_public` 的全部步骤、kb-sync 的 `public` 腿、镜像下限预检脚本在真实镜像里的表现、临时容器 (无网络) 能否起到 healthy、两段 key 探测、红线检查、中断兜底 (`p3_public_leg_impl.md` §7; `p3_step3.4_tunnel.md`「合并前没法验证的事项」)。
3. Gitea / act_runner: job 级 `vars` 门控在「变量未开 → 跳过」这个方向上已由 run 216 (`deploy_public`) 与 217 (kb-sync `public`) 证实 (run 214 / 215 里 `deploy_public` 也是 skipped, 但那两次 deploy=false, 区分不出是不是变量门控); `always()` 那半边 (私有腿失败后公开腿照跑)、变量打开后的行为、`concurrency` 是否真的让两个 workflow 排队、取消时兜底步骤是否执行, 都没有验证。
4. 定时触发: 最近 30 次运行里没有任何定时触发的 kb-sync (只有手动派发的)。cron 写的是 `17 3 * * *`: 按 UTC 算的话 03:17Z 落在这次会话中间, 而 run 215 → 216 → 217 的编号是连续的 (03:13Z – 03:25Z), 中间没有别的运行, 03:17Z 没有触发; 按日本时间算的话下一次是 18:17Z, 上两个 18:17Z (11-26、11-27) 也都没有运行。定时器看起来没有在跑, 没有查原因。如果它之后恢复, 那会是两 job 版第一次无人值守运行, 预期是 private same / public skipped。
5. 私有档的 cookie 属性在真机上无 cookie 可比 (上文); 登录门打开时的 session cookie 只有单测和变异作依据。
6. 私有 `deploy` job 加固后「拒绝不合法输入」那半边 (多行、结尾换行) 只有本机用真实 bash 跑的测试, 没有在 Gitea 上派发过不合法的 tag。
7. 在 runner 镜像里跑完整的 CI 测试命令没有做成 (我放进容器的是不带 `.git` 的归档, 收集阶段报 2 个错); 依据是 run 215 自己的结果。
8. 独立审查留下、这次没有改的: LOW-1 / LOW-2 / LOW-3、`_end_process_group` 对僵尸的处理、兜底测试「只发 SIGTERM」的缺口、README 里镜像下限的说法 (`_progress.json` 的 `todo_later`, 前四项标了「必须在打开公开部署开关之前处理」)。

## 小结 (规则 C)
- **保留下来的做法**: squash 之前先在暂存区改掉含用户名的路径, 提交信息自己写; 合并结果用机械核对 (树 diff 为空 / 逐补丁比较 / numstat) 而不是靠读; 推送前检查逐提交扫 `git log -p`; 测试端口的比较脚本用 `r["键"]` 取值并加下限断言; 变异每次先确认打上了 (这次拦下一次没打上的); 部署前后用不含 mtime 的快照做 diff, 公开侧只取元数据; 只构建与正式部署之间不动 main。
- **必须补上的缺口**:
  1. 两条分支各自全绿, 合并后红了 5 条测试, 三种原因都只在「合到一起」或「换个环境」时才出现: 同一个快照文件被两条测试当成两种东西用 (2 条); CI 的 checkout 深度是 1, 取不到基点提交 (2 条); CI 的 job 容器 1 号进程不回收孤儿, 僵尸被当成活进程 (1 条)。前两种靠「深度 1 的克隆 + 独立 venv」能在 push 前发现; 第三种只有在 Linux runner 镜像里才能发现, 我的浅克隆模拟在 macOS 上, 漏了, 付出了一次失败的只构建。⇒ 并行分支合并前: 试合 → 深度 1 的克隆跑全量 → 涉及进程 / 信号 / 文件系统语义的测试再在 runner 镜像里跑一遍。
  2. 「取得到时才核对」是一种会静默失效的闸 (成因 C 的变体): 我第一版的基点 fixture 核对在 CI 里从不执行, 是独立审查做「workflow 与 fixture 同步改」的变异才发现的。
  3. 我的测试端口脚本第一趟的限流对比条件不对等 (两边空闲时间不同), 得到了一组看起来「行为不同」的数; 对比两边时, 有状态的东西 (令牌桶) 要先回到同一个起点。
  4. 测试数据里的假密钥要在运行时拼, 不要写成完整的密钥形状 (公开仓库会被扫描器报警)。
- **关键决策复盘**: (1) 覆盖快照后本机一红就停下来问, 同时顺手做了浅克隆模拟, 一次把 4 条都报上去, 而不是修两条再撞两条; (2) 审查的 MEDIUM-1 当场改掉 (把 blob 号写死) 而不是记成后续项, 因为它正是协调方要求确认的「检出能力」; (3) 窄范围审查的两条可选建议没有采纳, 保持在 runner 镜像里验证过的版本, 没有为了更严而把一个没在 Linux 上跑过的写法推上去; (4) 协调方中途追加的假密钥改写没有插进只构建与部署之间, 放到部署之后单独提交, 换来「部署的镜像 = 验过的那个提交」。

## 结束状态
- 收尾的两个提交 (都带 `[skip ci]`): `27da769` 只改 `tests/test_kbsync_public.py` (假密钥改写); 另一个是文档 (本文件 + 四个脚本 + 进度 / trace / 复盘)。推送前检查同一口径再扫一遍 (结果在向协调方的最终汇报里)。
- `git status -sb`: `## main...origin/main`, 工作区干净; main = origin/main (Gitea 与 GitHub 相同), sha 见本提交。
- 线上镜像对应提交 `613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7`; 其后只有这两个收尾提交 (测试 + 文档, 没有运行时代码)。
- 两条分支 `hakupao/public-tunnel` (`9d21808`)、`hakupao/public-kb-leg` (`1265aa6`) 和它们的子工作区都没有动, 留给协调方处理。
- Gitea 仓库变量仍为空; 公开侧没有任何变化。

## 复跑命令
```sh
R=<本仓根>; cd $R; PY=.venv/bin/python
# 合并 (提交信息自己写; 公开腿那次在 commit 之前先解 README 冲突、改掉两行路径)
git merge --squash hakupao/public-tunnel && git commit -F <信息>
git merge --squash hakupao/public-kb-leg   # deploy/README.md 冲突: 两边新增都保留 (公开腿的小节在前)
git diff 319654c hakupao/public-tunnel                                                    # 空
diff <(git diff 9a8ad43 hakupao/public-kb-leg) <(git diff 319654c 781521d)                # 只有 README 上下文 + 两行路径
git diff --numstat 9a8ad43 e50a9f8 -- deploy/README.md                                    # 115 0
# 快照 (只读; 文件经标准输入传入)
cat deploy/container/compose.public.yml | ssh <mini 主机> 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- sudo env IMAGE_TAG=abc docker compose -f - config --format json' | cmp - tests/fixtures/kbsync/compose_config_public_tunnel.json
# 本机全量 (前后各记一次 data/ 的状态)
find data -type f -print0 | sort -z | xargs -0 stat -f '%N|%z|%m' > <临时目录>/before.txt
$PY -m pytest -m "not slow" -q -o addopts="" -rs
# CI 同款: 深度 1 的克隆 + 独立 venv (没有 data/, 取不到基点提交)
git clone --depth 1 --no-tags file://$R <临时目录>/ci_sim && cd <临时目录>/ci_sim && git submodule update --init --depth 1 && uv sync --extra dev --frozen
env -u VIRTUAL_ENV .venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs
env -u VIRTUAL_ENV .venv/bin/python -m pytest tests/test_workflow_conditions.py tests/test_kbsync_deploy_public.py -q -o addopts="" -rA \
  -k "changed_only_where_intended or without_a_pinned_subnet or public_network_is_read or real_probe_script"
# 变异 (在深度 1 的副本里; 改完先用 cmp 确认文件确实变了)
sed -i '' 's/seq 1 60/seq 1 5/' .gitea/workflows/sdtm-rag.yml tests/fixtures/workflows/base_9a8ad43_sdtm-rag.yml
$R/.venv/bin/python -m pytest tests/test_workflow_conditions.py -q -o addopts="" -p no:cacheprovider -k changed_only
# Gitea API (账号与口令取自 git credential, 不写进任何文件; 下面用占位符)
API=https://git.bojiang.org/api/v1/repos/bojiang/sdtm-rag
curl -u <账号>:$P -H 'Content-Type: application/json' -X POST $API/actions/workflows/sdtm-rag.yml/dispatches \
  -d '{"ref":"main","inputs":{"tag":"<空或40位SHA>","deploy":"false|true","force_data_mismatch":"false"}}'
curl -u <账号>:$P -H 'Content-Type: application/json' -X POST $API/actions/workflows/kb-sync.yml/dispatches -d '{"ref":"main","inputs":{"ref":"","public_baseline_image":""}}'
curl -u <账号>:$P $API/actions/runs/<run>/jobs; curl -u <账号>:$P $API/actions/jobs/<job>/logs      # 214/455·456, 215/457·458, 216/459·460, 217/461·462
curl -u <账号>:$P $API/actions/variables                                                              # []
# 两次 CI 的测试点阵逐位比 (日志每行去掉时间戳前缀后)
python3 -c "import re,sys; m=[''.join(re.match(r'^([.sFEx]+) +\[ *\d+%\]',l).group(1) for l in open(f) if re.match(r'^[.sFEx]+ +\[ *\d+%\]',l)) for f in sys.argv[1:3]]; print(len(m[0]),len(m[1]),[(i,a,b) for i,(a,b) in enumerate(zip(*m)) if a!=b])" <job455 日志> <job457 日志>
# 测试端口 / 限流补测 / 快照 (在 VM 内执行)
VM='ssh <mini 主机> export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- bash -s'
cat .work/10_split_and_public/evidence/checkpoints/p3_tunnel_leg_merge_testport_613f048.sh   | $VM
cat .work/10_split_and_public/evidence/checkpoints/p3_tunnel_leg_merge_testport_ratelimit.sh | $VM
cat .work/10_split_and_public/evidence/checkpoints/p3_tunnel_leg_merge_snapshot.sh           | $VM     # 合并前 / 部署前 / 部署后 / kb-sync 后各一次, 两两 diff
# 假密钥改写的等价核对
$PY .work/10_split_and_public/evidence/checkpoints/p3_tunnel_leg_merge_scrub_equiv.py && $PY -m pytest tests/test_kbsync_public.py -q -o addopts="" -p no:cacheprovider
```
