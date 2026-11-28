# 价格固定的扩展: 启动自检覆盖全部走服务端 key 的模型, 预留覆盖回退模型 (2026-11-28, 分支 `hakupao/public-price-pin`)

接 `public_price_pin.md`。那份的汇报之后, 协调方对留下的两项做了裁定, 并让在同一条分支上接着做。
仍然: **没有 push、没有合并、没有部署、没有动生产**。

## 1. 裁定来源 (都是协调 bot 受托代裁, 不是主人逐条裁定)

| # | 裁定 | 落实 |
|---|---|---|
| 一 | 启动自检扩到公开档会走服务端 key 的全部答题模型: 内部四档 (default / hard / light / fallback) 的模型都要有固定价格; 单轮预留上限要覆盖回退模型和它的输出上限 (具体做法由实现者判断); 列全公开档一轮答题里走服务端 key 的模型调用, 会被调用又没有固定价格的纳入检查, 根本不会被调用的写明依据、不加检查 | 本文件 §2–§5 |
| 二 | provider registry 的模型能力位依赖在线表 —— 这次不做, 记入 `todo_later` | `_progress.json` |
| 顺带 | `tests/test_p3_4_public_https.py` 把环境变量留给后面的测试 —— 修, 只改测试 | §6 |
| 合并方式 | 快进合并、头提交带 `[skip ci]`, push 不触发; 之后手动「只构建 → 测试端口验证 → 部署」。分支上每个提交都带 `[skip ci]` | 这次新增的提交都带; 之前的三个代码提交 (`955190f`、`97d6aa0`、`a464243`) 不带, 没有为此改写 (它们不是头提交, 不影响快进合并后是否触发) |

协调方给的输入 (它只读看过部署机上公开站 env 文件里与模型有关的非密钥设置; 本会话没有读那个文件):
- `SDTM_RAG_DEFAULT_MODEL` / `HARD_MODEL` / `LIGHT_MODEL` / `FALLBACK_MODEL` 都是 `anthropic/claude-haiku-5-5`;
- `SDTM_RAG_SELECTABLE_MODELS` 只有一项: id `haiku-5-5`, 模型串 `anthropic/claude-haiku-5-5`, `max_output_tokens` 16000;
- `SDTM_RAG_EMBEDDING_MODEL` = `text-embedding-3-small`; `SDTM_RAG_RERANK_ENABLED` = `false`;
- 另设了 `SDTM_RAG_WEB_SEARCH_ENABLED`、`SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS`、`SDTM_RAG_EMBEDDING_DIM`、`SDTM_RAG_QUOTA_TRUSTED_PROXIES` (**值没有看**);
- key 只有 Anthropic 和 OpenAI 两把, 没有 DeepSeek; 没有设 `EXPANSION_MODEL` / `JUDGE_MODEL` / `COMPARE_MODELS`。

## 2. 公开档一轮答题里, 服务端 key 会调用哪些模型 (第 3 条)

付费调用都经过 `server/outbound.py` (用途清单 `PURPOSES`); 不经过它的只有 Cohere 重排 (`server/rag.py`)。逐项:

