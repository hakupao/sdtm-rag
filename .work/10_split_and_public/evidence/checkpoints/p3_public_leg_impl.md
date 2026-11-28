# P3 公开腿实现: 公开站的 KB 更新流程 + 公开部署先用临时容器验收 (2026-11-28, 分支 `hakupao/public-kb-leg`)

**状态: 已实现并在分支上验证; 没有 push、没有合并、没有触发任何 workflow、没有动虚拟机 / 数据根 / 容器 / Gitea 变量。**
workflow 的 job 只在 main 上执行, 所以真实运行一次都没有发生过; 分支上能做的验证见 §4, 做不到的见 §7。

## 0. 协调方需要先看的

**上一轮提出的五件事, 协调方 2026-11-28 已答复 (协调 bot 受托代裁), 都已落实:**

| # | 事项 | 答复 | 落实 |
|---|---|---|---|
| 1 | 候选镜像两条腿各构建一次 | 接受这个出入; 条件: 同一个 checkout 的同一个提交, 每条腿结束时清理自己构建的镜像 (成功失败都清) | 两条腿的「删除候选镜像」改成同一个写法: 自己建了才删, 删的是自己那个标签, 成功 / 失败 / 取消都删 (私有腿因此回到基点的原样)。README 与 §3.1 写成「与设计 v0.2 第 5 条的已知出入, 协调方接受」并说明为什么两条腿不会用到不同的镜像 |
| 2 | 答题 key 探测 | 保留; 措辞写准确 | README 与 §3.2: 「该接口不产生 token, 按此推断不计费; 官方文档没有专门的计费条目; 它只验 key 是否有效, 验不了额度」 |
| 3 | 私有部署 job 里继承下来的两处问题 | 修掉; 只做加固, 合法输入下行为不变; 配测试; 安全审查; 改前改后逐步对照 | 已改, §3.4 是对照 |
| 4 | 主仓索引文件被碰了修改时间 | 知道了; 以后依赖索引的测试用本工作区的副本 | 本轮在本工作区建了自己的 venv, 全量测试用本工作区的索引副本; 运行前后核对主仓 `data/` 0 个文件变化 (§4.1) |
| 5 | 线上公开数据里已有非 KB 集合、这次又不换数据 | 改成自动停站并明确失败; 故意偏严; 失败信息写明发现了哪些集合、正当新增要改哪里; 先看 journal, 判不出时保持现状并失败 | 已改, §3.2 第 4 步。**有两处比答复的原话多做了一点, 请知悉** (见下) |

**这一轮需要协调方知道的:**

1. **红线停站的范围比答复的原话宽** (理由相同: 发现了就不该继续对外): 答复说的是「这次部署不换数据」; 实现是只要这次公开部署读到线上公开 chroma 里有 `sdtm_kb_v1` 以外的集合就停 —— 包括这次要换数据的情形, 也包括「公开数据落后且没有候选」那个本来只告警跳过的情形 (第四轮审查指出它才是最常见的「不换数据」, 不查等于漏)。要收窄的话改一处判断即可。
2. **失败信息里的集合名不是全部原样打印**: 答复要求「写明发现了哪些集合」。本仓约定的代号形态 (`study_st<数字>…`、`sdtm_…`) 原样写出; 其余的名字只写指纹 (sha256 前 10 位) 和长度 —— 不按约定命名的集合, 名字里可能带真实研究的标识, 而红线是这类标识不外泄 (第四轮审查的意见)。个数总是写明的。如果要一律原样打印, 请明示。
3. **合并依赖** (没有变): 先以 squash 方式合并隧道那条线, 再合这条 (或同一次推送)。公开部署依赖隧道分支的 `deploy/public-net/isolation_probe.py`、`deploy/public-net/image_floor_check.py` 和 `compose.public.yml` 里写定的子网。合并后要把 `tests/fixtures/kbsync/compose_config_public_tunnel.json` 覆盖到 `compose_config_public.json`, 否则 CI 的测试步骤变红, 会连私有部署一起挡住 (§6 第 2 条)。
4. **`deploy/README.md` 的冲突怎么处理**: 这条线对它的改动是**纯新增、零删除、零修改**, 全部在「## KB 同步 (kb-sync)」这一节的末尾 —— 紧接原有的第 3 条「人工排查」之后新增一个小节「### 公开实例（P3；…）」, 一直到「## 回滚」之前。其他各节 (组成 / 发版 / 回滚 / 启动失败常见原因 / 其他) 一个字没动。合并时两边的新增都保留即可 (§6 第 10 条)。
5. **私有部署 job 这次被改了** (§3.4): 在合法提交号和空值两种输入下, 每个步骤拿到的值和执行的命令与改之前相同 (测试逐项核对, 第四轮审查逐步对照)。唯一能感知的差别: 手动填的 tag 末尾带一个换行时, 以前会放行, 现在被拒。
6. **四轮、五份独立审查都是 PASS-with-fixes, 没有 CRITICAL / HIGH** (§9)。第四轮意见的修正 (红线检查提前、副本删不掉不丢结论、集合名的显示规则) 没有再经独立审查; 第 7 条的三处小改动也没有。
7. **隧道那条线收尾后的三点 (协调方 2026-11-28 转达), 已处理**:
   - 全局限流: 临时验收容器照抄 compose 的环境变量, 同样带着限流 (每来源每分钟 60, 突发 20, `/api/health` 不计)。验收脚本对每个容器一共只发 2 个请求 (`/api/info`、`/openapi.json`), 每次验收只跑一遍; 等健康状态靠的是 docker 的健康检查 (打 `/api/health`), 新鲜度检查不走 HTTP。测试钉住「恰好 2 个, 4 倍仍在突发之内」。
   - 新的启动自检让临时容器起不来时: 验收判失败, 那条报错原样带进失败原因 (「容器没有进入 healthy 状态；启动报错：RuntimeError: …」), 日志末尾 40 行照旧打印。正式容器不动。
   - `tests/fixtures/kbsync/compose_config_public_tunnel.json` 已按隧道分支 **`9d21808`** 的 `compose.public.yml` 重新渲染 (该文件最后一次改动在 `ade6a59`; 环境变量 6 个键)。渲染方式与之前相同: 文件经标准输入传入, 虚拟机上不落文件 —— `cat <隧道分支>/deploy/container/compose.public.yml | ssh <mini> '… limactl shell deploy -- sudo env IMAGE_TAG=abc docker compose -f - config --format json'`, 输出不再加工。对方的 compose 再改, 这个文件要再渲染一次。

## 1. 同意与裁定来源
- 主人 2026-11-28 在协调方的待办项上选了「开始，先做 rag 的三项代码工作」(选项说明: 公开站 KB 更新流程、临时容器验收、隧道配置; 分支上做, 不合并不部署)。本文件是前两项; 隧道配置在另一个子工作区。
- 规格: `p3_public_kb_update_design.md` (v0.2 + 裁定登记 D1–D8, 协调 bot 受托代裁) 与 `p3_step3.2_compose.md` 文末「M3 裁定」(主人本人选定)。
- 实现中问出来的 4 条 (2026-11-28, **协调 bot 受托代裁**, 委托原话 2026-11-27「之前那些选项，你可以替我分析后决定嘛。我听从你的建议」; 不是主人逐条裁定):

| # | 问题 | 裁定 |
|---|---|---|
| Q1 | 正式容器部署前就是停止的 (或不存在), 临时验收通过之后怎么办 | 换入数据, 用新镜像重建正式容器, **不启动**; 日志和摘要写明启动需人工并给出命令 |
| Q2 | 正式容器原本在运行、为换数据已停下、换入被拒或失败、数据确认仍是部署前状态 | 保持停止; 把「停正式容器」尽量放到所有能提前做的检查之后 |
| Q3 | 没有任何镜像与公开数据配对时, kb-sync 公开腿的基线怎么办 | 明确失败并说明原因; 手动派发时有输入参数可指定基线; 「镜像内 KB 指纹 == 公开 stamp」的守卫保留 |
| 告知 | Anthropic key 没有任何自动步骤会用到 | 在临时验收里加一次不花钱的有效性探测 (只列模型); 不加真答题冒烟; key 不得出现在日志 / 命令行; 服务商接口暂时不可用时公开部署也不通过, 这个代价接受 |

隧道那条线汇报之后的补充裁定 (同日, 同样是协调 bot 受托代裁):

