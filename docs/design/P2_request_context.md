# P2 请求上下文接缝 (P2.0) — 出站清单 / 前后端契约 v1.2 / 分线归属

> 状态: **§2 契约 v1.2 已冻结** (2026-11-26, 分支 `p2`, P2.9 修正轮)。改契约 = 发新版本并通知 L1-L4, 不在某条线里顺手改。
>
> 变更记录: **v1** (2026-11-26) 首版。**v1.1** (2026-11-26, 独立复审 PASS-with-fixes 后) 断开时 settle 先于 finalize 且 finalize 后的 settle 必须 no-op;
> compare 拒绝上浮为请求级 4xx; `providers.log_processors()` 钩子 + rich traceback 关 show_locals; `route_corpus(None)` 保持旧兜底;
> 公开档未知模型的错误形态; L4 须容忍 `/api/info` 缺键; `/api/ask` 续写中途被拒丢弃半截答案; L2 存储线程安全; L1 跟进 Anthropic cache_control。
> **v1.2** (2026-11-26, P2.9 两份独立审查后; 证据 `.work/10_split_and_public/evidence/checkpoints/p2.9_fix.md`):
> ① 新拒绝码 `site_busy` (503 + `Retry-After` + `retry_after_s`: 进行中的预留占满额度, 已结算花费未到顶) 与 `storage_full` (507, `/api/flag` 日志满);
> `rate_limited` 另有三个来源 (每 IP 同时进行数、BYOK 错 key 次数、BYOK 附加调用每 IP 份额), 形状不变;
> ② **推翻 v1.1 一条**: `/api/ask` 续写轮被拒 ⇒ 保留已生成部分, `truncated=true` + `continue_error=<拒绝码>` (同续写普通失败); 首轮 / 重答轮被拒仍整体返回 4xx;
> ③ `quota.settle` 加仅关键字参数 `streamed_text` / `closed_early`: 流没带 usage 时按**怎么结束的**结算 (均不超过预留, 见 §3):
> 正常走完 = prompt + ceil(1.5 × 已流出); 我方 / 客户端提前关 = prompt + max(1.5 × 已流出, 已流出 + `quota_abort_buffer_tokens`=4096);
> 上游中途抛错 / 超时 / 未知异常 = 整笔预留; 开流被明确拒 (HTTP 4xx/5xx, 408/504 除外; 或连接没建立) = 只扣 prompt,
> 路由窄重试第一次 (`refund_open_error=True`) 被明确拒 = 不扣; 非流式调用失败仍扣整笔预留;
> ④ 免费题不联网的唯一归属 = L1 `providers.capability("web_tools")` 读 L2 键 `quota_free_web_enabled` (`quota.free_web_allowed`); L2 不再改写 `body.web`;
> 降级时 `done.web_status = "off"`; ⑤ `/api/info` 有额外键 / 公开档时带 `Cache-Control: no-store`; ⑥ §5 P3 就绪清单 (新增)。
> 计划: `.work/10_split_and_public/PLAN.md` §2 P2、§6。证据: `.work/10_split_and_public/evidence/checkpoints/p2.0_seam.md`。

接缝的形状:

```
endpoint (@request_scope) ── begin(): RequestContext{endpoint, request, tier, model, provider, credentials, quota, flags, notes}
   │                          (ContextVar 绑定; router.py 显式传 ctx, rag/federation/reviewer/compare 走 current())
   ├─ instance.check_request(ctx, body)    L3
   ├─ providers.check_model(ctx, s)        L1  (默认 = 原 known_model_groups 422)
   ├─ quota.admit(ctx, body)               L2  (检索与拼 prompt 之前; 可就地裁 body.history)
   ├─ 每次出站: outbound.{completion,acompletion,embedding,web_search}
   │     └─ providers.resolve(ctx, purpose, kind, router, kw) → (callable, kw)   L1
   │     └─ h = quota.reserve(ctx, purpose, kw) … quota.settle(ctx, purpose, h, usage, model)  L2
   └─ quota.finalize(ctx)  恰一次 (正常 / 异常 / 客户端断开)                       L2
```