| 用途 | 用哪个模型设置 | 公开档下会不会被调用 | 依据 | 固定价格 / 计量 |
|---|---|---|---|---|
| 答题 `answer`、续写 `continue` | 可选模型 (Router 组 = 可选模型的 id) | **会** | `/api/ask`、`/api/ask_stream` | 有固定价格才能启动 (上一轮已做); 计入限额 |
| 同上, Router 回退 | `fallback_model` + `fallback_max_output_tokens` (组 `default-fallback`) | **会** (主模型失败时) | `llm_config._fallback_map`: 每个答题组回退到 `default-fallback`; 输出上限挂在部署上, 回退后用回退档自己的 | **这次纳入**: 必须有固定价格; 预留和单轮上限覆盖它 (§3) |
| embedding | `embedding_model` | **会** (每次检索) | `server/rag.py` 的 `outbound.embedding` | **这次固定并纳入** (§4); 计入限额 |
| 用内部组名答题 (`default` 等) | `default_model` / `hard_model` / `light_model` | 不会 | 公开档对 `model` 是内部组名的请求一律 422 (`instance.check_request`; 既有测试 `test_internal_group_rejected_on_public`、`…_even_with_provider`) | **按裁定一第 1 条仍检查固定价格** (纵深防御: 四档的部署在公开档的 Router 里都存在); **不进单轮上限** (见下) |
| 判库 `route` | `light_model` | 不会 | 只在联邦路由里; 公开档 `federation_enabled` 强制关, 显式开 = 拒绝启动 (`PUBLIC_FORCED_OFF`) | 同上一行 |
| 重答 `regen` | 可选模型 | 不会 | 只在研读包答案闸里; 公开档 `dossier_enabled` 强制关, 请求里 `dossier=on` 被 403 | — |
| 查询扩写 `hyde` / `multiquery` | `expansion_model` (默认 `deepseek/deepseek-chat`) | **不会, 而且私有档的服务也不会** | 只有 `RAGEngine` 构造时传了 `query_expansion` 才会走; `server/` 里构造 `RAGEngine` 的两处 (`server/main.py`) 都没有传, `settings.query_expansion` / `expansion_model` 在 `server/` 里没有任何读取点 —— 只有评测脚本直接构造引擎时才用。所以它不是「被关掉、被跳过、或失败后降级」, 是根本没接进服务。公开站没有 DeepSeek 的 key 不影响 | 不检查 (测试 `test_model_settings_nothing_calls_on_public_are_not_checked`) |
| 语义复核 `review` | `hard_model` | 不会 | 只在 `/api/validate`; 公开档不注册 (404; 既有测试 `test_blocked_endpoint_is_404_on_public_and_routed_on_private`) | 不检查 (`hard_model` 的固定价格按上面那行检查) |
| 对比 `compare`、判分 `judge` | `compare_models`、`judge_model` | 不会 | 只在 `/api/ask_compare`; 公开档不注册 (同上), `check_request` 另拒 (`test_check_request_refuses_private_only_endpoints_on_public`) | 不检查 |
| 重排 (Cohere, 不经出站接缝) | `rerank_model` | 不会, 私有档的服务也不会 | `server/main.py` 构造引擎时没有传 `rerank_enabled`; 公开档 `rerank_enabled=true` 另被启动自检拒绝 | 不检查 |
| 联网检索 `web` (Tavily, 不是模型) | — | 免费题不会 (`quota_free_web_enabled` 默认关); 自带 key 的请求会 | `quota.free_web_allowed` | 不是按 token 计价的模型: 按设置项 `quota_web_search_usd` (0.016 美元 / 次, 代码里标着未核实、偏保守) 计入 BYOK 那一池, 另有每访客每日次数上限。不加固定价格检查 |

```sh
grep -rn --include='*.py' "query_expansion\|expansion_model\|rerank_enabled\|rerank_model" server/ | grep -v "^server/rag.py"   # 只有 config.py 的定义和 instance.py 的那条拒绝
grep -rn --include='*.py' "RAGEngine(" server/                                # server/main.py 两处, 参数里没有 query_expansion / rerank_enabled
grep -n "outbound\.\(completion\|acompletion\|embedding\)" server/*.py          # 全部调用点
```

**检查范围因此分成两种, 不能混:**
- **固定价格**: 可选模型 + 内部四档 + embedding。
- **单轮上限 (≤ 免费池 / 10)**: 只算一轮答题够得着的 —— 可选模型, 和它回退到的那一档。`default` / `hard` / `light` 不算: 公开站没有给这三档设输出上限 (内置 128000), 按 Haiku 的高档是 60000 × 0.50 + 128000 × 2.50 = 0.35 美元 > 0.30; 把它们算进去, 公开站现在的配置会被拒, 而这三档在公开档上答不了题。测试 `test_groups_that_never_answer_on_public_are_not_in_the_round_bound` 和变异 I8 钉住这一点。

