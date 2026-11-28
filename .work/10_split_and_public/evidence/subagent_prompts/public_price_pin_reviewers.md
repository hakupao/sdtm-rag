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