| # | 裁定 | 落实 |
|---|---|---|
| N1 | 临时验收容器不带网络; 环境变量照抄 (含新增的 `SDTM_RAG_QUOTA_TRUSTED_PROXIES`、`FORWARDED_ALLOW_IPS`), `networks` 段不照抄 | 原实现就是 `network_mode: none` + 白名单取键; 用隧道分支改后的 compose 的真实解析结果补了测试 |
| N2 | 答题 key 探测不放在临时容器里: 另起一次性容器, 接在公开网络 `sdtm-rag-public` 里, 放在临时验收通过之后、动正式容器之前 | 已改 |
| N3 | 动正式容器之前加三道只读预检: 公开网络子网、网络隔离核对、镜像下限 | 已加 (§3.2 第 0、5 步) |
| N6 | 接公开网络的一次性容器守五条: 不指定地址; 不叫 `sdtm-rag-public-api`、不加别名、不用 `compose run api`; `--cap-drop ALL`; key 只经只读挂载的 env 文件传入; `--rm` 且不监听端口 | 已做, 假 docker 逐次核对 |
| N7 | 镜像下限的判法: 对方的 `image_floor_check.py` 经标准输入送进待部署的镜像, 退出码 0 **并且**输出恰好是 `image-floor: ok`; shell 写法原样照抄, 并加测试钉住 | 已照抄; 测试让真实 bash 跑这一行 (合格 / 无输出 / 多一行 / 输出不对 / 退出码非 0 / 脚本不存在) |
| N8 | 对方的分支必须以 squash 方式合并 | §0、§5、§6 |

对上一轮「需要先看的」五件事的答复 (同日, 协调 bot 受托代裁): 见 §0 的表。
| N4 | 写清合并顺序上的依赖 | §0 第 4 条、§6 |
| N5 | 开变量之前必须先重建公开网络; 演练方案引用对方的, 不另写 | §5 |

## 2. 改了什么

| 文件 | 改动 |
|---|---|
| `.gitea/workflows/kb-sync.yml` | 单 job → `private` + `public` 两个 job; 数据根 / env 文件挪到 job 级 env; 新增输入 `public_baseline_image` |
| `.gitea/workflows/sdtm-rag.yml` | `deploy_public` job: 预检 (镜像, 含镜像下限) → `kbsync.py deploy-public` → 中断兜底 `public-abort` → 清理 `accept-down`; job 的 env 里多了隔离核对的脚本路径与目标清单。私有 `deploy` job: 只做加固 (标签校验改整串匹配, `run:` 里的表达式改经 env), 合法输入下行为不变 (§3.4) |
| `deploy/kbsync/kbsync.py` | 见下 |
| `deploy/README.md` | 「KB 同步」一节末尾加「公开实例」小节 |
| `tests/test_kbsync.py` | 假 docker 扩展 (compose 模型、按镜像给指纹、key 检查、验收副本); 原有 44 个测试不变 |
| `tests/test_kbsync_public.py` (新) | kb-only 两层、路径一致性、基线镜像、key 检查与失败归类、两个数据根互不相通 |
| `tests/test_kbsync_deploy_public.py` (新) | 公开部署编排的全部路径 (带容器状态的假 docker) |
| `tests/test_workflow_conditions.py` (新) | 两个 workflow 每个 job / step 的 `if` 真值表 + 结构不变量 |
| `tests/test_deploy_public_compose.py` | `test_public_job_gated_and_separate` 随 job 结构更新; 验收脚本的断言改为检查 `kbsync.ACCEPT_PY` |
| `tests/fixtures/kbsync/compose_config_{public,private}.json` (新) | 部署机上 `docker compose config --format json` 的真实输出 (只读采集) |
| `tests/fixtures/kbsync/compose_config_public_tunnel.json` (新) | 同上, 输入是隧道分支改过的 `compose.public.yml` (合并后的形状; 合并时用它覆盖上一行的 public 那份) |

`kbsync.py` 新增的子命令与行为:

| 子命令 / 参数 | 作用 |
|---|---|
| `candidate --kb-only` | 第一层: 候选评测之后、gate 之前, 用候选镜像读候选目录, 集合必须恰为 `{sdtm_kb_v1}`; 否则 `fail --reason kb_only_violation` 归档 (读不出 → `kb_only_unreadable`) |
| `deploy-swap --kb-only` | 第二层 (主闸): 守卫副本上线上与换入源都不得有非 KB 集合, 换入源必须有 KB 集合。「两边相同」不算通过 |
| `paths-check` | 数据根 / env 文件 == `docker compose -f compose.public.yml config` 解析出的 api 服务挂载源; 且数据根、env 文件、数据根的上一级目录都不与私有 compose 的任何挂载源重叠 (相同或互为上下级)。私有一侧取自私有 compose 文件, 不接受第二个数据根 |
| `key-check` | 用 env 文件里的 key 做一次最小 embedding 调用; 无效 / 额度用尽 / 无权限 / 限流分类报错, 只输出类别、状态码、异常类名 |
| `baseline-image` + `stamp` | 按给定顺序取第一个「镜像内 KB 指纹 == 数据根 stamp」的镜像; 没有则 rc 1, stdout 为空。stamp 由 `--via-image` (私有线上镜像) 去读, 候选基线镜像在配对之前不挂数据根; 不在本机的镜像不运行 |
| `candidate` 的步骤失败 | 追加原因归类 (`quota_exhausted` / `key_invalid` / `rate_limited`), 写进归档原因; 输出的 stderr 末尾先隐去 `sk-…` 片段 |
| `accept-stage` / `accept-clean` | 临时验收用的数据副本, 放在数据根的**上一级** `kbsync_accept_<ts>/data/{chroma,meta}` (不含 `quota.sqlite`); 兄弟容器里数据根是只读挂载 |
| `deploy-public` | 公开部署的整个编排 (§3); 新增必填参数 `--isolation-probe` / `--isolation-lan` / `--isolation-egress` |
| `public-abort` / `accept-down` | workflow 的中断兜底 (动过正式容器才停, 不碰数据) / 清理临时容器与副本 |
| `guard-copy` / `restore` / 所有带 `--fp` `--ts` 的子命令 | 目录名必须是数据根下的一级名字 (带 `/` 或 `..` 的拒绝, journal 里的名字也查); `--fp` 必须是 64 位十六进制, `--ts` 必须是时间戳格式 |
| `swap --expect-source` | 只换入验收过的那一份; 重新选出的换入源不同就拒绝 |

## 3. 行为说明

### 3.1 kb-sync 两条腿
- `private`: 步骤顺序与命令不变。**私有路径上可见的变化只有这几处**:
  1. 「确定 KB ref」的格式校验从 `grep -Eqx` 改成 bash 整串匹配 (更严: 多行输入不再放行; 合法值不受影响, 已让真实 bash 跑过);
  2. (上一轮曾给末尾「删除候选镜像」加条件, 这一轮已恢复成基点的原样);
  3. `candidate` 某一步失败时, 归档原因可能多一个归类后缀 (如 `ingest_rc1_quota_exhausted`), 打印的 stderr 末尾先隐去 key 片段;
  4. 文件系统子命令校验 `--fp` (64 位十六进制) 与 `--ts` (时间戳格式), `restore` 校验 journal 里的目录名 —— workflow 传的值都合法, `predeploy-check` / `swap` 的 `--target-fp` 不在此列 (`unknown` 照常可用);
  5. `deploy-swap` 的核对拆成 `swap_guard` + 改名两步, 行为不变 (原有 44 个测试未改且通过)。
  测试 `test_kb_sync_private_leg_changed_only_where_intended` 对照基点: 私有腿只有「确定 KB ref」一个步骤与基点不同。
  私有 `deploy` job (sdtm-rag.yml) 这一轮做了加固, 见 §3.4。
- `public`: `needs: private` + `if: always() && main && vars.SDTM_RAG_PUBLIC_DEPLOY == 'true'`。步骤: 确定 KB ref → 拉 KB 算指纹 (这两步与私有腿逐字相同, 有测试钉住) → 路径一致性断言 → 检测 → 构建候选镜像 → embedding key 检查 → 选基线镜像 → `candidate --kb-only` → 删镜像 (`always()`)。
- 任何一步失败 job 都是红的 (没有 `continue-on-error`, kbsync 的失败后面不接 `||`); 不影响私有腿, 公开站保持旧镜像 + 旧数据。
- 人工指定基线 (`public_baseline_image`): 只接受本仓镜像仓库里按 commit 打标签、且已在部署机本地的镜像 (基线镜像会挂载公开数据根和公开 env 文件); 守卫照旧, 不配对就失败, 不回落到自动选。
- 用户输入的 KB ref 用 bash 整串匹配校验 (`grep -x` 是逐行匹配, 多行输入里有一行合法就放行)。
- **与设计 v0.2 第 5 条的已知出入, 协调方接受 (2026-11-28)**: 没有单独的「构建 / 删除镜像」job, 也不靠跨 job 输出。两条腿在需要时各自 `docker build`, 结束时各自删除自己构建的那个镜像 (成功 / 失败 / 取消都删; 两条腿的这一步逐字相同, 有测试钉住)。
  - 为什么这样做: job 级 `always()` 与 `needs.*.outputs` 在这台 Gitea 上从未真正运行过, 步骤级 `always()` 是现有 workflow 已经在用的机制; 私有腿因此与基点逐步相同, 只差一处格式校验。每次都 build 而不是「镜像在就复用」, 是为了不拿上次运行残留的旧代码镜像去建候选。
  - 为什么不会出现两条腿用了不同镜像的情况: 两条腿是同一次运行、同一个提交的 checkout; 镜像标签是 KB 指纹的前 12 位。标签相同 ⇒ 仓库提交相同且 KB 内容相同 ⇒ 构建出来的镜像内容相同 (第二次构建通常直接命中层缓存; 缓存没命中也只是多花几分钟, 内容仍相同)。两条腿解析到不同的 KB 时 (两条腿之间恰好有新 tag), 指纹不同、标签不同, 各用各的, 不会混用。
  - 候选记录 (`kbsync_gate.json`) 里记的是镜像标签; 残留的候选镜像 (运行被取消等) 需要人工清理, README 有命令。