## 3. 预留与单轮上限覆盖回退模型 (第 2 条; 做法是实现者的判断)

**问题** (上一轮审查第 8 条的另一半): 预留按可选模型算; 主模型失败、Router 回退之后, 实际答题的是回退档的模型, 用的是回退档自己的输出上限。回退档更贵或上限更大时, 实际花费可以高于预留 —— 账是按真实用量记的, 不会少记, 但在途的预留偏低, 并发时每日上限可能被冲过; 启动自检的单轮上限也没有看回退档。

**做法**: 不只改启动自检, 而是让**预留本身**覆盖回退 —— 一次调用的预留 = 它可能落到的各个部署里最贵的那个 (各自的模型价 × 各自的输出上限)。启动自检的单轮上限用的是同一个函数, 所以「自检算的」和「运行时订的」是一回事。只改自检的话, 上限是对了, 运行时订的仍然是偏低的数, 审查指出的那个口子还在。

- `quota._call_candidates(s, 组名)`: 这个组自己, 加上 `llm_config._fallback_map` 里它回退到的组。回退表就是 `create_router` 交给 Router 的那一张, 没有另写清单。不是 Router 组的名字 (embedding 的模型串、不经 Router 的直连调用) 没有回退。
- 预留时拿到的是组名: `providers.resolve` 对服务端 key 的调用原样返回参数 (读代码确认); 自带 key 的答题不走 Router, 也不计量。
- 调用方显式传了 `max_tokens` 时 (服务路径上没有, 评测脚本有), 各候选都用这个值。

**在公开站现在的配置下不改变任何数**: 回退档与可选模型是同一个模型、同一个上限 (16000), 两个候选都是 0.07 美元。

**`SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS` 的值协调方没有读到** (16000 取自 `p3_step3.3.md`)。回退档是 Haiku 时, 单轮上限 = 0.03 + 上限 × 2.50 / 1,000,000, 所以这个值 **≤ 108,000 都通过, 超过就拒绝启动** (测试钉了 100,000 通过、120,000 被拒)。请对照实际值。

**两档都生效** (上一轮列过四处, 这是第五处): 私有档默认不开计量, 没有影响; 开了计量的私有档按内置配置, 可选模型 (Sonnet 5.5, 128000 输出) 比回退档 (DeepSeek, 32000 输出) 贵, 预留仍是可选模型自己的, 数值不变 (测试 `test_private_default_config_reserves_what_it_did_before`)。只有回退档更贵的配置, 预留才会变大。既有的配额 / 实例 / 路由测试没有一条因此变化。

**没有覆盖的** (改之前就有): 一次预留对应的实际调用可能不止一次 —— Router 重试 (1 次) 或流中途回退时, 主模型已经生成的部分和回退模型的整轮都会被服务商计费, 两者之和可以超过「较贵者」。结算记的是最后那次响应回报的用量。

## 4. embedding 的固定价格

| 模型 | 输入 (美元 / 百万 token) | 出处 | 查阅 |
|---|---|---|---|
| `text-embedding-3-small` | 0.02 (没有输出 token) | OpenAI 官方定价页 <https://platform.openai.com/docs/pricing> (跳转到 `developers.openai.com/api/docs/pricing`): 「Embeddings」表 `text-embedding-3-small` = `0.02`; 模型页 `…/docs/models/text-embedding-3-small`: `Price $0.02`、`Embeddings Per 1M tokens … Cost $0.02`、`text-embedding-3-small $ 0.02` | 2026-11-28 08:33Z |

litellm 包内表的数值相同 (没有网络时也取得到), 所以这一行改变的是「价格从哪来」, 不改变数。固定价只认本名或 `openai/` 前缀 (`azure/…` 不认)。
顺带: 服务商前缀的查法改成查不到就当作「只认本名」, 不抛异常 (上一轮安全审查的可选建议; 以前新加一行别家的价格而忘了登记前缀时, 带前缀的写法会在计量里抛 `KeyError`)。

## 5. 启动自检现在的样子 (公开档; 私有档不做)

