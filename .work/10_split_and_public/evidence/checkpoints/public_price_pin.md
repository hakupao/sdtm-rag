# 公开档可选模型的价格固定进代码 (2026-11-28, 分支 `hakupao/public-price-pin`)

第一次公开部署 (run id 219) 在「临时容器验收」失败之后的修正。只在分支上做: **没有 push、没有合并、没有部署、没有动生产**。
失败本身的归档 (规则 B) 在 `../failures/p3_stageD_public_deploy_attempt_1.md`, 现场记录在 `p3_stageDE_first_public_deploy.md`; 本文件只写这次的复核、修法和验证。

## 1. 授权与裁定来源
- 协调方 (bot) 按主人 2026-11-27 的授权派的后续任务 (范围: 不 push、不打 tag、不合并、不部署、不碰生产)。
- 修法「把价格固定进代码」是**协调方受托代裁**的设计取舍, 不是主人裁定 (`_progress.json` 的 `decisions_2026_11_27_delegated.stage_d_failure_2026_11_28`)。
- 下面 §4 的取舍是**实现者 (本会话) 的判断**, 已交独立审查 (§8; 第 5、6 条是按审查意见加的); 协调方或主人可以改。
- 真实镜像里的一次性容器 (§7.4) 是协调方在派单里预先同意的 (同样的条件一共起了 3 次: 修之前、修之后、审查修正之后的最终文件)。合并和部署要等主人另行同意。

## 2. 根因复核 (先于动手; 逐条附命令)

| # | 上一个会话的说法 | 复核 | 结论 |
|---|---|---|---|
| 1 | 单轮预留额 = 60000 × 输入价 + 16000 × 输出价 | `server/quota.py` 的 `round_estimate_usd`: 提示词 = `quota_history_max_chars` (20000) + `PROMPT_OVERHEAD_TOKENS` (40000), 输出 = 该可选模型的 `max_output_tokens` (公开站配的 16000) | 一致 |
| 2 | 回退费率 5 / 25 美元每百万 token | `quota._DEFAULTS` 的 `quota_fallback_in_usd_per_mtok` / `quota_fallback_out_usd_per_mtok`; `_price` 在 `cost.estimate_cost` 给不出价时用它 | 一致 |
| 3 | 价格来源的顺序: 写死的表 → provider registry → litellm | `cost.estimate_cost`; `provider_registry.yaml` 里 `claude-haiku-5-5` 那一行没有 `price` 也没有 `price_ref`, 所以 registry 这一环给不出价 | 一致 |
| 4 | litellm 在被 import 时联网取在线价格表, 取不到就退回包内旧表 | `litellm/__init__.py`: `model_cost = get_model_cost_map(url=model_cost_map_url)`; `get_model_cost_map.py`: `httpx.get(url, timeout=5)`, 失败或校验不过 → 包内 `model_prices_and_context_window_backup.json`; 环境变量 `LITELLM_LOCAL_MODEL_COST_MAP=True` 时不联网直接用包内表。版本 1.88.6 (`uv.lock`) | 一致 |
| 5 | 包内旧表没有这个模型 → 0.70 美元; 有网 0.1 / 0.5 → 0.014 美元 | 本机两种条件各跑一次 (下面的命令): 包内表里 Claude 5.x 的五个模型一个都没有; 在线表里都有。真实镜像里的复现见 §7.4 | 一致 |

**与上一个会话不一致、或它没有提到的:**

1. **在线价格表对 Haiku 5.5 本身就是低估的。** 官方价按提示词长度分两档 (§3)。litellm 的在线表里有高档的数值, 但 1.88.6 的计价函数不用它: 15 万 token 的提示词算出来还是低档价 (输入 0.015 美元, 应为 0.075)。也就是说「有网时估出来 0.014 美元」只对不超过 10 万 token 的提示词成立; 超过的请求, 计量会少记到五分之一。公开站的自动续写轮会把前几轮的输出带进提示词, 能越过这条线。这次一并修掉了 (§4.2)。
2. **同一个依赖不只在 `claude-haiku-5-5` 上。** 修之前的固定表只有四行 (Sonnet 4.6 / Opus 4.7 / Haiku 4.5 / DeepSeek V4 Pro); 内置可选列表的四个模型和内部四档的默认模型 (`claude-sonnet-5-5`) 都不在表里。私有档不做成本自检所以没有暴露, 但没有网络时私有档的成本显示是「—」。
3. **启动路径上还有一处随在线价格表而变的行为**, 不在成本自检里: provider registry 的模型能力位 (§6 第 2 条)。

```sh
# 包内表 vs 在线表 (本机, litellm 1.88.6)
LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -c "import litellm; print([k for k in litellm.model_cost if 'claude-haiku-5-5' in k or 'claude-sonnet-5-5' in k])"   # []
.venv/bin/python -c "import litellm; print(litellm.model_cost['claude-haiku-5-5']['input_cost_per_token'], litellm.model_cost['claude-haiku-5-5']['input_cost_per_token_above_100k_tokens'])"   # 1e-07 5e-07
# litellm 不应用高档: 15 万 token 的提示词
.venv/bin/python -c "import litellm; print(litellm.cost_per_token(model='anthropic/claude-haiku-5-5', prompt_tokens=150000, completion_tokens=1000))"   # (0.015, 0.0005); 按官方价应为 (0.075, 0.0025)
```