- **基线镜像**: 设计写「公开容器存在用其镜像, 否则用私有线上镜像」。保留, 并加守卫「镜像内 KB 指纹 == 公开 stamp」。核对依据: 镜像 `099c2c9` 的 submodule 是 `7819398` (旧 KB, 指纹 `f863e454…` == 公开 stamp), `f798709` 是 `b2bd837` (新 KB) 且题集改了 5 处 (`git diff 099c2c9 f798709 -- eval/test_set_v3.yml`)。私有线上镜像配公开旧数据会让基线先掉分, 相对闸被放宽。失败停机后公开容器是「没通过的新镜像」, 守卫会跳过它。选定后按镜像 ID 使用。

### 3.2 公开部署 (`deploy-public`) 的顺序
0. (workflow 的预检步骤, 只读) tag 格式 → 拉镜像 → 镜像能按公开档启动 → WorkingDir → **镜像下限** (隧道那条线的 `image_floor_check.py` 经标准输入送进待部署的镜像: 看 `server.auth.PUBLIC_EDGE_LEVEL >= 1`, 再实际调一次「可信代理必须是单主机」的检查; 合格 = 退出码 0 并且输出恰好是 `image-floor: ok`。隧道这一步之前的镜像拒绝, 用 tag 回滚到旧镜像时也走这里)。
1. 路径一致性; compose 解析出的镜像必须等于要部署的镜像。不一致 → 失败, 什么都没挂载。
2. 清掉上次被杀留下的临时容器与副本。
3. KB 对齐: `journal_pending` → 失败。记录部署前状态 (运行中 / 已停止 / 不存在; 查不出来 → 失败, 不当作「不存在」)。
4. **红线检查**: 在副本上读线上公开 chroma 的集合 (读完删副本)。有 `sdtm_kb_v1` 以外的集合 → 先看 journal: 有残留或判不出 → 保持现状并失败, 不做任何动作; 否则写「已动过」标记, `compose stop` 整个公开项目, 确认已停, 失败。失败信息写明个数与集合名 (约定的代号形态原样写, 其余写指纹和长度)、这是故意偏严的检查、正当新增一个 KB 集合时要改 `kbsync.py` 的 `KB_COLLECTION` 并核对 `server/instance.py` 的 `check_chroma`、处理完如何恢复。这一步排在「缺候选就跳过」之前, 也排在网络预检之前; 读不出集合 (副本打不开) 不算「发现了」, 按部署前检查出错处理, 不停站。只停不起, 不改数据。
   然后才是 `missing` / `unknown` → `::warning::` 跳过 (D1, rc 0); `same` / `swap` 继续。
5. **网络预检 (只读)**: 公开网络的实际子网 == compose 里写定的子网 (compose 没写定 → 失败: 隧道那条线还没合进来; 实际不同 → 失败: 「先做网络重建那一步」)。然后**隔离核对**: 公开网络里的一次性容器 (不挂数据、不带 env 文件、去掉全部 capability) 对一批内网目标和外网目标各连一次, 默认网桥上的一次性容器对同一批内网目标作对照, 两份观测交给隧道那条线的 `isolation_probe.py judge --isolated-net <子网>`; 退出码非 0 (不隔离 / 无结论) → 失败。
6. **临时验收** (此阶段不碰正式容器, 不写公开数据根; 临时容器没有网络): 复制副本 (`swap` 时复制候选, `same` 时复制线上) → 副本集合恰为 `{sdtm_kb_v1}` → 起临时容器 → healthy → 档位 = public / `/openapi.json` 404 → `check_index_freshness` → 清理 (finally)。
7. **答题 key 探测**: 公开网络里的一次性容器 (只挂 env 文件, 只读; 不指定地址、不起名字或别名、去掉全部 capability、`--rm`), 只列模型。
8. `swap` 时先做换入前置核对 (`swap_guard`, 只读, 在副本上; kb-only; 换入源必须是验收过的那一份)。
   第 5–8 步任何一项不过: rc 1, 「正式容器和正式数据都没有动」(第 8 步时正式容器还没有被停)。
9. **重新读一次正式容器的状态, 以这一刻为准** (前面几步要几分钟; 期间被人工停下的不拉起)。写「已动过」标记文件, 然后才动正式容器 (起 / 停只针对 `api` 服务):
   - `swap`: `compose stop api` → 确认已停 → 再核对一次 (主闸) → **再确认一次仍然是停的** → 改名换入 (`--expect-source`)。
   - 此刻在运行: `compose up -d api` → 确认镜像 → 复验 (与临时容器同一套)。
   - 此刻停止 / 不存在: `compose up --no-start api` → 确认「新镜像、未启动」。
   - 换过数据: `finish`; 之后 `prune` 出任何错都只告警。
10. 第 9 步里的任何失败或异常 → `public_halt`: `compose stop` (整个公开项目) → 确认已停 (没确认就不碰数据) → `journal-state` → 0: 没有 journal; 3: `restore`; 2: 不改数据 → 保持停止。摘要写明停着的容器实际是哪个镜像。这个函数里没有任何启动动作, 它自己的每一步出错都按「没做成」记, 不往外抛。
11. 第 1–8 步里的基础设施错误 (docker 报错、解析不了输出) 统一处理: 「部署前检查出错…正式容器和正式数据都没有动」, rc 1。同一个处理如果在标记文件已经写下之后被触发 (属意外), 说的是「动过正式容器之后出错…确认之前不要 docker start」。
12. 中断兜底 (`public-abort`, workflow 在失败 / 取消时调用): 先尽力结束还活着的编排进程 —— 真实运行时编排自成进程组, 兜底整组结束 (连同它起的 docker 子进程); pid 不合理、已被别的进程复用、或者就是兜底自己所在的组时不发信号。再看标记: 正式容器已被动过才停整个公开项目, 停完隔几秒复查, 又起来了就再停 (最多三轮); 不碰数据。

临时容器: 由解析后的 compose 模型按白名单取 `image / environment / mem_limit / healthcheck / command / entrypoint`, 只读挂载原样带上, `/app/data` 换成副本; 另一个 compose 项目 `sdtm-rag-public-accept`, 容器名 `sdtm-rag-public-accept-api`, `network_mode: none`, `restart: "no"`。公开 compose 里的 ports / networks / 别名 / 其他服务带不进来; 出现第二个可写挂载或非 bind 挂载时拒绝 (不知道如何隔离)。

答题 key 探测 (协调方 2026-11-28: 保留): 公开网络里的一次性容器 (只挂 env 文件, 只读; 按公开档解析配置; 受公开网络的隔离规则约束) 里用 `anthropic` SDK 调 `models.list(limit=1)`。依据官方文档 (`platform.claude.com/docs/en/api/models/list`: `GET /v1/models`; `…/api/errors`: 401 = `authentication_error`)。**该接口不产生 token, 按此推断不计费; 官方文档没有专门的计费条目; 它只验 key 是否有效, 验不了额度。**配置的答题模型 (默认 / 回退 / 内部组 / 全部可选模型) 里只要有一个是 `anthropic/…` 就探测; 一个都没有时不探测并告警。Anthropic 接口暂时不可用时这一项也不通过 (重试两次后), 公开部署失败、旧版继续对外 —— 协调方已接受这个代价。

### 3.3 各种失败后公开站的状态

