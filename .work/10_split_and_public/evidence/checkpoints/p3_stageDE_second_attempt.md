# 公开腿演练阶段 D / E 第二次: 价格固定分支合并 → 只构建 → 测试端口 → 部署 (私有站换新镜像 + 公开站第一次部署) → 启动公开容器 (2026-11-28)

本文件随各步完成续写。时间戳是 UTC。先例: `p3_stageDE_first_public_deploy.md` (第一次, run id 219, 失败)、`p3_tunnel_leg_merge_deploy.md` (只构建 → 测试端口 → 部署)、
`public_price_pin.md` / `public_price_pin_ext.md` (这次合并进来的修正)。方案: `p3_public_leg_impl.md` §5「阶段 D」「阶段 E」+ `docs/plans/P3_4_tunnel_drill.md` 第 5 步。

## 授权
主人 2026-11-28 在协调方的待办项上亲自选定 (**经待办项转达的选择**, 不是在本会话里说的):
- 问题一:「可以合并修复分支、构建新镜像并重新部署吗（私有站会重启一次，公开容器保持停止）？」→ 主人选「可以」。说明里写的顺序: 合并并推送 (不触发自动部署)
  → 只构建新镜像, 在测试端口上和线上镜像对比 (两条检索闸逐题对比、私有站行为不变) → 正式部署: 私有站换成新镜像、重启一次、数据不变; 同一次运行里公开站重做
  第一次部署 (网络隔离核对 → 无网络的临时容器验收 → 验证公开站的 Anthropic key → 换入候选数据 → 用新镜像重建公开容器并保持停止)。每一关不过就停下来汇报。
  公开腿再失败时公开站保持原样, 私有站已是新镜像。
- 问题二:「部署成功后，可以启动公开容器并做启动后的核对吗（仍没有对外入口）？」→ 主人选「可以，部署成功后接着做」。内容同上次: 健康、公开档、HTTPS 安全头、
  全局限流、只信任连接器地址; 删掉公开站 env 文件里那行旧的可信代理设置。
- **只覆盖**: 一次快进合并和 push; 一次只构建; 一次正式部署派发; `docker start sdtm-rag-public-api`; 演练方案第 5 步的核对、5a、5b; 收尾文档的 push。
  **不包括**: 重跑失败的部署、连接器、token、隧道、Cloudflare 的任何操作、改 Gitea 变量。

执行中协调方 (bot) 的决定 (**协调方的决定, 不是主人逐条裁定**):
- 2026-11-28: 合并后主仓全量测试有 1 条失败 (下文「合并后才红的 1 条测试」)。我列了三个选项, 协调方选「先修再 push, 由本会话修, 修完过独立审查」。
  理由 (协调方原话的要点): 改的只是一条测试, 代价是多一个提交; 换来 main 上不留一条「在有本机 .env 的检出里必红」的用例, 「主仓全量 0 failed」如实满足后再往下走;
  镜像仍然是「验过的提交」(只构建和测试端口验证本来就在 push 之后对新的头提交做)。范围: 只改这一条守卫用例及它的夹具所在的测试文件。
  因此头提交和镜像标签是 `66cb55d`, 不是任务最初写的 `c3c13ee`; 派单里「不起子代理」也因为这一条而有一处例外 (独立审查)。

## 起点 (13:21Z; 只读)
| 项 | 结果 |
|---|---|
| 本仓 | main = origin/main = `45fc1c6` (Gitea 与 GitHub 相同), 工作区干净; 分支 `hakupao/public-price-pin` = `c3c13ee`, merge-base = `45fc1c6` (可以快进); 分支头提交带 `[skip ci]` (12 个提交里 `955190f` `97d6aa0` `a464243` 三个不带) |
| Gitea | 最新运行 219 (`completed` / `failure`), 总数 25; 变量 `SDTM_RAG_PUBLIC_DEPLOY` = `true` |
| 私有站 | api Id `a9937c62…` / ui Id `e5d92671…`, 启动于 `2026-11-28T03:23:47.097798686Z` / `03:23:57.678917638Z`, 重启 0 次, 镜像 `613f048…`; `healthy`, 200; stamp `477bac3ce565…` / 4333; `meta.yaml` sha256 `b484d49e…`; chroma inode 53422、130 个文件; `study` 1557 个文件 |
| 公开站 | 容器 Id `2a33f280…`, `created` / 从未启动, 镜像 `…:099c2c9…`; 网络 Id `eff48d9c…` `10.201.8.0/24`, 0 个容器; 隔离表 1 张 5 条 `drop`; 巡检定时器与隔离单元 `active` / `enabled`; `nftables.service` `disabled` |
| 公开数据根 | 上一级只有 `data`; `chroma` (inode 50497, 内容摘要 `dabd65645e3d3d9a`, stamp `f863e45445a6…` / 4329)、`chroma_cand_477bac3ce565` (inode 56800, `2d36c96fc0e32d5d`, 4333)、`meta` (50534, `5db4931da6ddf8c0`)、`meta_cand_477bac3ce565` (56810, `0ace313802a980cb`)、`quota.sqlite`; journal / guard / prev / failed / accept 都是 0 |
| 机器 | 可用内存 5229 MB (总 7913 MB); 容器 23 个, 运行中 22 个, 非运行的只有公开容器 |

中途 Orca 重启过一次 (守卫用例修正做到一半, 还没有提交)。重启后复查 (15:25Z): 两个远端的 main、运行列表、变量、虚拟机快照 (同一个脚本, 去掉带时间的一行后机械 diff) 都与起点无差异; 本地未提交的改动原样在。

## 第一段: 合并 + push

### 推送前检查 (在合并**之前**做: 快进合并改不了历史, 命中只能先问)
范围 `45fc1c6..c3c13ee`, 逐提交扫 `git log -p` 的新增行 (2098 行, 16 个文件) 和 12 条提交信息:

| 口径 | 新增行 | 提交信息 |
|---|---|---|
| home 路径 (`/Users/<名>`、`/home/<名>`) | 0 | 0 |
| 本机账号名、提交者邮箱原值 | 0 | 0 |
| 邮箱 (`noreply@anthropic.com` 与示例域除外) | 0 (正则命中 2 种, 都是 `@pytest.fixture` / `@pytest.mark.parametrize` 装饰器) | 0 |
| 密钥形状 (各家 key 的前缀、私钥头、带值的 Bearer; 正则同 `p3_tunnel_leg_merge_deploy.md`「推送前检查」那一行) | 0 | 0 |
| JWT 形状 | 0 | 0 |
| 口令赋值形状、`curl -u 名:字面量` | 0 | 0 |

- 测试与离线探针里的 key 都是运行时拼的假值 (`"fake-" + "a" * 24` 之类), 没有完整的密钥形状。审查任务书 `public_price_pin_reviewers.md` 里没有本机路径。
- 红线扫描: 分支的 hook 当时是按 `OIDSCAN_NO_CATALOG=1` 跳过的, 快进合并也不触发 hook, 所以用主仓的 catalog 对分支改过的 16 个文件 (取分支头的内容) 和提交信息各补扫一次:
  `CLEAN: 0 处未在 allowlist 的 OID/label 命中`。
- 只计数、不拦截: 内网 / 公开网段地址 2 行, `bojiang` 1 行, 不含用户名的机器路径 2 行。

### 合并
`git merge --ff-only hakupao/public-price-pin` → main = `c3c13ee` (12 个提交)。submodule 仍是 `b2bd837` (`kb-2026.11.28`)。

### 合并后才红的 1 条测试 (规则 B: `../failures/p3_stageDE2_merge_pytest_attempt_1.md`)
主仓 `pytest -m "not slow"` (`c3c13ee`): **1 failed** / 3700 passed / 2 skipped —— 任务的判据是 0 failed, 停下来问了协调方 (没有 push)。

- 失败的是分支新加的守卫用例 `tests/test_p3_4_public_https.py::test_this_file_leaves_no_sdtm_rag_env_behind`。
- **原因 (测试自身的问题, 不是产品代码)**: 守卫的「跑之前」快照由模块级 autouse 夹具在文件开始时取一次; 本文件用到的模块级夹具 `engines`
  (`tests/test_p2_l2_integration.py`) 用自己的 `MonkeyPatch` 删掉全部 `SDTM_RAG_` 开头的环境变量, 模块收尾时还原。快照取在它之前, 守卫用例里看到的环境在它之后。
  主仓有本机 `.env` (18 个 `SDTM_RAG_` 键; `server/config.py` 导入时 `load_dotenv` 进环境), 于是快照 18 个、用例里 0 个, 必红 —— 而没有任何用例留下东西
  (逐条看环境键数: 第一条用到 `engines` 的用例 18 → 0, 最后一条之后 0 → 18)。
- **为什么在分支上没暴露**: 分支只在没有 `.env` 的检出里跑过 (深度 1 的克隆、子工作区)。又一种「合并后才红」: 只在有本机 `.env` 的检出里红。
- 对照实验 (临时目录里的深度 1 克隆): 没有 `.env` → 47 passed; 放一个只含一行 `SDTM_RAG_AUTH_ENABLED=false` 的 `.env` → 同一条红; 删掉 → 47 passed。
- 不受影响的: CI 条件 (`c3c13ee` 的深度 1 克隆 + 独立 venv, 没有 `data/`、没有 `.env`) 3642 passed / 0 failed / 61 skipped, 与分支记录一致; `tests/` 不进镜像。