1. `SDTM_RAG_SELECTABLE_MODELS` 显式设置 (原有)。
2. **(新)** `default_model`、`fallback_model`、`hard_model`、`light_model`、`embedding_model` 各自要有固定价格, 没有就报: `fallback_model (SDTM_RAG_FALLBACK_MODEL) = '<模型串>': no pinned price — add the provider's official price to _PRICES in server/cost.py …` —— 写明设置项和模型。
3. **(新)** 可选模型的 id 与内部组撞名: 列进问题清单。这种配置以前在建 Router 时才报错; 现在算单轮上限要读回退表, 不先拦下会在自检里抛出另一种异常。
4. 每个可选模型: 显式的 `max_output_tokens` (原有); 有固定价格 (上一轮); **(改)** 单轮上限取「它自己」与「它回退到的档」里较贵的, 超过免费池的十分之一就拒绝。较贵的是回退档时, 报错写明回退档的模型和输出上限, 并指向 `SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS`; 是它自己时, 报错与原来相同。回退档没有固定价格时只报第 2 条那一句, 不再拿回退费率算出一个金额。
5. `security_headers_enabled` (原有)。

## 6. 测试串扰的修正 (只改测试)

`tests/test_p3_4_public_https.py::test_compose_env_wins_over_dotenv_same_key_and_case_variant` 用 `load_dotenv` 把小写的 `sdtm_rag_quota_trusted_proxies` 写进进程环境, 末尾用 `monkeypatch.delenv` 删 —— 对一个 monkeypatch 此前没有碰过的名字, 这样删会让它在收尾时把那个值「恢复」回来, 留给后面所有测试; 之后要建公开档应用的测试会被「大小写变体取值冲突」拒掉。
- 修法: 在 `load_dotenv` 之前先让 monkeypatch 登记这个名字 (设一次再删), 收尾时恢复的就是「不存在」。原测试自己的前提 (小写变体在 `load_dotenv` 之前不存在) 和全部断言不变。
- **更正上一份 checkpoint (§6 第 6 条) 的说法**: 那里写「两条测试」留下了环境变量。实际只有这一条、这一个小写键。另一条 (`…cannot_turn_the_global_rate_limit_off`) 的两个大写键在 `load_dotenv` 之前已经由 monkeypatch 设过, 收尾时会被清掉, 没有泄漏 —— 我先按「两条」写了修正, 撤回其中一条时守卫用例照样绿, 才发现它本来就没有问题, 已把那处多余的改动去掉。
- 证明: ① 倒序命令 `pytest tests/test_p3_4_public_https.py tests/test_p2_l3_instance.py tests/test_p2_9_public_e2e.py`: 修之前 (`ccac8eb` 的归档副本) `59 failed, 80 passed`, 修之后 `140 passed`; ② 文件末尾加守卫用例 `test_this_file_leaves_no_sdtm_rag_env_behind` (本文件跑完之后进程环境里的 `SDTM_RAG_*` 与跑之前相同, 不分大小写); ③ 变异 XT: 撤回修正 → 恰好红在守卫用例上 (`{'sdtm_rag_quota_trusted_proxies': '0.0.0.0/0'} == {}`)。
- 守卫用例的边界: 它检查的是「排在它前面的用例」, 单独挑几条跑时不保证; 本文件之外的泄漏它不管。

## 7. 验证 (代码 = `a2c9374`; 复核后只补了一条断言和一条变异 = `a567626`, `server/` 没有再动)

### 7.1 新增 / 改动的用例 (`tests/test_public_price_pin.py` 46 → 75 条)