## 3. 固定的价格、出处、查阅日期

查阅时间 2026-11-28 07:36Z (Anthropic) / 07:41Z (DeepSeek)。单位: 美元每百万 token。只固定输入和输出两项 —— 代码读用量只读 `prompt_tokens` / `completion_tokens`, 没有别的计价项 (缓存见 §6 第 5 条)。

| 模型 (表里的键) | 输入 | 输出 | 官方页上的原文 | 用在哪 |
|---|---|---|---|---|
| `claude-haiku-5-5` | 0.10 | 0.50 | `Claude Haiku 5.5 (for prompts up to 100,000 tokens)`: Base input `$0.10 / MTok`, Output `$0.50 / MTok` | **公开站唯一的可选模型**; 公开站的内部四档也配成它 |
| `claude-haiku-5-5` 提示词超过 100,000 token | 0.50 | 2.50 | `Claude Haiku 5.5 (for prompts over 100,000 tokens)`: `$0.50 / MTok`, `$2.50 / MTok`; 「Long context pricing」: 整个请求按高价, 提示词长度含缓存读写 | 同上 |
| `claude-sonnet-5-5` | 2.00 | 10.00 | `Claude Sonnet 5.5`: `$2 / MTok`, `$10 / MTok` | 内置可选; 内部 default / hard / light 的默认值 |
| `claude-sonnet-5` | 2.00 | 10.00 | `Claude Sonnet 5`: `$2 / MTok`, `$10 / MTok` (脚注 3: 上线优惠价已成为正式价) | 内置可选 |
| `claude-opus-5-5` | 4.00 | 20.00 | `Claude Opus 5.5`: `$4 / MTok`, `$20 / MTok` | 内置可选 |
| `claude-opus-5` | 5.00 | 25.00 | `Claude Opus 5`: `$5 / MTok`, `$25 / MTok` | 内置可选 |
| `claude-sonnet-4-6` / `claude-opus-4-7` / `claude-haiku-4-5` | 3 / 5 / 1 | 15 / 25 / 5 | 同一张表; 原有三行 (2026-06 取自 DEPLOY_PLAN §9), 这次对过, 相符 | 旧行, 未改 |
| `deepseek-v4-pro` | 1.32 | 3.96 | DeepSeek 官方页 `1M INPUT TOKENS (CACHE MISS)` PEAK `$1.32`, `1M OUTPUT TOKENS` PEAK `$3.96`; 非高峰时段减半 | 旧行 (原来取自 litellm, 代码里留着「上线前对官方页核实」的注记); 这次核实相符, 数值未改。取高峰价, 不会低估 |

- Anthropic: <https://platform.claude.com/docs/en/about-claude/pricing> (取的是 Markdown 版 `…/pricing.md`, sha256 `0f6deb28aacef431…`); 旁证 <https://platform.claude.com/docs/en/models/haiku-5-5/overview> 的「Pricing」表, 数值相同。
- DeepSeek: <https://api-docs.deepseek.com/quick_start/pricing>。
- litellm 在线表 (同日) 这几项数值相同, 只作旁证。
- 没有「未核实」的行。**没有固定**: embedding 模型和其他 provider 的模型 (§6 第 3 条)。

## 4. 修法与取舍

改了三个文件 (`server/cost.py`、`server/quota.py`、`server/instance.py`), 外加测试、两个留档脚本和文档。

1. **固定表补上 Claude 5.x 五个模型**; 表里有的模型只从表里取价, 不再问 litellm, 有没有网络都一样。
2. **Haiku 5.5 的两档都固定** (`_LONG_PROMPT_PRICES`)。怎么取档 (取舍, 理由是「提示词长度是估算值时不能按便宜的那一档记账」):
   - **预留**和**启动自检的单轮上限**: 手里只有提示词长度的估算值 (按字符数折算, 新分词器下不保证偏高), 一律按高档。公开站现在的配置: 60000 × 0.50 + 16000 × 2.50 = **0.07 美元** ≤ 0.30。
   - **结算**: 拿到服务商回报的用量时, 按那次请求实际所在的档位; 流中断没有用量时仍按高档 (长度还是估算值)。
   - 代价: 未结算期间, 一次答题占用的预留额是按低档时的 5 倍 (最坏的一轮 0.07 美元 vs 0.014), 免费池 3 美元能同时容纳的在途答题从约 214 个降到约 42 个 (都按最坏的一轮算); 结算后按实际扣。限额数值本身没有动。
   - 这一条的第一版是「按估算长度取档」, 提交后自动安全检查指出贴着分档线时预留会偏低, 改成了现在这样。
