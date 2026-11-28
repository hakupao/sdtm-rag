# 公开腿演练阶段 D: 第一次公开部署 attempt 1 失败 (Gitea run id 219, 2026-11-28)

完整记录在 `checkpoints/p3_stageDE_first_public_deploy.md`; 这里是规则 B 的归档 (输入 / 产物 / 判定 / 下一 attempt 的输入)。时间戳是 UTC。

## 输入
- main = origin/main = `0a85a43`; 仓库变量 `SDTM_RAG_PUBLIC_DEPLOY` = `true`。
- 手动派发 `sdtm-rag` 工作流一次 (07:29:29Z): 在 `main` 上运行, `tag` = `613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7` (私有站线上镜像), `deploy` = true, `force_data_mismatch` = false。
- 公开侧起点: 公开容器 `created` / 从未启动 / 镜像 `…:099c2c9…`; 公开线上 stamp `f863e454…` / 4329; 过闸候选 `chroma_cand_477bac3ce565` / `meta_cand_477bac3ce565`。
- 派发前的五条只读预检全部满足 (checkout 的提交、`deploy_public` 的 `if`、私有容器不会被重建、镜像与镜像下限、基线快照)。

## 产物
- run id 219 (`run_number` 25), 头提交 `0a85a43`, 07:29:33Z → 07:30:52Z, `completed` / **`failure`**。
- `deploy` (job 465) **success**: 标签 `613f048…`, KB 对齐 `same`, 不换数据, `up -d` 两个容器都是 `Running` (没有重建), 健康检查 200。
- `deploy_public` (job 466) **failure**, 不是 skipped。走到的步骤: 镜像预检 (含镜像下限) → KB 对齐 `swap` → 部署前状态 → 公开网络子网 → 隔离核对 11 行全 PASS → 临时容器启动 → **临时容器验收不通过**。日志里的失败行 (已过编排自己的脱敏):
  ```
  [deploy-public] 失败：临时容器验收不通过 —— 容器没有进入 healthy 状态；启动报错：RuntimeError: SDTM_RAG_INSTANCE=public refuses to start: selectable model 'haiku-5-5': one answer round reserves $0.700 > free pool / 10 = $0.300 (lower its max_output_tokens)
  [deploy-public] 正式容器和正式数据都没有动（公开实例仍是停止状态）。
  ```
- 没有走到: 答题 key 探测、换入前置核对、停正式容器、换入、`up --no-start`。
- 兜底步骤: `[deploy-public] 正式容器没有被动过，不做任何事`; 清理步骤 success。
- 没有重跑, 没有手工回滚, 没有用 `force_data_mismatch`, 变量没有动。

## 技术判定
- 拒绝启动的是公开档的成本自检 (`server/instance.py` 的 `_public_cost_problems`): 每个可选模型「一轮答题的最坏预留额」不得超过免费池的十分之一。报错里的上限是 0.30 美元, 即免费池 3.0 美元; 这与 `server/quota.py` 的默认值算出来的一致 (每日总额上限 5.0 − BYOK 预留 2.0), 公开站的 env 文件我没有读, 所以只能说「与默认值一致」, 不能说它没有另外设置。
- 预留额 = 提示词上限 (历史 20000 + 固定开销 40000 = 60000 token) × 输入单价 + 输出上限 × 输出单价。输出上限按 `p3_step3.3.md` 的记载是 16000 (同样没有读 env 文件; 用它算出来的数与报错里的 0.700 分毫不差)。
- 单价的来源 (`server/cost.py` 的 `estimate_cost`): 先查写死的价格表 `_PRICES` → 再查 provider registry → 最后问 litellm。`claude-haiku-5-5` **不在写死的价格表里**, 只能靠 litellm。
- litellm 在被 import 时联网去取在线价格表 (`raw.githubusercontent.com` 上的 `model_prices_and_context_window.json`); 取不到就退回安装包里自带的旧表。**临时验收容器按设计没有网络** (`network_mode: none`, 协调方补充裁定 N1), 所以用的是包内的旧表, 里面没有这个模型 → `estimate_cost` 返回 `None` → 按回退费率 (输入 5 / 输出 25 美元每百万 token) 估: 60000 × 5 + 16000 × 25 = **0.70 美元** > 0.30 → 拒绝启动。
- 实测 (同一个镜像 `613f048`, 一次性容器, 不挂数据、不带 env 文件; 脚本 `checkpoints/p3_stageDE_price_probe.py`):

  | 条件 | 输入 / 输出单价 (美元每百万 token) | litellm 价格表条数 | 表里有这个模型 |
  |---|---|---|---|
  | `--network none` (与临时验收容器相同) | `None` / `None` (并打印取在线价格表失败、退回本地备份的告警) | 2764 | 没有 |
  | 默认网桥 (有外网) | `0.1` / `0.5` | 7194 | 有 |

  有网络时的预留额 = 60000 × 0.1 + 16000 × 0.5 = 0.014 美元, 远低于 0.30。