| 要钉住的事 | 用例 | 两档 |
|---|---|---|
| 内部四档 / embedding 没有固定价格: 公开拒绝并报出设置项和模型; 私有照常启动 | `test_public_refuses_a_server_model_setting_without_a_pinned_price[…]` / `test_private_starts_with_the_same_unpinned_server_model_setting[…]` (各 5 组) | **各一组** |
| 上面那 5 个设置项就是「全部内部组 + embedding」(字面量对照 `_INTERNAL_GROUP_MODEL_FIELDS`) | `test_the_literal_field_list_is_every_internal_group_plus_embedding` | — |
| 公开档上调用不到的模型设置不检查 | `test_model_settings_nothing_calls_on_public_are_not_checked` | 公开 |
| 回退表取自 `_fallback_map`; hard / light / 回退档自己 / 普通模型串没有回退 | `test_the_router_fallback_table_is_what_the_meter_reads` | 共用 |
| 预留和单轮上限都取较贵的候选 (含经过真实的预留存储); 公开站现在的配置下数值不变 | `test_a_round_is_reserved_at_its_dearest_candidate` | 公开 |
| 开了计量的私有档、内置配置: 预留与改之前相同 | `test_private_default_config_reserves_what_it_did_before` | 私有 |
| 单轮上限覆盖回退模型和它的输出上限; 报错指向回退档; 阈值 (Haiku: 100,000 通过 / 120,000 被拒) | `test_public_bound_covers_the_fallback_model_and_its_output_cap` / `test_private_ignores_the_fallback_bound` | **各一条** |
| 公开档上不答题的内部档 (128000 输出) 不进单轮上限 | `test_groups_that_never_answer_on_public_are_not_in_the_round_bound` | 公开 |
| embedding 从固定表取价, 不经过 litellm; 前缀规则 (`openai/` 认、`azure/` 不认) | `test_the_embedding_model_is_priced_from_the_table`; 匹配规则那一组 25 → 31 组 | 共用 |
| 没有登记服务商的行只认本名, 不抛异常 | `test_a_row_of_an_unlisted_family_matches_its_bare_id_only` | 共用 |
| 可选模型 id 与内部组撞名: 报出来, 不崩 | `test_public_names_colliding_selectable_ids_instead_of_crashing` | 公开 |
| **没有在线价格表时** (新开解释器, 只用包内表): 公开站的整套模型配置通过; 回退档没有固定价格 → 公开报出设置项, 私有照常启动 | `test_public_cost_check_passes_without_the_online_price_map` 等 4 条改用公开站的模型配置; 新增 `test_public_names_the_unpinned_fallback_setting_without_the_online_price_map` / `test_private_starts_with_an_unpinned_fallback_without_the_online_price_map` | **各一条** |

### 7.2 变异 (`public_price_pin_mutations.py`, 在 `a567626` 的归档副本上)

`49/49 killed` (`a2c9374` 时 48 / 48; 复核后加 I10), 基线与还原后都是 `75 passed`。三个文件的 sha256 前 16 位: `cost.py b870f37e21242afd`、`instance.py 786162a0db295f97`、`quota.py aec66b6ae0bcfe67`。上一轮的 32 条 (锚点随代码更新) + 这次 17 条:

| 编号 | 变异 | 打红的预登记用例 |
|---|---|---|
| I4 | 内部四档和 embedding 不再要求固定价格 | 「公开拒绝设置项」 |
| I5 / I6 | embedding 不在检查里 / 回退档不在检查里 | 同上 |
| I7 | 单轮上限只看可选模型自己 | 「上限覆盖回退」 |
| I8 | 把不答题的内部档也算进单轮上限 | 「不答题的内部档不进上限」 |
| I9 | 回退档没有固定价格时仍拿回退费率算上限 | 离线场景「报出回退档设置项」 |
| Q13 / Q14 / Q15 | 预留不看回退 / 自检的估算不看回退 / 取最便宜的候选 | 「取较贵的候选」 |
| Q16 / Q17 | 回退候选沿用可选模型的输出上限 / 任何组都当成有回退 | 「回退表」 |
| C17 / C18 / C19 | 拿掉 embedding 这一行 / 价格少一位 / 服务商前缀写错 | 「内置模型都有固定价格」/「表 = 官方价」/ 匹配规则 |
| C20 | 服务商查不到时抛异常 | 「没有登记服务商的行」 |
| XT | 测试文件撤回串扰修正 | 守卫用例 |
| I10 | 可选模型 id 撞名时仍去估算 (回退表会抛 `ValueError`; 复核时审查者的存活变异) | 「撞名: 报出来, 不崩」 |