| 失败点 | 正式容器 | 正式数据 | job |
|---|---|---|---|
| kb-sync 公开腿任何一步 (key、基线、入库、评测、kb-only、闸) | 不变 | 不变 (候选归档 `*_failed_*`) | 红 |
| 公开部署: 路径 / 镜像不一致、journal 残留 | 不变 | 不变 | 红 |
| 公开部署: 线上公开 chroma 里有 KB 以外的集合 (不管换不换数据、有没有候选) | **停止** (journal 有残留或判不出时: 不变) | 不变 | 红 |
| 公开部署: 缺过闸候选 (线上数据干净) | 不变 | 不变 | 绿 + 告警 |
| 镜像下限 / 公开网络子网 / 隔离核对不过 | 不变 (运行的继续对外) | 不变 | 红 |
| 临时验收不过 (含集合不纯) / 答题 key 探测不过 | 不变 (运行的继续对外) | 不变 | 红 |
| 换入前置核对不过 | 不变 (没有被停) | 不变 | 红 |
| 停机后换入被拒 / 失败 | 停止 (旧镜像) | 部署前状态 (必要时按 journal 退回) | 红 |
| 换入后起不来 / 复验不过 | 停止 (新镜像, **不要直接 start**) | 按 journal 退回旧数据 | 红 |
| 退回失败或 journal 判不出 | 停止 | journal 保留; 下次公开部署与 kb-sync 公开腿都 `journal_pending` | 红 |
| job 被取消 / 超时 | 动过才停 | 不碰 (journal 由下次预检拦) | — |

### 3.4 私有部署 job 的加固: 改前改后对照 (只做加固, 合法输入下行为不变)

改的是 `sdtm-rag.yml` 的 `deploy` job (私有站正在用)。相对基点 `9a8ad43`, 14 个步骤的名字和顺序不变, 4 个步骤有改动, 其余 10 个逐字未变; job 的 `if` / `outputs` / `timeout`、workflow 级 env 与触发条件都没有变 (测试 `test_private_deploy_job_changed_only_where_intended` 对照基点逐项核对)。

| 步骤 | 改之前 | 改之后 |
|---|---|---|
| 登录镜像仓库 (两个 job 各一处) | `-u "${{ gitea.actor }}"` | env `ACTOR: ${{ gitea.actor }}`, 脚本里 `-u "$ACTOR"` |
| 确定要部署的标签 | `[ -n "$TAG" ] \|\| TAG="${{ gitea.sha }}"`; `printf '%s' "$TAG" \| grep -Eqx '[0-9a-f]{40}' \|\| …` | env `SHA: ${{ gitea.sha }}`; `[ -n "$TAG" ] \|\| TAG="$SHA"`; `[[ "$TAG" =~ ^[0-9a-f]{40}$ ]] \|\| …` |
| 构建并推送 | 两处 `"$IMAGE:${{ steps.tag.outputs.tag }}"` | env `TAG: ${{ steps.tag.outputs.tag }}`, 脚本里 `"$IMAGE:$TAG"` |
| 部署 | 四处内联的 `${{ steps.tag.outputs.tag }}` | env 里加 `TAG` (原有三项不变), 脚本里 `$TAG`; 除了这个替换, 脚本逐字相同 |

为什么要改: `grep -x` 是**逐行**匹配 —— 多行输入里只要有一行是合法的提交号就放行, 多出来的行还会原样写进 `GITHUB_OUTPUT` (等于往后面的步骤注入任意的输出键); `${{ }}` 写在 `run:` 里是在交给 bash 之前按文本替换, 等于把一段字符串拼进命令。现在两个 workflow 的所有 `run:` 脚本里都没有 `${{ }}` (有测试钉住)。

**逐步对照 —— 两种合法输入** (`<提交号>` = 手动填的 40 位小写提交号; `<当前提交>` = 这次运行的 `gitea.sha`):

| 步骤 | 合法的 40 位提交号 (手动回滚) | 空值 (push, 或手动留空) | 改前改后 |
|---|---|---|---|
| 测试 | `inputs.tag != ''` → 跳过 | 执行 | 未改 |
| 登录镜像仓库 | 用户名 = 触发者 | 同左 | 值相同, 只是经 env 传入 |
| 确定要部署的标签 | 退出码 0; `GITHUB_OUTPUT` 写一行 `tag=<提交号>`; 打印 `部署标签：<提交号>` | 退出码 0; 写 `tag=<当前提交>`; 打印 `部署标签：<当前提交>` | 三样逐项相同 (下表前两行, 真实 bash 执行) |
| 构建并推送 | 跳过 | `docker build -t "$IMAGE:<当前提交>"` + `docker push` | 命令相同 |
| 记录当前线上镜像 / KB 数据对齐检查 | 用 `<提交号>` 的镜像 | 用 `<当前提交>` 的镜像 | 未改 (本来就经 env 用 `TAG`) |
| 部署 | `docker image inspect … "$IMAGE:<提交号>"`; 换数据时 `IMAGE_TAG=<提交号> docker compose … stop` 与 `deploy-swap --image "$IMAGE:<提交号>"`; `IMAGE_TAG=<提交号> docker compose … up -d` | 同左, 值是 `<当前提交>` | 命令相同 |
| 健康检查 / 新鲜度 / 收尾 / 两个退回步骤 / 退出登录 | — | — | 未改 |

**「确定要部署的标签」用真实 bash 分别执行改前与改后的脚本** (`p3_public_leg_tag_step_compare.py`; 每格是 退出码 / 写进 `GITHUB_OUTPUT` 的各行 / 打印的内容):

| 输入 | 改之前 | 改之后 | |
|---|---|---|---|
| 合法的 40 位提交号 | 0 / `['tag=<提交号>']` / `部署标签：<提交号>` | 0 / `['tag=<提交号>']` / `部署标签：<提交号>` | 相同 |
| 空值 | 0 / `['tag=<当前提交>']` / `部署标签：<当前提交>` | 0 / `['tag=<当前提交>']` / `部署标签：<当前提交>` | 相同 |
| 提交号 + 换行 + `tag=evil` | 0 / `['tag=<提交号>', 'tag=evil']` / 放行 | 1 / `[]` / `标签必须是 40 位小写 commit SHA` | **不同 (这就是要堵的洞)** |
| 提交号 + 结尾换行 | 0 / `['tag=<提交号>', '']` / 放行 | 1 / `[]` / 被拒 | **不同** (手动粘贴带了换行时, 以前能部署, 现在被拒) |
| 前导空格 / 结尾空格 / 大写 / 39 位 / 41 位 / 分支名 | 1 / `[]` / 被拒 | 1 / `[]` / 被拒 | 相同 |

测试 (都由真实 bash 执行 workflow 里的脚本): 19 种不合法输入 (多行 3 种、首尾换行、首尾空白与制表符、回车、大写与混合大小写、39 / 41 / 7 位、非十六进制、分支名、带命令替换、带引号分号、只有空白) 全部被拒且 `GITHUB_OUTPUT` 为空; 两种合法输入新旧逐项相同; 另有一条对照测试证明旧写法确实会被多行输入绕过。
没有采纳的建议: 给 job 加 `defaults.run.shell: bash` —— 显式指定 shell 可能改变 runner 调用 bash 的参数 (多一个 `pipefail`), 而这个 job 里有 `ip route | awk '… exit'` 这类依赖管道前半段可以提前结束的写法, 属于「合法输入下行为可能变」, 不在只做加固的范围内。runner 用的是 bash 的依据: 线上一直在跑的 kb-sync 用了 `${FP:0:12}` 这种 bash 才有的写法。

## 4. 验证 (全部可复跑; 都在本机, 不碰虚拟机)

```bash
git submodule update --init --depth 1 && uv sync --extra dev --frozen   # 本工作区自己的 venv (不要软链主仓的, 见 §7 第 9 条)
T="tests/test_kbsync.py tests/test_kbsync_public.py tests/test_kbsync_deploy_public.py tests/test_workflow_conditions.py tests/test_deploy_public_compose.py"
.venv/bin/python -m pytest $T -q -o addopts=""                                   # 相关 5 个文件
.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs                     # CI 同款 (本机无 data/study 时)
.venv/bin/python .work/10_split_and_public/evidence/checkpoints/p3_public_leg_mutations.py   # 变异
.venv/bin/python .work/10_split_and_public/evidence/checkpoints/p3_public_leg_dryrun.py      # 替身数据根实跑
.venv/bin/python .work/10_split_and_public/evidence/checkpoints/p3_public_leg_key_probe.py   # 两段 key 探测真跑
.venv/bin/python .work/10_split_and_public/evidence/checkpoints/p3_public_leg_if_tables.py   # 生成 if 真值表
.venv/bin/python .work/10_split_and_public/evidence/checkpoints/p3_public_leg_tag_step_compare.py   # 私有部署的标签步骤: 改前改后对照
for f in kb-sync sdtm-rag; do sed 's/gitea\./github./g' .gitea/workflows/$f.yml | actionlint -; done   # 静态检查 (含 shellcheck)
```