3. **公开档遇到没有固定价格的可选模型: 拒绝启动, 报出是哪个模型** (第 4 条取舍)。报错: `selectable model '<id>' (<模型串>): no pinned price — add the provider's official price to _PRICES in server/cost.py …`。
   - 理由: 没有固定价格时, 启动自检的上限和运行时的记账用的是同一个猜出来的价 (在线表取得到就用它, 取不到就用回退费率), 两种都不是核对过的数; 回退费率也不总是偏高 (官方价高于 5 / 25 的模型存在, 如 Fable 系列 8 / 40 起)。明确的失败发生在临时容器验收, 公开站不动。
   - **私有档不变**: 不做这项检查, 照常启动。**运行时不变** (两档都是): 请求里遇到给不出价的模型, 仍走原来的链 (registry → litellm → 回退费率), 不让请求失败。
   - 只检查**可选模型**, 没有扩到内部四档和 embedding (§6 第 3 条说明原因)。
4. **表内模型的匹配收紧**: 只认「本名」或「本名 + `-YYYYMMDD` 快照后缀」。原来是宽松的前缀匹配 (原注释说 `claude-haiku-4-5-turbo` 借不到 `claude-haiku-4-5` 的价, 实际借得到)。表里加了 `claude-opus-5` 之后, 宽松前缀会让将来的 `claude-opus-5-7` 之类悄悄借到价, 启动自检也会放行 —— 正是「加了模型没加价格」要防的事。**这一条两档都生效**: 原有四行上, 带非日期后缀的变体不再借价 (落到 registry / litellm, 都没有就显示「—」)。仓库里没有调用方或测试依赖旧行为 (`grep -rn "4-6-2026\|4-5-2025\|-turbo" tests/` 无命中)。代码审查者在新旧两份代码上对照实测: 不再命中的写法有 `claude-sonnet-4-6@20260514`、`claude-haiku-4-5@20251001`、`claude-sonnet-4-6-v1`、`claude-opus-4-7-thinking`、`deepseek-v4-pro-0813` 等; 这些串的成本显示从有数变成「—」, 开了计量时改按回退费率 (例: `claude-haiku-4-5@20251001` 的一轮预估 0.14 → 0.70 美元, 多记, 方向安全)。对比徽章用的是配置里的模型串, 不受影响; 会不会真的撞上取决于服务商在响应里回报什么名字 (没有发真实请求, 未核实), 所以加了下面第 6 条。
5. **固定价只认本服务商的前缀** (安全审查 LOW-4, 审查后加): 表里是第一方价格, 只匹配不带前缀的本名或带自家前缀的写法 (`anthropic/…`、`deepseek/…`)。`bedrock/claude-haiku-5-5`、`vertex_ai/…`、`openrouter/…` 这类走别的渠道的模型串不按第一方价 (那些渠道另有定价, 官方页写明区域端点贵 10%), 公开档会当成没有固定价格而拒绝启动。两档都生效。
6. **结算的下限** (代码审查 MEDIUM, 审查后加): 结算用的是服务商回报的模型名。回报的名字不在表里、而这次调用预留时用的模型在表里时, 记的账不低于「所预留模型的固定价」—— 其余价格来源 (litellm 的在线表只按低档; 或别的更便宜的数) 可能比实际低。回报的名字在表里时 (同一模型的日期快照、Router 回退到的 `deepseek-v4-pro`) 按它自己的固定价。所预留的模型本来就不在表里时, 计价链与改之前相同。

没有做的 (按派单): 没有让临时容器联网; 没有改限额、免费池、回退费率的数值; 没有改检索 / 答题逻辑; 没有改 `eval/`。

## 5. 改动的文件与部署路径过滤

`.gitea/workflows/sdtm-rag.yml` 的 `paths:` 含 `server/**`、`README.md` (仓根那个)、`deploy/container/**` 等, 不含 `tests/`、`deploy/README.md`、`.work/`。

| 文件 | 在部署路径过滤里 | 说明 |
|---|---|---|
| `server/cost.py` | **在** | 固定表、分档、匹配规则、`pinned_rates` |
| `server/quota.py` | **在** | `_price` 先查固定表; 估算长度按高档, 回报用量按实际档 |
| `server/instance.py` | **在** | 公开档: 可选模型没有固定价格 → 拒绝启动 |
| `tests/test_public_price_pin.py` (新) | 不在 | |
| `deploy/README.md` | 不在 | 「公开实例」「启动失败常见原因」各加一条 |
| `.work/10_split_and_public/…` (本文件、两个脚本、`_progress.json`、`trace.jsonl`、审查任务书) | 不在 | |
| `docs/retrospectives/RETROSPECTIVE_public_kb_leg.md` | 不在 | 追加一节 |

⇒ **合并到 main 并 push 会命中路径过滤**: 构建新镜像、部署私有站; 公开部署开关现在开着, 所以同一次运行还会带上公开部署 (预检 → 隔离核对 → 临时验收 → key 探测 → 换入候选 → `up --no-start`)。这需要主人另行同意; 不想连带公开部署的话, 用「只构建」(deploy 不勾)。

## 6. 同类问题 (第 5 条): 启动时还有没有别的依赖联网