**修法** (提交 `66cb55d`, 带 `[skip ci]`; 只改这一个测试文件):
- 函数级 autouse 夹具 `_record_sdtm_rag_env` 在**每条用例**前后各取一次 `SDTM_RAG_*` (不分大小写) 的快照, 有变化就把「哪条用例、哪些名字、added / removed / changed」记进一个模块级夹具持有的记录里;
  文件末尾的守卫读这份记录。
- **为什么这样就不受本机 `.env` 影响**: 两次快照都取在函数级、同一条用例的前后。pytest 先建模块级 / 会话级夹具再建函数级的, 并且在文件最后一条用例结束之前不收尾它们,
  所以一条用例的两次快照看到的是同一个模块级状态 —— `.env` 带来的名字要么两次都在 (还没有用到 `engines` 的用例), 要么两次都不在。autouse 夹具先于用例按名字请求的夹具建立,
  所以晚于用例自己的 `monkeypatch` 收尾: 第二次快照取在 monkeypatch 还原之后, 原来那种泄漏 (monkeypatch 把 `load_dotenv` 写进去的值「还原」回来) 正好落在两次快照之间。
- 守卫的三条断言: ① 守卫是本文件被选中的最后一条 (后面加了用例、或命令行把它排在前面 → 红, 信息写明两种原因); ② 本文件被选中的每条用例都被记录夹具看到
  (按 node id 比; 带 `skip` / `skipif` / `xfail(run=False)` 标记的用例可能在任何夹具建立之前就被跳过, 不要求被看到 —— conftest 在没有研究数据时给 `local_data` 用例加的就是 `skip` 标记, CI 正是这种情形);
  ③ 记录为空。只选中守卫一条时没有东西可查, `pytest.skip` 并写明原因 (以前是悄悄通过)。
- 只记名字和变化的种类: 旧写法失败时会把检出目录 `.env` 里的取值打印进断言信息。

**验证** (最终文件 sha256 前 16 位 `38b1971a5cfb8954`):

| 条件 | 全量 `pytest -m "not slow"` | 倒序命令 (上一轮复现串扰用的三文件命令) | 单文件 |
|---|---|---|---|
| 主仓文件夹 (有本机 `.env`) | **3701 passed / 0 failed / 2 skipped** | 140 passed | 47 passed; 只选守卫 → 1 skipped |
| 深度 1 克隆 + 独立 venv, 没有 `.env` (= CI 的条件) | **3642 passed / 0 failed / 61 skipped** | 140 passed | 47 passed |
| 同一个克隆, 放一个只含一行 `SDTM_RAG_AUTH_ENABLED=false` 的 `.env` | **3642 passed / 0 failed / 61 skipped** | 140 passed | 47 passed |

**变异** (`p3_stageDE2_guard_mutations.py`; 只在副本上跑、必须用副本自带的 venv, 先比 sha → 精确替换 → 回读 → `finally` 写回原始字节再比 sha; 判定看 summary 行和失败信息里预登记的文字):
没有 `.env` **17/17**、一行 `.env` **18/18** 与预登记一致, 基线与还原后都是 47 passed。

| 编号 | 变异 | 结果 |
|---|---|---|
| G1 | 把原来那处泄漏原样放回去 (= `public_price_pin_mutations.py` 的 XT) | 恰好守卫一条红: `('…::test_compose_env_wins_over_dotenv_same_key_and_case_variant', {'sdtm_rag_quota_trusted_proxies': 'added'})` |
| G2 / G3 | G1 + 拿掉「记录为空」的断言 / + 记录夹具不再比较前后 | 47 passed (漏过去 = 那条断言 / 那次比较确实在起作用) |
| G4 / G5 | 记录夹具不再 autouse / + 放回泄漏 + 拿掉断言 ② | 红 (`did not see these tests of this file: […`) / 47 passed |
| G6 / G7 / G7b | 守卫后面加一条用例 / + 拿掉断言 ① / + 两条都拿掉 | 红 (`the guard is not the last selected test`) / 仍红 (被 ② 抓住: 两条在这一情形上重叠, ① 留着是为了失败信息说对原因) / 48 passed |
| G8 | 另一种泄漏: 用例直接写 `os.environ` (大写名) | 红: `{'SDTM_RAG_LEFT_BY_A_MUTATION': 'added'}` |
| G9 (只在有 `.env` 时) | 反方向: `engines` 建起来之前的一条用例把 `.env` 带来的名字删掉不还原 | 红: `{'SDTM_RAG_AUTH_ENABLED': 'removed'}` |
| G10 / G11 | 类里一个同名的空夹具把记录夹具遮掉, 类里的用例泄漏 / + 拿掉断言 ② | 红 (列出那条用例的 node id) / 48 passed |
| G12 / G13 | 只选守卫一条 / + 拿掉「单独选中就 skip」 | 1 skipped (原因是预登记的那一句) / 1 passed (空过) |
| G14 / G15 | 遮掉记录夹具的类里, 泄漏的用例与模块级的一条用例同名 / + 整体退回按用例名比 | 红 / 48 passed (按用例名比会漏) |
| G16 / G17 | 加四条不会真正运行的用例 (`skip` / `skipif` / `xfail(run=False)` / `local_data`) / + 不再排除带 `skip` 标记的 | 47 passed, 3 skipped, 1 xfailed (不误报) / 红 (列出 `local_data` 和 `skip` 那两条) |

我自己的脚本在这个过程里错过三次, 都是「判定这一侧」的错, 都在跑出来的表上直接看得见 (记为 BAD, 没有被当成通过): 失败信息只取了第一行 (预登记文字在后面几行);
summary 行的匹配不认 `skipped`; 断言 ② 加强之后 G7 的预期没有跟着改。还有一条变异 (G9) 第一版设计错了 (在 `engines` 已经建起来之后去删名字, 删不到), 改成插在文件第一条用例之前。

**独立审查 (规则 D)**: `oh-my-claudecode:code-reviewer` (opus), 只读, 实验在它自己的临时副本里做; 任务书 `../subagent_prompts/review_guard_env_fix.md`。三轮:

| 轮 | 看的版本 | 结论 | 要点 |
|---|---|---|---|
| 1 | 第一版 | PASS-with-fixes (没有阻塞项) | 原泄漏抓得住; 不再受 `.env` 影响; 失败信息不再带取值。四处小改: 断言 ② 加强成「每条用例都被看到」(它构造的「遮掉记录夹具」变异漏了)、两处文档字符串说大了 / 不完整、只选守卫时应 skip、断言 ① 的信息在「命令行顺序」情形下说错原因 |
| 2 | `d7691d91…` | PASS-with-fixes | 第一轮建议的「每条用例都被看到」带进两个问题: 带 skip 类标记的用例误报红 (**`local_data` 会本机绿、CI 红**, MEDIUM); 按用例名比有同名盲区 (LOW-MEDIUM)。建议换成 node id, 并排除不会运行的用例 |
| 3 | `38b1971a…` (= 提交的) | **PASS, 没有合并前必须改的** | node id 改全了; 第二轮列的 18 种情形逐个重跑, 两个问题都已修掉, 没有新的误报 / 漏报; conftest 动态加的 `skip`、`pytest.param(marks=…)`、类级 `pytestmark` 上的标记都取得到 |

处置与没有改的:
- 第二轮「排除不会运行的用例」, 审查者给的写法用 pytest 的私有接口 (`_pytest.skipping.evaluate_*`); 我改用公开接口按「标记是否存在」排除。代价 (第三轮审查者实际构造并确认, 认为可以接受):
  带着会运行的 skip 类标记 (如 `skipif(False)`) **并且**记录夹具被遮掉的用例, 泄漏会漏过去; 模块级 `pytestmark = skipif(…)` 会让断言 ② 对整个文件失效 (现在文件里没有任何 skip 类标记)。
- 没有改、只记录: conftest 在 `pytest_runtest_setup` 钩子里直接 `pytest.skip()` (不留标记) 会让守卫误报红 (本仓没有这种钩子; 是大声的红); conftest / 插件里出现请求 `monkeypatch` 的 autouse 夹具时,
  守卫会对每条经 monkeypatch 设环境变量的用例误报红 (写在夹具的文档字符串里; 同样是大声的红); 模块级夹具的 setup、导入时的代码、守卫自己的用例体不在覆盖范围内 (旧写法能看到模块级夹具留下的小写名, 这一点比旧写法窄;
  反过来 `engines` 建起来之前写进去的大写名旧写法看不到、新写法看得到); `-x` 在守卫之前停下、`--deselect` 守卫时不检查 (改之前就这样)。
- 审查者没能核实的: 全量测试 (它的副本没有 KB 和 `data/`; 上表的全量是我跑的); 用副本自带的 venv 实际跑我的变异脚本 (它读了代码, 另做了等价变异); 只在 pytest 9.0.3 上验证。
- **审查过程里的一件事 (如实记录)**: 我在任务书里让审查者用主仓的 venv 跑副本。litellm 在导入时会从它的安装位置往上找 `.env` (`LITELLM_MODE` 为默认值时),
  于是主仓的 `.env` 被读进了副本的测试进程 —— 「副本里没有 `.env`」的条件不成立。审查者发现后改设 `LITELLM_MODE=PRODUCTION`。发现之前的第一趟里, 旧版守卫的失败信息把主仓 `.env`
  里几个配置项的取值 (截断的; 它说看到的是路径、数字这类非密钥值) 显示在了它的工具输出里, 没有写进任何文件或报告。我自己的副本用的是副本自带的 venv, 没有这个问题。已补记在任务书末尾,
  变异脚本也加了「解释器必须是副本自带的 venv」的检查。