- 3.3 试跑 (2026-11-26, 旧镜像 `099c2c9`) 为什么没有暴露: 那次的公开容器接在有外网的 docker 网络里, 取到了在线价格表。`server/instance.py`、`server/quota.py`、`server/cost.py`、`server/provider_registry.py`、`server/llm_config.py` 在 `099c2c9` 与 `613f048` 之间没有任何改动 (`git diff --stat` 为空), 两个提交的 `uv.lock` 里 litellm 都是 1.88.6, 旧提交的写死价格表里同样没有这个模型 —— 不是这次的镜像带来的回归, 是「没有网络的容器」第一次真的去启动公开档。(旧镜像本身没有拿去在断网条件下跑, 这一句的依据是源码和锁文件相同。)
- 不是 key 的问题 (key 探测没有走到), 不是数据的问题 (候选副本的集合检查通过之后才起的容器), 不是隔离的问题 (隔离核对 PASS)。

## 业务判定
- **公开站没有受任何影响**: 部署前后的快照机械 diff 为空; 公开容器仍是 `created` / 从未启动 / 镜像 `099c2c9`; 线上数据、两个候选目录的 inode 与内容摘要不变; 没有 journal / guard / prev / 验收副本残留。失败发生在「动正式容器之前」, 编排的结论与实际状态一致。
- **私有站没有受影响**: 容器 Id、启动时间、重启次数、数据指纹前后相同; health 200。
- **这个失败会稳定复现**: 只要公开站可选模型的价格只能从在线价格表取得, 任何镜像都过不了没有网络的临时验收。变量开着期间, 每一次带公开部署的运行都会在同一处变红 (公开站不变, 私有部署照常成功)。
- 同一个依赖在正式容器上也存在 (这次没有走到): 正式公开容器每次启动都要取到那份在线价格表才能通过自检; 取不到 (GitHub 不可达、出网被挡) 就拒绝启动 (按代码推的, 没有在正式容器上试过)。方向是安全的 (不会带着错的额度启动), 但等于把公开站能不能启动交给了一个外部地址。
- 设计阶段的漏判: `p3_public_leg_impl.md` §7 第 2 条把「没有网络的临时容器能否起到 healthy」列为未验证, 依据写的是「lifespan 没有出站调用」—— 漏了 import 阶段 litellm 自己的那次联网, 以及启动自检对价格的依赖。替身数据根实跑里的 docker 是假的, 不会真的起应用。

## 下一 attempt 的输入
- 协调方 2026-11-28 答复 (协调方的决定, 不是主人逐条裁定): 修法定为「把公开档可选模型的价格固定进代码, 启动自检不依赖联网」, 由协调方另开一个子工作区的会话在分支上做; 本会话不改代码。
- 修完之后需要构建新镜像 (超出这次同意的范围, 要主人另行同意); 新镜像部署时公开腿会从头走一遍 (预检 → 隔离核对 → 临时验收 → key 探测 → 换入 → `up --no-start`)。
- 没有采用的两条路 (汇报时列过): 只改公开站 env (把回退费率设成该模型的实际价格, 或提高每日总额上限 —— 前者是绕过, 后者改的是花费上限; 这两种改法能不能生效只读过代码、没有实测); 让临时验收容器联网 (与 N1 裁定相反)。
- 修法要顺带回答的: 修完之后同一个镜像在 `--network none` 下跑 `p3_stageDE_price_probe.py` 应当给出价格; 公开档的启动自检最好有一条「没有网络也能过」的测试 (现在的测试环境有没有网络决定了这条路径测没测到)。

## 复跑
```sh
# 取运行结果与日志 (账号口令取自 git credential, 经标准输入交给 curl, 不写进任何文件)
API=https://git.bojiang.org/api/v1/repos/bojiang/sdtm-rag
curl -s -u <账号>:$P "$API/actions/runs/219"; curl -s -u <账号>:$P "$API/actions/runs/219/jobs"
curl -s -u <账号>:$P "$API/actions/jobs/465/logs" > $OUT/job_465.log; curl -s -u <账号>:$P "$API/actions/jobs/466/logs" > $OUT/job_466.log
grep -nE '\[deploy-public\]|refuses to start' $OUT/job_466.log
# 定价诊断 (VM 内的一次性容器; 不挂数据、不带 env 文件)
IMG=192.168.100.58/bojiang/sdtm-rag:613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7
VM "sudo docker run --rm -i --network none --cap-drop ALL --entrypoint python $IMG -" < .work/10_split_and_public/evidence/checkpoints/p3_stageDE_price_probe.py
VM "sudo docker run --rm -i --cap-drop ALL --entrypoint python $IMG -" < .work/10_split_and_public/evidence/checkpoints/p3_stageDE_price_probe.py
# 「不是这次镜像带来的回归」的依据
git diff --stat 099c2c9 613f048 -- server/cost.py server/provider_registry.py server/instance.py server/quota.py server/llm_config.py   # 空
for c in 099c2c9 613f048; do git show "${c}:uv.lock" | grep -A1 '^name = "litellm"'; done                                              # 都是 1.88.6
git show 099c2c9:server/cost.py | sed -n '/^_PRICES/,/^}/p' | grep -c haiku-5-5                                                          # 0
# 判据所在的代码
grep -n "reserves" server/instance.py; grep -n "quota_site_cap_usd\|quota_byok_side_budget_usd\|quota_fallback_.*_usd_per_mtok\|PROMPT_OVERHEAD_TOKENS =" server/quota.py; sed -n '/^_PRICES/,/^}/p' server/cost.py
```