默认实现与引入前逐字节一致 (特征测试 `tests/test_p2_seam_characterization.py` 的 golden 录于 main `36499a7`)。

## §1 服务器 key 出站调用清单

行号为 `p2` 分支 seam 提交后。「触发路径」= 哪个请求会走到。全部经 `server/outbound.py`, 除表末两行。

| # | file:line | 调用 | purpose | 触发路径 | 流式 |
|---|---|---|---|---|---|
| 1 | `server/router.py:647` | `Router.completion(model=body.model)` | `answer` / `continue` (触顶续写) / `regen` (研读包闸重答) | `/api/ask` | 否 |
| 2 | `server/router.py:927,933` | `Router.acompletion(stream=True, [tools])` (第二次 = 去掉 `stream_options` 的窄重试) | `answer` / `continue` / `regen`; 联网时同一 purpose 跑多轮工具 | `/api/ask_stream` | 是 |
| 3 | `server/router.py:1146` → `server/web_search.py:101` | Tavily `requests.post` | `web` | `/api/ask_stream` 且 `web=true` 且 `web_search_enabled` | 否 |
| 4 | `server/federation.py:104` | `Router.completion(model="light")` 判库 | `route` | `/api/ask`, `/api/ask_stream` 在 federation 开 + `corpus=auto` | 否 |
| 5 | `server/rag.py:761` | `litellm.embedding(text-embedding-3-small)` | `embedding` | 每次 `retrieve` (CDISC / study cards / study docs 各一次; 研读包 CDISC 补取; validate 2-3 次; compare 1 次) | 否 |
| 6 | `server/rag.py:1009` | `litellm.completion(expansion_model, temperature=0)` | `hyde` / `multiquery` | 仅 `query_expansion != none` (**生产 OFF**) | 否 |
| 7 | `server/reviewer.py:208` | `Router.completion(model="hard")` | `review` | `/api/validate` 且 `semantic_review=true` | 否 |
| 8 | `server/compare.py:59` | `litellm.acompletion(model=任意串)` ×N 并发 | `compare` | `/api/ask_compare` | 否 |
| 9 | `server/compare.py:232` | `litellm.acompletion(judge_model, temperature=0)` | `judge` | `/api/ask_compare` 且 `judge.enabled` | 否 |
| — | `server/rag.py:963` | Cohere `rerank` (SDK, 非 litellm) | — | 仅 `rerank_enabled` (**生产 OFF**), **不经接缝** | 否 |
| — | 启动期 | 无出站 (lifespan 只建索引 / 读文件) | — | — | — |

不在请求路径上的 (不经接缝, 不受影响): `scripts/ingest.py` (embedding), `eval/*` (直调 litellm / RAGEngine), `scripts/mine_implicit_relations.py`, `ui/streamlit_app.py` (只调本服务 HTTP)。这些地方 `current()` 为 None, 钩子必须原样放行。

开放项: Cohere rerank 不经接缝 —— 公开档 L3 须在启动期拒绝 `rerank_enabled=true` (或 L1 把它接进 outbound)。

## §2 前后端契约 v1.1 (冻结)

### 2.1 BYOK 请求头
| 头 | 含义 | 档位 |
|---|---|---|
| `X-LLM-Api-Key` | 用户自己的 provider key。只存浏览器 (独立 localStorage 键), 服务端不落盘、不写日志 | 两档 |
| `X-LLM-Api-Base` | 自定义 OpenAI 兼容地址 | **仅私有档**; 公开档带了 → 400 `custom_base_not_allowed` |

常量在 `server/providers.py` (`BYOK_KEY_HEADER` / `BYOK_BASE_HEADER`)。有 key 头 ⇒ 本请求**不回退到服务器 key** (2.6)。

头与 `provider` 字段的组合 (L1 实现, L4 照此发):