1. **启动自检本身**: `instance.check_startup` 其余各项、`auth.install_security` / `_install_quota` 只读配置、环境变量和本地路径, 没有联网 (读代码)。本机用断网替身 (解析 / 连接任何非回环地址都当场失败并记录) 按公开档导入应用并建一次应用: 修之后成功, 全程唯一的联网尝试是 litellm 取价格表那一次; 同一个替身在修之前的代码上复现了 `$0.700 > … $0.300` (§7.3)。
2. **provider registry 的模型能力位随在线价格表而变 —— 不小, 只汇报, 没有改。** `server/provider_registry.py` 对没有写 `capabilities` 的行, 从 litellm 的表里取「支持工具调用 / 支持图像 / 上下文长度 / 支持缓存」和输出上限。没有在线表时, Claude 5.x 的行全部落到保守默认值:

   | | 有在线表 | 没有在线表 |
   |---|---|---|
   | `claude-haiku-5-5` / `claude-sonnet-5-5` / `claude-opus-5` 的能力位 | 工具 ✓ 图像 ✓ 上下文 1,000,000 缓存 ✓ | 工具 ✗ 图像 ✗ 上下文 0 缓存 ✗ |
   | `claude-haiku-5-5` (registry 行没写输出上限) 自带 key 时的输出上限 | 128000 | 8192 |

   不会让启动失败, 方向是保守的 (功能被降级并带降级说明: 联网检索不可用、图像不可用、研读包不自动挂)。但**私有站也受影响**: 私有容器哪天在取不到 GitHub 的时候启动, 这些功能会一直降级到下一次重启。修法是在 `provider_registry.yaml` 里把这几行的 `capabilities` / `max_output_tokens` 写死 (同样要按官方资料核对), 属于另一个改动。
3. **内部四档和 embedding 的价格没有纳入启动自检 —— 只汇报。** 内部四档的默认值 (`claude-sonnet-5-5`、回退 `deepseek-v4-pro`) 现在都在固定表里; 公开站按 `p3_step3.3.md` 把四档都配成了 `claude-haiku-5-5` (在表里)。embedding (`text-embedding-3-small`) 不在固定表里, 靠 litellm 包内表给价 (包内表有, 每百万 0.02 美元, 没有网络也取得到)。没有把它们加进「没有固定价格就拒绝启动」: 这些是部署机 env 文件里的值, 本会话看不到 (也不该去读), 新增一条拒绝启动的检查有再失败一次部署的风险。残留的口子: 有人把公开站的内部四档配成一个不在表里、官方价又高于 5 / 25 的模型, 而容器恰好取不到在线表时, 那个模型的调用会按回退费率少记。要不要把检查扩到内部四档, 请协调方定。
4. **lifespan (建检索引擎、BM25、读 meta、建 Router) 和健康检查、`check_index_freshness`**: 读代码没有发现出站调用 (chromadb 1.5.9 的产品遥测类是空实现, 不联网)。**没有在无网络的容器里实测到 healthy** —— 这次同意的一次性容器只调用成本自检函数、不挂数据, 起不了完整应用。「没有网络的临时容器能否起到 healthy、要多久」仍然要等下一次真实的公开部署才有答案。
5. **缓存读写的计价没有区分** (改之前就有, 没有改): 计量把 `prompt_tokens` 全按基础输入价算。缓存读更便宜 (高估, 无害), 缓存写更贵 (5 分钟 1.25 倍 / 1 小时 2 倍, 会低估)。代码里唯一下缓存断点的地方是研读包, 公开档强制关闭; 私有档默认不开计量。
6. **测试之间的串扰** (改之前就有, 没有改, 只让新测试自己不受影响): `tests/test_p3_4_public_https.py` 的两条测试用 `load_dotenv` 往进程环境里写了键, 再用 `monkeypatch.delenv` 删 —— 收尾时 monkeypatch 会把它们「恢复」回来, 于是 `sdtm_rag_quota_trusted_proxies` (小写) 等键留在后面的测试里。按文件名顺序跑时, 排在它后面又要建公开档应用的测试会被拒 (「大小写变体取值冲突」)。在未改动的 `0a85a43` 上把顺序倒过来就能复现: `pytest tests/test_p3_4_public_https.py tests/test_p2_l3_instance.py tests/test_p2_9_public_e2e.py` → 59 failed。

## 7. 验证

提交号见文末「提交」(都在变基到 main `45fc1c6` 之后)。独立审查看的是 `97d6aa0`; 之后的修正在 `990e75d`、`a464243`、`0eb2c1e`。

### 7.1 单测 (`tests/test_public_price_pin.py`)

