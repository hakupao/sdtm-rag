# 独立安全审查任务书: 「打开公开部署开关之前」的几处修正 (2026-11-28)

审查者: `oh-my-claudecode:security-reviewer` (与实现者不同的 subagent_type, 规则 D)。只读审查, 不改仓库里的任何文件。

## 你在哪
sdtm-rag 仓的一个子工作区 (当前目录), 分支 `hakupao/pre-switch-fixes`。要审的是 `560213e..HEAD` 这两个提交 (`git log --oneline 560213e..HEAD`, `git diff 560213e HEAD`)。
背景: 仓库有一个公开实例 (还没有上线), 它的部署由 `deploy/kbsync/kbsync.py deploy-public` 编排, 由仓库变量 `SDTM_RAG_PUBLIC_DEPLOY` 控制 (现在是关的)。这批改动是「打开这个开关之前必须处理」的后续项, 出处是上一轮合并审查留下的 LOW-1 / LOW-2 / LOW-3 / LOW-6 和一次 CI 失败 (run 214):
- `.work/10_split_and_public/evidence/checkpoints/p3_tunnel_leg_merge_deploy.md` (「第 2 步」的审查意见表、「第 4 步 attempt 1」)
- `.work/10_split_and_public/evidence/failures/p3_tunnel_leg_merge_build_attempt_1.md`
项目规则: `CLAUDE.md`、`docs/RULES.md` (规则 5 = 红线类改动要做变异验证; 变异验证自身也会静默失效)。

## 改了什么 (实现者的说法, 请当成待核实的陈述, 不要当成结论)
`deploy/kbsync/kbsync.py`:
1. `SAFE_COLLECTION_RE` 收窄: 红线停站的失败信息里, 原样写出的集合名只剩 `sdtm_kb_v<1–3 位数字>` / `study_st<2–3 位数字>` / 后者加 `_docs`; 其余只写 sha256 前 10 位和长度 (`_show_collection`)。
2. `accept_check`: 容器没有进入 healthy 时, `docker logs` 的末尾 40 行会被打印进 job 日志, 最后一条报错写进失败原因和步骤摘要。带出之前过两道: `scrub` (key 片段) 和新增的 `_hide_study_names` (以 study 开头的词按上面的白名单处理)。
   为什么要隐: 公开档启动自检 (`server/instance.py` 的 `check_chroma` / `check_startup`) 会把 study 集合名写进报错, 名字可能带着真实研究的标识 (本仓红线: 真实研究的 OID / label / 真名不进 git, 也不该进日志)。
3. `_end_process_group` + 新增的 `_only_zombies_left`: 兜底结束 deploy-public 进程组之后, 判断「都没了」时把僵尸排除。原先只靠 `killpg(pgid, 0)`: CI 的 job 容器里 1 号进程是 `/bin/sleep`, 不回收孤儿, 僵尸让信号 0 永远成功, 于是等满约 10 秒并多打一行「可能还没有结束」。
`tests/test_kbsync_deploy_public.py`: 上面各项的测试; `test_abort_first_ends_a_deploy_process_that_is_still_alive` 改成子进程忽略 SIGTERM (原先「兜底只发 SIGTERM、不升级 SIGKILL」的变异不会变红)。
`.gitea/workflows/kb-sync.yml`: 去掉 `schedule` 触发, 只留手动派发 (协调方的设计取舍, 原因在文件头)。`tests/test_workflow_conditions.py`: 钉住「没有 schedule 触发」。
文档: `deploy/README.md`、`CLAUDE.md`、`docs/plans/P3_4_tunnel_drill.md`、两份留档 checkpoint 里的一行。
变异脚本: `.work/10_split_and_public/evidence/checkpoints/pre_switch_fixes_mutations.py`。

## 请重点看 (按重要性)
1. **失败信息 / 日志会不会带出不该带的内容。** 从 `accept_check`、`live_contaminated_stop`、`_summary`、`deploy_public` 的各个出口往回追:
   - 新的白名单还有没有能把真实研究标识原样放出来的写法 (正则本身、`fullmatch`、Unicode、大小写、换行)。
   - `_hide_study_names` 的切词规则 (`STUDY_NAME_RE`) 有没有漏: 什么样的集合名会被切成两段、后半段漏出来; 什么位置的名字不会被匹配到 (前一个字符的限制); 它声明「挡不住」的两种情形是否就是全部。
   - `accept_check` 里是否还有没过这两道就带出去的路径 (例如另一处 `docker exec` 的 stderr、别的函数里带出容器输出的地方)。指出来即可, 是否属于这次的范围由协调方定。
   - 指纹 (sha256 前 10 位 + 长度) 本身泄不泄漏, 是改之前就有的设计, 可以评论但不算这次的缺陷。