| key 头 | `provider` | 结果 |
|---|---|---|
| 无 | `null` | 服务器 key (免费题 / 私有站), `model` 取 `selectable_models` id |
| 有 | 注册表 id | BYOK, `model` 取该 provider 的模型 id; 不占免费题 |
| 有 | `null` | 400 `provider_required` (不猜 provider: 猜错 = 把 key 发给别家) |
| 无 | 非 `null` | 400 `byok_key_missing` (不静默改用服务器 key) |

### 2.2 请求体字段 (`/api/ask`, `/api/ask_stream`)
| 字段 | 取值 | 说明 |
|---|---|---|
| `provider` | `null` (默认, 服务器 key) 或 provider 注册表 id (`anthropic` `openai` `gemini` `deepseek` `qwen` `kimi` `glm` `siliconflow` …, 列表以 `/api/info.providers` 为准; 私有档另有 `custom`) | 已加进两个请求模型, 默认无作用 |
| `model` | 服务器 key: `/api/info.selectable_models[].id`; BYOK: `/api/info.providers[].models[].id` | 既有字段, 语义扩展 |

其余字段不变。`/api/ask` 仍是 `extra="forbid"` (未知字段 422)。

### 2.3 拒绝 (4xx/429) JSON 体
开流前: HTTP 状态码 + `{"detail": {"code": <str>, "message": <人读文案, 中文>, ...附加字段}}` (`ServiceRefusal`)。429 带 `Retry-After` 头 (秒)。

| code | 状态 | 附加字段 | 来源 |
|---|---|---|---|
| `free_quota_exhausted` | 429 | `remaining: 0`, `reset_at` (ISO8601) | L2 每访客每日免费题 |
| `site_cap_reached` | 429 | `reset_at` | L2 全站 $ 封顶 (免费题关, BYOK 照常) |
| `free_tier_disabled` | 503 | — | L2 紧急开关 |
| `rate_limited` | 429 | `retry_after_s` | L2 每分钟限流 (BYOK 也受) |
| `byok_key_invalid` | 401 | `provider` | L1 上游 401/403 |
| `byok_provider_error` | 502 | `provider`, `upstream_status` | L1 上游其它错误 (不含 key) |
| `model_not_allowed` | 422 | `allowed` (id 列表) | L1/L3 (公开档拒内部组 `default`/`hard`/`light`/`default-fallback`) |
| `custom_base_not_allowed` | 400 | — | L3 公开档 |
| `not_on_this_tier` | 403 | `feature` (`dossier` / `study_corpus` …) | L3 (公开档 `dossier="on"`、`corpus=study` 等) |
| `request_too_large` | 413 | `limit` | L2 2.2 请求体上限 (history 超限是**裁剪**不是拒: 服务端保留最近的轮次) |
| `provider_required` | 400 | — | L1, 见 2.1 组合表 |
| `byok_key_missing` | 400 | `provider` | L1, 见 2.1 组合表 |
| `site_busy` (v1.2) | 503 | `retry_after_s` (+ `Retry-After` 头) | L2: 进行中预留 (上界估算) 暂时占满池子, 已结算花费未到顶 ⇒ 稍后重试 (前端保留重试按钮, 不算额度类拒绝) |
| `storage_full` (v1.2) | 507 | — | L2 `/api/flag`: dogfood 日志达 `flag_file_max_bytes` |

`rate_limited` (429) 的来源 (v1.2 起): 每分钟限流 (访客 / IP)、每 IP 同时进行的计量请求数 (`quota_inflight_per_ip`, 默认 3)、BYOK 每 IP 每日错 key 次数
(`quota_byok_bad_key_per_ip_day`, 默认 20)、BYOK 附加 (服务器 key) 调用每 IP 每日份额 (`quota_byok_side_per_ip_usd`, 默认 $0.5)、BYOK 每日联网次数、`/api/flag` 每 IP 每日字节
(`flag_bytes_per_ip_day`)。