PRE (三个文件整个换回 `0a85a43` 的字节) 仍然红出 `selectable model 'm1': one answer round reserves $0.700 > free pool / 10 = $0.300`。

### 7.3 全量

| 环境 | 提交 | 结果 |
|---|---|---|
| 深度为 1 的克隆 + 独立 venv | `a2c9374` | 3642 passed / 0 failed / 61 skipped |
| 同上 | `a567626` (最终的测试) | 3642 passed / 0 failed / 61 skipped |

上一轮最终是 3612 (`4a53fe5`); 多出的 30 条 = 价格那份文件 29 条 + 守卫用例 1 条。

### 7.4 真实镜像里的离线对照 (2026-11-28 08:46Z, 部署虚拟机; 条件与上一轮相同)

镜像 `…/sdtm-rag:613f048…`; `--rm -i --network none --cap-drop ALL --security-opt no-new-privileges --memory 1g`, 不带 env 文件、不挂目录、不发布端口。输入 = §1 那份模型设置, 作为环境变量在脚本里设 (两把 key 和访客密钥是运行时拼的假值); 协调方没有读值的三项用 `p3_step3.3.md` 记的值 (`FALLBACK_MAX_OUTPUT_TOKENS=16000`、`WEB_SEARCH_ENABLED=false`、`EMBEDDING_DIM=1536`); `DEFAULT` / `HARD` / `LIGHT` 的输出上限不设 (生效值 128000, 与那边一样)。这次除了成本自检函数, 还调用了整个 `check_startup` (只读配置和本地路径)。

| | A: 镜像原样 (修之前) | B: 覆盖 `a2c9374` 的三个文件 |
|---|---|---|
| 载入的模块 | `/app/server/` 下三个, sha 同 `0a85a43` | `/tmp/ov/server/cost.py b870f37e21242afd`、`quota.py aec66b6ae0bcfe67`、`instance.py 786162a0db295f97` |
| litellm 价格表 | 包内表 2764 条, 没有 `claude-haiku-5-5` (`Temporary failure in name resolution`) | 同左 |
| 成本自检 | `["selectable model 'haiku-5-5': one answer round reserves $0.700 > free pool / 10 = $0.300 (lower its max_output_tokens)"]` | `[]` |
| 一轮答题的候选 | — | `('haiku-5-5', 'anthropic/claude-haiku-5-5', 16000, 0.07)`、`('default-fallback', 'anthropic/claude-haiku-5-5', 16000, 0.07)` |
| 单轮上限 / 免费池的十分之一 | 0.70 / 0.30 | 0.07 / 0.30 |
| embedding 每百万 token | 0.02 (litellm 包内表) | 0.02 (固定表) |
| `check_startup` | 拒绝启动 (同一句) | 通过 |

前后核对 (08:46:44Z / 08:46:48Z): 私有站 `/api/health` 200 / 200; `sdtm-rag-api`、`sdtm-rag-ui` 的启动时间 (`03:23:47…Z`、`03:23:57…Z`)、重启次数 0、镜像 `613f048` 不变; 全部容器的名单与状态和今天第一次核对时逐字相同 (公开容器仍是 `created`); 一次性容器已不存在; 没有未结束的 Actions 运行。没有碰公开容器、公开数据根、`/opt/sdtm-rag-public/`、隔离规则。今天这类一次性容器累计起了 5 次 (上一轮 3 次 + 这次 2 次)。

## 8. 独立审查 (规则 D; 同两位审查者, 固定提交 `a2c9374`, 审查期间分支没有动)

任务书 `../subagent_prompts/public_price_pin_reviewers.md` 第三轮 (只给事实、协调方的裁定和要审的问题)。

| 审查者 | 结论 | 分级 |
|---|---|---|
| 代码审查 (`oh-my-claudecode:code-reviewer`) | **PASS** | 没有要改才能合的; LOW 2、备注若干 |
| 安全审查 (`oh-my-claudecode:security-reviewer`) | **PASS** | 没有阻断项; 查出的都是改之前就有的 |

