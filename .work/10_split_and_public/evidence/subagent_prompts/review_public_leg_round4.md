# 第四轮 (窄范围) 安全审查: 公开腿合并前的最后一批改动

你是独立安全审查者 (只读, 不改任何文件, 不 push, 不连虚拟机, 不读 `.env` 内容, 不跑变异脚本, 不跑全量 pytest)。
仓库: 当前工作目录, 分支 `hakupao/public-kb-leg`。全程中文。

## 范围
`git diff 5b8a044~1 -- deploy .gitea tests` 里**还没有被独立审查过**的部分, 一共三块 (以工作区为准, 最新改动尚未提交):

A. 第三轮审查意见的修正 (提交 `5b8a044` 里的这些, 第三轮审的是它们之前的状态):
   接入公开网络的一次性容器加 `--cap-drop ALL --security-opt no-new-privileges` (`ONE_OFF_HARDENING`, `_probe`, `isolation_check` 里的 `probe`);
   隔离探测输出的形状校验; `_proc_kind` / `_end_process_group` 对「已退出但没被回收的组长」的处理; `container_state` 空输出;
   `scrub` 增加 JWT 形状; 候选记录里的 `prod_image_ref`; 镜像下限预检改成 `deploy/public-net/image_floor_check.py` 的判法
   (workflow `sdtm-rag.yml` 的 `deploy_public` 预检步骤里那两行 shell: 退出码与输出两样都核对)。
B. **私有部署 job 的加固 (改的是私有站正在用的部署 job, 请格外仔细)** —— `.gitea/workflows/sdtm-rag.yml` 的 `deploy` job:
   「确定要部署的标签」从 `printf … | grep -Eqx` 改成 bash 整串匹配 `[[ "$TAG" =~ ^[0-9a-f]{40}$ ]]`, `gitea.sha` 改经 env (`SHA`);
   「构建并推送」「部署」两个步骤里内联的 `${{ steps.tag.outputs.tag }}` 改成 env 里的 `TAG`; 两个登录步骤的 `gitea.actor` 改经 env (`ACTOR`)。
   要求是**只做加固, 合法输入下行为不变**。基点是 `9a8ad43` (`git show 9a8ad43:.gitea/workflows/sdtm-rag.yml`)。
   另外 `kb-sync.yml`: 私有腿「删除候选镜像」的条件恢复成基点的写法, 公开腿改成与它相同 (每条腿删自己建的那个标签)。
C. **线上公开数据里发现非 KB 集合就停站** (协调方 2026-11-28 裁定: 红线, 发现了就不该继续对外; 停机是安全方向; 这是故意偏严的断言,
   失败信息要写明发现了哪些集合、正当新增要改哪里; 同样先看 journal, 判不出时保持现状并失败, 不做别的动作):
   `deploy/kbsync/kbsync.py` 的 `live_extra_collections`、`live_contaminated_stop`, 以及 `_deploy_public` 里调用它们的位置。
   注意: 裁定的原话针对「这次部署不换数据」的情形; 实现对「换数据」的情形也一样停站 (理由相同)。请判断这个扩展有没有带来问题。

背景与红线: `.work/10_split_and_public/evidence/subagent_prompts/review_public_leg_security.md`。
前三轮的意见: `.work/10_split_and_public/evidence/checkpoints/p3_public_leg_impl_review.md` (「处置」列是写作者的说法, 不要采信)。

## 请重点看
1. (B) 逐步对照基点与现在的 `deploy` job: 对「合法的 40 位小写提交号」和「空值」两种输入, 每个步骤拿到的值、执行的命令是否完全相同。
   有没有哪个步骤现在用到了 `$TAG` 却没有在 env 里定义 (会变成空串 —— 例如 `"$IMAGE:$TAG"` 变成 `"$IMAGE:"`);
   job 级 / workflow 级有没有同名变量会被遮蔽; `deploy_public` 的 job 级 `TAG` 与步骤级是否冲突。
   bash 的 `[[ =~ ]]` 在 `bash -e` 下、变量未加引号的右侧正则、locale 对 `[0-9a-f]` 的影响 (例如某些 locale 下 `[a-f]` 是否匹配大写)。
   多行、首尾空白、大小写、长度不对的输入是否都被拒; 被拒时有没有东西已经写进 `GITHUB_OUTPUT`。
2. (C) 停站路径: 会不会在不该停的时候停 (误报: 读集合失败、guard 副本残留、KB 集合自己被算成「额外」);
   会不会该停的时候没停; journal 判不出 / 有残留时是否真的什么都不做; 有没有任何启动动作; 失败信息里打印集合名有没有泄露风险
   (集合名形如 `study_<代号>`, 这类代号在仓库文档里本来就有; 请判断是否可接受)。停站之后「已动过」标记与中断兜底的配合。
   这一步放在网络预检和临时验收之前是否合适。
3. (A) `--cap-drop ALL` 之后这两类容器还能不能完成它们的工作 (Python 发起 TCP 连接、HTTPS 请求、DNS 解析是否需要任何 capability);
   `no-new-privileges` 有没有副作用。镜像下限那两行 shell 在 `bash -e -o pipefail` 下的各种失败是否都落到 `exit 1`。
4. 新增测试有没有恒真断言或没有分辨力的数据; 用真实 bash 执行步骤脚本的那几条测试 (`_run_step`) 是否真的执行了 workflow 里的脚本。

可以跑: `.venv/bin/python -m pytest tests/test_kbsync.py tests/test_kbsync_public.py tests/test_kbsync_deploy_public.py tests/test_workflow_conditions.py tests/test_deploy_public_compose.py -q -o addopts=""`
(`.venv` 是本工作区自己的, 不是主仓的。)

## 输出
结论 (PASS / PASS-with-fixes / FAIL) + 分级问题清单 (CRITICAL / HIGH / MEDIUM / LOW; 每条: 文件与函数 / 步骤名、攻击或触发场景、建议改法)
+ 一张表: 私有 `deploy` job 每个步骤在「合法提交号」「空值」两种输入下改前改后是否等价 (等价 / 不等价 + 依据)
+ 实际跑过的命令。没把握的写成疑问。不要输出任何真实研究标识或密钥。
