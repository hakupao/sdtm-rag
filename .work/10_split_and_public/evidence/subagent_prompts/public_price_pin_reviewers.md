# 「公开档可选模型的价格固定进代码」的独立审查任务书 (2026-11-28)

两位审查者同时派出, 互不知道对方; 类型都与实现者 (orca worker, 主会话) 不同, 模型 opus。审查时的提交是 `97d6aa0` (范围 `45fc1c6..HEAD`)。
任务书只给事实和要审的问题, 没有给实现者的结论。结论与处理见 `../checkpoints/public_price_pin.md` 文末「审查」。

## 1. 代码审查 (`oh-my-claudecode:code-reviewer`)

你是独立代码审查者（规则 D：写的人和审的人不同）。请用中文汇报。只读审查，不要改工作区里的任何文件，不要 push / commit / 触碰远端、虚拟机、主仓目录 `<主仓路径>`。需要跑东西时，先 `git archive HEAD | tar -x -C <你自己的临时目录>` 出一份副本在副本里跑，解释器用工作区的 `<工作区>/.venv/bin/python`（不要重装依赖）。

### 仓库与范围
- 工作区：`<工作区>`（分支 `hakupao/public-price-pin`）。
- 审查范围：`git diff 45fc1c6..HEAD`（两个提交）。改动文件：`server/cost.py`、`server/quota.py`、`server/instance.py`、`tests/test_public_price_pin.py`、`.work/10_split_and_public/evidence/checkpoints/public_price_pin_mutations.py`、`.work/10_split_and_public/evidence/checkpoints/public_price_pin_offline_probe.py`。
- 先读 `CLAUDE.md` 和 `docs/RULES.md`（规则 5：变异验证及其失效方式）。

### 背景（事实，不是结论）
sdtm-rag 是 FastAPI RAG 服务，有私有档和公开档（`SDTM_RAG_INSTANCE=public`）。公开档有按美元计的每日花费上限（`server/quota.py`：每次调用先预留估算额、调用后按用量结算）。公开档启动自检 `server/instance.py::_public_cost_problems` 要求每个可选模型「一轮答题的最坏预留额 ≤ 免费池 / 10」。
2026-11-28 第一次公开部署失败：部署流程用一个**没有网络**的临时容器验收新镜像，公开站唯一的可选模型 `anthropic/claude-haiku-5-5`（输出上限 16000）不在 `server/cost.py` 写死的价格表里，价格靠 litellm 在 import 时联网取的在线价格表；取不到时 litellm 退回包内旧表（没有该模型），于是按回退费率 $5/$25 每百万 token 估成 $0.70 > $0.30，拒绝启动。失败记录：`.work/10_split_and_public/evidence/failures/p3_stageD_public_deploy_attempt_1.md`。
派给实现者的任务：把公开档可选模型的价格固定进代码（出处须是服务商官方定价页，不是 litellm、不是旧模型的价）；公开档遇到没有固定价格的可选模型时怎么办由实现者判断（倾向拒绝启动并报出模型）；**不得改变私有档行为**；不得改限额、免费池、回退费率的数值；不得让临时容器联网；加防回归测试并做变异验证。