既有错误不变: 空问题 422 `{"detail": "question must not be empty"}`; 检索失败 502; LLM 失败 502。
未知模型: **私有档**保持旧形态 422 `{"detail": "unknown model …; known: […]"}` (字符串 detail); **公开档**未知 id 与内部组 id
(`default` / `hard` / `light` / `default-fallback`) 一律 422 `model_not_allowed` (对象 detail, `allowed` = 公开可选 id), 不区分"不存在"与"不给用"。
前端判别: `typeof detail === "object" && detail.code`, 否则把字符串 detail 当文案。

`/api/ask` (非流式) **续写轮**被拒 (`ServiceRefusal`, 例: 续写撞全站封顶) ⇒ **v1.2: 200 + 已生成部分**, `truncated=true`, `continue_error` = 拒绝码
(与续写普通失败同口径; v1.1 的"丢弃半截"已推翻: 已经花掉的钱换来的正文不该扔)。首轮被拒 (没有正文) 与**重答轮**被拒仍整体返回该 4xx/429。
流式端点已流出的 token 留在前端, 以 `error` 事件收尾。

### 2.4 SSE (`/api/ask_stream`)
**v1 不新增事件名** (`tests/test_sse_contract.py` 要求后端每个事件名前端都认得)。新信息挂在既有事件上:

| 事件 | 新键 | 何时出现 |
|---|---|---|
| `sources` | `downgrades: [{capability, reason, detail?}]` | 只在开流前已有降级时 (例: 所选模型不支持工具 ⇒ 联网关闭) |
| `done` | `downgrades: [...]` | 本次请求累计降级, 非空才有 |
| `done` | `quota: {free_remaining, free_per_day, reset_at, byok}` | L2 提供时才有 (`quota.response_fields`) |
| `error` | `code` + `message` (+ 2.3 的附加字段) | 流已开后 hook 拒绝 (例: 续写轮撞全站封顶)。旧的无 code 形态 `{"message": "LLM stream failed"}` 保留 |

`capability` 取值: `web_tools` (不支持工具 ⇒ 不联网), `vision` (不支持看图 ⇒ 不附 PDF 画面), `dossier_auto` (上下文太短 ⇒ 不自动挂研读包); `reason` 为短标识 (`no_tool_calling` / `no_vision` / `context_too_small` …), 前端按表出文案, 未知 reason 显示原值。
联网额度用尽沿用既有 `tool_result.status = "quota_exceeded"` (不杀流)。
免费题 (服务器 key, 公开档) **不联网** (PLAN Q2): 请求带 `web=true` 不报错, 服务端按 `web_tools` 降级 ——
`sources.downgrades` 含 `{capability: "web_tools", reason: "free_tier_no_web"}`, `done.web_status` 照旧。L4 发送前据
`/api/info.web_search` 与 `/api/info.quota.byok` 决定联网勾选框是否可用 (免费题下置灰 + 说明)。

`/api/ask` (非流式) 同义: 响应体可选键 `quota`、`downgrades` (只在有值时出现)。

### 2.5 剩余额度字段
`quota = {"free_remaining": int, "free_per_day": int, "reset_at": ISO8601, "byok": bool}` —— `done.quota`、`/api/ask` 的 `quota`、`/api/info.quota` 同一形状 (`/api/info` 里是该访客当前值)。私有档可不提供 (键缺失 = 无限额, 前端不显示)。

### 2.6 `/api/info` 按档位
| 键 | 私有档 | 公开档 |
|---|---|---|
| 既有全部键 (见 `InfoResponse`) | 原样 | 去内部字段: 不出现 `collection_name` `chunk_count` `fallback_model` `compare_models` `judge_model` `index_freshness_reason` `dossier_*` `federation` (L3 决定最终清单) |
| `tier` | `"private"` | `"public"` |
| `providers` | `[{id, label, byok: true, base_fixed: bool, models: [{id, label, capabilities: {tools, vision, context_tokens}}]}]` | 同左, 无 `custom` |
| `quota` | 可缺 | 2.5 形状 |