### 4.1 结果 (最终代码上的实测)
| 项 | 结果 |
|---|---|
| 相关 5 个测试文件 | **464 passed, 1 skipped** (test_kbsync 44 / test_kbsync_public 89 / test_kbsync_deploy_public 169 + 1 skip / test_workflow_conditions 155 / test_deploy_public_compose 7)。那 1 个 skip 是「用真实隔离探测脚本再跑一遍」, 脚本在隧道分支上, 合并后生效 |
| CI 同款全量 (`-m "not slow"`), 最终代码 | **3355 passed, 57 skipped, 0 failed**。用的是本工作区自己的 venv (`uv sync`) 和本工作区的索引副本 (`data/chroma` 从主仓复制一份), 没有 `data/study`; 57 个 skip: 52 个 `local_data` (本机没有研究数据)、2 个要 playwright、1 个研究数据不在、1 个真实隔离探测脚本、1 个其他。运行前后用文件时间核对: **主仓 `data/` 下 0 个文件变化** |
| 变异 (`p3_public_leg_mutations.py`) | **149 条全部被抓**。在提交 `6bb4268` 上整份运行 145 条: 142 条被抓, 2 条漏网 (K6、C6), 1 条因清单里的片段不再唯一被跳过 (D14)。漏网的两条都是本轮新行为让旧测试失去了分辨力, 补了测试 (kb-only 前置核对的两种「相等比较会放行」的情形; 验收脚本用替身 `urlopen` 数实际请求数并覆盖各分支); D14 拆成两条。这 3 条连同新加的 4 条单独复跑, 7 / 7 被抓。整份运行之后只加了测试、没有改代码, 其余 142 条的结论不受影响。分布: kb-only 7、路径 6、基线与 key 6、数据根边界 4、临时容器隔离 6、验收项 9、状态机 16、红线停站 11、审查后补的守卫 35、网络预检 / 隔离核对 / 一次性容器 16、workflow 26、私有部署 job 的标签步骤 7 |
| 替身数据根实跑 (`p3_public_leg_dryrun.py`) | **20 个场景全部与预期一致** (§4.2) |
| actionlint + shellcheck (把 `gitea.` 换成 `github.` 后) | kb-sync.yml 0 条; sdtm-rag.yml 只有 1 条 SC2034, 在私有 `deploy` job 的健康检查循环里, 是原有的 |
| workflow 里的 shell 由真实 bash 执行 (不是用 Python 模拟) | 私有部署的标签步骤: 19 种不合法输入全拒、2 种合法输入与改之前逐项相同、对照组证明旧写法会被多行输入绕过 (§3.4); 另 6 处 `[[ … =~ … ]]` 共 41 个取值; 镜像下限那两行 7 种情形 |
| 容器里跑的脚本本身 | embedding key 检查、答题 key 探测、验收脚本 (档位 / 内部接口) 都有执行同一段源码的测试; key 探测另用真实 key 与无效 key 各跑过一次 (本机开发用的 key, 不是公开站的) |
| 用隧道分支上的真实 `isolation_probe.py` 跑 `isolation_check` | 5 种情形 (正常 / 隔离侧连得上内网 / 对照侧连不上 / 源地址不在网段 / 外网不通) 的结论分别是 通过 / 退出码 1 / 2 / 2 / 1, 与预期一致 (探测容器由假 docker 代答, judge 是真的) |

已知的等价变异 (没有放进清单): `deploy-swap --kb-only` 里「线上有非 KB 集合」这一项单独去掉时, 紧接着的「线上 == 换入源」比较仍会拒绝 (换入源此时必须为空), 所以它由别处负责。

### 4.2 替身数据根实跑 (`p3_public_leg_dryrun.py`)
临时目录里按生产布局搭私有根 (带 study 集合与 `study/`) 和公开根 (KB + `quota.sqlite`), 每一步都经 `kbsync.py` 的命令行入口; 文件系统子命令真跑, docker / compose 是带容器状态的假实现。每个场景结束时核对: 私有根逐字节未变、公开根里没有私有内容、没有任何挂载碰到私有根、临时容器与副本已清、不变量违例为空。

| 场景 | 结果 |
|---|---|
| A1 整条公开腿 (公开容器原本停止): 检测 → key → 基线 (取公开容器镜像) → 建候选 → kb-only → 过闸 → 部署换入 | 部署 rc 0; 正式容器停止 / 新镜像; 数据新; 无 journal; 启动 0 次; `quota.sqlite` 未动 |
| A2 公开容器原本运行: 临时验收 → 停 → 换入 → 起 → 复验 → 收尾 | rc 0; 运行 / 新镜像; 数据新; 启动 1 次 |
| B1 候选混入非 KB 集合 | candidate rc 1, 归档原因 `kb_only_violation`; 之后部署只告警跳过; 公开站不变 |
| B2 闸不过 (回退 2 题) | candidate rc 1, verdict FAIL 归档; 公开站不变; 私有根的检测不受影响 |
| B3 embedding key 无效 | key-check rc 1 (`key_invalid`); 没有留下候选 |
| B4 没有配对的基线镜像 | baseline-image rc 1; 没有建候选 |
| B5 数据根指到私有根 | paths-check rc 1; 没有任何挂载 |
| C1 临时验收不过 (索引不新鲜) | rc 1; 正式容器运行 / 旧镜像; 数据逐字节未变 |
| C2 答题 key 无效 | rc 1; 正式容器不动; 探测排在临时验收通过之后, 接在公开网络里 |
| C4 公开网络还没有重建 (子网不是 compose 写定的; 这正是部署机现在的状态: `172.18.0.0/16`) | rc 1; 网络预检拦下; 没有起临时容器; 数据逐字节未变 |
| C5 公开网络里的容器连得上内网 (隔离规则没装或失效) | rc 1; 隔离核对拦下; 没有起临时容器、没有做 key 探测 |
| C3 线上公开数据里发现非 KB 集合 (这次要换数据) | rc 1; 先看 journal → **停站**; 不换入, 数据逐字节未变; 启动 0 次 |
| C6 线上公开数据里发现非 KB 集合 (这次不换数据) | rc 1; 停站; 数据未改; 失败信息里有正当新增时要改的地方 |
| C8 公开数据落后且没有候选 (本来只告警跳过), 但线上数据里有非 KB 集合 | rc 1; 照样停站 |
| C7 发现非 KB 集合但 journal 状态判不出 | rc 1; 保持现状, 没有停站 |
| D1 换入后复验不过 | rc 1; 停止 / 新镜像; 数据已退回旧版; 无 journal; 候选还在; 启动只有部署那 1 次 |
| D2 换入中途出错 (journal 残留) | rc 1; 按 journal 退回; 停止; 启动 0 次 |
| D3 原本停止 + 换入后重建容器失败 | rc 1; 数据退回; 仍停止; 启动 0 次 |
| D4 退回失败 (journal 保留) | 之后再部署 rc 1、kb-sync 检测 `journal_pending`; 人工 `restore` 后数据旧 / 候选 gated |
| D5 job 被取消的兜底 | 没动过不停; 动过只停机, 数据未改 |

### 4.3 用真实 docker / compose 做过的只读核对 (部署机, 没有创建任何东西)
- `docker compose -f - config --format json` (stdin 喂 compose 文件): 取得两份真实输出作 fixture。
- 生成的临时验收项目文件经 `docker compose -p sdtm-rag-public-accept -f - config` 校验通过 (Compose v5.7.0): 渲染出 `network_mode: none`、`restart: 'no'`、无 networks / ports、数据挂载指向副本。
- `docker compose up --help` 有 `--no-start`; `docker inspect --type container` 对不存在的容器返回 rc 1 + `No such container`; `docker network inspect sdtm-rag-public` 现在的子网是 `172.18.0.0/16` (还没有重建), 对不存在的网络返回 rc 1; 公开容器 `{{.State.Running}}=false`、镜像 `099c2c9`、公开 stamp `f863e454…`、4329 条 (与协调方看到的一致)。
- 公开 env 文件的属主与权限位 (只看元数据, 没有读内容): `0:0 600`; docker 不是 rootless, 镜像没有指定运行用户 (容器里是 uid 0) —— 去掉全部 capability 之后, 探测容器里的 root 仍是这个文件的属主, 按属主权限位可读 (第四轮审查的疑问; 真实效果仍要到演练时看)。
- 隧道分支改过的 `compose.public.yml` 同样只读渲染了一遍 (存为 `compose_config_public_tunnel.json`): 网络写定 `10.201.8.0/24`, api 服务只接这一个网络, 环境变量三个。
- 两段 key 探测脚本在本机真跑 (本机开发用 key, 不是公开站的 key): 真实 key → ok; 无效 key → `key_invalid` / 401; 输出里没有 key 片段。

### 4.4 `if` 条件真值表
全表 (两个 workflow 每个带 `if` 的 job / step, 外加 `deploy_public` 里隐含 `success()` 的主步骤) 在 `p3_public_leg_if_tables.md`, 由测试里的 `TABLE` 生成, 每一行都是一个通过的测试。另有一条测试保证「新加一个带 `if` 的 step 而表里没有」会变红。要点:

