# 独立安全审查任务书: 隧道 + 公开腿两条分支合并进 main 的结果 (2026-11-28)

你是独立审查者 (规则 D: 写的人和审的人不是同一个)。只读, 不改任何文件, 不 push, 不碰部署机, 不触发 workflow。
工作目录 = 本仓根 (分支 main, 未 push)。下面的路径都是仓内相对路径。请自己读代码和 diff 得出结论; 文档里「已改 / 已验证」之类的处置说明**不要采信**, 只当线索。

## 背景 (事实, 不是结论)

- 基点 `9a8ad43` (= origin/main, 也是线上私有站镜像 `f798709` 之后的文档提交)。
- 本地 main 上多了三个提交, 都还没有 push:
  1. `319654c` = 分支 `hakupao/public-tunnel` (HEAD `9d21808`) 的 squash。
  2. `781521d` = 分支 `hakupao/public-kb-leg` (HEAD `1265aa6`) 的 squash。
  3. `e50a9f8` = 合并后的整合提交 (快照文件、4 条测试的修正、进度与裁定登记)。
- push 之后会对**私有站**做一次重新部署, 预期私有站行为不变; 公开站这一步不动 (仓库变量 `SDTM_RAG_PUBLIC_DEPLOY` 未开, 公开容器停止)。
- 两条分支各自做过多轮独立审查 (记录: `.work/10_split_and_public/evidence/checkpoints/p3_step3.4_tunnel.md`「审查」、
  `.work/10_split_and_public/evidence/checkpoints/p3_public_leg_impl_review.md`)。这次只审下面三块。

## 范围 A: 公开腿分支上还没有被独立审查过的部分

`p3_public_leg_impl_review.md` 末尾写明两类改动没有经过独立审查:

1. 第四轮审查意见的修正: 红线检查挪到「缺候选就跳过」之前 (M1); 读出结论后副本删不掉不丢结论 (L1); 失败信息里集合名的显示规则 (L2);
   失败信息补恢复路径; README 的清理命令 (L3)。
2. 第四轮之后为对齐隧道那条线做的三处小改: 临时验收失败原因带出启动报错; 钉住验收请求数与限流余量的测试; fixture 重新渲染。

怎么看: `git diff a6f987d..1265aa6 -- deploy/kbsync/kbsync.py .gitea/workflows tests deploy/README.md` (分支 `hakupao/public-kb-leg` 上的提交;
其中私有 deploy job 的加固和红线停站的**初版**第四轮已审, 这次看的是它之后的修正, 但修正与初版在同一个提交 `8477734` 里, 请按上面的条目对照代码找)。
重点文件: `deploy/kbsync/kbsync.py` 里公开部署编排 (红线检查、`public_halt`、临时验收、失败信息的拼装)、`tests/test_kbsync_deploy_public.py`。

请判断:
- 红线检查现在的位置和各分支 (journal 有残留 / 判不出 / 读不出集合 / 副本删不掉) 有没有「该停没停」或「不该动却动了正式容器 / 数据」的路径; 有没有任何启动动作。
- 集合名的显示规则会不会把不符合约定的名字 (可能带真实研究标识) 原样打进日志; 指纹 + 长度的写法有没有泄漏面。
- 启动报错「原样带进失败原因」会不会把 env 文件里的值 (key、口令) 带进日志或摘要。

## 范围 B: 这次合并的结果

1. **冲突处理**: 两条分支只在 `deploy/README.md` 上冲突, 按「两边的新增都保留」处理。请核对: 相对基点是否只有新增、两边各自的新增是否都完整保留、
   两段放的位置是否合理、合并后的文字有没有互相矛盾或引用了不存在的小节 / 文件。
   `git diff 9a8ad43 e50a9f8 -- deploy/README.md`; 两边原样: `git diff 9a8ad43 hakupao/public-tunnel -- deploy/README.md`、`git diff 9a8ad43 hakupao/public-kb-leg -- deploy/README.md`。
2. **squash 是否忠实**: `git diff 319654c hakupao/public-tunnel` 应为空; `git diff 781521d hakupao/public-kb-leg` 应只有 README (上一条) 和
   `.work/10_split_and_public/evidence/subagent_prompts/review_public_leg_round3.md` 的两行 (本机绝对路径换成占位写法)。有别的差异请指出。
3. **快照文件**: `tests/fixtures/kbsync/compose_config_public.json` 被换成与 `compose_config_public_tunnel.json` 相同的内容 (据称是合并后
   `deploy/container/compose.public.yml` 在部署机上 `docker compose config --format json` 的输出)。请对照 compose 文件本身核对这份 JSON 是否与它一致
   (服务、挂载、环境变量、网络 / 子网 / 网桥名、容器名), 有没有夹带别的东西。