### 请重点审（每条都要自己找证据，不要采信代码注释或提交信息里的说法）
1. **固定价格与官方页逐项一致吗？** 自己去取官方页核对（Markdown 版可直接 curl）：`https://platform.claude.com/docs/en/about-claude/pricing.md`（"Model pricing" 表与 "Long context pricing" 小节）和 `https://api-docs.deepseek.com/quick_start/pricing`。核对 `server/cost.py` 里 `_PRICES` 的每一行和 `_LONG_PROMPT_PRICES`，以及注释里对出处、分档规则的每一句描述是否属实。取不到页面就明说「未核实」。
2. **会不会把成本低估？**（低估 = 花费保护变弱，这是最要紧的一条。）逐条走查预留（`reserve` → `_estimate_parts` → `_price`）、结算（`settle` 的三个分支）、启动自检上限（`round_estimate_usd`）在分档模型上的行为；找出任何「实际计费比系统记的账高」的路径，包括：分档边界、提示词长度是估算值还是服务商回报值、`model` 参数在结算时是服务商回报的模型名（可能带日期后缀或与配置不同）、provider 前缀归一化、缓存读写 token 的计价、`estimate_cost` 的其他调用方（如对比徽章）。对每条说明是这次改动引入的、还是改之前就有的、还是被这次改动修好的。
3. **私有档行为是否不变？** 找出这次改动在私有档（含私有档打开 quota 的情形）下任何可观察的行为差异，哪怕是有意的；特别看 `_pinned_key` 把原来的宽松前缀匹配收紧成「本名或 `-YYYYMMDD` 后缀」这件事对原有四行（claude-sonnet-4-6 / claude-opus-4-7 / claude-haiku-4-5 / deepseek-v4-pro）的影响，以及仓库里是否有调用方或测试依赖旧的前缀行为。
4. **有没有别的启动路径仍然依赖联网？** 从 `server/main.py` 的 `create_app`、`lifespan`、`server/auth.py::install_security`、`scripts/check_index_freshness.py` 往下读，列出公开档在没有网络的容器里启动到 healthy 这一路上任何会联网、或结果随「取没取到 litellm 在线价格表」而变的地方（例如 `server/provider_registry.py` 从 litellm 表取模型能力）。区分「会让启动失败」「不会失败但行为变了」「无影响」。
5. **测试是否真的在测？** 审 `tests/test_public_price_pin.py`：有没有永真断言、测的是不是被改的那份代码、离线场景那个子进程夹具是否真的模拟了「litellm 没有在线价格表」；审变异脚本的框架有没有规则 5 里列的那几种失效（变异没打上、还原不干净、判定只看退出码）。请自己在副本上跑一遍变异脚本（跑法在脚本文件头），并**自己另想至少 5 个脚本里没有的变异**在副本上试，报告哪些存活。
6. 一般性的正确性、可读性问题，以及报错信息是否足够让运维知道该改哪里。

### 汇报格式
按严重度分级（CRITICAL / HIGH / MEDIUM / LOW / 备注），每条给：文件与行号、问题、你怎么验证的（命令与真实输出的关键行）、建议改法。最后给总评：PASS / PASS-with-fixes / FAIL，并单列「我没能核实的事项」。不要客套，不要复述代码。

## 2. 安全审查 (`oh-my-claudecode:security-reviewer`)

你是独立安全审查者（规则 D：写的人和审的人不同）。请用中文汇报。只读审查，不要改工作区里的任何文件，不要 push / commit / 触碰远端、虚拟机、主仓目录 `<主仓路径>`。需要跑东西时，先 `git archive HEAD | tar -x -C <你自己的临时目录>` 出一份副本在副本里跑，解释器用工作区的 `<工作区>/.venv/bin/python`（不要重装依赖）。

### 仓库与范围
- 工作区：`<工作区>`（分支 `hakupao/public-price-pin`）。
- 审查范围：`git diff 45fc1c6..HEAD`。改动文件：`server/cost.py`、`server/quota.py`、`server/instance.py`、`tests/test_public_price_pin.py`，以及 `.work/10_split_and_public/evidence/checkpoints/` 下的 `public_price_pin_mutations.py`、`public_price_pin_offline_probe.py`。
- 先读 `CLAUDE.md`、`docs/RULES.md`，以及 `server/quota.py` 文件头的生命周期说明。

### 背景（事实，不是结论）
这是一个即将对匿名访客开放的公开站（经 Cloudflare 隧道），站长自己出 API 费用。防线是 `server/quota.py` 的每日美元上限：每次走服务端 key 的调用先按估算预留、调用后按用量结算；公开档启动自检（`server/instance.py::_public_cost_problems`）要求每个可选模型一轮答题的最坏预留额 ≤ 免费池 / 10。
2026-11-28 第一次公开部署在**没有网络**的临时验收容器里失败：公开站的模型 `anthropic/claude-haiku-5-5`（输出上限 16000）的价格原先只能从 litellm 联网取的在线价格表得到，离线时退回 $5/$25 的回退费率，估成 $0.70 > $0.30 而拒绝启动。这次改动把价格固定进 `server/cost.py`，并让公开档对没有固定价格的可选模型拒绝启动。约束：不改私有档行为；不改限额、免费池、回退费率的数值；不让临时容器联网。