### push
- 对新提交补做推送前检查 (范围 `c3c13ee..66cb55d`, 338 行新增 + 1 条提交信息): 各口径都是 0 (邮箱正则命中的 1 种是 `@pytest.fixture`); 提交过了 pre-commit 红线闸 (CLEAN, 3 个文件), 提交信息另扫 CLEAN。
- **16:06:40Z** `git push origin main` (非强推): Gitea 与 GitHub 都是 `45fc1c6..66cb55d`; 两个远端的 main = `66cb55d288ccae318dee79c2310aa698f51a7f1a`。13 个提交 = 分支的 12 个 + 守卫修正 1 个; 头提交带 `[skip ci]`。
- 推后 30 / 60 / 90 秒各看一次运行列表: **没有被这次 push 触发的运行**, 最新仍是 219; 变量仍是 `true`。
- 主仓 `data/`: 合并前记一次 (2090 个文件的大小与修改时间; 备份目录之外 1725 个文件的 sha256), 收尾时 (四趟全量和若干趟单文件都跑完之后) 两样各重新量一次: 只有 `data/chroma` 下 9 个文件的修改时间变了, 0 个文件大小变化,
  内容有变的是 `chroma.sqlite3` 和 2 个 `data_level0.bin` (chromadb 打开索引时自己改写, 同先例), `data/chroma` 之外 0 个文件有变化; `check_index_freshness` OK (`477bac3ce565…`)。第一趟全量之后量的那一次结果相同。

## 第二段 2a: 只构建 —— run 220 success
- 派发前从 workflow 确认 `deploy` = false 时公开部署不运行: `deploy_public` 的 `if` 是 `gitea.ref == 'refs/heads/main' && vars.SDTM_RAG_PUBLIC_DEPLOY == 'true' && (gitea.event_name != 'workflow_dispatch' || format('{0}', inputs.deploy) != 'false')`;
  真值表 (`p3_public_leg_if_tables.md`) 里「ref=main, 公开变量=true, event_name=workflow_dispatch, 输入.deploy=false → 否」; `tests/test_workflow_conditions.py` 165 passed; `.gitea/` 与 `deploy/` 下自 `45fc1c6` 以来只有 `deploy/README.md` 有改动。
  这个方向 (变量开着 + deploy=false) 此前没有在真机上见过 (run 214 / 215 时变量还没开)。
- **16:09:10Z** `POST …/actions/workflows/sdtm-rag.yml/dispatches`, 正文 `{"ref":"main","inputs":{"tag":"","deploy":"false","force_data_mismatch":"false"}}` → HTTP 204。**只派发了这一次。**
- run id **220** (`run_number` 26), `head_sha` = `66cb55d288ccae318dee79c2310aa698f51a7f1a`, 16:09:12Z → 16:11:43Z, `completed` / `success`。
- `deploy` (job 467): checkout (`git log -1` 打印 `66cb55d…`) / **测试** / 登录 / 确定标签 (`部署标签：66cb55d288ccae318dee79c2310aa698f51a7f1a`) / **构建并推送** success; 记录线上镜像、KB 对齐、部署、健康检查、新鲜度、换数据收尾、两个退回步骤 **全部 skipped**。
- CI 测试: **3642 passed / 0 failed / 61 skipped** (与本机深度 1 克隆的数字相同)。
- 镜像 `192.168.100.58/bojiang/sdtm-rag:66cb55d288ccae318dee79c2310aa698f51a7f1a`, digest `sha256:ddcfc476d0c3d4ccb5761b6e1ccc27c9693b976e567159f0225af97ea97ed7a0`。
- `deploy_public` (job 468) **skipped** (没有开始, 没有日志)。「变量开着 + deploy=false → 公开腿跳过」第一次在真机上见到。
- 只构建前后的线上快照 (`p3_stageC_snapshot.sh`) 机械 diff 只差一行: 虚拟机本地的 `sdtm-rag` 镜像数 4 → 5、镜像总数 36 → 37 (runner 用的就是虚拟机的 docker, 新镜像构建在本地)。私有站、公开容器、公开数据根都没有变。

## 第二段 2b: 测试端口验证 —— PASS (`p3_stageDE2_testport.sh`; 16:12:11Z – 16:15:34Z)
新镜像 `66cb55d` (镜像 ID `sha256:ddcfc476…`) 对线上镜像 `613f048` (`sha256:9e1ac10b…`), 各用线上 chroma 的一份副本, 线上 meta 与生产 env 只读挂载; 不发布端口, 全部经 `docker exec`。

| 判据 | 新镜像 | 线上镜像 (对照) |
|---|---|---|
| 启动 | 起容器后 9 秒内 health 200 | 12 秒内 |
| freshness | OK, `477bac3ce565…`, 4333 条 | 同 |
| 容器里读到的数据 (防挂错) | 集合 4333 / 959 / 125; `model_defhome` 75, EPOCH → `model/02` | 同 |
| CDISC 140 题 | 138 满分 / avg 0.9917, 非满分 q38、q126 | 同; **逐题 recall 0 差** |
| study 51 条 | avg 0.875, 满分 45 | 同; **逐题 recall 0 差** |
| `/api/ask` (真答题) | 200 | 200 |
| `/api/info` | 19 个键, 无 tier / providers / quota | **键集相同** |

- `top5_sources` 不同的题数 (不是判据, 如实记录): CDISC 1 题, study 2 题, recall 都不变 (同一份索引两趟之间的波动, 先例里记过)。预登记判据 (recall 相差不超过 1 题) 满足。
- **私有档行为不变**:
  - 生产 env 下两边读到的开关相同: `instance = 'private'`, `auth_enabled=False`, `rate_limit_enabled=True`, `security_headers_enabled=True`, 限额未开。
  - 响应头: 13 个探测 (首页、静态文件、health、info、openapi、docs、不存在的路径、GET / POST login、422、flag、带伪造的 `X-Forwarded-Proto` / `CF-Connecting-IP` 的请求、真答题) 新旧**逐项相同**
    (状态码、响应头名集合、除 date / content-length / etag / last-modified 外各头的值; 探测数与每个响应的头数有下限断言)。HSTS 新旧都是 0 次。
  - cookie: 新旧都是 0 条 `Set-Cookie` (生产配置下登录门和限额都没开, 不发 cookie —— 真机上无 cookie 可比, 同先例)。
  - **新加的「没有固定价格就拒绝启动」不影响私有档**: 新镜像带生产 env 照常起到 healthy, `check_startup` 通过。把公开档的成本自检函数直接用在这份私有配置上, 它会报 5 条
    (没有显式设可选模型; 内置四个可选模型的单轮预留 1.4 – 3.5 美元超过 0.30) —— 新旧镜像报的一样。会报而应用照常启动 = 私有档确实不走这道检查。
- **成本估算的新旧对比** (这次改动特有): 私有站生产配置里实际出现的模型串, 新旧镜像各调一次 `cost.estimate_cost` (服务里对比徽章用的就是它)。口径: 提示词 50,000 + 输出 2,000 token (不跨 Haiku 5.5 的 100,000 分档线), 另列 150,000 + 2,000。
  两边 litellm (1.88.6) 的价格表都是联网取到的 7194 条 (来源 remote), 所以「原来有数」这条基线是有效的; 比较前有下限断言 (模型串不少于 5 个、旧侧至少 3 个有数、两侧读到的模型串集合相同)。

  | 模型串 | 出现在 | 50k 口径 旧 → 新 (美元) | 150k 口径 旧 → 新 | 新镜像固定表里有 |
  |---|---|---|---|---|
  | `anthropic/claude-sonnet-5-5` | default / hard / light、可选 `sonnet-5-5` | 0.12 → 0.12 | 0.32 → 0.32 | 有 |
  | `anthropic/claude-sonnet-5` | 可选 `sonnet-5` | 0.12 → 0.12 | 0.32 → 0.32 | 有 |
  | `anthropic/claude-opus-5-5` | 可选 `opus-5-5` | 0.24 → 0.24 | 0.64 → 0.64 | 有 |
  | `anthropic/claude-opus-5` | 可选 `opus-5` | 0.30 → 0.30 | 0.80 → 0.80 | 有 |
  | `anthropic/claude-sonnet-4-6` | 对比 | 0.18 → 0.18 | 0.48 → 0.48 | 有 |
  | `deepseek/deepseek-v4-pro` | fallback、对比 | 0.07392 → 0.07392 | 0.20592 → 0.20592 | 有 |
  | `openai/gpt-4o` | 对比 | 0.145 → 0.145 | 0.395 → 0.395 | 没有 (litellm 给价) |
  | `deepseek/deepseek-chat` | 扩写、判分 | 0.01484 → 0.01484 | 0.04284 → 0.04284 | 没有 (litellm 给价) |
  | `text-embedding-3-small` | embedding | 0.001 → 0.001 | 0.003 → 0.003 | 有 (旧: litellm 给价, 数值相同) |
  | `rerank-v3.5` | 重排 | 没有 → 没有 | 没有 → 没有 | 没有 (不是按 token 计价的模型; 改之前就没有数) |
  | `claude-sonnet-5-5` (服务商在响应里回报的名字) | 真答题 | 0.12 → 0.12 | 0.32 → 0.32 | 有 |

  **11 个模型串新旧逐个相同; 「原来有数、现在没有」0 个; 两种口径都是。** 可选模型的 (id, 模型串, 输出上限) 新旧相同 (私有站没有显式设可选模型, 用的是内置的四个, 输出上限 128000)。
  分支 checkpoint 列的五处「两档都生效」的改动 (匹配只认本名或日期后缀、只认本服务商的前缀、结算的下限、预留覆盖回退档、Haiku 5.5 的高档) 在私有站实际配置上没有碰到任何一个模型串:
  配置里没有带非日期后缀或别的渠道前缀的写法, 没有 Haiku 5.5, 私有站也没有开计量。