2. **进程组收尾有没有把「还活着的进程」误判成「已结束」。** `_only_zombies_left` 返回 True 的每一条路径: `/proc/<pid>/stat` 的解析 (字段位置请对照 proc(5) 自己核一遍: 状态第 3、进程组第 5、线程数第 20 个字段)、进程名里的 `)` / 空格 / 非 UTF-8、多线程进程主线程先退出的情形、pid 命名空间、竞态 (列目录与读文件之间进程退出 / 被回收 / pid 被复用)、`whole` 为假时只看一个进程、`/proc` 读不到时。返回 True 之后 `public_abort` 会少等、少打一行, 然后照常停机并复查三轮 —— 请判断误判的后果有多大。
   另外: 它只在 `send(0)` 成功之后才被调用, 且在发过结束信号之后; 这一点有没有被别的路径绕过。
3. **测试是不是真的在测。** 请自己做变异 (在你自己的临时副本里, 见下), 不要只读实现者的变异表。特别是:
   - 假 `/proc` 的那几条测试 (`_stat` / `_fake_proc`) 是不是循环论证 (测试和实现共用同一个可能错的字段位置假设)。
   - `test_abort_first_ends_a_deploy_process_that_is_still_alive`: 子进程是否一定在收到 SIGTERM 之前就装好了忽略; 「只发 SIGTERM」的变异是否稳定变红; 这条测试在没有 `/proc` 的系统 (本机是 macOS) 和有僵尸的系统上各自验的是什么。
   - `test_no_workflow_has_a_schedule_trigger` 能不能被绕过 (换写法把定时加回来而测试不红)。
4. **kb-sync 去掉定时**: 除了 `on` 和注释, 工作流在手动派发下的行为有没有任何变化; 文档里对 Gitea 行为的陈述是否有依据不足之处 (你核实不了的就写核实不了)。
5. **文档是否与代码一致**: `deploy/README.md` 里镜像下限的判据 (对照 `deploy/public-net/image_floor_check.py` 和 `sdtm-rag.yml` 的预检步骤)、白名单的描述、「前提」那一段; `P3_4_tunnel_drill.md` 的改动是否与 `p3_stageB_network_isolation.md` 的实测一致。
6. **不该出现的内容**: 新增行与两个提交信息里有没有用户名、home 路径、邮箱、真名、口令 / 密钥 / token (完整形状的假密钥也算; 测试里的假值应当是运行时拼接的)。`git log -p 560213e..HEAD` 逐提交看新增行。

## 环境与限制
- 只读: 不改这个工作区里的任何文件, 不 `git stash` / `git checkout` / `git commit`, 不 push, 不触发任何 workflow, 不连部署机 / 虚拟机, 不动任何容器。
- 要跑测试或做变异: 把仓库复制到你自己的临时目录再做 (例如 `git archive HEAD | tar -x -C <临时目录>`), 用本工作区的解释器 `"$PWD/.venv/bin/python"` 从副本根目录运行 (`python -m pytest tests/test_kbsync_deploy_public.py -q -o addopts="" -p no:cacheprovider`)。测试通过文件路径加载 `deploy/kbsync/kbsync.py`: 每次先确认加载的是副本里的那一份 (`python -c "from tests.test_kbsync import ks; print(ks.__file__)"`), 每个变异先确认打上了。
- 本机是 macOS, 没有 `/proc`, 也没有 docker: 真实的僵尸语义你在这里验不了, 如实写「没有验」即可, 不要用别的环境替代后当成验过。
- 报告里不要写带用户名的绝对路径。

## 请这样回报
- 结论: PASS / PASS-with-fixes / FAIL, 以及会不会阻止「合并进 main」。
- 逐条发现: 严重程度 (CRITICAL / HIGH / MEDIUM / LOW)、位置 (文件:行)、你怎么确认的 (命令或变异 + 真实输出)、建议。
- 你做过的变异清单 (变异 → 哪条测试红 / 没有红)。
- 你核实不了的事项。