### 攻击者视角，请重点回答
1. **这次改动有没有让花费保护变弱？** 匿名访客（或很多个访客）能不能构造请求，让实际发生的 API 费用高于系统预留 / 记账的金额，从而突破每日上限？重点看：
   - Haiku 5.5 官方按提示词长度分两档（请自己取 `https://platform.claude.com/docs/en/about-claude/pricing.md` 核对档位与价格；取不到就明说）。预留用的提示词长度是 `_text_tokens` 的估算值，结算在有用量时用服务商回报值。走查 `reserve` / `settle`（三个分支）/ `finalize` / `round_estimate_usd`，找出预留低于实际、结算低于实际的路径；包括自动续写轮（提示词逐轮变长）、流中断没有用量、litellm 自己合成的用量、`model` 是服务商回报的名字时查不到固定价格而落到别的价格来源的情形。
   - `_pinned_key` 的匹配规则（本名或 `-YYYYMMDD` 后缀）能否被绕过或误配，让一个更贵的模型按更便宜的固定价格记账（provider 前缀归一化 `split("/",1)[-1]`、大小写、BYOK 路径与服务端 key 路径共用这张表的后果）。
   - 公开档启动自检只检查「可选模型」。内部四档（default / default-fallback / hard / light）的模型串、embedding 模型、Router 回退到的模型，价格从哪来？在没有固定价格、又取不到在线表时，按回退费率 $5/$25 记账是否一定偏保守（有没有官方价高于 $5/$25 的模型会因此被低估）？这属于改动之前就有的问题还是新引入的，请分清。
2. **这次改动有没有让拒绝服务更容易？** 分档模型现在一律按高档预留（比按低档多 5 倍）。结合 `quota_site_cap_usd`、`quota_byok_side_budget_usd`、`quota_inflight_per_ip`、`quota_byok_side_per_ip_usd` 的默认值算一算：一个 / 少数几个 IP 靠并发的未结算预留把免费池占满（`site_busy`）所需的并发数，改动前后各是多少；是否构成值得处理的问题。
3. **报错信息与日志**：新增的启动报错把模型 id 和模型串写进 RuntimeError，这条报错会被部署流程带进 CI 日志（`deploy/kbsync/kbsync.py` 的 `_sanitize_log` 之后）。有没有泄露敏感内容的可能。
4. **留档脚本**：`public_price_pin_offline_probe.py` 会经标准输入送进生产镜像的一次性容器执行（`--network none --cap-drop ALL`，不挂载、不带 key）；`public_price_pin_mutations.py` 会改文件再还原。看有没有危险写法（路径拼接、对工作区的破坏性操作、把凭据带进输出）。
5. 密钥卫生：整个 diff 里有没有口令、token、用户名、邮箱、内网地址之外的敏感信息；测试里的假密钥是否是运行时拼接的写法。
6. **没有网络时启动还依赖什么**：读 `server/main.py`（`create_app`、`lifespan`）、`server/auth.py::install_security`、`server/provider_registry.py`，列出任何结果随「litellm 取没取到在线价格表」而变的安全相关行为（例如模型能力位、输出上限的来源）。

### 汇报格式
按严重度分级（CRITICAL / HIGH / MEDIUM / LOW / 备注），每条给：文件与行号、攻击或失效场景（具体到输入与数字）、你怎么验证的（命令与真实输出的关键行，或逐行推演）、是这次改动引入 / 改之前就有 / 被这次改动修好、建议改法。最后给总评：PASS / PASS-with-fixes / FAIL，并单列「我没能核实的事项」。不要客套，不要复述代码。

---

# 第二轮: 审查之后的修正送回复核 (同两位审查者, 续用各自的上下文; 范围 `git diff 97d6aa0..769f03f -- server/ tests/test_public_price_pin.py`)

## 代码审查

请复核审查之后的修正（只读，规则同上次；中文简短汇报）。范围：`git diff 97d6aa0..HEAD -- server/ tests/test_public_price_pin.py`（HEAD 现在是 769f03f；代码最后一次改动在 a464243）。
改了什么（请自己看 diff 核对，不要采信这段描述）：① `server/cost.py::_pinned_key` 加了服务商前缀限制；② `server/quota.py` 新增 `_settle_price`，`settle` 的两个分支改用它——注意它没有照你建议的「直接改用 entry.model 的固定价」，而是在回报的名字不在表里、所预留模型在表里时取两者中较高的；③ `server/instance.py` 报错文字；④ 测试补了你那两条存活变异（X2、X3）对应的断言，变异脚本加了 9 条。
只回答三个问题，每个给证据（命令和关键输出，或逐行推演）：
1. 这段 diff 有没有引入新的「实际计费高于系统记账」的路径？特别看 `_settle_price` 的条件（`model and model != reserved_model and …`）在这些情形下的结果：回报名字是所预留模型的日期快照；Router 回退到在表里的另一个模型；回退到不在表里的模型；`model` 为 None；回报名字带服务商前缀（如 `anthropic/claude-haiku-5-5` 对所预留的 `anthropic/claude-haiku-5-5`，以及回报裸名对所预留带前缀名）。取「较高者」相对于你原来的建议，有没有哪种情形反而更差？
2. 相对 97d6aa0，私有档（含开了计量的私有档）有什么新的可观察差异？
3. 新增的测试和变异有没有不在测东西的；你另想 3 个针对这段 diff 的变异在副本上试，报告存活的。
最后给：PASS / PASS-with-fixes / FAIL。

