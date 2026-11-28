# 第三轮 (窄范围) 审查: 公开腿最后一批改动

你是独立审查者 (只读, 不改任何文件, 不 push, 不连虚拟机, 不读 `.env` 内容, 不跑变异脚本, 不跑全量 pytest)。
仓库: 当前工作目录, 分支 `hakupao/public-kb-leg`。全程中文。

## 范围
`git diff e1b5765 -- deploy .gitea tests` (e1b5765 之后的工作区改动, 还没有提交)。只审这部分; 之前的内容已经过两轮审查。
背景与红线: `.work/10_split_and_public/evidence/subagent_prompts/review_public_leg_security.md`。

## 这批改动做了两类事
A. 处理第二轮安全审查的意见 (意见原文见 `.work/10_split_and_public/evidence/checkpoints/p3_public_leg_impl_review.md` 「第二轮」一节的「意见」列;
   「处置」列是写作者自己的说法, 不要采信, 对着代码判断):
   `public_halt` 自身不往外抛、外层异常处理按「已动过」标记分流、`_end_process_group` / `_looks_like_deploy` / `public_abort` (进程组、pid 校验、停机后复查)、
   基线镜像选定后按镜像 ID 使用、`docker inspect --type container`、`paths_problems` 覆盖全部服务、`scrub` 正则补全、换入前再确认容器已停。
B. 协调方的新裁定 (已定, 不要重新设计; 只判断实现对不对):
   1. 临时验收容器不带网络 (`network_mode: none`), 环境变量照抄 compose, 不照抄 `networks` 段;
   2. 答题 key 的有效性探测改到一个独立的一次性容器里, 接在公开网络 `sdtm-rag-public` 上, 排在临时验收通过之后、动正式容器之前;
   3. 动正式容器之前加三道只读预检, 不通过就不动:
      - 公开网络的子网必须是 compose 里写定的那个 (`10.201.8.0/24`), 不是就失败并提示先重建网络;
      - 网络隔离核对: 公开网络里的一次性容器跑另一条线的 `deploy/public-net/isolation_probe.py probe` (脚本不进镜像, 经标准输入送进去),
        默认网桥上的一次性容器用同一批内网目标作对照, 再跑它的 `judge --isolated F --control F --isolated-net CIDR` (退出码 0 才算通过);
      - 镜像下限: 镜像里 `server.auth` 没有 `_HSTS` 就拒绝 (workflow 的预检步骤里)。
   该脚本与 `_HSTS`、compose 里写定的子网都在另一条线的分支上 (只读可看: 另一条线的子工作区 (分支 `hakupao/public-tunnel`),
   文件 `deploy/public-net/isolation_probe.py`、`server/auth.py`、`deploy/container/compose.public.yml`、`docs/plans/P3_4_tunnel_drill.md` 第 3 步)。
   本分支的测试用的是命令行相同的替身 (`tests/test_kbsync_deploy_public.py` 里的 `PROBE_STANDIN`)。

## 请重点看
1. `isolation_check` 调用真实 `isolation_probe.py` 的方式对不对: probe 的参数、输出格式 (它往标准输出打什么)、judge 的参数与退出码;
   替身的行为与真实脚本有没有会掩盖缺陷的出入。对照侧用默认网桥容器、只传内网目标, 是否符合对方 checkpoint 集成备注第 2 条的口径
   (另一条线的子工作区里的 `.work/10_split_and_public/evidence/checkpoints/p3_step3.4_tunnel.md`)。
2. 预检、临时验收、key 探测、换入核对、动正式容器这几段的顺序与失败分支: 有没有哪条失败路径会动到正式容器或数据, 或者把失败报成成功。
3. `_end_process_group` 的每个分支: 会不会给不该收到信号的进程 / 进程组发信号; `main()` 里的 `setpgid` 有没有副作用。
4. `public_halt` 现在用宽泛的 except 包住每一步: 会不会吞掉本该让流程停下的情况, 或者让摘要说错状态。
5. workflow 的改动 (`sdtm-rag.yml` 的预检步骤与 env、`kb-sync.yml` 的基线步骤): shell 写法在 bash -e 下的失败传播; 有没有把输入拼进命令。
6. 新增测试有没有恒真断言或没有分辨力的数据。

可以跑: `.venv/bin/python -m pytest tests/test_kbsync.py tests/test_kbsync_public.py tests/test_kbsync_deploy_public.py tests/test_workflow_conditions.py tests/test_deploy_public_compose.py -q -o addopts=""`

## 输出
结论 (PASS / PASS-with-fixes / FAIL) + 分级问题清单 (CRITICAL / HIGH / MEDIUM / LOW; 每条: 文件与函数名、触发条件、建议改法) + 实际跑过的命令。
没把握的写成疑问。不要输出任何真实研究标识或密钥。
