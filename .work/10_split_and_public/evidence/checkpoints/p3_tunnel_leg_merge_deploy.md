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
- 本机 `pytest -m "not slow"`, 最终代码 (本文件所在的提交): **3542 passed / 0 failed / 2 skipped** (两个 skip 都是要 playwright 的真浏览器闸)。修正前是 2 failed (上节)。「用真实隔离探测脚本」那条 (`test_isolation_check_with_the_real_probe_script`, 合并前是 skip) 现在真的运行并通过。
- CI 同款 (深度 1 的全新克隆 + 独立 venv, 无 `data/`): `e50a9f8` 上 3483 passed / 0 failed / 61 skipped; 4 条修正过的测试用 `-rA` 看都是 PASSED, 不是 SKIPPED。
- 主仓 `data/`: 运行前后对比 2090 个文件的大小与修改时间, 以及备份目录之外 1725 个文件的 sha256。**只有 `data/chroma` 下 9 个文件的修改时间变了**, 其中 `chroma.sqlite3` 和 2 个 `data_level0.bin` 内容有变、大小不变 (chromadb 打开索引时自己改写, 与 `p3_merge_deploy.md` 记的现象相同)。只读核对: 三个集合 4333 / 959 / 125 条, stamp `477bac3ce565…` / 4333, `check_index_freshness` OK。`data/study`、`data/meta` 0 变化。之后的几趟全量同理。
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

## 第 4–7 步 (续)
(第二次 push、重新只构建、测试端口、部署、kb-sync 空跑核对、收尾: 各步完成后续写)

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
```
