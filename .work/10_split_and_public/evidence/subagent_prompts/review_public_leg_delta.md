# 增量安全审查: 公开腿在第一轮审查之后新增的改动

你是独立安全审查者 (只读, 不改任何文件, 不 push, 不连虚拟机, 不读 `.env` 内容)。仓库: 当前工作目录, 分支 `hakupao/public-kb-leg`。全程中文。

## 范围 (只看增量)
`git diff 0cbbc38 -- deploy .gitea tests` (0cbbc38 之后的提交加工作区未提交的改动, 以工作区为准)。
背景与规格: `.work/10_split_and_public/evidence/subagent_prompts/review_public_leg_security.md` (第一轮任务书, 含背景、红线、裁定)。
第一轮的两份审查意见清单见 `.work/10_split_and_public/evidence/checkpoints/p3_public_leg_impl_review.md` 的两张表的「意见」一列 —— 「处置」一列是写作者自己的说法, 请不要采信, 自己对着代码判断。

## 这批改动里新出现的机制 (请逐个攻击)
1. `public_abort` / `_end_process_group`: 用 pid 文件结束还活着的编排进程组, 然后停公开项目并复查。
   会不会误杀别的进程 (pid 复用、pid 文件被篡改、进程组算错)? 结束不掉时的表现? 复查逻辑有没有漏洞?
2. `baseline_image` + kb-sync「选基线镜像」步骤: 人工指定的基线镜像的限制 (镜像仓库 + 40 位 SHA + 必须在本机)、stamp 由谁去读。
   还有没有办法让一个不可信镜像拿到公开数据根或公开 env 文件? `docker image inspect` 的本机检查与后续 `docker run` 之间有没有空子?
3. `deploy_public` 在动正式容器之前重新读状态 (`prev_running`); `swap --expect-source`; 部署前阶段的统一异常处理 (`_deploy_public` 外层的 try)。
   重新读状态之后到真正动手之间还有没有窗口? 外层 try 会不会把「已经动过正式容器之后」的异常也当成「没有动」?
4. `scrub` 的新正则: 有没有会漏的常见 key 写法, 有没有可能把诊断信息误删到看不懂, 有没有灾难性回溯 (ReDoS) 的输入?
5. workflow 里改成 `[[ "$X" =~ … ]]` 的四处格式校验, 以及 `inspect.err` 这个临时文件的用法。
6. `run_fs` / `candidate` 的 `--fp` / `--ts` 校验与 `restore` 对 journal 目录名的校验: 有没有绕过; 会不会让私有腿原本合法的调用失败。
7. `accept_spec` / `paths_problems` / `via` (STAGE_CMDS 的层级限制) 的增量部分。
8. 起停命令现在限定到 `api` 服务 (`compose stop api` / `up -d api` / `up --no-start api`), 失败与兜底仍停整个项目: 有没有因此出现「该停的没停」。

可以跑: `.venv/bin/python -m pytest tests/test_kbsync.py tests/test_kbsync_public.py tests/test_kbsync_deploy_public.py tests/test_workflow_conditions.py tests/test_deploy_public_compose.py -q -o addopts=""`
不要跑 `p3_public_leg_mutations.py` (它会临时改文件)。

## 输出
结论 (PASS / PASS-with-fixes / FAIL) + 分级问题清单 (CRITICAL / HIGH / MEDIUM / LOW; 每条: 文件与函数名、攻击或触发场景、建议改法)。
另外单列一张表: 第一轮安全审查的 M-1、M-2、M-3、L-1、L-3、L-4、L-6、L-7 与代码审查的 M1、M2、M3、L1、L2, 每条写「确认已修 / 没修好 / 引入了新问题」及依据。
没把握的写成疑问。不要输出任何真实研究标识或密钥。