| 要钉住的事 | 用例 | 两档 |
|---|---|---|
| 表 = 官方价 (字面量对照) | `test_pinned_table_is_the_official_prices` | 共用 |
| 内置可选模型 + 内部四档默认值 + 公开站在用的模型, 都有固定价格 (任务第 2 条) | `test_every_builtin_server_model_has_a_pinned_price` | 共用 |
| 只认本名或日期后缀、只认本服务商的前缀; 少了一行不会被更短的键顶上 | `test_a_pinned_row_matches_the_id_or_a_dated_snapshot_only` (25 组)、`test_a_missing_row_is_not_covered_by_a_shorter_key` | 共用 |
| 分档边界 (100000 / 100001 / 长度未知; 带日期后缀的快照同样分档) | `test_haiku_5_5_is_priced_by_prompt_length` | 共用 |
| 预留按高档、回报用量按实际档 (含经过真实的预留 / 结算存储走一遍) | `test_the_meter_reserves_at_the_upper_tier_and_settles_at_the_reported_one`、`test_reserve_and_settle_through_the_store_use_those_tiers` | 公开 |
| 回报的名字不在表里时不低于所预留模型的固定价; 所预留模型不在表里时计价链不变 | `test_settle_never_charges_less_than_the_reserved_models_pinned_price` / `test_settle_keeps_the_old_price_chain_when_the_reserved_model_is_not_pinned` | 公开 / 私有 (开计量) **各一条** |
| 表内模型不经过 litellm (把 litellm 的计价函数换成一调用就报错的) | `test_a_pinned_model_is_priced_without_litellm[public]` / `[private]` | **各一条** |
| 公开站现在的配置能过成本自检并建出应用 | `test_the_deployed_public_config_passes_the_cost_check` | 公开 |
| 没有固定价格的可选模型: 公开拒绝并报出模型; 私有照常启动 | `test_public_refuses_a_selectable_model_without_a_pinned_price` / `test_private_starts_with_the_same_unpinned_model` | **各一条** |
| 运行时给不出价的模型仍按回退费率 | `test_an_unpriced_model_still_meters_at_the_fallback_rate[public]` / `[private]` | **各一条** |
| **run 219 的场景 (任务第 3 条)**: 新开一个解释器, `LITELLM_LOCAL_MODEL_COST_MAP=True` 让 litellm 只用包内表, 再把表里含该模型名的键删掉 (防以后的包内表带上它); 夹具先断言「litellm 此时确实给不出价」 | `test_public_cost_check_passes_without_the_online_price_map` / `test_private_is_priced_the_same_without_the_online_price_map` / `test_public_names_the_unpinned_model_without_the_online_price_map` / `test_private_keeps_the_fallback_rate_without_the_online_price_map` | **各两条** |

为什么离线场景要新开解释器: litellm 只在 import 时读一次价格表, 而且本机有网络; 在同一个进程里打桩, 测到的是桩。

公开站的可选模型列表只存在于部署机的 env 文件里, 仓库里没有这张表可以遍历。所以「以后有人加了新模型却没加价格」分两层挡: 加进仓库内置配置的 → 上表第 2 行的测试变红; 只加进部署机 env 的 → 公开档启动自检拒绝 (上表「公开拒绝」那一行钉住这道闸), 部署停在临时容器验收。

### 7.2 变异验证 (规则 5)

脚本 `public_price_pin_mutations.py` (框架照 `pre_switch_fixes_mutations.py`: 只在 `git archive` 出来的副本上跑, 先比 sha、精确替换一处、回读、`finally` 用冻结的原始字节写回再比 sha; 判定要求预登记的那条用例真的红了, 没有 error)。结果见文末「变异结果」。其中:
- 任务第 2 条「从表里拿掉一个 → 红」: C1–C4 (四行各拿掉一次)。
- 任务第 3 条的变异: C1、I2, 以及 **PRE** —— 把三个文件整个换回修之前的字节, 只跑离线那一条, 必须红且输出里有 `$0.700 > free pool / 10 = $0.300`。
- 第一轮有一条变异 (I3 的初版「私有档一律跑公开档的自检」) 被判 INVALID: `server.main` 在导入时就用默认配置建一次应用, 那样整份测试收集不起来。换成了更窄的写法后打红。
- **`97d6aa0` 上 PRE 是 INVALID** (20 / 21): 那个提交给测试里的离线探针加了修之前不存在的参数, 换回旧代码后探针直接报错, 而不是红出原句。也就是说在 `97d6aa0` 这个状态, 「修之前必红」没有被证明; 判定规则没有把它记成 killed。`990e75d` 把探针改成只调用新旧代码都有的函数, 之后 PRE 打红 (代码审查者独立复跑确认)。
- 代码审查者另想的 10 个变异里有 2 个存活 (X2: 分档表按原始模型名查, 带日期后缀的快照丢掉高档; X3: 日期后缀放宽到 `@YYYYMMDD`)。两条都补了断言, 并收进脚本 (C16、C13)。

### 7.3 全量测试

| 环境 | 提交 | 结果 |
|---|---|---|
| 深度为 1 的克隆 + 独立 venv (CI 同款; 没有 `data/`) | `97d6aa0` | 3596 passed / 0 failed / 61 skipped (59 条是 `local_data`, 2 条要 playwright) |
| 同上 | `0eb2c1e` (最终的代码与测试) | 3611 passed / 0 failed / 61 skipped |

基线对照: 上一个单元在 `2834d5e` 的浅克隆是 3566 / 0 / 61; 这次多出的就是新文件里的用例 (`97d6aa0` 时 30 条, 最终 45 条)。

```sh
T=<临时目录>; git clone --depth 1 --branch hakupao/public-price-pin file://<主仓路径> $T/shallow && cd $T/shallow \
  && git submodule update --init --depth 1 && uv sync --extra dev \
  && .venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs -p no:cacheprovider
```

