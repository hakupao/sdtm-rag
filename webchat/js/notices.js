// 拒绝 (§2.3) / 降级 (§2.4) / 剩余额度 (§2.5) 的文案 (zh + en) + 降级提示的一行渲染。
// 语言: 跟页面 <html lang> 走 (今天固定 zh); 只有本模块的新文案有英文, 不翻既有界面。
// ⚠ 形状校验全在这里: 字段经 SSE / localStorage 往返到达, 一抛异常死的是整段历史渲染。

export function pickLang(tag) { return String(tag || "").toLowerCase().startsWith("en") ? "en" : "zh"; }
export function uiLang() {
  try { return pickLang(globalThis.document?.documentElement?.lang); } catch (_) { return "zh"; }
}

const fmtTime = (iso) => {
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};
const str = (v) => (v === undefined || v === null ? "" : String(v));

const REFUSAL = {
  zh: {
    free_quota_exhausted: (d) => `今日免费额度已用完${d.reset ? ` (${d.reset} 重置)` : ""}。可在设置里填入自己的 API key 继续提问。`,
    site_cap_reached: (d) => `本站今日免费总额度已用完, 免费提问暂停${d.reset ? ` (${d.reset} 恢复)` : ""}; 填入自己的 API key 仍可使用。`,
    free_tier_disabled: () => "免费提问暂时关闭; 填入自己的 API key 仍可使用。",
    rate_limited: (d) => `请求太频繁, 请${d.retry ? ` ${d.retry} 秒后` : "稍后"}再试。`,
    byok_key_invalid: (d) => `API key 无效或无权限${d.provider ? ` (${d.provider})` : ""}。请在设置里检查或清除 key。`,
    byok_provider_error: (d) => `${d.provider || "服务商"} 返回错误${d.upstream ? ` (HTTP ${d.upstream})` : ""}, 请稍后再试。`,
    model_not_allowed: (d) => `所选模型不可用${d.allowed ? `。可选: ${d.allowed}` : ""}`,
    custom_base_not_allowed: () => "本站不支持自定义 API 地址。",
    not_on_this_tier: (d) => `本站不提供该功能${d.feature ? ` (${d.feature})` : ""}。`,
    request_too_large: (d) => `请求过大${d.limit ? ` (上限 ${d.limit})` : ""}, 请缩短问题或新开对话。`,
    provider_required: () => "请在设置里选择这个 API key 对应的服务商。",
    byok_key_missing: (d) => `已选服务商${d.provider ? ` ${d.provider}` : ""}, 但没有填 API key。`,
  },
  en: {
    free_quota_exhausted: (d) => `Today's free questions are used up${d.reset ? ` (resets at ${d.reset})` : ""}. Add your own API key in Settings to keep going.`,
    site_cap_reached: (d) => `The site's free budget for today is used up${d.reset ? ` (back at ${d.reset})` : ""}; your own API key still works.`,
    free_tier_disabled: () => "Free questions are temporarily off; your own API key still works.",
    rate_limited: (d) => `Too many requests — please retry${d.retry ? ` in ${d.retry}s` : " shortly"}.`,
    byok_key_invalid: (d) => `API key rejected${d.provider ? ` (${d.provider})` : ""}. Check or clear it in Settings.`,
    byok_provider_error: (d) => `${d.provider || "The provider"} returned an error${d.upstream ? ` (HTTP ${d.upstream})` : ""}; please retry later.`,
    model_not_allowed: (d) => `That model is not available${d.allowed ? `. Allowed: ${d.allowed}` : ""}`,
    custom_base_not_allowed: () => "Custom API base URLs are not supported on this site.",
    not_on_this_tier: (d) => `This feature is not available on this site${d.feature ? ` (${d.feature})` : ""}.`,
    request_too_large: (d) => `Request too large${d.limit ? ` (limit ${d.limit})` : ""}; shorten it or start a new chat.`,
    provider_required: () => "Pick the provider this API key belongs to in Settings.",
    byok_key_missing: (d) => `Provider${d.provider ? ` ${d.provider}` : ""} selected but no API key entered.`,
  },
};