## 安全审查

请复核审查之后的修正（只读，规则同上次；中文简短汇报）。范围：`git diff 97d6aa0..HEAD -- server/ tests/test_public_price_pin.py`（HEAD 现在是 769f03f；代码最后一次改动在 a464243）。
改了什么（请自己看 diff 核对，不要采信这段描述）：① 针对你的 LOW-4，`server/cost.py::_pinned_key` 加了服务商前缀限制；② `server/quota.py` 新增 `_settle_price`，`settle` 的两个分支改用它：服务商回报的模型名不在固定表里、而这次调用所预留的模型在表里时，取「按回报名字算出的价」与「所预留模型的固定价」中较高的；③ `server/instance.py` 报错文字。
只回答三个问题，每个给证据（命令和关键输出，或逐行推演）：
1. 前缀限制能否被绕过或误伤：大小写、空白、多段前缀（`a/b/claude-…`）、空前缀（`/claude-…`）、`_PINNED_PROVIDERS[key.split("-", 1)[0]]` 会不会抛异常（例如将来加了别家的行）；公开站现在的模型串 `anthropic/claude-haiku-5-5` 和服务商在响应里可能回报的裸名 `claude-haiku-5-5` 是否都仍命中。
2. `_settle_price` 有没有引入新的少记路径，或让攻击者能影响记账的输入（`model` 来自上游响应）；它在「回报名字带前缀 / 不带前缀与所预留名字不一致」时的行为；取较高者会不会造成值得在意的多记（例如把免费池更快耗尽）。
3. 这段 diff 有没有新的敏感信息或危险写法。
最后给：PASS / PASS-with-fixes / FAIL。

---

# 第三轮: 扩展部分 (固定提交 `a2c9374`, 审查期间分支不动; 结论见 `../checkpoints/public_price_pin_ext.md` 文末「复核」)

## 代码审查 (范围 `git diff ccac8eb..a2c9374 -- server/ tests/ .work/10_split_and_public/evidence/checkpoints/public_price_pin_mutations.py`)

请复核这次新增的部分（只读，规则同前两次；中文汇报）。固定提交：`a2c9374`；范围见上。审查期间分支不会动。
背景（协调方的裁定，事实）：上一轮你和安全审查者都建议把公开档启动自检扩到「会走服务端 key 的全部模型」，并指出预留是按可选模型算的、Router 回退到的模型可能更贵或输出上限更大。这次照此做了，另外顺带修了 `tests/test_p3_4_public_https.py` 把环境变量留给后面测试的问题（只改测试）。公开站实际的模型配置（协调方只读看过部署机 env 的非密钥项）：default/hard/light/fallback 四档都是 `anthropic/claude-haiku-5-5`；可选模型只有 `haiku-5-5`（同一模型串，max_output_tokens 16000）；embedding `text-embedding-3-small`；rerank 关；env 里设了 `SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS`（值没有读，旧记录是 16000）；DEFAULT/HARD/LIGHT 的输出上限没有设（内置 128000）；没有 DeepSeek 的 key；没有设 EXPANSION_MODEL / JUDGE_MODEL / COMPARE_MODELS。
请回答（每条给证据：命令与关键输出，或逐行推演；不要采信代码注释和提交信息）：
1. **在上面那份公开站配置下，扩之后的启动自检会不会拒绝启动？** 自己构造这份 Settings 跑 `instance.check_startup`；并算出 `SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS` 取多大时会被拒（这个值协调方没读到）。
2. **公开档一轮答题里走服务端 key 的模型调用是否列全了？** 实现者的结论是：只有「答题 / 续写（可选模型组，Router 可回退到 default-fallback 组）」和「embedding」两种；查询扩写（expansion_model，hyde / multiquery）、判库（light）、重答（regen）、review（hard）、compare / judge、rerank 在公开档都调用不到；联网检索（Tavily）不是模型，按固定设置计价。请独立从 `server/outbound.py` 的 PURPOSES 和各调用点往回追，逐项确认或反驳，并找有没有不经 `outbound` 的付费调用。特别核对：`server/main.py` 构造 `RAGEngine` 时是否把 `query_expansion` / `rerank_enabled` 传进去；公开档对 `model="default"` 等内部组名的请求是否确实被拒。
3. **预留覆盖回退（`quota._call_candidates` / `_estimate_parts` / `round_estimates`）对不对？** 预留时 `kw["model"]` 是不是组名（`providers.resolve` 之后）；回退表是否确实取自 `llm_config._fallback_map`、与 `create_router` 给 Router 的是同一张；per-call `max_tokens` 存在时的行为；BYOK、embedding、不经 Router 的直连调用（llm_router=None）会不会被错误地加上回退候选；有没有哪条路径预留反而变小了。
4. **私有档行为差异**（含开了计量的私有档）：相对 `ccac8eb` 有哪些可观察差异？`_public_cost_problems` 里新增的「可选模型 id 与内部组撞名」那一条会不会影响私有档或改变原有报错。
5. **embedding 的固定价**：自己取 OpenAI 官方定价页核对 `text-embedding-3-small`（`https://platform.openai.com/docs/pricing`，会跳到 developers.openai.com；取不到就明说未核实）；`_pinned_provider` 的匹配有没有漏洞。
6. **测试与变异**：新增用例有没有不在测东西的；在副本上跑变异脚本（跑法见脚本文件头；这次应是 48 条含 PRE 和 XT）；自己另想至少 5 个针对这段 diff 的变异，报告存活的。`tests/test_p3_4_public_https.py` 的修正是否只改了测试、原有断言的意图是否保留；守卫用例 `test_this_file_leaves_no_sdtm_rag_env_behind` 有没有误报 / 漏报的情形；倒序命令 `pytest tests/test_p3_4_public_https.py tests/test_p2_l3_instance.py tests/test_p2_9_public_e2e.py` 在 ccac8eb 与 a2c9374 上各是什么结果。
最后给：PASS / PASS-with-fixes / FAIL，并单列「我没能核实的事项」。