本机的断网替身 (§6 第 1 条; 脚本没有入库, 做法: 把 `socket.getaddrinfo` 和 `socket.socket.connect` 换成对非回环地址一律报错并记录, 设公开档的环境变量后 `import server.main`):

| 代码 | 结果 | 记录到的联网尝试 |
|---|---|---|
| 修之前 (`0a85a43` 的归档副本) | `RuntimeError: … selectable model 'haiku-5-5': one answer round reserves $0.700 > free pool / 10 = $0.300 …` | 只有 `raw.githubusercontent.com` |
| 修之后 (工作区) | 导入并建出应用, 档位 public | 只有 `raw.githubusercontent.com` |

### 7.4 真实镜像里的离线场景 (2026-11-28 07:53Z, 部署虚拟机)

镜像 `…/sdtm-rag:613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7` (私有站线上镜像; `git diff 613f048 45fc1c6 -- server/` 为空, 所以「镜像原样」= 修之前的 `server/`)。脚本 `public_price_pin_offline_probe.py` 经标准输入送进一次性容器, 只调用 `instance._public_cost_problems` (公开档 + 公开站现在的可选模型配置)。

```sh
docker run --rm -i --name ppp-offline-probe --network none --cap-drop ALL --security-opt no-new-privileges --memory 1g --entrypoint python <镜像> -
```
不带 env 文件、不挂任何目录、不挂 docker socket、不发布端口、不带任何 key。

| | 第 1 次: 镜像原样 (修之前) | 第 2 次: 用改过的三个文件覆盖 (修之后) |
|---|---|---|
| 载入的模块 (sha256 前 16 位) | `/app/server/cost.py fc8264ed3c0ef2e1`、`quota.py 0aab05b97bcbd7b1`、`instance.py fb515bdb5363e2ea` (= `0a85a43` 的三个文件) | `/tmp/ov/server/cost.py d5e0b6d679cc6def`、`quota.py 78f2486e0dfbab80`、`instance.py 5f83856d370328ee` (= `97d6aa0` 的三个文件) |
| litellm 价格表 | 包内表, 2764 条, 没有 `claude-haiku-5-5`; 原因 `Temporary failure in name resolution` | 同左 |
| 成本自检 | `["selectable model 'haiku-5-5': one answer round reserves $0.700 > free pool / 10 = $0.300 (lower its max_output_tokens)"]` | `[]` |
| 单轮上限 / 免费池的十分之一 | 0.70 / 0.30 | 0.07 / 0.30 |
| 结论 | **拒绝启动** (与 run 219 的失败同一句) | **通过** |

- 第 2 次里 `estimate_cost` 对「100 万 token 的提示词」给出的输入价是 0.5、对「0 提示词 + 100 万输出」给出的输出价也是 0.5: 前者落在高档 (输入 0.50), 后者落在低档 (输出 0.50)。主仓的 `p3_stageDE_price_probe.py` 用的就是这种问法, 合并后在离线容器里跑它会打印 `0.5 0.5`, 不是 `0.1 0.5` —— 是问法跨了档, 不是价格错了; 计量不走这种问法 (§4.2)。
- **第 3 次 (08:15:47Z), 审查修正之后的最终文件**: 载入 `/tmp/ov/server/cost.py 11424dac266090b0`、`quota.py d4337733a7d70284`、`instance.py a665259d54e754a1` (= `a464243` / `0eb2c1e` 的三个文件); 价格表同样是包内表 2764 条、没有该模型; 成本自检 `[]`; 单轮上限 0.07 / 0.30; **通过**。
- 每次跑完: `docker rm -f ppp-offline-probe` (容器带 `--rm`, 已自行删除); `docker ps -a --filter name=ppp-offline` 为空。
- 前后核对 (第 1、2 次: 07:53:30Z / 07:53:34Z; 第 3 次: 08:15:46Z / 08:15:49Z; 三个时点之间也无差别): 私有站 `/api/health` 200 / 200; `sdtm-rag-api` 启动于 `2026-11-28T03:23:47.097798686Z`、`sdtm-rag-ui` 启动于 `03:23:57.678917638Z`, 重启 0 次, 镜像 `613f048`, 前后相同; 全部容器的名单与状态前后逐字相同 (公开容器仍是 `created`); 没有未结束的 Actions 运行 (最近一次是 run 219)。
- 没有碰: 公开容器、公开数据根、`/opt/sdtm-rag-public/`、隔离规则。

## 8. 独立审查 (规则 D)

两位审查者同时派出, 类型与实现者不同、彼此也不同, 模型 opus; 任务书 `../subagent_prompts/public_price_pin_reviewers.md` (只给事实和要审的问题)。审的是 `97d6aa0`。两位都自己取了官方定价页核对。

| 审查者 | 结论 | 分级 |
|---|---|---|
| 代码审查 (`oh-my-claudecode:code-reviewer`) | **PASS-with-fixes** | CRITICAL 0 / HIGH 1 / MEDIUM 3 / LOW 若干 |
| 安全审查 (`oh-my-claudecode:security-reviewer`) | **PASS** (风险 LOW) | CRITICAL 0 / HIGH 0 / MEDIUM 0 / LOW 4 |