两位各自独立核对、结论一致的:
- **公开站那份配置下, 扩之后的启动自检通过**; `SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS` 取 108,000 通过、108,001 起被拒 (前提: 免费池是 3 美元、历史上限是 20000 —— 见本节末的说明)。
- **§2 的清单成立**: 公开档上服务端 key 只调得到答题 / 续写 (可选模型组, 可回退到 `default-fallback`) 和 embedding。两位都从出站接缝的调用点往回追, 并各自确认 `server/main.py` 构造引擎时没有传 `query_expansion` / `rerank_enabled`、公开档对内部组名 (含不带 `model` 时的默认值 `default`) 一律拒绝。安全审查者另试了 `model` / `corpus` / `dossier` / 自定义地址 / 自带 key 的各种组合, 没有能走到内部档的。不经出站接缝的付费调用只有 Cohere 重排 (公开档调不到) 和自带 key 的直连 (用户自己付费)。
- **预留覆盖回退是对的**: 预留时拿到的是组名; 回退表与交给 Router 的是同一个函数; 没有哪条路径预留变小 (新的预留 = 原来的估算与回退候选取较大者); embedding、直连调用、自带 key 的答题都没有被错加回退候选。
- **私有档**: 内置配置下各组的预留额新旧完全相同 (代码审查者在两个提交上对照, 另试了回退上限 128K、回退模型换成 Opus 4.7); 只有「开了计量 + 回退档比主模型贵」时预留变大。新增的检查只在公开档调用。
- **embedding 的价格**: 代码审查者自己取了 OpenAI 官方定价页 (`…/api/docs/pricing.md` 的 Standard 表 `text-embedding-3-small | $0.02`, 模型页 `Price $0.02`); 安全审查者这次没有重新取。
- **测试与变异**: 代码审查者在副本上复跑出 `48/48 killed`, 倒序命令 `ccac8eb` `59 failed, 80 passed` / `a2c9374` `140 passed`, 全量回归没有新增失败。`tests/test_p3_4_public_https.py` 只改了测试, 原断言的意图保留。没有新的敏感信息。

| # | 来源 / 级别 | 意见 | 处理 |
|---|---|---|---|
| 1 | 代码: 存活变异 Z6 (LOW) | 撞名时去掉「不再估算」那一行, 测试照样绿 | **已补** 断言和变异 I10 (`a567626`; 撞名的 id 与正常的 id 并存时, 回退表会抛 `ValueError`, 这条断言钉住「仍是列出问题的拒绝」)。这条断言没有再送审 |
| 2 | 代码 LOW | 回退上限恰好超出一点 (108,001) 时报错显示成 `$0.300 > $0.300` (金额只保留三位小数) | 没有改: 报错同时写明了是回退档和它的输出上限 |
| 3 | 安全 LOW (改之前就有) | 流式中途出错时 litellm 的 Router 带着已生成的内容改调回退模型; 它合并两段用量的代码取不到主模型那一段 (审查者实测), 主模型已生成的部分不进账, 整次调用可以到预留的约 2 倍。访客无法主动触发。按公开站的配置, 回退仍是 Haiku 5.5, 而 Claude 4.6 以后的模型不接受这种续写, 回退大概率直接失败、按全额预留扣 (这一点审查者没有核实) | 没有改, 记入 `todo_later` |
| 4 | 两位都提到 (改之前就有, 未核实) | 非流式调用超时 / 失败后 Router 重试再回退: 服务商若对超时的那次仍计费, 一次预留对应多次计费, 结算只看最后一次 | 没有改, 同上 (§3 末已写) |
| 5 | 安全 备注 | 站长若把回退档换成默认的 DeepSeek (32000 输出): 每次预留约 0.15–0.21 美元, 三四个 IP 就能用未结算的预留占满免费池。现在的配置不是这样 (而且部署机没有 DeepSeek 的 key) | 只记录: 换回退模型时同时调低 `SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS` |
| 6 | 代码 备注 | 守卫用例只管 `sdtm_rag_*`; 依赖自己排在文件最后 (被 `-k` 选掉、顺序被打乱、用 xdist 分进程时会漏报; 没有误报的情形) | 属实, §6 已写边界 |