| 条件 | 何时执行 |
|---|---|
| kb-sync `public` job | main + 变量开; 私有腿成功 / 失败 / 取消都执行。变量没开或不是 main → 不执行 |
| kb-sync `public` 的建候选各步 | 检测结果 `changed` 且前面步骤都成功 (key 检查或基线失败 → 不入库) |
| kb-sync 删镜像 | 两条腿相同: 自己建了镜像 (`changed`) 就删, 成功 / 失败 / 取消都删 |
| sdtm-rag `deploy_public` job | main + 变量开 + 不是「只构建」+ 私有部署成功。私有部署失败或取消 → 不执行 |
| 中断兜底 `public-abort` | 前面失败或被取消 (进了以后看标记文件决定停不停) |
| 清理 `accept-down` | 预检成功后, 无论成功 / 失败 / 取消 |

⚠ 求值器是按 GitHub Actions 的约定写的语义模型 (隐含 `success()`、字符串比较不分大小写、不存在的属性是空串), 不是 act_runner 本身。

## 5. 合并后的演练方案 (不执行; 开变量与每一步演练都要主人另行同意)

隧道那条线的演练方案是 `docs/plans/P3_4_tunnel_drill.md` (在它的分支上; 下面写「隧道第 N 步」指的是它)。网络重建、隔离规则、连接器、隧道验收都以它为准, 这里不另写一套; 这里只写这条线自己的步骤, 以及两边怎么穿插。

**合并注意**
- 先 squash 合并隧道那条线, 再合这条 (或同一次推送里一起进 main; §0 第 4 条)。合并后把 `compose_config_public.json` 换成新的解析结果 (§6 第 2 条), 并跑一遍相关测试 —— 其中 `test_isolation_check_with_the_real_probe_script` 在合并前是 skip, 合并后会用真脚本跑。
- `sdtm-rag.yml` 在部署路径过滤内 (隧道那条线的 `server/**`、`deploy/container/**` 也在), 推到 main 不带 `[skip ci]` 就会触发一次私有部署 (私有 job 没改, 指纹一致不换数据, 但会重建镜像并重部署)。`deploy/kbsync/**`、`kb-sync.yml`、`tests/**` 不在过滤内; `kbsync.py` 从 checkout 运行, 合并后下一次 workflow 运行即生效。
- 公开部署只接受**隧道那条线合并之后构建的镜像** (镜像下限)。现在线上的 `f798709` 不满足, 不能拿它的 tag 去做第一次公开部署。
- 隧道那条线必须以 **squash** 方式合并 (它的镜像下限标记只在 squash 之后的那个提交起才有)。

| 阶段 | 做什么 | 应该看到 | 回退 |
|---|---|---|---|
| A 变量未开 (合并后的默认状态) | 等凌晨的 kb-sync, 或经同意后手动派发一次 (ref 留空) | kb-sync 这次运行有两个 job: `private` 成功 (检测 `same`, no-op), `public` **skipped**。下一次 `sdtm-rag` 部署里 `deploy_public` 仍是 skipped。公开容器、公开数据根都不变 | 若 `public` 没有被跳过 (变量没开却跑了): 立即 `git revert` 这条线的 workflow 与 kbsync 提交 (带 `[skip ci]`) |
| B 开变量之前 | 隧道第 1–4 步: 只读记录现状 → **重建公开网络** → 装隔离规则 (先红后绿) → 核对地址段。隧道第 3 步的对照侧是虚拟机本机; 这里的部署预检用的是默认网桥上的容器, 所以在第 3 步里**用容器对照也跑一遍** (`docker run --rm -i --network bridge --entrypoint python <镜像> - probe <内网目标>`), 容器连不上的内网目标要从清单里去掉 —— 否则部署预检会判无结论而拒绝。清单有变就把 `sdtm-rag.yml` 的 `ISOLATION_LAN` 同步改掉 | 见隧道方案。做完后公开网络的子网是 `10.201.8.0/24`, 隔离判定 PASS | 见隧道方案的回退总表 |
| C 开变量后第一次 kb-sync (补建公开候选) | 先只读核对: 公开容器的状态与镜像 (隧道第 2 步重建网络时容器可能被重建过; 以当时的实际情况为准) / 公开 stamp `f863e454…` / 虚拟机可用内存。然后手动派发 kb-sync | `private`: `same`, 末尾「删除候选镜像」被跳过。`public`: 路径一致 → 检测 `changed` → 构建镜像 → 「embedding key 检查通过」(**公开站 OpenAI key 第一次被真正使用**) → 基线镜像: 公开容器的镜像与公开 stamp 配对就用它 (现在是 `…:099c2c9…`, 指纹 `f863e454…`), 否则回落到私有线上镜像, 都不配对则失败并提示用 `public_baseline_image` → 入库 (约 95 秒, 约 $0.05, 预期 4333 条) → 「kb-only：sdtm_kb_v1 在，非 KB 集合 0 个」→ gate。预期基线满分 138 (q38、q126, 3.3 的记录), 候选按私有站同一 KB 的结果也是 138 / avg 0.9917 → PASS。之后公开数据根多出 `chroma_cand_477bac3ce565` / `meta_cand_477bac3ce565`, 线上 chroma 不变, 公开容器状态不变 | 不想要候选: 把两个 `*_cand_*` 目录改名移走 (不删)。停用公开腿: 关变量。key 失败: job 红, 日志有类别, 公开站不变 |
| D 第一次公开部署 = 隧道第 5 步 (换入; 容器保持停止; **做完后按表下的核对清单逐条看**) | 用合并后的镜像部署: 合并提交本身触发的那次构建 (或手动派发 `sdtm-rag`, `tag` 留空 / 填该镜像的 SHA, `deploy` 勾选) | `deploy_public`: 预检 (镜像, 含镜像下限) → 路径一致 → KB 对齐 `swap` (换入源 `chroma_cand_477bac3ce565`) → 部署前状态 → 「公开网络 … 的子网是 10.201.8.0/24，与 compose 一致」→ 隔离核对的判定行 → 「网络隔离核对通过」→ 临时容器启动 → 验收通过并清理 → 「答题 key 探测通过」(**公开站 Anthropic key 第一次被验证, 只验有效性**) → 换入 → `up --no-start` → 「成功：镜像已更新…**公开容器保持停止**…`docker start sdtm-rag-public-api`」 | 公开站此时没有对外 (停止), 最稳的回退是保持停止并关变量。要把数据退回旧版: 公开容器停止状态下, 在部署机上 `kbsync.py --via <镜像> predeploy-check / swap --target-fp <旧指纹> … / finish` 换回 `chroma_prev_*`, 并 `IMAGE_TAG=<旧 tag> docker compose -f compose.public.yml up --no-start api`。⚠ 不能靠给 `sdtm-rag` 填旧 tag 来只回滚公开站 —— 同一个 tag 也作用于私有站, 而且旧镜像过不了镜像下限 |
| E 启动公开容器 (隧道第 5 步的后半) | 在部署机上 `docker start sdtm-rag-public-api`。⚠ 隧道方案第 5 步写的是「部署后公开站运行中」; 按 Q1 的裁定, 部署不会启动一个原本停着的容器, 所以这里要多这一步 | healthy; `/api/info` tier = public; `check_index_freshness` OK; 再做隧道第 5 步列的只读核对 (网络、可信代理、HSTS、cookie)。新镜像 + 新数据第一次在正式容器里启动 (此前只在临时容器里用副本验过) | `docker stop sdtm-rag-public-api` |
| F 隧道第 6–9 步 | 连接器、访问策略与路由、隧道验收、放开 | 见隧道方案。真答题一次才算 Anthropic key 的额度被验证 | 见隧道方案 |
| G 运行中的后续部署 | 之后任意一次部署 | `deploy_public`: 网络预检 → KB 对齐 `same` → 临时验收 → key 探测 → `up -d api` 换新镜像 → 复验 → 「成功：公开实例已换成镜像…并通过复验」。下一次 KB 发版走完整路径: 两条腿各建候选 → 「KB 更新」推送 → 私有换入 + 公开「停 → 换 → 起 → 复验」。公开实例被重建后连接器是否无需重启就能连上: 隧道第 8 步验 | 失败时编排自己停机并退数据 (§3.3); 恢复 = 排查 → 重新运行 `sdtm-rag` → `docker start` |

阶段 D 之后在部署机上的只读核对 (都不改任何东西):