`selectable_models` 两档都在 (服务器 key 可选模型; 公开档只列公开模型 id)。
⚠ L4 必须容忍 `/api/info` **任何键缺失** (旧服务端 / 私有档 / L3 裁掉的键): 缺 `tier` 当 `private`, 缺 `providers` 不显示 BYOK 面板, 缺 `quota` 不显示额度。新增键由 `providers.info_fields` / `quota.info_fields` 提供, `instance.shape_info` 合成 (L3 可改形状)。

### 2.7 各档端点
| 端点 | 私有 | 公开 |
|---|---|---|
| `GET /api/health`, `GET /api/info`, `POST /api/ask`, `POST /api/ask_stream`, `POST /api/flag` (限大小/频率) | ✓ | ✓ |
| `POST /api/ask_compare`, `POST /api/validate`, `POST /api/validate-study` | ✓ | **不注册** (404) |
| `/docs`, `/openapi.json`, `/redoc` | ✓ | **关** |
| `/login` `/logout` (登录门) | 按配置 | 不用 (访客 = 签名 cookie) |
| Streamlit `ui` | ✓ | 不部署 |

## §3 分线归属与合并序

| 线 | 可改的文件 (独占) | 只读 / 不许改 |
|---|---|---|
| L3 实例档位 + 接口收口 (2.1/2.3) | `server/instance.py`, `server/main.py`, `server/config.py` (加 `instance` 等字段), `tests/test_p2_l3_*.py` | |
| L1 provider + BYOK (2.4/2.5/2.6) | `server/providers.py` (含 `log_processors()` 日志脱敏钩子, `main.py` 已调用, L1 不改 main.py), `server/llm_config.py`, `server/cost.py`, 新 `server/provider_registry*`, `tests/test_p2_l1_*.py` | `server/main.py` |
| L2 限额 (2.2/2.7 + 2.3 的 `/api/flag` 频率限制) | `server/quota.py`, `server/auth.py` (`/api/flag` 限频放在这里的 ASGI 中间件, 按路径), 新 `server/quota_store*` (SQLite 在 `data/`; ⚠ **必须线程安全**: `reserve/settle` 会从线程池调用 —— `/api/ask` 是同步端点跑在线程池, 联网检索走 `asyncio.to_thread`; 每线程独立连接或加锁, 计数用单条 SQL 原子更新), `tests/test_p2_l2_*.py` | `/api/flag` 的字段长度上限已在 `FlagRequest`; 写到 `data/` 挂载 = `dogfood_log_path` 配置 (L3) |
| L4 UI (2.8) | `webchat/**` only | 只按 §2 写, 不碰 `server/` |
| 全部 | | **`server/router.py`, `server/rag.py`, `server/federation.py`, `server/reviewer.py`, `server/compare.py`, `server/request_context.py`, `server/outbound.py`, 特征测试与其 golden** |

`config.py` 只有 L3 改; L1/L2 需要的新配置项写进各自 PR 说明, 由 L3 合入后补 (或在自己模块里用 `getattr(settings, "x", 默认)` 读)。真发现必须改 router.py 的地方 = 接缝缺口, 退回 P2.0 补 v1.1, 不在线里改。

合并序 **L3 → L1 → L2 → L4**; 每合一条跑全部零 LLM 闸 (pytest / node / 140q 逐题 / 特征测试)。特征测试 golden 只能因"默认档位行为有意变化"重录 (`P2_SEAM_REGEN=1`), 并在 PR 里写明哪一步变了。