两位都没能核实的: 部署机上 `SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS` 的实际值、每日总额上限和免费池有没有被 env 改过 (后一项其实有旁证: run 219 的真实验收容器照抄的就是公开站的环境变量, 它的报错是 `reserves $0.700 > free pool / 10 = $0.300` —— 免费池确实是 3 美元; 0.70 = 60000 × 5 + 16000 × 25 也与历史上限 20000、可选模型输出上限 16000 相符。所以真正没有读到的输入只剩回退档的输出上限); Router 真实回退时的行为 (没有发真实请求); 真实镜像里的离线对照 (审查者没有 docker, §7.4 仍只有实现者自己跑的一遍)。

## 9. 改动的文件 (相对上一轮的最终提交 `ccac8eb`)

| 文件 | 在部署路径过滤里 | 改动 |
|---|---|---|
| `server/cost.py` | 在 | 固定 `text-embedding-3-small`; 服务商前缀的查法不抛异常 |
| `server/quota.py` | 在 | `_call_candidates`; 预留取最贵的候选; `round_estimates` |
| `server/instance.py` | 在 | 内部四档 + embedding 的固定价格检查; 单轮上限覆盖回退档; 撞名 |
| `tests/test_public_price_pin.py` | 不在 | 46 → 75 条 (`a567626` 在其中一条里加了断言) |
| `tests/test_p3_4_public_https.py` | 不在 | 串扰修正 + 守卫用例 |
| `deploy/README.md`、`docs/design/P2_request_context.md`、`docs/retrospectives/…`、`.work/10_split_and_public/…` | 不在 | 文档、脚本、进度 |

按协调方定的合并方式 (快进、头提交带 `[skip ci]`): push 不触发任何运行; 之后手动「只构建 → 测试端口验证 → 部署」。

## 10. 仍未验证 / 留给后面的
- **`SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS` 的实际值** (≤ 108,000 才通过, §3); `SDTM_RAG_WEB_SEARCH_ENABLED`、`EMBEDDING_DIM` 的实际值同样没有读到, 这两项不影响成本自检。
- **没有网络的临时容器能否一路起到 healthy**: 仍然只验了启动自检 (这次是整个 `check_startup`), 没有挂数据起完整应用; 要等合并后第一次真实的公开部署。
- Anthropic / OpenAI / DeepSeek 在响应里回报的模型名的实际写法 (没有发真实请求)。
- 一次预留对应多次实际调用 (重试、流中途回退) 时费用之和可以超过预留 (§3 末, 改之前就有)。
- 联网检索的单价 `quota_web_search_usd` 在代码里一直标着未核实 (这次没有核; 免费题不联网)。
- 裁定二: provider registry 的模型能力位依赖在线表 —— 不做, 已记 `todo_later`。

## 提交 (这一轮新增; 分支 `hakupao/public-price-pin`, 基于 main `45fc1c6`; 没有 push)

| 提交 | 内容 |
|---|---|
| `a2c9374` `[skip ci]` | 启动自检扩到内部四档与 embedding; 预留与单轮上限覆盖回退模型; embedding 固定价; 测试串扰修正; 测试 75 条; 变异脚本与离线对照脚本 |
| `a567626` `[skip ci]` | 复核意见: 撞名情形的断言 + 变异 I10 |
| 之后的一个文档提交 `[skip ci]` (分支头) | 本文件; 上一份 checkpoint 的指引; README; 设计文档; 复盘; 进度与 trace; 审查任务书 |

红线检查: 同上一轮 (工作区没有 catalog, hook 按 `OIDSCAN_NO_CATALOG=1` 跳过; 每次提交前用主仓的 catalog 对暂存文件手动扫, 最后对整个分支改过的全部文件补扫, 都是 CLEAN)。