```sh
docker inspect -f '{{.State.Status}} {{.State.Running}} {{.Config.Image}}' sdtm-rag-public-api   # 期望: created 或 exited / false / 新 tag (up --no-start 重建且没有启动)
docker ps -a --filter name=sdtm-rag-public-accept --format '{{.Names}}'                          # 期望: 空 (临时容器已清)
docker network ls | grep -i accept                                                               # 期望: 空 (network_mode none 不建网络)
ls /Volumes/DevSSD/deploy-data/sdtm-rag-public/                                                  # 期望: 只有 data (没有 kbsync_accept_*)
ls /Volumes/DevSSD/deploy-data/sdtm-rag-public/data                                              # 期望: chroma meta quota.sqlite chroma_prev_f863e45445a6_<ts> meta_prev_…; 没有 kbsync_swap.json / kbsync_guard_*
grep kb_fingerprint /Volumes/DevSSD/deploy-data/sdtm-rag-public/data/chroma/ingested_at_commit.txt   # 期望: 477bac3ce565…
docker inspect -f '{{.Config.Image}} {{.State.Status}} {{.State.StartedAt}}' sdtm-rag-api         # 私有站: 镜像与启动时间没有因公开部署而变
```
另看 run 日志: 「答题 key 探测通过」这一行是否出现 —— 探测容器去掉了全部 capability, 它要能读到只读挂载的 env 文件 (静态依据见 §4.3; 读不到时表现为 `setup_error` / `no_result`, 部署失败); 「临时容器 … 已启动」到「临时容器验收通过」之间用了多久 (没有网络的容器启动是否正常); 「换入」一段有没有 `readonly` 相关报错 (嵌套只读挂载是否生效); 隔离核对的判定行是不是 PASS 且隔离侧源地址在 `10.201.8.0/24` 里; 答题 key 探测在隔离规则下能连上 Anthropic。
重启虚拟机或 docker 守护进程之后再看一次第一条命令: 从未启动过的容器在 `restart: unless-stopped` 下应当仍然不在运行。

## 6. 集成备注 (给协调方 / 隧道那个会话)

1. **我没有改 `compose.public.yml`**, 也不需要它改; 没有新增任何 compose 文件, 没有重复定义公开网络。冻结的名字我只读取: 容器名、镜像、公开网络名与子网都取自 `docker compose config` 的解析结果; 数据根与 env 文件在两个 workflow 的 env 里各写了一次, 由 `paths-check` 在运行时、由测试在静态上与 compose 对齐。
2. **合并隧道那条线之后必须做的一步** (fixture 对应隧道分支 `9d21808`): 它改了 `compose.public.yml` (五个环境变量、网络定义), `tests/fixtures/kbsync/compose_config_public.json` 要换成新的解析结果, 否则 `test_compose_fixtures_match_the_compose_files` 变红, CI 的测试步骤在部署之前, 会挡住私有部署。我已经用它分支上的文件在部署机上只读采好了一份: `tests/fixtures/kbsync/compose_config_public_tunnel.json`。合并时执行 `cp tests/fixtures/kbsync/compose_config_public_tunnel.json tests/fixtures/kbsync/compose_config_public.json` 再跑一遍相关测试即可 (重新采集的命令在该测试的 docstring 里)。之后 `compose.public.yml` 再改 api 服务的挂载 / 环境变量 / 容器名 / 网络, 同样要重采。
3. **这条线对隧道分支的三处依赖** (本分支上都还不存在, 所以本分支单独合并后公开部署必然失败, 失败时什么都不动):
   - `deploy/public-net/isolation_probe.py` 的命令行: `probe --lan H:P … --egress H:P …` 往标准输出打一行 JSON; `judge --isolated F --control F --isolated-net CIDR` 退出码 0 = 通过。它改接口要同步改 `kbsync.isolation_check`。
   - `deploy/public-net/image_floor_check.py`: 合格时退出码 0 且标准输出恰好是 `image-floor: ok`。workflow 里那两行 shell 是照它的文件头抄的, 有测试钉住; 它改输出就要同步改。
   - `compose.public.yml` 里公开网络写定的子网 (`ipam.config[0].subnet`), 以及 api 服务只接这一个网络。
   隔离核对的目标清单在 `sdtm-rag.yml` 的 `ISOLATION_LAN` / `ISOLATION_EGRESS`, 抄自隧道第 3 步; 演练时清单有变要同步。
4. **对方改了 `compose.public.yml` 的其他情况**:
   - 给 api 服务加了**可写**挂载 (除 `/app/data`) 或非 bind 挂载 → `accept_spec` 会拒绝, 公开部署失败 (正式容器不动)。只读挂载会原样带进临时容器 (源不得指向私有挂载源, 路径检查会拦)。
   - 加了 `command` / `entrypoint` → 临时容器会带上; 加了 `ports` / 其他键 → 临时容器不带, 日志里会列出被忽略的键名。`networks` 段永远不带。
   - 环境变量整份照抄 (现在是 6 个键, 含全局限流的三个)。限流再收紧的话要对照验收的请求数: 每个容器 2 个, 有测试用 fixture 里的突发值核对 4 倍余量。
   - 在同一个文件里加第二个服务 → 部署时的起 / 停都只针对 `api` 服务, 不会起停它; 只有失败停机与中断兜底的 `compose stop` 是整个公开项目。隧道那条线的测试已经钉住「服务只有 api」, 连接器在另一个 compose 文件里, 互不影响。
5. **隧道方案第 5 步需要补一句**: 部署成功后公开容器是「已更新、保持停止」(Q1 的裁定), 要人工 `docker start sdtm-rag-public-api` 之后才是它写的「运行中, 没有入口」。连接器的起停不在本实现里。
6. **主仓共享文件我没有动**: `.work/10_split_and_public/_progress.json` (`decisions_p3.open`、2026-11-28 的代裁各条)、`PLAN.md` 1.9 行 (验收拆为私有正例 + 公开正例)、`docs/PROGRESS.md`、`CLAUDE.md` 的「KB 更新」路由词 (现在只写了私有流程) —— 两个会话都可能改, 留给协调方合并时统一更新。
7. *(这一条上一轮是「没改, 只上报」; 协调方答复后本轮已修, 见 §3.4。以下保留原文作记录。)* **继承代码里的一处输入校验问题 (安全审查发现)**: 私有 `deploy` job 的「确定要部署的标签」用 `grep -Eqx` 校验手动输入的 tag (逐行匹配, 多行输入可绕过), 同一个 job 里还有几处把 `${{ steps.tag.outputs.tag }}` 直接写进 `run:`。能不能被利用取决于 Gitea 的派发接口是否接受带换行的输入、以及重复的 output 键取哪一个 (没有验证), 而且需要有派发 workflow 的权限。本任务不动私有部署 job, 所以只上报: 建议另开一个小改动, 把这一处改成整串匹配 (`[[ "$TAG" =~ ^[0-9a-f]{40}$ ]]`), 并把内联的表达式改成经 `env:` 传入。公开 job 已经用整串匹配重新校验 tag。
8. 安全审查的两条后续建议没有做: ① 在每个数据根里放一个身份标记文件 (内容 `public` / `private`), 公开腿在任何写操作之前先读它 —— 能防「公开根其实是指向私有根的符号链接」这类字面路径比不出来的情况; 需要改部署机上的数据根。② `--expect-source` 只核对换入目录的名字, 不核对内容有没有在验收之后被就地重建 —— 靠两个 workflow 共用的并发组保证不会同时有人改 (并发组是否真的生效见 §7)。
9. 本工作区: `git submodule update --init`; 第一轮曾软链主仓的 `.venv` / `.env` / `data/study` (已删); 本轮改用自己的 venv (`uv sync`) 和索引副本 (`data/chroma`, gitignored, 交付前删除); 提交时为了过红线闸临时软链 `data/study` (闸要读研究目录的清单), 提交完即删。都没有进提交。
10. **`deploy/README.md` 的合并** (协调方核对: 两条分支只在这个文件上有重叠): 这条线对它的改动是纯新增 (相对基点 0 行删除、0 行修改), 位置只有一处 —— 「## KB 同步 (kb-sync)」一节的最后, 紧接原有的第 3 条「人工排查：…」之后, 新增小节「### 公开实例（P3；仓库变量 `SDTM_RAG_PUBLIC_DEPLOY=true` 时才启用，默认关）」, 到「## 回滚」之前为止 (小节内三条: kb-sync 公开腿 / 公开部署 / 人工兜底)。「组成」「发版」「回滚」「启动失败常见原因」「其他」各节没有动。冲突时两边的新增都保留; 如果隧道那条线也在「KB 同步」一节末尾加了内容, 两段先后放置即可, 互不引用。

## 7. 没能在合并前验证的事项