各线必须守的接缝规则:
- 钩子收到 `ctx is None` (eval / scripts) 必须原样放行。
- 访客身份 / 设置从 `ctx.request` 取 (cookie、`CF-Connecting-IP`、`ctx.request.app.state.settings`); ⛔ 不读模块级 `server.config.settings` (与 app.state 可能不是同一份)。
- `quota.reserve` 返回的句柄原样回到同一次调用的 `settle`; `settle` 的 `model` = provider 报的模型 (Router 回退会改变它, 计价按它)。`route` / `review` / `embedding` / `hyde` 用的不是 `ctx.model`, 以 `reserve` 的 `kw["model"]` 与 `settle` 的 `model` 为准。
- 拒绝只用 `ServiceRefusal` (状态码 + §2.3 code); 其它异常类型会被各处兜底吞掉。
- v1.2: `quota.settle(ctx, purpose, handle, usage, model, *, streamed_text=None, closed_early=False)`。`outbound._metered` 记本次流已产出的文本
  (content + reasoning_content + 工具调用参数) 和结束方式。usage 缺失时: 正常耗尽 ⇒ `prompt 估算 + ceil(1.5 × 已流出)`; 提前关闭 (GeneratorExit /
  取消) ⇒ 至少 `已流出 + quota_abort_buffer_tokens` (provider 看到断开前还在生成); 上游异常 ⇒ 不传 `streamed_text` = 整笔预留 (模糊失败不打折)。
  开流失败: `outbound._clear_rejection` (HTTP 4xx/5xx 但非 408/504, 或 `httpx.ConnectError`) ⇒ `streamed_text=""` 只扣 prompt; 其余 (超时 / 取消 /
  读错误 / 未知) ⇒ 整笔。非流式失败扣整笔 (可能上游已生成后才失败, 我们没有可数的输出)。`finalize` / 过期仍按整笔预留扣。
- `quota.settle` 的 `usage` 可能为 None (调用失败 / 客户端提前停读), 也可能是 litellm **估算**值: 流结束时没收到 usage 片, litellm 就自己数 token 补一个 —— 上游中途断流 (分块传输缺结束块) litellm **不抛异常**, 也走这条 (BYOK 探针第 5 条)。`finalize` 结算未结清的预留。
- 顺序 (v1.1): 断开 / 循环体抛错时, 打开着的流先被关闭 (`aclosing` + `finalizing` 先 `aclose` 内层) ⇒ 它的 `settle` **先于** `finalize`。Starlette 断开时不主动关 `body_iterator`, 所以 `finalize` 在响应迭代器被关闭 / 回收时才跑 (CPython 下及时, 但不是同步于断开)。**`finalize` 之后到达的 `settle` 必须是 no-op** (按句柄幂等: 已结算或已被 finalize 按预留扣过的句柄不再计费)。
- BYOK 调用**不得**走带 `fallbacks` 的 Router 组 (探针: 逐次 `api_key` 会被带进回退目标 = 用户的 A 家 key 发给 B 家)。
- key 不得出现在日志里: v1.1 起 `main.py` 的 rich traceback 已关 `show_locals` (测试 `test_rendered_exception_log_line_has_no_frame_locals`), 但异常**消息**本身 (`str(e)` 进 `error=` 字段) 仍可能带 key (有的 SDK 把请求头写进报错)。L1 验收: 让上游带 key 报错, 经 `main.py` 配好的整条处理链**渲染出日志行**再 grep, 不许只测处理器函数的返回值。
- ⛔ 不序列化 ctx (`asdict` / `vars` / 当 log kwargs): repr 已遮罩, 字段没有。
- L1 跟进: BYOK 走 Anthropic 时 prompt cache (`cache_control`, 研读包布局) —— `_prompt_cache_capable` 按服务器配置的模型串判, BYOK 的 provider/model 不在其中; 需 L1 通过 `providers.resolve` 改写 messages 或经 v1.2 接缝处理, 并量缓存命中。

## §4 并行工作树配置 (实测可用)

```bash
git worktree add -b p2-l3 ../sdtm-rag-l3 p2        # 每线一个; 路径任意
cd ../sdtm-rag-l3
git submodule update --init --depth 1              # KB (CDISC)
uv sync --extra dev                                # 各自 venv
git config core.hooksPath                          # 已是 .githooks (worktree 共享主仓 config, 无需再设)
cp -R /Volumes/DevSSD/Project/sdtm-rag/data/study data/study   # 复制 (32M), 进 gitignored 的 data/study; pre-commit 闸要 catalog
export SDTM_RAG_CHROMA_DIR_OVERRIDE=/Volumes/DevSSD/Project/sdtm-rag/data/chroma   # 只读共享, 跑 140q 闸用
```

