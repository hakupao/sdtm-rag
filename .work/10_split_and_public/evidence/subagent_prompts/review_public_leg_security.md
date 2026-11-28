# 安全审查: 公开腿实现 (公开数据根的 KB 更新 + 公开部署先用临时容器验收)

你是独立安全审查者 (只读, 不改任何文件, 不 push, 不连虚拟机)。仓库: 当前工作目录 (分支 `hakupao/public-kb-leg`, 基点 `9a8ad43`)。
用 `git diff 9a8ad43 -- .gitea deploy tests` 看全部改动 (以工作区为准)。全程中文。

## 背景
同一台部署机上有两个实例: 私有站 (数据根 `…/deploy-data/sdtm-rag/data`, chroma 里含真实研究数据的 study 集合, 另有 `study/` 目录)
和公开站 (数据根 `…/deploy-data/sdtm-rag-public/data`, chroma 只应含 CDISC 公开标准的 `sdtm_kb_v1`; 将来经隧道对外)。
红线: 真实研究数据绝不能进入公开数据根或被公开实例读到。公开站各有自己的 env 文件与 API key。
CI job 容器访问不了数据根, 文件操作经 `kbsync.py --via <镜像>` 在兄弟容器里做 (按原路径挂载数据根)。

## 要审的东西
`deploy/kbsync/kbsync.py`、`.gitea/workflows/kb-sync.yml`、`.gitea/workflows/sdtm-rag.yml` (`deploy_public`)、
对应测试 (`tests/test_kbsync*.py`、`tests/test_workflow_conditions.py`、`tests/test_deploy_public_compose.py`)、
`deploy/container/compose.public.yml` 与 `compose.yml` (只读参考, 本次没改)。
规格: `.work/10_split_and_public/evidence/checkpoints/p3_public_kb_update_design.md` (v0.2 + 裁定登记)、
`p3_step3.2_compose.md` 文末「M3 裁定」; 2026-11-28 协调方补充裁定: 部署前停止的正式容器在成功路径上也不启动 (只更新数据和镜像);
正式容器被停下之后的任何失败都保持停止; 基线镜像必须与公开 chroma 配对; 临时验收里加不花钱的答题 key 有效性探测。

## 请重点攻击这几条 (逐条给出"成立 / 不成立 + 依据")
1. **公开数据根不混入研究数据**: 有没有任何子命令、参数组合、挂载方式、目录名 (含 `..`、符号链接、journal 文件内容被篡改) 能把私有根的内容
   带进公开根或公开实例的挂载范围? `--kb-only` 两层 (候选过闸前; 换入时线上与换入源) 有没有绕过路径 (例如 `chroma_prev_*` 作换入源、
   decision = same 时)? 临时验收副本放在数据根的上一级目录, 这个挂载有没有扩大到能碰私有根?
2. **失败路径不把公开站意外拉起**: 列出代码里所有会启动公开正式容器的调用点, 逐个说明在哪些状态下可达; 部署前是停止的容器有没有任何路径被启动;
   取消 / 超时 (workflow 的兜底步骤) 与编排内部的失败处理有没有冲突或竞态。
3. **不留在半换入状态**: swap 写 journal 之后的每个失败点, 最终数据与容器处于什么状态; 有没有"数据已换、journal 已删、容器是旧镜像在跑"
   或"旧镜像 + 新数据对外"的可达状态; 正式容器没确认停止时会不会改数据。
4. **临时验收容器的隔离**: 不联网、无端口、不与正式容器共用可写状态 (尤其 `quota.sqlite`)、不会被按容器名解析到、清理是否可靠
   (含上次被杀留下的); 生成的 compose 模型能否被 `compose.public.yml` 将来的改动 (加 ports / networks / 第二个服务) 带偏。
5. **密钥**: 两段探测脚本 (`KEY_CHECK_PY`、`ANSWER_KEY_PY`) 与失败日志会不会把 key 或其片段写进日志 / 命令行 / 进程参数;
   `scrub` 的正则够不够; workflow 里有没有把用户输入直接拼进 shell (注入)。
6. 其他你认为重要的 (OWASP 视角、fail-open 的默认值、TOCTOU)。

可以自己跑测试: `.venv/bin/python -m pytest tests/test_kbsync.py tests/test_kbsync_public.py tests/test_kbsync_deploy_public.py tests/test_workflow_conditions.py tests/test_deploy_public_compose.py -q -o addopts=""` (不要跑变异脚本, 另一位审查者可能在跑)。

## 输出
结论 (PASS / PASS-with-fixes / FAIL) + 分级问题清单 (CRITICAL / HIGH / MEDIUM / LOW), 每条给文件与函数名、攻击 / 触发场景、建议改法。
没把握的写成疑问。不要输出任何真实研究标识或密钥。