两位一致的结论: 固定的价格与官方页逐项一致 (代码审查者连 DeepSeek 页一起核了; 安全审查者没有核 DeepSeek 那一行); 这次改动没有让花费保护变弱, 并修好了「长提示词少记到五分之一」这个旧问题; 离线夹具确实在模拟没有在线价格表; 没有永真断言; diff 里没有密钥。

| # | 来源 / 级别 | 意见 | 处理 |
|---|---|---|---|
| 1 | 代码 HIGH | `97d6aa0` 的变异脚本 PRE 判 INVALID (「修之前必红」在那个提交没有被证明) | **已修** (`990e75d`, 审查期间实现者自己也跑出来了); 审查者复跑确认 PRE killed |
| 2 | 代码 MEDIUM (自评置信度低) | 结算用服务商回报的模型名; 名字不在表里时落到别的价格来源, 可能偏低 | **已改** (§4 第 6 条, `a464243`)。没有照建议「直接改用所预留模型的固定价」: Router 回退到另一个不在表里的模型时那样会少记, 所以取两者中较高的 |
| 3 | 安全 LOW-4 (这次引入) | 去掉服务商前缀后, `bedrock/claude-haiku-5-5` 之类也按第一方价并通过公开档自检 | **已改** (§4 第 5 条, `a464243`) |
| 4 | 代码: 存活变异 X2、X3 | 带日期快照的分档、`@YYYYMMDD` 后缀没有测试锁住 | **已补** 断言和变异 (C16、C13) |
| 5 | 代码 LOW | 报错没有提到分档表 | **已改**: 报错里加了 `_LONG_PROMPT_PRICES` |
| 6 | 代码 LOW | 变异脚本只用一种方式核对导入路径 (venv 里有指向工作区的可编辑安装) | **已改**: 两种导入方式都核对 |
| 7 | 安全 备注 N5 | 离线脚本的 `emit` 接受绝对路径 / `..` | **已改**: 拒绝 |
| 8 | 代码 MEDIUM + 安全 LOW-1 (改之前就有) | 启动自检只看可选模型: 内部四档、embedding、Router 回退到的模型不在检查里。公开档答题组会回退到 `default-fallback`, 预留是按可选模型算的; 回退模型更贵、输出上限更大时, 在途预留低于实际 (账按真实用量记, 不会少记, 但并发时日上限可能被冲过)。两位都建议把检查扩到公开档会走服务端 key 的全部模型 | **没有改, 请协调方定** (§6 第 3 条的同一件事): 按 `p3_step3.3.md`, 公开站的四档都是 `claude-haiku-5-5`、回退的输出上限 16000, 现在不可利用; 但那是部署机 env 里的值, 本会话没有看也不该看 |
| 9 | 安全 LOW-2 (这次引入) | 按高档预留后, 用未结算的预留把免费池占满所需的并发降到约五分之一 (最坏的一轮: 43 个并发、每 IP 限 5 个并发 ⇒ 约 9 个 IP; 改之前约 43 个 IP) | **接受, 没有改**。审查者的评估: 占住预留要一直开着流 (每个请求最长 180 秒)、每 IP 每天 50 题; 用真实花费把池子耗光只要约 6 个 IP, 比占并发还便宜。它建议的收窄办法依赖一个它自己没有核实的假设 (每个 token 至少 1 字节) |
| 10 | 安全 LOW-3 (改之前就有, 与这次无关) | 上游中途断流时 litellm 不抛异常, 输出量是它自己估的, 结算当成实报; 每轮最多少记约 0.04 美元 | 没有改, 只汇报 |
| 11 | 代码 MEDIUM + 安全第 6 问 (改之前就有) | provider registry 的模型能力位随在线价格表而变; 临时验收容器验到的行为与线上不同。安全审查者建议在镜像里设 `LITELLM_LOCAL_MODEL_COST_MAP=True` 让两边用同一份表; 代码审查者建议在 registry 里写死能力位 | 没有改, 只汇报 (§6 第 2 条)。注意: 只设那个环境变量而不写死能力位, 线上的 Claude 5.x 会全部落到保守默认值 (联网检索、图像、研读包自动挂载都降级), 两件事要一起做 |
| 12 | 代码 备注 | 离线探针只调用成本自检函数, 证明不了能一路启动到 healthy | 属实, 已写在 §6 第 4 条和 §9 |

两位审查者都没能核实的: Anthropic / DeepSeek 在响应里回报的模型名的实际写法 (没有发真实请求); 部署机上公开站 env 文件的真实内容; 真实镜像里的离线对照 (审查者没有 docker, §7.4 是实现者自己跑的, 没有第二个人复跑)。

**审查之后的修正 (`990e75d` 里的探针改动、`a464243`、`0eb2c1e`) 没有再经独立审查**; 它们由测试和变异覆盖 (文末), 最终文件在真实镜像里跑过一次 (§7.4 第 3 次)。

## 变异结果 (最终; 测试与被测代码 = `a464243`, 脚本 = `0eb2c1e`)