- **第一次核实到的: 服务商回报的模型名的写法。** 两次真答题 (新旧各一次, 走 default = `anthropic/claude-sonnet-5-5`) 响应里的 `model_used` 都是裸名 `claude-sonnet-5-5`, 能命中固定表。
  按回报的名字与用量估算: 新 0.053612 / 旧 0.055452 美元 (提示词都是 18671 token; 输出 1627 / 1811 token, 两次答案长度不同; 单价相同)。Haiku 5.5 和 DeepSeek 回报什么名字仍然没有核实 (没有发那样的请求)。
- 线上不受影响: 验证前后线上 api 的镜像 `613f048`、启动时间 `03:23:47.097798686Z` 不变, health 200; 临时容器与副本已清 (脚本有出错清理)。
- 相对先例去掉的两组: 限流对比 (R) 与大小写变体 (C) —— 都是上次合并特有的检查, 这次的改动不碰那两处。

## 第二段 2c: 正式部署之前的只读预检 (16:16Z – 16:17Z) —— 都满足
| # | 项 | 结论 | 依据 |
|---|---|---|---|
| 1 | tag 非空时 job checkout 的提交 | main 的当前提交 `66cb55d` | workflow 里没有 `ref:` 键, 两个 job 都是 `actions/checkout@v4`; Gitea main = `66cb55d…`; Gitea main 上 6 个文件的 blob 号与本地逐个相同 (`sdtm-rag.yml` `d67d9d11…`、`kbsync.py` `45ce8d1c…`、`compose.public.yml` `a5d67787…`、`compose.yml` `f7270884…`、`image_floor_check.py` `890f2fbf…`、`isolation_probe.py` `523736d7…` —— 与 run 219 那次也相同: 这些文件没有变) |
| 2 | `deploy_public` 的 `if` | 在「手动派发 + tag 有值 + deploy = true + 变量已开」下为真 | 真值表对应行「…输入.deploy=true, 输入.tag=0000… → 是」; `tests/test_workflow_conditions.py` 165 passed; 变量读回 `true` |
| 3 | 镜像 | 仓库里和虚拟机本地都在; 满足镜像下限; 镜像内 KB 指纹与候选一致 | 本地 `sha256:ddcfc476…`, `WorkingDir` `/app`; Gitea 包接口对该标签返回 200 (建于 16:11:42Z); 镜像下限 `docker run --rm -i --entrypoint python <镜像> - < image_floor_check.py` 退出码 0、输出恰为 `image-floor: ok`; 镜像内 KB 指纹 `477bac3ce565aa810c38aeb14a35bf22f2c760c13a7e0b5f7d3bcf6ee24e3236`, chromadb `1.5.9`, `anthropic 0.107.1` 能 import, `PUBLIC_EDGE_LEVEL` = 1; `deploy/container/` 自 `613f048` 以来没有改动 |
| 4 | 基线快照 | 与起点一致 (只多一个本地镜像) | 无运行中的 Actions (最新 220 已完成), 没有 job 容器 / 网络残留; 公开容器 `created` / 镜像 `099c2c9…`; 公开线上 stamp `f863e454…` / 4329, 两个候选在, journal / guard / prev / failed / accept 都是 0; 隔离表 1 张 5 条 `drop`, 巡检定时器 `active` / `enabled`; 私有站 health 200, 容器 Id、启动时间、数据指纹同起点; 可用内存 5233 MB |
| 5 | **离线自检对照 (这次特有)** | **通过** | 见下 |

**离线自检对照** (16:16:41Z – 16:16:44Z): 合并进来的 `public_price_pin_offline_probe.py emit` (不带文件参数 = 镜像原样), 经标准输入送进新镜像的一次性容器:
`docker run --rm -i --name ppp-offline-probe --network none --cap-drop ALL --security-opt no-new-privileges --memory 1g --entrypoint python <镜像> -`。不带 env 文件、不挂数据、不挂宿主目录、不发布端口; key 是脚本里运行时拼的假值;
模型设置是公开站那一份 (四档与可选都是 `anthropic/claude-haiku-5-5`, 可选项与回退档输出上限 16000, embedding `text-embedding-3-small`)。

| 项 | 结果 |
|---|---|
| 载入的模块 | `/app/server/cost.py b870f37e21242afd`、`quota.py aec66b6ae0bcfe67`、`instance.py 786162a0db295f97` —— 是镜像里的文件, sha256 与本地 main 上的三个文件相同 |
| litellm 价格表 | 包内表 (`local`), 2764 条, 没有 `claude-haiku-5-5`; 原因 `Temporary failure in name resolution` (确实没有网络) |
| 成本自检 | `[]` |
| 一轮答题的候选 | `('haiku-5-5', 'anthropic/claude-haiku-5-5', 16000, 0.07)`、`('default-fallback', 'anthropic/claude-haiku-5-5', 16000, 0.07)` |
| 单轮上限 / 免费池的十分之一 | 0.07 / 0.30 |
| 整个 `check_startup` | passes; `VERDICT: PASS (no problems)` |

前后核对: 私有站 `/api/health` 200 / 200, 两个容器的启动时间、重启次数、镜像不变, 全部容器的名单与状态指纹前后相同; 一次性容器 (`--rm`) 已不存在。
这一步上一次是「修之后才想到」的缺口 (第一次部署的复盘第 1 条); 这次放在派发之前。它验的仍然只是启动自检, 不挂数据、起不了完整应用 —— 「没有网络的临时容器能否一路起到 healthy」要看下面真实的临时验收。

## 第二段 2d: 正式部署 —— run id 221, 两个 job 都 success
- 派发前起只读轮询 (`p3_stageDE_poll.sh`, 约 4 秒一个样本, 落本机文件), 取 `p3_stageDE_pubdirs.sh` 一份; 派发前一刻再读一次: 最新运行 220 已完成, Gitea main `66cb55d`, 变量 `true`, 本地没有已跟踪文件的改动。只构建与部署之间没有 push。
- **16:17:25Z** `POST …/actions/workflows/sdtm-rag.yml/dispatches`, 正文 `{"ref":"main","inputs":{"tag":"66cb55d288ccae318dee79c2310aa698f51a7f1a","deploy":"true","force_data_mismatch":"false"}}` → HTTP 204。**只派发了这一次。**
- run id **221** (`run_number` 27), `head_sha` = `66cb55d…`, 16:17:27Z → 16:19:03Z, `completed` / **`success`**。

### `deploy` (job 469, 16:17:27Z → 16:18:00Z, 33 秒) —— success, 与预期一致
| 步骤 | 结论 | 关键日志行 |
|---|---|---|
| checkout | success | `66cb55d288ccae318dee79c2310aa698f51a7f1a` |
| 测试 / 构建并推送 | skipped | (tag 非空) |
| 确定要部署的标签 | success | `部署标签：66cb55d288ccae318dee79c2310aa698f51a7f1a` |
| 记录当前线上镜像 | success | `部署前线上镜像标签：613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7` |
| KB 数据对齐检查 | success | `Status: Image is up to date for …:66cb55d…` → `{"prod_fp12": "477bac3ce565", "target_fp12": "477bac3ce565", "decision": "same"}` →「镜像 KB 指纹与生产 chroma 一致，不换数据」 |
| 部署 | success | `挂载目标目录：/app`; ` Container sdtm-rag-api Recreate` / `Recreated`, ` Container sdtm-rag-ui Recreate` / `Recreated`, api `Starting` / `Started` (16:17:47.98Z) / `Waiting` / `Healthy` (16:17:58.49Z, 约 10.5 秒), ui `Started`; 两个容器的运行镜像都是 `…:66cb55d…` |
| 健康检查 | success | `健康检查通过（172.18.0.1:8000/api/health 返回 200）` |
| 新鲜度 / 换数据收尾 / 两个退回步骤 | skipped | |

### `deploy_public` (job 470, 16:18:02Z → 16:19:03Z, 61 秒) —— success
| # | 步骤 | 结论 | 用时 | 关键日志行 |
|---|---|---|---|---|
| 0 | checkout | success | 3 秒 | `66cb55d288ccae318dee79c2310aa698f51a7f1a` |
| 1 | 登录镜像仓库 | success | <1 秒 | |
| 2 | 公开实例预检 (镜像) | success | 5 秒 | `Status: Image is up to date for …:66cb55d…`; 四条检查 (能 import `server.instance` / 公开档解析为 public / `WorkingDir` = `/app` / 镜像下限) 都没有报错 |
| 3 | 临时容器验收，通过后才换正式容器 | **success** | 48 秒 | 见下 |
| 4 | 中断时停掉已被动过的公开实例 | skipped | | (没有失败, 不触发) |
| 5 | 清理临时容器与验收副本 | success | <1 秒 | |
| 6 | 退出镜像仓库 | success | <1 秒 | |