1. **act_runner / Gitea 的真实行为**: job 级 `always()` (私有腿失败后公开腿是否照跑)、job 级 `vars.*`、`needs` 为 skipped / failure 时的判定、`steps.<id>.outcome`、`timeout-minutes` 是否生效、`concurrency:` 是否真的让两个 workflow 排队、job 被取消后 `failure() || cancelled()` 的步骤是否执行、取消时正在跑的步骤进程是否被结束、每个步骤的进程组与 PID 命名空间是什么样 (决定中断兜底是整组结束还是只结束一个进程)、派发接口是否接受带换行的输入。**编排在真实运行时自成一个进程组**: 如果 runner 是靠给步骤的进程组发信号来取消的, 编排会收不到, 只能靠兜底步骤来结束它 —— 建议演练时实际取消一次公开部署, 看兜底步骤的输出。`deploy_public` 与 kb-sync 的 `public` job 在这台 Gitea 上从未真正执行过。失败方向: 公开腿被多跳过 (公开站保持旧状态), 或镜像多留一份。
2. **没有网络的临时容器能否起到 healthy**: 应用启动 (含 litellm 导入、BM25 建索引) 在 `network_mode: none` 下是否正常、多久。代码上 lifespan 没有出站调用, 但没有用真实镜像跑过。起不来时的表现: 临时验收不过, 正式容器不动。阶段 D 是第一次真实验证。
3. **真实 docker 行为**: `compose up --no-start api` 对「已存在、已停止、镜像不同」的容器是否如预期重建且不启动; 这样建出来、从未启动过的容器在 `restart: unless-stopped` 下, 守护进程或虚拟机重启后是否仍不启动; `docker inspect --type container` 对不存在的容器的报错文案 (`No such container`, 已在部署机上只读确认) 在 docker 升级后是否不变 (变了会表现为部署失败, 不会放行); 嵌套挂载 (上一级可写 + 数据根只读) 在这台虚拟机的文件共享上是否生效; 在容器运行时复制线上 chroma 得到的副本是否总能打开 (打不开时表现为验收不过, 可重试); `compose stop api` / `up -d api` 在有 `depends_on` 的多服务项目里会不会连带起停别的服务 (现在只有一个服务, 不涉及)。
4. **隔离核对与网络预检**: `isolation_probe.py` 与 `image_floor_check.py` 是隧道分支上的文件。本分支的测试用的是判定照搬真脚本的替身; 另在本机用对方分支上的真 `isolation_probe.py` 跑过 5 种情形 (正常 / 隔离侧连得上内网 / 对照侧连不上 / 源地址不在网段 / 外网不通), 结果与预期一致。真实环境里默认网桥上的对照容器是否连得上那批内网目标、去掉全部 capability 的容器能否正常解析域名并连上 Anthropic、答题 key 探测在隔离规则下是否通, 都要到阶段 B / D 才知道。
5. **时间**: `deploy_public` 的 `timeout-minutes` 从 20 提到 30 是估计值 (两次最长 180 秒的健康等待 + 三次副本复制 + 四次读集合 + 隔离探测每个内网目标最长 4 秒), 没有实测。
6. **公开站的两个新 key**: OpenAI key 要到 kb-sync 公开腿第一次运行才第一次真正使用 (key-check); Anthropic key 的探测只验有效性, **额度 / 月上限够不够无法免费验证**, 要到第一次真答题才知道。我没有读过公开 env 文件的内容。
7. **`$GITHUB_STEP_SUMMARY`**: 编排会往里写摘要; Gitea 界面是否展示没有验证 (日志里一定有同样的内容)。
8. **公开腿的闸结果与 docker 层缓存**: 预期基线 138 / 候选 138 是按 3.3 的记录和私有站同一 KB 的结果推的, 没有在公开数据根上跑过; 两条腿都 `changed` 时第二次 build 命中缓存是预期, 没有实测。
9. **第一轮会话可能碰过主仓的 `data/chroma` (已上报, 协调方已知; 本轮已改做法)**: 本轮用本工作区自己的 venv 和索引副本跑全量, 运行前后用文件时间核对, 主仓 `data/` 下 0 个文件变化。以下是第一轮的记录: 复用的 `.venv` 是主仓的, 里面有一个把主仓路径加进 `sys.path` 的可编辑安装; 全量 pytest 里有的测试会在别的目录起子进程, 子进程里的 `server` 包因此解析到主仓, 打开了主仓的 chroma (chromadb 一打开就会改写 sqlite 和索引段文件的时间)。依据: 主仓 `data/chroma` 里的文件修改时间落在我第三次全量 pytest 的起止时刻 (相隔 58 秒, 那次运行耗时 57 秒)。**内容完好**: 用 sqlite 只读方式核对, `sdtm_kb_v1` 4333 条 (与 stamp 一致), 两个 study 集合都在。主仓 `data/study` 在本会话期间没有任何文件变化。发现之后没有再跑全量 pytest。核对命令:
   ```sh
   REF=<主仓>/.git/worktrees/public-kb-leg/commondir      # 本工作区的创建时刻
   find <主仓>/data/study -newer $REF | wc -l              # 0
   find <主仓>/data/chroma -newer $REF | head              # 有: 只是修改时间
   sqlite3 -readonly "file:<主仓>/data/chroma/chroma.sqlite3?mode=ro&immutable=1" \
     "select c.name, count(e.id) from collections c join segments s on s.collection=c.id join embeddings e on e.segment_id=s.id group by c.name;"
   ```
   建议: 以后子工作区跑全量 pytest 用自己的 venv (`uv sync`), 不要软链主仓的。

## 8. 已知的尖角 (不是缺陷, 但使用者要知道)
- 换入后失败停机时, 停着的正式容器是**没通过的新镜像**, 数据已退回旧版。直接 `docker start` 会得到「新镜像 + 旧数据」。摘要按容器的实际镜像写明是哪种情况 (已换成新镜像时写「不要直接 docker start」); 恢复路径是排查 → 重新运行 `sdtm-rag` → `docker start`。D2 的裁定是不自动退回旧镜像, 所以没有加「把容器改回旧镜像」的动作。
- 公开站不能单独回滚镜像: `deploy_public` 用的 tag 就是私有部署的 tag; 而且隧道这一步之前的镜像过不了镜像下限。
- 人工指定基线镜像时守卫照旧: 本机已经没有任何配对镜像时 (旧镜像被清掉), 只能走 README 里的人工兜底 (直接重建公开 chroma)。
- 临时验收用的是数据副本、没有网络: 「正式数据目录本身损坏」「需要出网才暴露的问题」要到正式容器复验或真实访问才会暴露。
- Anthropic 的接口或隔离核对的某个对照目标暂时不可用时, 公开部署会失败 (旧版继续对外)。
- 中断兜底结束编排进程是尽力而为: 已经发给 docker 守护进程的操作收不回来, 所以兜底在停机后会隔几秒复查、最多停三轮。
- 线上公开 chroma 里出现 KB 以外的集合会**自动停站** (协调方 2026-11-28 裁定)。这是故意偏严的: 将来正当新增一个 KB 集合, 第一次公开部署就会把公开站停掉, 要先改 `KB_COLLECTION` 再部署。它只在公开部署运行时检查 (不是常驻监控); 读不出集合时不算发现; journal 有残留或判不出时只失败不停站。
- 手动派发私有部署时, tag 末尾带换行以前能过、现在被拒 (§3.4)。

## 9. 审查 (规则 D)
三轮独立审查, 结论都是 **PASS-with-fixes**, 都没有 CRITICAL / HIGH。逐条意见与处置见 `p3_public_leg_impl_review.md`。

| 轮 | 审查者类型 | 审的是 | 分级 |
|---|---|---|---|
| 1 | `oh-my-claudecode:code-reviewer` | `0cbbc38` + 当时的工作区 | MEDIUM 4 / LOW 8 |
| 1 | `oh-my-claudecode:security-reviewer` | 同上 | MEDIUM 3 / LOW 7 |
| 2 (增量) | `oh-my-claudecode:security-reviewer` | 第一轮意见的修正 (`0cbbc38` 之后) | MEDIUM 1 / LOW 7 |
| 3 (窄范围) | `oh-my-claudecode:code-reviewer` | 第二轮意见的修正 + 协调方补充裁定的实现 (`e1b5765` 之后) | MEDIUM 1 / LOW 7 |
| 4 (窄范围) | `oh-my-claudecode:security-reviewer` | 第三轮意见的修正 + 私有部署 job 的加固 + 红线停站 | MEDIUM 2 / LOW 4 |

没有采纳或没有做的: 所有 `docker run` 加 `--pull never` (会改到私有腿; 改为基线一律按镜像 ID 使用); 私有 `deploy` job 的 tag 校验 (本任务不动私有部署 job, 已上报, §6 第 7 条); 数据根身份标记文件与换入源的内容核对 (§6 第 8 条); 编排自成进程组的取舍 (第三轮 Q2, §7 第 1 条)。
第四轮对私有部署 job 的结论: 逐步对照基点, 在「合法的 40 位小写提交号」和「空值」两种输入下, 14 个步骤拿到的值和执行的命令全部等价; 没有用了 `$TAG` 却没在 env 里定义的步骤, 没有同名变量被遮蔽。
**没有经过独立审查的部分**: ① 第四轮意见的修正本身 (红线检查提前到「缺候选就跳过」之前、读出结论后副本删不掉不丢结论、集合名按约定形态显示、失败信息补恢复路径、README 的清理命令); ② 第四轮之后为对齐隧道线最新约定做的三处小改动 (§0 第 7 条)。都有测试和变异钉住, 但写的人和验的人是同一个。