实测 (2026-11-26, 一次性工作树): 不放 `data/study` ⇒ hook 以 `catalog 不在本机` 拦下 (fail-closed, 正确)。
**符号链接不行**: hook 能过、`git status` 干净, 但 pytest 3 failed + 16 errors (`scripts/study/paths.py` 的
`out_dir 必须在 STUDY_DATA_ROOT 内` 安全检查对 resolve 后的路径报错; git 报 `pathspec … is beyond a symbolic link`)。
**复制可以**: hook 过、`git status` 干净、`pytest -m "not slow"` 2656 passed 0 failed。
⛔ 不许 `--no-verify`, 也不要用 `OIDSCAN_NO_CATALOG=1` 绕过。工作树里没有 `.env`: 测试不需要 (特征测试自己清掉
`SDTM_RAG_*` 环境变量); 要真起服务再单独处理。收尾 `git worktree remove` 会连同复制的研究数据一起删掉。

## §5 P3 就绪清单 (v1.2 新增)

公开档启动即校验 (fail-loud, `instance.check_startup` + `auth.install_security`), 下列任一不满足 ⇒ 拒绝启动:

| 要求 | 为什么 |
|---|---|
| 计量开着: `SDTM_RAG_QUOTA_ENABLED` 不设或为真 (布尔严格解析, `ture`/`y` 之类拒启动) | 关掉 = 免费题无上限 |
| `SDTM_RAG_QUOTA_*` / `VISITOR_*` / `FLAG_*` / `FREE_*` 无拼错的键 (`quota.validate`; 生效值启动时打日志, secret 只记 set/unset) | 拼错 = 静默用默认值 |
| `SDTM_RAG_VISITOR_SECRET` 已设 | 访客 cookie 签名 |
| `SDTM_RAG_QUOTA_TRUSTED_PROXIES` 已设且每段 ≥ /24 (IPv4) / ≥ /120 (IPv6) | 只信隧道连接器 (cloudflared) 一台主机; 更宽 = 同网段任何主机都能伪造 `CF-Connecting-IP` 冒充任意访客 |
| `SDTM_RAG_RATE_LIMIT_TRUST_FORWARDED` 不为真 | `X-Forwarded-For` 穿过隧道可被访客伪造; 公开档全局限流按 `CF-Connecting-IP` (仅可信代理来源) 计 |
| `SDTM_RAG_SELECTABLE_MODELS` 显式设置, 每个模型显式写 `max_output_tokens`, 且单轮预留 ≤ 免费池 / 10 (`quota.round_estimate_usd`: 历史上限 + 40k token prompt 余量 + max_output) | 内置清单是私有站的 Claude 128K 输出 (一轮 ≈ $3); 例: DeepSeek v4-pro 32000 输出 ≈ $0.21 ≤ $0.30 |
| `security_headers_enabled=true` | BYOK key 在浏览器 localStorage, CSP 是 XSS 的第二道防线 |

**部署要求 (P3.2 compose 落实, 本轮不改 compose)**: 公开容器的服务端口只绑 `127.0.0.1` 或专用 docker 网络, 不暴露到宿主机 LAN;
`SDTM_RAG_QUOTA_TRUSTED_PROXIES` 只写 cloudflared 容器 / 主机的那一个地址 (/32 或其所在的专用 /24 网络)。否则 LAN 上任何主机直连端口即可绕过隧道、伪造访客 IP。

**已裁 (主会话, 2026-11-26)**: 免费题每 IP 每日 30 题 (`quota_free_per_ip_day`) 与「每访客 10 题」并存 —— 接受; 换 cookie 的同一 IP 最多 30 题,
总量由免费池 $3 (= $5 封顶 − $2 BYOK 附加预算) 兜底。BYOK 附加调用每 IP 每日 $0.5 (≤ $2 池的 1/4: 至少 4 个 IP 才能耗尽; 够 30 次联网检索 $0.48 + embedding)。