// detail = §2.3 的 {code, message, ...}。未知 code ⇒ 服务端 message (再不行 code 原值)。
export function refusalText(detail, lang = uiLang(), retryAfter = null) {
  const d = detail && typeof detail === "object" ? detail : {};
  const code = typeof d.code === "string" ? d.code : "";
  const fn = (REFUSAL[lang] || REFUSAL.zh)[code];
  if (!fn) return str(d.message) || code || (lang === "en" ? "Request refused" : "请求被拒绝");
  return fn({
    reset: fmtTime(d.reset_at),
    retry: str(d.retry_after_s ?? retryAfter),
    provider: str(d.provider),
    upstream: str(d.upstream_status),
    allowed: Array.isArray(d.allowed) ? d.allowed.join(", ") : "",
    feature: str(d.feature),
    limit: str(d.limit),
  });
}

// 开流前的非 2xx 响应 → {text, detail}。detail 只在 §2.3 对象形态时非 null。
//   对象 + code   → 按表出文案
//   字符串 detail → 「服务错误 N: <detail>」(私有档未知模型 422 的旧形态)
//   其它 (FastAPI 校验错误数组 / 非 JSON) → 与 P2 前逐字相同的「服务错误 N」
export function httpErrorView(status, body, retryAfter = null, lang = uiLang()) {
  const det = body && typeof body === "object" ? body.detail : undefined;
  if (det && typeof det === "object" && !Array.isArray(det) && typeof det.code === "string") {
    return { text: refusalText(det, lang, retryAfter), detail: det };
  }
  if (typeof det === "string" && det) return { text: `服务错误 ${status}: ${det}`, detail: null };
  return { text: `服务错误 ${status}`, detail: null };
}

const CAPABILITY = {
  zh: { web_tools: "本次未联网", vision: "未附 PDF 画面", dossier_auto: "未自动挂载研读包" },
  en: { web_tools: "Web search off", vision: "PDF page images not attached", dossier_auto: "Study dossier not auto-attached" },
};
const REASON = {
  zh: { no_tool_calling: "所选模型不支持工具调用", no_vision: "所选模型不支持看图",
        context_too_small: "所选模型上下文太短", free_tier_no_web: "免费额度不联网, 填入自己的 API key 后可用" },
  en: { no_tool_calling: "the model has no tool calling", no_vision: "the model has no vision",
        context_too_small: "the model's context window is too small", free_tier_no_web: "free questions don't search the web; add your own API key" },
};

// 未知 capability / reason ⇒ 原值照显 (契约: 未知 reason 显示原值)。
export function downgradeLines(list, lang = uiLang()) {
  if (!Array.isArray(list)) return [];
  const caps = CAPABILITY[lang] || CAPABILITY.zh, reasons = REASON[lang] || REASON.zh;
  return list.filter((d) => d && typeof d === "object" && typeof d.capability === "string")
    .map((d) => {
      const r = typeof d.reason === "string" ? d.reason : "";
      const why = reasons[r] || r;
      return `⚠ ${caps[d.capability] || d.capability}${why ? `: ${why}` : ""}`;
    });
}

// 文案为空时在建任何元素之前返回 (同 renderDossierBadge): 没降级时 DOM 与 P2 前逐字节相同。
export function renderDowngrades(turn, list) {
  const old = turn.querySelector(":scope > .turn-note.downgrade");
  if (old) old.remove();   // sources 先画一次, done 汇总后覆盖
  const lines = downgradeLines(list);
  if (!lines.length) return;
  const el = document.createElement("div");
  el.className = "turn-note downgrade";
  el.textContent = lines.join(" · ");
  const meta = turn.querySelector(":scope > .turn-meta");
  if (meta) meta.insertAdjacentElement("afterend", el);
  else turn.appendChild(el);
}

// §2.5 剩余额度。缺失 / 形状坏 ⇒ null (= 不显示; 私有档无限额)。
export function quotaText(q, byokActive = false, lang = uiLang()) {
  if (!q || typeof q !== "object" || !Number.isFinite(q.free_remaining) || !Number.isFinite(q.free_per_day)) return null;
  if (byokActive || q.byok === true) return lang === "en" ? "Using your own API key" : "使用自己的 API key · 不占免费额度";
  const reset = fmtTime(q.reset_at);
  if (lang === "en") return `Free today: ${q.free_remaining}/${q.free_per_day}${reset ? ` · resets ${reset}` : ""}`;
  return `今日免费 ${q.free_remaining}/${q.free_per_day} 题${reset ? ` · ${reset} 重置` : ""}`;
}