第 3 步的输出 (`[deploy-public]` 开头的行原样; 这一步的输出是结束时一次性刷出来的, 日志时间戳都是 16:19:01.00Z):
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
[deploy-public] 临时容器验收通过，已清理临时容器与数据副本
[deploy-public] 答题 key 探测通过（只列模型，未发答题请求）
{"swapped": true, "ts": "20261128T161813Z", "target_fp": "477bac3ce565…", "old_fp": "f863e45445a6…", "source_chroma": "chroma_cand_477bac3ce565", "source_meta": "meta_cand_477bac3ce565", …}
[deploy-public] 旧数据副本清理：{"kept": ["chroma_prev_f863e45445a6_20261128T161813Z"], "removed": []}
[deploy-public] 成功：镜像已更新为 192.168.100.58/bojiang/sdtm-rag:66cb55d288ccae318dee79c2310aa698f51a7f1a，数据已换入 chroma_cand_477bac3ce565；**公开容器保持停止**（部署前就是停止的，部署不会把它拉起）。
[deploy-public] 启动需人工：在部署机上执行 `docker start sdtm-rag-public-api`（首次上线和故障后恢复都走这一步）。
```

各小步的时刻 (轮询样本; 16:17:05Z – 16:19:28Z 共 37 个样本, 约 4 秒一个, 所以是区间):

| 事件 | 时刻 (UTC) | 依据 |
|---|---|---|
| 私有 api 被重建并启动 | 16:17:47 的样本是 `created`, 16:17:51 起 `running`, 启动于 `16:17:47.908311993Z` | 轮询 + 日志 |
| 公开腿第 3 步开始 | 16:18:13 | 日志; 换入的时间戳与验收副本目录名也是 `161813Z` |
| 红线检查 (在副本上读线上公开 chroma 的集合) | 16:18:16 的样本里数据根多一个 `kbsync_guard_20261128T161813Z`, 16:18:20 已删 | 轮询看到的只是目录出现和消失; 「是红线检查建的」按编排的代码顺序判断: `kbsync.py` 的 `_deploy_public` 里, 排在隔离核对之前、会建这个副本的只有 `live_extra_collections` |
| 网络预检、隔离核对 | 约 16:18:20 – 16:18:43 (约 23 秒; 7 个内网目标各等满超时) | 这一段里数据根和它的上一级都没有变化 |
| **临时容器: 启动 → healthy → 清掉** | **16:18:43 还没有容器; 16:18:47 `running/starting`** (验收副本 `kbsync_accept_20261128T161813Z` 同时出现在上一级); **16:18:51 `running/healthy`**; 16:18:55 容器和副本都已清掉 | 轮询。**从启动到 healthy 不超过约 8 秒** |
| 答题 key 探测、换入前的核对 | 16:18:55 的样本里又有 `kbsync_guard_…`, 16:18:59 已删 | 轮询。临时验收之后会建这个副本的是 `swap_guard`, 它在编排里被调用两次 (换入前置核对、停机之后的主闸), 用同一个目录名 —— 一个样本分不出是哪一次 |
| 换入、`up --no-start` | 16:19:03 的样本: 数据根 = `chroma chroma_prev_f863e45445a6_20261128T161813Z meta meta_prev_… quota.sqlite`; 公开容器 Id `50ba94ed…`、镜像 `66cb55d2`、`created` / `run=false` | 轮询 |

整个运行期间公开容器每个样本都是 `created` / `run=false`; 可用内存最低 4754 MB。轮询是虚拟机里的一个 shell 循环, 运行结束后从本机断开; 之后在虚拟机和本机各看过, 没有残留的进程。

checkpoint 点名要记的三件事:
- **没有网络的临时容器从启动到 healthy 用了多久**: 不超过约 8 秒 (上表)。这是第一次有答案: 价格这一关过了之后, 后面 (BM25 建索引、其余启动自检、健康检查、档位 / 内部接口 / `check_index_freshness` / 集合检查) 在没有网络的条件下都正常。
- **「换入」一段有没有 `readonly` 相关报错**: 没有 (整份日志里 `readonly` / `read-only` 0 行)。嵌套挂载 (上一级可写 + 数据根只读) 下的副本、改名换入、`finish`、`prune` 都做成了。
- **key 探测容器能否读到只读挂载的 env 文件**: 能 —— 「答题 key 探测通过」这一行出现了 (去掉全部 capability 的探测容器读到了 env 文件, 并在隔离规则下连上了 Anthropic)。**公开站的 Anthropic key 第一次被验证, 只验了有效性**。

### 与预期逐条对照
| 预期 | 实际 |
|---|---|
| 私有 `deploy`: KB 对齐 `same`, 不换数据, 换成新镜像 (容器重建, 启动时间变), 健康检查 200, 线上数据与 meta 不变 | **一致** (新鲜度那一步在工作流里只在换数据时跑, 这次是 skipped; 部署后在容器里另跑了一次, OK) |
| `deploy_public`: 预检 (含镜像下限) → 路径一致 → KB 对齐 `swap` → 部署前状态 → 子网与 compose 一致 → 隔离核对 PASS (源地址在 `10.201.8.0/24`) | **一致** (路径一致时编排不打印, 没有「路径不一致」的行; 源地址 `10.201.8.128`) |
| 临时容器启动 → 验收通过并清理 | **一致** |
| 「答题 key 探测通过」 | **一致** |
| 换入 → `up --no-start` → 「成功：镜像已更新…公开容器保持停止…」 | **一致** |

## 2d 之后、第三段之前的闸 —— 全部满足 (`p3_stageDE2_gate.sh`)
| 闸的条件 | 结果 |
|---|---|
| run 整体 success, 两个 job 都 success | 满足 (run 221; job 469、470) |
| 三行日志都在: 隔离核对 PASS 且源地址在公开网段内 / 临时容器验收通过 / 「答题 key 探测通过」 | 都在 |
| 公开容器未运行、镜像是新 tag | `created` / `running=false` / `started=0001-01-01T00:00:00Z` / 镜像 `…:66cb55d…` (被 `up --no-start` 重建: Id `2a33f280…` → `50ba94ed…`; 重启策略 `unless-stopped`) |
| 没有 `sdtm-rag-public-accept` 临时容器; 没有 accept 网络 | 满足 |
| 公开数据根上一级只有 `data` | 满足 |
| 数据根里有 `chroma_prev_f863e45445a6_<ts>` / `meta_prev_…`, 没有 `kbsync_swap.json` / `kbsync_guard_*` | `chroma  chroma_prev_f863e45445a6_20261128T161813Z  meta  meta_prev_f863e45445a6_20261128T161813Z  quota.sqlite`; journal 0 / guard 0 / cand 0 / failed 0 |
| 线上 stamp `477bac3ce565…` | `kb_fingerprint=477bac3ce565aa810c38aeb14a35bf22f2c760c13a7e0b5f7d3bcf6ee24e3236`, 4333 条 |
| 私有站 health 200、数据指纹不变 | `66cb55d`、`running` / `healthy`、200; 容器内 `check_index_freshness` OK; `/api/info` 19 个键、无 tier / providers / quota、`chunk_count` 4333、响应头没有 HSTS; 快照 diff 里私有数据根没有任何一行变化 |
| 两份 job 日志只计数的扫描为 0 | job 469 (311 行) / job 470 (218 行): 密钥形状 0, JWT 形状 0, `study` 开头的词 0, 带用户名的路径 0, 带取值的 key / token 赋值 0 |

换入对不对, 按 inode 和内容摘要对上了 (`p3_stageDE_pubdirs.sh` 部署前后各一份): 线上 `chroma` = 原来的候选 (inode 56800, 内容摘要 `2d36c96fc0e32d5d`, 15 个文件, 含 `kbsync_gate.json` 与 `kbsync_eval/`);
`chroma_prev_f863e45445a6_20261128T161813Z` = 原来的线上 (inode 50497, `dabd65645e3d3d9a`); `meta` (inode 56810, `0ace313802a980cb`) 与 `meta_prev_…` (50534, `5db4931da6ddf8c0`) 同理; `quota.sqlite` 的 inode / 大小 / mtime 没变。

## 第三段: 启动公开容器 + 启动后的核对 —— 全部符合预期
| # | 项 | 结果 |
|---|---|---|
| 1 | **16:20:44Z** `docker start sdtm-rag-public-api` | 11 秒内 `running` / `healthy`; 启动于 `2026-11-28T16:20:44.135511911Z`, 重启 0 次。新镜像 + 新数据第一次在正式容器里启动 |
| 2 | 档位 / 新鲜度 / 内部接口 | `/api/info` tier = `public` (7 个键; 可选模型 `haiku-5-5`); 容器内 `check_index_freshness` OK (`477bac3ce565…`); `/openapi.json` 404 (`/docs` 也是 404); `/api/health` 200 |
| 3 | 演练方案第 5 步的只读核对 (原样命令) | `healthy sdtm-rag-public=10.201.8.128 ports=map[8000/tcp:[] 8501/tcp:[]]` —— 只在 `sdtm-rag-public` 网络上 (网络数 1), 地址在动态段 (`.128` – `.255`) 里, 没有发布端口 (方括号里是空的: 只是镜像声明的端口; `HostConfig.PortBindings` = `map[]`); 可信代理 `10.201.8.2`; `FORWARDED_ALLOW_IPS = ''`; HSTS `max-age=31536000`; cookie `sdtm_visitor` 的属性 `Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax; Secure` (没有打印值) |
| 4 | 5a 全局限流 (16:21:27Z) | `设置: True 60 20`; `25 次 /api/info: 20 个 200, 5 个 429`; `健康检查: 200`; 容器仍 `healthy` |
| 5 | 5b 删旧行 (16:21:38Z – 16:22:20Z; 演练方案的原样命令) | 见下 |
| 6 | 隔离复核 (`isolation_probe.py`; 公开网络里的一次性容器 + 虚拟机本机对照) | **结论 PASS**: 隔离侧源地址 `10.201.8.129` 在 `10.201.8.0/24` 里 (`.128` 被公开容器占着); 7 个内网目标隔离侧 `timeout` / 对照侧 `open`; 3 个外网目标可达。规则表 5 条 `drop`, 巡检定时器 `active` / `enabled`, 隔离单元 `active`, `nftables.service` `disabled` |
| 7 | 没有对外入口 (`p3_stageDE2_stage3_readonly.sh`) | 公开容器 `PortBindings=map[]`、`PublishAll=false`; 没有连接器 / cloudflared 容器; 公开网络里只有 `sdtm-rag-public-api=10.201.8.128/24`; token 目录 `/opt/sdtm-rag-public/cloudflared` 不存在。从开发机 (局域网) 和 mini 本机连 `10.201.8.128:8000` 都超时; 只有虚拟机本机能直连它的网桥地址 (200) —— 预期内: 能进虚拟机本来就等于 root, 隔离规则管的是公开容器往外连, 不管虚拟机连它 |
| 8 | 启动成本自检与在线价格表 | 见下 |

**5b 的经过** (全程没有显示 env 文件的内容):
1. 删之前「先确认」: `环境变量: 10.201.8.2` / `应用实际用的: 10.201.8.2` / `env 文件里这个键的行数 (不分大小写): 1` —— 前两行都是 `10.201.8.2`, 可以删。
2. `sudo cp -p … .env.before-cleanup` → `sudo sed -i '/^SDTM_RAG_QUOTA_TRUSTED_PROXIES=/d' …/.env` → 行数与权限: **备份 16 行, 现在 15 行 (正好少 1); `600 root:root`** (备份文件也是 `600 root:root`)。
3. `docker restart sdtm-rag-public-api` → `healthy` (启动于 `2026-11-28T16:22:03.299279989Z`)。
4. 复核: 「先确认」再跑一遍 → 前两行仍是 `10.201.8.2`, 行数 `0`; `设置: True 60 20`、tier `public`、HSTS、cookie `Secure`、`FORWARDED_ALLOW_IPS = ''`、`/openapi.json` 404、健康检查 200、freshness OK, 都与删之前相同。
5. 复核通过后 `sudo rm /opt/sdtm-rag-public/.env.before-cleanup`。目录里现在只有 `.env` 和 `.env.bak-20261127` (都是 `600 root:root`); **后者是协调方以前留的, 没有读、没有动**。
没有触发「恢复备份」。

**第 8 项**: 容器日志里**不打印**单轮上限 —— 日志只做了计数 (这次容器创建以来 68 行): `Traceback` 0, error 级 0, `refuses to start` 0, 价格表相关的告警 0, `Application startup complete` 2 次 (第一次启动 + 5b 的重启)。
数值是用容器的真实环境在容器里新开一个进程读出来的 (只打印模型类设置和数字):

| 项 | 值 |
|---|---|
| 档位 / 四档 / embedding | `public`; 四档都是 `anthropic/claude-haiku-5-5`; `text-embedding-3-small` |
| 可选模型 (id, 模型串, 输出上限) | `('haiku-5-5', 'anthropic/claude-haiku-5-5', 16000)` |
| **回退档输出上限 (`SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS`) 的实际值** | **16000** —— 分支 checkpoint 里一直没人读到的那个输入 (≤ 108,000 才通过); 现在有了 |
| 成本自检问题 | `[]`; `check_startup` passes |
| 一轮答题的候选 | `('haiku-5-5', 'anthropic/claude-haiku-5-5', 16000, 0.07)`、`('default-fallback', 'anthropic/claude-haiku-5-5', 16000, 0.07)` |
| **单轮上限 / 免费池的十分之一** | **0.07 美元 / 0.30 美元** |
| 在线价格表 (公开容器现在有网络) | 取得到: 来源 `remote`, 7194 条, 有 `claude-haiku-5-5`; `import litellm` 4.2 秒。启动没有因为取在线价格表而报错或卡住 (两次启动都在 11 秒内 `healthy`) |

## 前后对比
同一个快照脚本 (`p3_stageC_snapshot.sh`) 在起点、只构建前后、部署前后、第三段结束各取一份, 两两机械 diff (去掉带时间和余量的一行)。

| 侧 | 项 | 起点 (13:21Z) | 结束 (16:23Z) |
|---|---|---|---|
| 私有 | 镜像 | `613f048…` | **`66cb55d…`** |
| 私有 | 容器 | api Id `a9937c62…` 启动 `03:23:47.097798686Z`; ui `e5d92671…` 启动 `03:23:57.678917638Z` | api `0e129647…` 启动 **`16:17:47.908311993Z`**; ui `85085ec2…` 启动 **`16:17:58.49493504Z`** (重建一次, 预期内); 重启 0 次 |
| 私有 | health | `healthy` / 200 | `healthy` / 200 |
| 私有 | 数据 | stamp `477bac3ce565…` / 4333; `meta.yaml` `b484d49e…`; chroma inode 53422、130 个文件; `*_prev_*`、`*_failed_*`; `study` 1557 个文件 | **没有任何一行变化** |
| 公开 | 容器 | Id `2a33f280…`, `created` / 从未启动, 镜像 `099c2c9…` | Id **`50ba94ed…`**, **`running` / `healthy`**, 镜像 **`66cb55d…`**, 启动于 `16:22:03.299279989Z` (5b 的重启), 重启计数 0 |
| 公开 | 线上数据 | stamp `f863e45445a6…` / 4329 (inode 50497) | stamp **`477bac3ce565…` / 4333** (inode 56800 = 原来的候选) |
| 公开 | 数据根 | `chroma chroma_cand_… meta meta_cand_… quota.sqlite` | `chroma chroma_prev_f863e45445a6_20261128T161813Z meta meta_prev_… quota.sqlite` + 运行中的 `quota.sqlite-shm` / `-wal` |
| 公开 | 网络与隔离 | 网络 Id `eff48d9c…` `10.201.8.0/24`, 0 个容器; 隔离表 5 条 `drop`; 定时器与单元 `active` / `enabled` | 同一个网络, **1 个容器**; 隔离表、定时器、单元不变 |
| 公开 | env 文件 | `600 root:root` (没有读内容) | `600 root:root`, 少了旧的可信代理那一行 (16 → 15 行) |
| 机器 | 容器 / 镜像 | 23 个容器, 运行中 22; `sdtm-rag` 镜像 4 个 | 23 个容器, **运行中 23**; `sdtm-rag` 镜像 5 个; 没有 job 容器 / 网络残留; 可用内存 4790 MB |
| Gitea | 变量 / 运行 | `true`; 最新 219 | `true` (没有动); 最新 221 (220 只构建、221 部署, 都 success) |

公开容器启动之后线上 `chroma.sqlite3` 的修改时间和内容摘要变了、大小不变 (chromadb 打开索引时自己改写, 私有站和本机都是这个现象); 所以「线上 = 原来的候选」是用**启动之前**那一份快照按内容摘要对上的, 启动之后只能按 inode 对。

这次在虚拟机上起过、已经不在的东西: run 220 / 221 的 job 容器; 编排起的一次性容器和临时验收容器及其数据副本; 测试端口的两个临时容器 (`sdtm-rag-tpnew` / `tpold`) 和两份 chroma 副本;
我自己起的一次性容器 (都是 `--rm`): 镜像下限 1 个、镜像内指纹与版本 1 个 (`--network none`)、离线自检对照 1 个 (`--network none`)、隔离复核 1 个 (公开网络)。`.env.before-cleanup` 建了又删了。

## 现在的状态
- **公开站**: 容器 `sdtm-rag-public-api` **运行中** (`healthy`), 镜像 `66cb55d288ccae318dee79c2310aa698f51a7f1a`, 线上 stamp `477bac3ce565…` / 4333 条 (KB `kb-2026.11.28`); 旧数据保留在
  `chroma_prev_f863e45445a6_20261128T161813Z` / `meta_prev_f863e45445a6_20261128T161813Z`。**没有对外入口**: 没有发布端口, 没有连接器, 没有 token, 没有隧道。重启策略 `unless-stopped` ——
  **从现在起虚拟机或 docker 守护进程重启后它会自己起来** (此前「从未启动」时不会)。
- **私有站**: 镜像 `66cb55d…`, `healthy`, 数据不变。
- **变量 `SDTM_RAG_PUBLIC_DEPLOY` = `true`** (开着)。之后每一次带部署的运行都会走「运行中的后续部署」那条路 (阶段 G: 临时验收 → key 探测 → `up -d api` 换新镜像 → 复验), 那条路还没有在真机上走过。
- 演练方案做到第 5 步 (含 5a、5b)。第 6 步起 (连接器、访问策略与路由、隧道验收、放开) 都没有做, 每一步都要主人另行同意。

## 回滚办法
- **立即下线公开站**: 在部署机上 `docker stop sdtm-rag-public-api`。现在没有对外入口, 停不停对外都不可达; 停掉之后它在虚拟机重启时也不会自己起来 (`unless-stopped`)。恢复: `docker start sdtm-rag-public-api`。
- **私有站回到 `613f048`**: **先关公开部署开关**, 再手动运行 `sdtm-rag` 工作流 (`tag=613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7`, deploy=true)。KB 指纹相同 (`477bac3ce565`), 预检会判 same, 不换数据。
  为什么要先关: 同一个 tag 也作用于公开站; `613f048` 过得了镜像下限, 但它的启动自检在没有网络的临时容器里给 Haiku 5.5 定不了价 (run 219 就是这样失败的), 公开腿会在临时验收变红 —— 公开站不会被动 (仍是 `66cb55d` 在运行), 私有站也会照常回滚成功, 但这次运行会显示失败, 而且两个站从此不是同一个镜像。
  关变量: `DELETE …/actions/variables/SDTM_RAG_PUBLIC_DEPLOY` (或 `PUT` 正文 `{"value":"false"}`), 再 `GET` 读回; 关掉之后 kb-sync 的 `public` 腿也会被跳过。要主人或协调方定。
- **公开站的数据退回旧版** (`f863e454…`): 旧数据配的是旧 KB, 而现在的镜像 `66cb55d` 内置的是新 KB —— **数据和镜像要一起退**, 不能只退数据 (新镜像 + 旧数据启动时 KB 与索引对不上)。做法 (`p3_public_leg_impl.md` §5 阶段 D 一行):
  先 `docker stop sdtm-rag-public-api`; 在部署机上用 `kbsync.py --via <镜像> predeploy-check / swap --target-fp f863e45445a6… … / finish` 把 `chroma_prev_f863e45445a6_20261128T161813Z` / `meta_prev_…` 换回来 (现在的线上会变成新的 `*_prev_477bac3ce565_<ts>`);
  再 `IMAGE_TAG=099c2c930ec869e254b2e9052c3d4a6a85d6d539 docker compose -f compose.public.yml up --no-start api` (compose 文件经标准输入传入)。
  ⚠ 旧镜像 `099c2c9` 没有隧道那一步的加固 (过不了镜像下限), 退回之后**公开站必须保持没有入口**, 不能接隧道; 也不能靠给 `sdtm-rag` 填旧 tag 来只回滚公开站 (同一个 tag 也作用于私有站, 而且旧镜像过不了镜像下限)。
  旧数据副本按「保留最新 2 份」清理: 之后再换两次数据, 这一份就会被 `prune` 删掉。
- **5b 删掉的那一行**: 不需要恢复 —— 它本来就不起作用 (部署配置里写死的 `10.201.8.2` 优先), 删之后的复核与删之前相同。备份已按方案删掉; 要找回原文只能问主人 (或看协调方留的 `.env.bak-20261127`, 我没有读过它, 不知道里面是哪一版)。
- **停用公开腿和公开部署**: 关变量 (同上)。
- **本仓回退**: 对 `45fc1c6..66cb55d` 里的四个 `server/` 提交做 `git revert` (带 `[skip ci]`), 再走只构建 → 测试端口 → 部署; 守卫用例的修正 (`66cb55d`) 与此无关, 不用退。

## 发现 (只汇报, 没有改)
1. **又一种「合并后才红」: 只在有本机 `.env` 的检出里红** (上文)。分支的验证只在没有 `.env` 的检出里做过。⇒ 涉及环境变量的测试, 合并前要在带本机 `.env` 的检出里也跑一遍 (已记入 `todo_later`)。
2. **litellm 在导入时会读一个 `.env`** (默认的 `LITELLM_MODE` 下, 从它的安装位置往上找): 拿工作区的 venv 去跑别处的副本, 工作区的 `.env` 会被带进去。这次它让审查者的「副本里没有 `.env`」条件不成立, 并让主仓 `.env` 的几个取值显示在了审查者的工具输出里 (上文)。
   ⇒ 在副本里做实验要用副本自带的 venv, 或设 `LITELLM_MODE=PRODUCTION`。这也意味着容器里 litellm 同样可能读到 `/app/.env` —— 与 `server/config.py` 自己读的是同一个文件, 没有新增的暴露面, 只记一笔。
3. **隔离核对仍占公开腿的小一半时间** (61 秒里约 23 秒: 7 个内网目标各等满 4 秒超时, 串行)。不是问题。
4. **公开容器从这次起会在虚拟机 / docker 重启后自己起来**, 而「规则先于容器装入」的开机顺序仍然只有静态阅读 (第一次部署的 checkpoint), 没有真的重启验证过。重启之后要立刻重跑隔离探测 (演练方案第 3 步的 3a + 3d), 并确认巡检定时器开着。
5. **公开 env 文件所在目录里协调方留的旧备份 `.env.bak-20261127` 还在** (没有读、没有动)。协调方此前说等公开站的 Anthropic key 验证通过后处理 —— key 的有效性这次已经验证通过。
6. 私有站「对比」里的 `openai/gpt-4o` 和扩写 / 判分用的 `deepseek/deepseek-chat` 不在固定表里, 价格靠 litellm 的在线表 (新旧相同); 私有容器哪天在取不到在线表的时候启动, 这两个的成本显示会变 (包内表里有没有它们没有查)。与这次改动无关, 改之前就这样。

## 仍未验证的事项
1. **公开站一次真答题都还没有发过** (新镜像 + 新数据): Anthropic key 只验了有效性, **额度 / 月上限够不够**要到第一次真答题才知道; 公开站的 OpenAI key 在运行中的正式容器里也还没有被检索请求用过 (kb-sync 公开腿入库时用过)。发真答题不在这次同意的范围里。
2. **Haiku 5.5 在响应里回报的模型名**: 这次只核实了 Sonnet 5.5 回报的是裸名。Haiku 5.5 回报的名字如果是固定表不认识的写法, 那次调用会按回退费率记 (多记, 不会少记)。同样要等第一次真答题。
3. **`deploy_public` 对「运行中的公开容器」的路径** (阶段 G: `up -d api` 换镜像 → 复验): 没有走过。变量开着, 下一次带部署的运行就会第一次走它。
4. **其余失败路径**: key 无效、换入被拒、换入后重建失败、退回失败、job 被取消时的兜底 —— 真机上仍然只走过「临时验收不过」这一条 (run 219)。
5. **重启**: 规则先于容器装入的开机顺序; 公开容器在 `unless-stopped` 下重启后自己起来时的隔离状态; (「从未启动的容器重启后是否仍不启动」这一条随着容器已经启动而不再适用。)
6. **隧道这一层的一切** (演练方案第 6 步起): 连接器、访客 IP 的采信、伪造头、Cloudflare 一侧的限速与访问策略、公开容器被重建后连接器是否无需重启就能连上。
7. 全局限流只验了「从容器内按 `127.0.0.1` 计的桶」; 经连接器按访客 IP 计的那一路要到第 8 步。cookie 的 `Secure` 只看了属性在不在, 没有经 HTTPS 实际走一遍。
8. Gitea / act_runner 留下的: `always()` 的另一半、`concurrency` 是否真的让 kb-sync 与部署排队、取消时兜底步骤是否执行、`$GITHUB_STEP_SUMMARY` 是否展示。
9. 私有档的 cookie 属性在真机上仍然无 cookie 可比; 对比徽章 (`/api/ask_compare`) 没有真的调用 (会发多家模型的请求), 成本显示的对比是直接调同一个估算函数做的。
10. 守卫用例修正留下的窄盲区 (上文「处置与没有改的」)。
11. **这份部署记录没有独立审查**: 派单要求不起子代理 (守卫修正的审查是协调方另外要求的例外), 第二、三段的记录是执行者自己写的 (规则 D 的缺口; 需要的话由协调方另派)。快照 diff、日志、轮询样本都可以机械复核, 命令在下面。

## 小结 (规则 C)
- **保留下来的做法**: 推送前检查放在合并之前 (快进合并改不了历史); 派发前把「现在就能查出来的失败」查掉, 这次补上了上一次漏的那一条 (新镜像在没有网络的容器里跑一遍启动自检);
  只构建与部署之间不动 main, 证据脚本留在工作区; 派发前起只读轮询 (编排的输出是步骤结束时一次性刷出来的, 「启动到 healthy 多久」只有轮询能回答);
  换入用 inode + 内容摘要对上, 而不是只看目录名; 5b 逐步核对 (先确认 → 行数与权限 → 重启 → 复核 → 才删备份), 命令一律写完整文件名; 看容器日志只做计数;
  对比新旧镜像的成本时先确认两边的价格表都是在线表、加下限断言, 并且不用会跨分档线的问法。
- **必须补上的缺口**: (1) 分支上的测试只在没有 `.env` 的检出里跑过, 合并后在主仓红了一条 —— 「环境不同才红」这一类第四次出现 (快照文件两用、CI 浅克隆、Linux runner 的僵尸进程、这次的本机 `.env`)。
  (2) 我给审查者的实验说明没有想到 venv 的位置会把 `.env` 带进去, 让审查者看到了不该出现在它输出里的取值; 「副本」不等于「隔离」, 解释器从哪来也是条件的一部分。
  (3) 我自己的变异脚本的判定一侧错了三次 (都被表上的 BAD 暴露出来, 没有被当成通过): 写判定的时候要拿一次真实的失败输出来对, 不要凭印象写匹配。
  (4) 第一轮审查建议的加强 (「每条用例都被看到」) 我照做了, 没有先问「哪些合理用法会因此变红」; 第二轮才由审查者指出 `local_data` 会本机绿、CI 红。采纳一条建议时, 建议本身也要先验算。
- **关键决策复盘**: (1) 主仓 1 failed 时停下来问, 没有以「CI 条件下是绿的」自行放行 —— 判据写的是主仓 0 failed。(2) 第二轮审查给的修法用 pytest 的私有接口, 我改用公开接口按标记是否存在排除, 把因此放过的情形写明并送第三轮确认, 没有悄悄换写法。
  (3) 审查通过之后测试文件没有再动 (第三轮的两条可选建议里, 改变异脚本的那条做了, 改测试文件注释的那条没有做), 提交的就是审过的那一版。(4) 第三段里额外做了两件任务清单之外的只读核对 (从局域网侧确认连不上公开容器; 在容器里读出单轮上限和回退档输出上限的实际值), 都不改任何东西。

## 收尾提交的推送前检查
范围 = 收尾的那一个文档提交 (870 行新增 + 1 条提交信息; 13 个文件, 不含仓库根的 `README.md`, 不命中部署路径过滤): home 路径 0、本机账号 0、邮箱 0、密钥形状 0、JWT 形状 0、暂存目录路径 0;
红线扫描 (pre-commit 闸 + 提交信息另扫) CLEAN。只计数、不拦截: 内网 / 公开网段地址 31 行, `bojiang` 8 行, 不含用户名的机器路径 10 行。
- 「口令赋值形状」命中 **1 行**: 新入库的测试端口脚本 `p3_stageDE2_testport.sh` 里响应头探测清单的那条 `POST /login` —— 请求体里是一个故意写错的占位口令, 用来探私有站登录路径的响应头, 不是任何真实口令;
  同一行在已经公开的先例脚本 `p3_tunnel_leg_merge_testport_613f048.sh` 里就有 (这次的脚本从它起步, 原样沿用, 也按这个内容实际跑过)。
  按任务要求没有自己放行, 报给了协调方。**协调方 (bot) 的判断: 按现状 push** —— 那一行不是真实口令, 而且保持脚本与实际跑过的那一版逐字一致更重要 (协调方的决定, 不是主人逐条裁定)。
- 第一遍扫时「密钥形状」有 1 行, 是本文件「推送前检查」表里列举各口径名称的那一行自己; 改成了引用先例的写法, 重扫为 0。

## 结束状态
- main = origin/main (Gitea 与 GitHub 相同); 线上镜像对应提交 `66cb55d288ccae318dee79c2310aa698f51a7f1a`; 其后只有收尾的文档提交 (带 `[skip ci]`, 提交号见向协调方的最终汇报)。
- 变量 `SDTM_RAG_PUBLIC_DEPLOY` = `true`。公开容器运行中、没有入口。
- 分支 `hakupao/public-price-pin` (`c3c13ee`) 和它的子工作区没有动, 留给协调方处理。

## 复跑命令
```sh
R=<本仓根>; cd $R; OUT=<本机临时目录>; C=.work/10_split_and_public/evidence/checkpoints
VM()  { ssh <mini 主机> "export PATH=/opt/homebrew/bin:\$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- $*"; }
VMS() { ssh <mini 主机> 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- bash -s'; }
TAG=66cb55d288ccae318dee79c2310aa698f51a7f1a; IMG=192.168.100.58/bojiang/sdtm-rag:$TAG
API=https://git.bojiang.org/api/v1/repos/bojiang/sdtm-rag      # 账号与口令取自 git credential, 经标准输入交给 curl (curl -K -), 不进命令行、不写进任何文件
# 推送前检查 (合并之前): 逐提交的新增行与提交信息; 红线扫描用主仓的 catalog
git log -p --format='COMMIT %H' 45fc1c6..c3c13ee | grep -E '^\+' | grep -vE '^\+\+\+ ' > $OUT/added.txt; git log --format='%B' 45fc1c6..c3c13ee > $OUT/msgs.txt
grep -cE '<各口径的正则, 同 p3_tunnel_leg_merge_deploy.md「推送前检查」>' $OUT/added.txt $OUT/msgs.txt
T=$OUT/redline; mkdir -p $T; git archive c3c13ee $(git diff --name-only 45fc1c6..c3c13ee) | tar -x -C $T
(cd $T && $R/.venv/bin/python $R/scripts/oidscan_evidence.py $(git -C $R diff --name-only 45fc1c6..c3c13ee) --catalog $R/data/study/st01/catalog.json)
# 合并 + 本机全量 (前后各记一次 data/)
git merge --ff-only hakupao/public-price-pin
find data -type f -print0 | sort -z | xargs -0 stat -f '%N|%z|%m' > $OUT/data_before.txt
.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs -p no:cacheprovider
# CI 同款: 深度 1 的克隆 + 独立 venv (没有 data/、没有 .env); 「一行 .env」条件 = 在这个克隆里 printf 'SDTM_RAG_AUTH_ENABLED=false\n' > .env
git clone -q --depth 1 --no-tags --branch main file://$R $OUT/ci_sim && cd $OUT/ci_sim && git submodule update -q --init --depth 1 && uv sync --extra dev --frozen
env -u VIRTUAL_ENV .venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs -p no:cacheprovider
env -u VIRTUAL_ENV .venv/bin/python -m pytest tests/test_p3_4_public_https.py tests/test_p2_l3_instance.py tests/test_p2_9_public_e2e.py -q -o addopts="" -p no:cacheprovider   # 倒序命令: 140 passed
# 守卫用例的变异 (副本自带的 venv)
GUARD_MUT_ROOT=$OUT/ci_sim env -u VIRTUAL_ENV $OUT/ci_sim/.venv/bin/python $R/$C/p3_stageDE2_guard_mutations.py                      # 17/17
GUARD_MUT_ROOT=$OUT/ci_sim GUARD_MUT_DOTENV=1 env -u VIRTUAL_ENV $OUT/ci_sim/.venv/bin/python $R/$C/p3_stageDE2_guard_mutations.py   # 18/18
# 快照 / 目录指纹 / 轮询 (只读; 各阶段前后取, 两两 diff)
VMS < $C/p3_stageC_snapshot.sh > $OUT/snap_N.txt; VMS < $C/p3_stageDE_pubdirs.sh > $OUT/pubdirs_N.txt
diff <(grep -v '^\[T\]' $OUT/snap_A.txt) <(grep -v '^\[T\]' $OUT/snap_B.txt)
VMS < $C/p3_stageDE_poll.sh > $OUT/poll.txt &
# 测试端口验证
{ echo "NEW_TAG=$TAG"; cat $C/p3_stageDE2_testport.sh; } | VMS
# 2c 预检
for f in .gitea/workflows/sdtm-rag.yml deploy/kbsync/kbsync.py deploy/container/compose.public.yml deploy/container/compose.yml deploy/public-net/image_floor_check.py deploy/public-net/isolation_probe.py; do
  curl -s -K - "$API/contents/$f?ref=main"; git rev-parse HEAD:$f; done
.venv/bin/python -m pytest tests/test_workflow_conditions.py -q -o addopts="" -p no:cacheprovider      # 165 passed
VM "sudo docker image inspect $IMG --format '{{.Id}} {{.RepoDigests}} {{.Config.WorkingDir}}'"
out=$(VM "sudo docker run --rm -i --entrypoint python $IMG -" < deploy/public-net/image_floor_check.py); echo "rc=$? [$out]"   # rc=0 [image-floor: ok]
# 离线自检对照 (新镜像原样; 不挂数据、不带 env 文件)
.venv/bin/python $C/public_price_pin_offline_probe.py emit | VM "sudo docker run --rm -i --name ppp-offline-probe --network none --cap-drop ALL --security-opt no-new-privileges --memory 1g --entrypoint python $IMG -"
# —— 下面三条会改状态, 需要主人同意; 这次各只执行了一次 ——
git push origin main
curl -s -K - -H 'Content-Type: application/json' -X POST "$API/actions/workflows/sdtm-rag.yml/dispatches" -d '{"ref":"main","inputs":{"tag":"","deploy":"false","force_data_mismatch":"false"}}'          # 只构建 → run 220
curl -s -K - -H 'Content-Type: application/json' -X POST "$API/actions/workflows/sdtm-rag.yml/dispatches" -d "{\"ref\":\"main\",\"inputs\":{\"tag\":\"$TAG\",\"deploy\":\"true\",\"force_data_mismatch\":\"false\"}}"   # 部署 → run 221
# 运行结果与日志 (220: job 467 / 468; 221: job 469 = deploy, 470 = deploy_public)
curl -s -K - "$API/actions/runs/221"; curl -s -K - "$API/actions/runs/221/jobs"; curl -s -K - "$API/actions/jobs/470/logs" > $OUT/job_470.log
grep -nE 'git log -1|部署标签|decision|Container sdtm-rag|健康检查通过|\[deploy-public\]|swapped' $OUT/job_469.log $OUT/job_470.log
# 闸
VMS < $C/p3_stageDE2_gate.sh
# 第三段 (docker start / 5b 会改状态; 其余只读)。第 2–5 项的命令是 docs/plans/P3_4_tunnel_drill.md 第 5 步、5a、5b 的原样命令
VM "docker start sdtm-rag-public-api"
VM "python3 - probe $LAN" < deploy/public-net/isolation_probe.py > $OUT/control.json           # LAN / NET 见演练方案第 3 步
VM "docker run --rm -i --network sdtm-rag-public --entrypoint python $IMG - probe $LAN $NET" < deploy/public-net/isolation_probe.py > $OUT/after.json
python3 deploy/public-net/isolation_probe.py judge --isolated $OUT/after.json --control $OUT/control.json --isolated-net 10.201.8.0/24      # 结论: PASS
VMS < $C/p3_stageDE2_stage3_readonly.sh
```
