# P2 step 2.5 BYOK 探针 (2026-11-26, litellm 1.88.1 = uv.lock)

零花费、零真实 key: 本机回环桩服务器按 OpenAI / Anthropic / Gemini 线格式应答并记录收到的鉴权头与请求体;
所有 provider key 环境变量在 import litellm 之前设为哨兵 (`env-sentinel-*`, litellm import 时的
`load_dotenv()` 不覆盖已设变量, 且从无 `.env` 的目录运行)。若某次 `api_base` 没生效, 请求会带哨兵 key 打到
真 provider (401, 不花钱)。

## 复跑

```bash
cd /tmp && /Volumes/DevSSD/Project/sdtm-rag/.venv/bin/python -I \
  /Volumes/DevSSD/Project/sdtm-rag/.work/10_split_and_public/evidence/probes/p2_byok_probe.py
```
退出码 0; 14 行 JSON, 本次原始输出 `evidence/probes/p2_byok_probe_output.jsonl` (`grep -c env-sentinel` = 0:
没有任何一次请求用上环境 key)。

## 结论

| # | 问题 | 结果 (桩实际收到的) |
|---|---|---|
| 1 | Router 路径逐次 `api_key`/`api_base` 生效? | **是**。deployment 只有模型串 + `max_tokens` (与 `llm_config.create_router` 同形), 逐次传 key/base ⇒ 桩收到 `Bearer byok-openai` / `x-api-key: byok-anthropic`; deployment 的 `max_tokens` 照样带上 |
| 2 | 直调 (`litellm.acompletion` / `aembedding`) 生效? | **是**, OpenAI / Anthropic / Gemini (`x-goog-api-key`) / DeepSeek / OpenAI 兼容国内预设 (`openai/<model>` + 固定 `api_base`) / embedding 全部收到用户 key |
| 3 | **逐次 key 与 Router fallbacks** | ⚠ **key 跟着走进回退目标**: 主组 500 ×2 (num_retries=1 重试也带用户 key) 后回退到 `default-fallback` (DeepSeek, 另一 base), 桩收到的仍是 `Bearer byok-primary` ⇒ 用户给 A 家的 key 被发给 B 家。⇒ **BYOK 必须绕开带 fallbacks 的 Router 组** (直调 litellm 或无 fallbacks 的专用 Router) |
| 4 | 流式 usage 回来? | OpenAI / DeepSeek / 国内兼容: 请求体带 `stream_options.include_usage`, 末片 usage 回来。Anthropic: litellm **不转发** `stream_options` (原生 `message_start`/`message_delta` 自带 usage), usage 照样回来。Gemini: 原生 `usageMetadata`, 回来 |
| 5 | 上游中途断流 | litellm **不抛异常**, 流正常结束, 且 **usage 是 litellm 自己估算的** (OpenAI 例: 真 prompt 11 → 报 8, completion 1; Anthropic 例: prompt 来自 `message_start` 的 11, completion 1, 正文为空)。⇒ 断流看起来像成功且有 usage; 结算不能把它当 provider 实报, 也不能把"有 usage"当"答完了" |
| 6 | 客户端提前停止消费 | 拿不到 usage (None) ⇒ 只能按预留扣 (2.7 "中断流按预留扣") |

## 对 P2.0 接缝的影响 (已落实)

- `providers.resolve` 返回 **(callable, kwargs)** 而不只是 kwargs: L1 可为 BYOK 换掉 Router (第 3 条)。
- `quota.settle(usage)` 的 usage 可能为 None 或为估算值; `quota.finalize` 恰一次兜底 (第 5、6 条)。
- 流式结算在 `outbound._metered` 里取最后一个 usage 片 —— 与 router.py 的 `cu_round` 同口径。

## 未覆盖 (L1 跟进)
真 provider 行为 (桩只证 litellm 的拼法与转发); Gemini / 国内 provider 的工具调用格式; Anthropic prompt cache 与 BYOK 共存。