`29/29 killed`, 基线和还原后都是 `45 passed`。三个文件的 sha256 前 16 位: `cost.py 11424dac266090b0`、`instance.py a665259d54e754a1`、`quota.py d4337733a7d70284`。

| 组 | 编号 | 变异 | 打红的预登记用例 |
|---|---|---|---|
| 表里少一行 | C1–C4 | 分别拿掉 `claude-haiku-5-5` / `claude-sonnet-5-5` / `claude-opus-5-5` / `deepseek-v4-pro` | 离线场景那一条 (C1); 「内置模型都有固定价格」(C2–C4) |
| 价格数值 | C5、C6、C12 | Haiku 输出价少一位; Opus 5.5 输出价写低; 高档输出价写成低档的 | 「表 = 官方价」 |
| 匹配规则 | C7、C8、C13、C14、C15 | 退回宽松前缀; 日期后缀只匹配开头; 后缀放宽到 `@`; 不看服务商前缀; 前缀判断写反 | 匹配规则那一组 |
| 分档 | C9、C10、C11、C16 | 拿掉高档; 边界写成大于等于; 长度未知不取高档; 分档表按原始模型名查 | 分档那一条 |
| 计量 | Q1–Q5 | 不查固定表; 估算长度按自己的档; 结算一律按高档; `reported` 不起作用; 没有用量的流式结算按低档 | 「不经过 litellm」「预留按高档 / 回报按实际档」「经过存储走一遍」 |
| 结算下限 | Q6–Q9 | 去掉下限; 写成上限; 所预留模型不在表里时也套; 直接改用所预留模型的价 | 下限那两条 |
| 启动自检 | I1–I3 | 不再要求固定价格; 用 id 而不是模型串去查; 显式配了可选模型的私有档也跑公开自检 | 「公开拒绝」; 离线场景; 「私有照常启动」 |
| 修之前 | PRE | 三个文件整个换回 `0a85a43` 的字节 (sha `fc8264ed3c…`、`0aab05b97b…`、`fb515bdb53…`) | 离线场景那一条, 输出里有 `selectable model 'm1': one answer round reserves $0.700 > free pool / 10 = $0.300` |

```sh
T=<临时目录>; mkdir -p $T/mut $T/pre && git archive HEAD | tar -x -C $T/mut \
  && git archive 0a85a43 server/cost.py server/quota.py server/instance.py | tar -x -C $T/pre
PPP_MUT_ROOT=$T/mut PPP_PREFIX_ROOT=$T/pre .venv/bin/python .work/10_split_and_public/evidence/checkpoints/public_price_pin_mutations.py
```

历次: 第一版代码 (`955190f`) 19 / 20 (I3 初版 INVALID → 改窄后 killed); `97d6aa0` 20 / 21 (PRE INVALID, 见 §7.2); `a464243` 28 条全部 killed, PRE 那一步因脚本里新加的常量与已有变量重名而报错 (脚本自己的错, `0eb2c1e` 改名); 最终 29 / 29。

## 提交 (分支 `hakupao/public-price-pin`, 基于 main `45fc1c6`; 没有 push)

| 提交 | 内容 | 命中部署路径过滤 |
|---|---|---|
| `955190f` | 固定表 + 分档 + 匹配规则 + 公开档启动自检; 测试; 变异脚本 | 是 (`server/**`) |
| `97d6aa0` | 估算长度按高档预留, 回报用量按实际档; 离线对照脚本 | 是 |
| `990e75d` `[skip ci]` | 本文件、README、复盘、进度登记、审查任务书; 离线探针改成新旧代码都能跑 | 否 |
| `a464243` | 审查意见: 服务商前缀、结算下限、报错补充; 测试与变异 | 是 |
| `0eb2c1e` `[skip ci]` | 变异脚本常量改名 | 否 |
| 之后的一个文档提交 `[skip ci]` | 本文件的审查 / 变异 / 提交三节, 进度与 trace | 否 |

提交信息带 `[skip ci]` 只对「这个提交是 push 的头提交」有意义; 这些提交合并进 main 时, 整体仍然命中路径过滤 (§5)。
提交时的红线检查: 工作区没有研究数据的 catalog, hook 按具名开关 `OIDSCAN_NO_CATALOG=1` 跳过; 每次提交之前另用主仓的 catalog 对暂存文件手动跑了同一个扫描 (`.venv/bin/python -m scripts.precommit_oidscan --catalog <主仓>/data/study/st01/catalog.json`), 结果都是 CLEAN。没有用 `--no-verify`。

## 9. 还没有做 / 留给后面的
- 合并、构建新镜像、部署 (私有站 + 公开站): 等主人同意。合并后第一次公开部署会从头走一遍, 这次才会知道「没有网络的临时容器能否起到 healthy」。
- §6 第 2 条 (模型能力位依赖在线表, 私有站也受影响)、第 3 条 (内部四档 / embedding 是否纳入检查)、第 6 条 (测试串扰): 只汇报, 没有改。
- 价格会变: 固定表是 2026-11-28 的官方价。服务商调价后要人工更新表和测试里的字面量 (两处, 故意的); 没有自动比对。调低不影响花费保护, 调高会让记账偏低。