4. **4 条测试的修正** (`git show e50a9f8 -- tests/`), 这是协调方专门要求确认的:
   - `tests/test_kbsync_deploy_public.py`: `test_compose_without_a_pinned_subnet_stops_the_deploy`、`test_public_network_is_read_from_the_compose_model`
     原来把 `compose_config_public.json` 当作「没有写定子网的 compose」; 现在改用 `_unpinned()` (从快照里去掉 `ipam` 段)。
   - `tests/test_workflow_conditions.py`: `test_private_deploy_job_changed_only_where_intended`、`test_kb_sync_private_leg_changed_only_where_intended`
     原来用 `git show 9a8ad43:…` 取基点; 现在读 `tests/fixtures/workflows/base_9a8ad43_{sdtm-rag,kb-sync}.yml`, 取得到基点提交时顺带断言 fixture 与 `git show` 逐字相同。
   请确认两件事, 并说明你是怎么确认的 (最好自己动手做变异, 在仓库的**副本**里做, 不要改这个工作目录):
   - **检出能力有没有被削弱**: 改之前能抓住的缺陷, 改之后是否仍然抓得住。写的人做过两个变异 (在副本里): ① fixture 改一个字节 → 有完整历史时
     `AssertionError: fixture 与基点提交里的 workflow 不一致`; ② 私有 deploy job 的「健康检查」步骤多改一行 → `changed == [...]` 的断言红。
     请判断这两个变异够不够, 还缺哪个方向 (例如: 在**取不到基点**的环境里 fixture 被改坏会怎样; `_unpinned()` 会不会在某种输入下什么都没去掉却照样通过;
     「没有写定子网」这个情形用合成的模型代替真实的旧输出, 有没有丢掉分辨力)。
   - **CI 的浅克隆下这 4 条是真的在跑, 而不是被跳过**: CI 的 checkout 是深度 1 (`.gitea/workflows/sdtm-rag.yml` 的 `actions/checkout@v4` 没有设 `fetch-depth`)。
     请看测试代码里有没有任何在取不到基点时 skip / 提前 return / 吞掉异常的路径。
5. **两条线的接缝**: 请逐项核对两边的写法对得上:
   - `.gitea/workflows/sdtm-rag.yml` 的 `deploy_public` job 引用的脚本路径 (`deploy/public-net/isolation_probe.py`、`deploy/public-net/image_floor_check.py`)
     是否存在, checkout 之后能否取到; `kbsync.py` 调用 `isolation_probe.py` 的命令行 (probe / judge 的参数、输出格式、退出码) 是否与脚本本身一致。
   - 镜像下限: workflow 里的判法 (退出码 0 并且输出恰好是 `image-floor: ok`) 与 `image_floor_check.py` 的实际输出、与 `server/auth.py` 的 `PUBLIC_EDGE_LEVEL` 是否对得上。
   - 网段常量: `deploy/container/compose.public.yml`、`deploy/container/compose.tunnel.yml`、`deploy/public-net/isolation.nft`、workflow 的 `ISOLATION_*`、
     `kbsync.py`、测试里的 `SUBNET` / 可信代理地址, 是否是同一组值。
   - `ISOLATION_LAN` / `ISOLATION_EGRESS` 的目标清单与 `docs/plans/P3_4_tunnel_drill.md` 第 3 步是否一致。
6. **共享文件** (`git show e50a9f8 -- .work/10_split_and_public/_progress.json .work/10_split_and_public/PLAN.md docs/PROGRESS.md CLAUDE.md`):
   有没有与代码或 checkpoint 矛盾的陈述; 有没有把「协调方受托代裁」写成「主人裁定」或反过来; 有没有不该公开的内容 (这个仓库是公开的)。

## 范围 C: 私有站行为不变 (这次 push 后要重新部署私有站)

`git diff 9a8ad43 e50a9f8 -- server/ .gitea/workflows/sdtm-rag.yml .gitea/workflows/kb-sync.yml deploy/container/compose.yml deploy/kbsync/kbsync.py`

- `server/auth.py`: 私有档 (`SDTM_RAG_INSTANCE_TIER` 不是 public) 下, 响应头、cookie 属性、限流中间件、启动检查, 有没有任何一处与改之前不同。
  特别看: HSTS 是否只在公开档发; cookie 的 `Secure` 在私有档是否保持原样; 「大小写变体」启动检查是否只在公开档执行; `_resolve_ip` 的改动在私有档会不会改变取到的 IP。
- 私有 `deploy` job 和 kb-sync 的 `private` job: 在「tag 留空」和「合法的 40 位提交号」两种输入下, 与基点相比是否等价; 变量未开时 `deploy_public` 和 kb-sync 的 `public` job 是否一定被跳过;
  `public` job 的存在 (`needs: private`、`if: always() && …`) 会不会改变 `private` job 的行为或整次运行的结论。
- `kbsync.py` 里私有路径会走到的函数 (`detect`、`candidate`、`predeploy-check`、`deploy-swap`、`swap`、`finish`、`restore`、`prune`): 新增的参数校验对 workflow 实际传入的值会不会误拒。

## 推送前的内容检查 (这个仓库是公开的)

`git log -p 9a8ad43..e50a9f8` 的新增行和三个提交的提交信息里, 有没有: 本机用户名或带用户名的 home 路径、邮箱、真实姓名、口令 / 密钥 / token 形状的字符串、
隧道 token、真实研究的标识。不含用户名的机器路径、本仓早已公开的内网地址 (镜像仓库地址、Gitea 域名) 不算。发现请给出文件和行号, 不要把值原样抄进报告。

## 输出

1. 总结论: PASS / PASS-with-fixes / FAIL (FAIL = 存在不该带着它 push 或部署私有站的问题)。
2. 按 CRITICAL / HIGH / MEDIUM / LOW 分级的发现, 每条给出文件、函数或步骤名、依据 (你读到的代码或你运行的命令和输出)、建议。
3. 对范围 B 第 4 条那两件事的明确回答 (检出能力 / CI 下真的在跑), 以及你自己做的变异和结果。
4. 你没有看、或看了没法下结论的部分。

可以运行的命令: `git` 只读命令; `.venv/bin/python -m pytest <文件> -q -o addopts=""` (只跑 `tests/test_kbsync*.py`、`tests/test_workflow_conditions.py`、
`tests/test_deploy_public_*.py`、`tests/test_p3_4_public_https.py`、`tests/test_p2_9_fixes.py`; 不要跑全量, 全量会打开本机索引)。
变异请在临时目录的副本里做 (`git worktree` 不要用; 用 `git archive e50a9f8 | tar -x -C <临时目录>` 或 `git clone`), 用完删除。