## 安全审查 (范围 `git diff ccac8eb..a2c9374 -- server/ tests/`)

请复核这次新增的部分（只读，规则同前两次；中文汇报）。固定提交：`a2c9374`；范围见上。审查期间分支不会动。
背景（协调方的裁定，事实）：上一轮你的 LOW-1 建议把公开档启动自检扩到会走服务端 key 的全部模型；代码审查者另指出预留按可选模型算、Router 回退到的模型可能更贵或输出上限更大。这次照此做了。公开站实际的模型配置（同上一份任务书的那一段）。
攻击者视角，请回答（每条给证据：命令与关键输出，或逐行推演）：
1. **公开档上，匿名访客还能让服务端 key 调用到哪些模型？** 实现者的结论：只有「答题 / 续写（可选模型组，Router 可回退到 default-fallback 组）」和「embedding」；查询扩写（expansion_model）、判库（light）、重答（regen）、review（hard）、compare / judge、rerank 都调用不到；联网检索对免费题关闭、对自带 key 的请求按固定设置计价并有每访客每日次数上限。请独立核对：有没有请求参数（`model`、`corpus`、`dossier`、`web`、自带 key 的各种组合、畸形输入）能让公开档走到这些内部档或别的付费调用；有没有不经 `server/outbound.py` 的付费调用。
2. **预留覆盖回退之后，还有没有「实际计费高于预留」的路径？** 看 `quota._call_candidates` / `_estimate_parts`：Router 回退（含 num_retries=1 的重试、流中途回退）时一次预留对应的实际调用可能不止一次——主模型已经生成了一部分再回退，这部分费用在不在账里、会不会超出预留；结算是按回报的模型名和用量记的，哪种情形下记的账会少于实际。区分这次引入 / 改之前就有 / 被这次修好。
3. **扩之后的检查能不能被配置绕过或造成误拒？** 例如模型串的各种写法（前缀、大小写、空白）、`SDTM_RAG_SELECTABLE_MODELS` 里与内部组撞名的 id、把 fallback 设成比可选模型贵得多的模型并配很大的输出上限、`quota_site_cap_usd` / `quota_byok_side_budget_usd` 的极端取值。在上面那份公开站配置下它会不会拒绝启动；`SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS` 取多大会被拒。
4. **拒绝服务**：预留现在取候选里最贵的。按公开站配置（回退档与可选模型相同）这一条不改变预留额；请确认，并说明如果站长把回退档换成默认的 DeepSeek（32000 输出）会变成多少、占满免费池需要的并发是多少。
5. 新增报错把设置项名和模型串写进 RuntimeError（会经 `_sanitize_log` 进 CI 日志）；embedding 的固定价与 `_pinned_provider`；`tests/test_p3_4_public_https.py` 的修正（只改测试）——有没有敏感信息或危险写法。
最后给：PASS / PASS-with-fixes / FAIL，并单列「我没能核实的事项」。
