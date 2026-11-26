import test from "node:test";
import assert from "node:assert/strict";
import { pickLang, refusalText, httpErrorView, downgradeLines, renderDowngrades, quotaText } from "../js/notices.js";

const hhmm = (iso) => { const d = new Date(iso); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
const RESET = "2026-11-27T00:00:00Z";

test("pickLang: en* ⇒ en, 其它一律 zh (页面今天是 lang=zh)", () => {
  assert.equal(pickLang("en"), "en");
  assert.equal(pickLang("en-US"), "en");
  assert.equal(pickLang("zh"), "zh");
  assert.equal(pickLang(undefined), "zh");
  assert.equal(pickLang("ja"), "zh");
});

test("§2.3 每个 code 都有 zh 与 en 文案, 且不是 code 原样回显", () => {
  const codes = ["free_quota_exhausted", "site_cap_reached", "free_tier_disabled", "rate_limited",
    "byok_key_invalid", "byok_provider_error", "model_not_allowed", "custom_base_not_allowed",
    "not_on_this_tier", "request_too_large", "provider_required", "byok_key_missing",
    "site_busy", "storage_full"];
  for (const lang of ["zh", "en"]) {
    for (const code of codes) {
      const t = refusalText({ code, message: "SERVER_MSG" }, lang);
      assert.ok(t && t !== code && !t.includes("SERVER_MSG"), `${lang}/${code}: ${t}`);
    }
  }
});

test("site_busy (v1.2) 带重试秒数, 且不算额度类拒绝 (重试按钮保留)", async () => {
  const { isQuotaRefusal } = await import("../js/notices.js");
  assert.ok(refusalText({ code: "site_busy", retry_after_s: 15 }, "zh").includes("15 秒"));
  assert.ok(refusalText({ code: "site_busy" }, "en", "15").includes("15s"));
  assert.equal(isQuotaRefusal({ code: "site_busy" }), false);
  assert.equal(isQuotaRefusal({ code: "site_cap_reached" }), true);
});

test("429 文案带重置时间 / 重试秒数; Retry-After 头兜底", () => {
  const zh = refusalText({ code: "free_quota_exhausted", remaining: 0, reset_at: RESET }, "zh");
  assert.ok(zh.includes("今日免费额度已用完") && zh.includes(hhmm(RESET)) && zh.includes("API key"), zh);
  const en = refusalText({ code: "free_quota_exhausted", reset_at: RESET }, "en");
  assert.ok(en.includes("free questions") && en.includes(hhmm(RESET)), en);
  assert.ok(refusalText({ code: "rate_limited", retry_after_s: 7 }, "zh").includes("7 秒"));
  assert.ok(refusalText({ code: "rate_limited" }, "en", "12").includes("12s"));
  assert.ok(refusalText({ code: "site_cap_reached", reset_at: RESET }, "zh").includes("本站今日免费总额度"));
  assert.ok(refusalText({ code: "model_not_allowed", allowed: ["a", "b"] }, "zh").includes("a, b"));
  assert.ok(refusalText({ code: "byok_provider_error", provider: "deepseek", upstream_status: 500 }, "en").includes("HTTP 500"));
});

test("未知 code ⇒ 服务端 message; 再没有 ⇒ code 原值; 畸形 detail 不抛", () => {
  assert.equal(refusalText({ code: "brand_new", message: "新拒绝" }, "zh"), "新拒绝");
  assert.equal(refusalText({ code: "brand_new" }, "zh"), "brand_new");
  assert.equal(typeof refusalText(null, "zh"), "string");
  assert.equal(typeof refusalText({ code: "free_quota_exhausted", reset_at: "garbage" }, "zh"), "string");
});

test("httpErrorView: 对象 detail / 字符串 detail / 其它 三种形态", () => {
  const r = httpErrorView(429, { detail: { code: "free_quota_exhausted", reset_at: RESET } }, "3600", "zh");
  assert.ok(r.text.includes("今日免费额度已用完"));
  assert.equal(r.detail.code, "free_quota_exhausted");
  // 私有档未知模型 422 的旧形态: 字符串 detail 当文案
  assert.deepEqual(httpErrorView(422, { detail: "unknown model x" }), { text: "服务错误 422: unknown model x", detail: null });
  // FastAPI 校验错误数组 / 非 JSON / 无 body ⇒ 与改前逐字相同
  assert.deepEqual(httpErrorView(422, { detail: [{ loc: ["body"] }] }), { text: "服务错误 422", detail: null });
  assert.deepEqual(httpErrorView(502, null), { text: "服务错误 502", detail: null });
  assert.deepEqual(httpErrorView(500, "junk"), { text: "服务错误 500", detail: null });
});

test("downgradeLines: 已知按表出文案 (zh/en), 未知 reason / capability 原值照显", () => {
  const list = [{ capability: "web_tools", reason: "no_tool_calling" },
                { capability: "web_tools", reason: "free_tier_no_web" },
                { capability: "vision", reason: "no_vision" },
                { capability: "dossier_auto", reason: "context_too_small" },
                { capability: "web_tools", reason: "weird_reason" },
                { capability: "teleport", reason: "nope" }];
  const zh = downgradeLines(list, "zh");
  assert.equal(zh[0], "⚠ 本次未联网: 所选模型不支持工具调用");
  assert.ok(zh[1].includes("免费额度不联网"));
  assert.equal(zh[2], "⚠ 未附 PDF 画面: 所选模型不支持看图");
  assert.equal(zh[3], "⚠ 未自动挂载研读包: 所选模型上下文太短");
  assert.equal(zh[4], "⚠ 本次未联网: weird_reason");
  assert.equal(zh[5], "⚠ teleport: nope");
  const en = downgradeLines(list, "en");
  assert.equal(en[0], "⚠ Web search off: the model has no tool calling");
  assert.equal(en[2], "⚠ PDF page images not attached: the model has no vision");
});

test("downgradeLines: 畸形输入 ⇒ [], 绝不抛", () => {
  for (const bad of [null, undefined, "x", 3, {}, [null, "s", 4, { reason: "r" }]]) {
    assert.deepEqual(downgradeLines(bad), []);
  }
});

// 最小 DOM: 只要 renderDowngrades 用到的那几样
class El {
  constructor(tag) { this.tagName = tag; this.children = []; this.parentNode = null; this.className = ""; this.textContent = ""; }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  insertAdjacentElement(_pos, c) { const p = this.parentNode; c.parentNode = p; p.children.splice(p.children.indexOf(this) + 1, 0, c); return c; }
  remove() { const p = this.parentNode; if (p) p.children.splice(p.children.indexOf(this), 1); this.parentNode = null; }
  querySelector(sel) {
    const want = sel.replace(":scope >", "").trim().split(".").filter(Boolean);
    return this.children.find((c) => want.every((w) => c.className.split(" ").includes(w))) || null;
  }
}
globalThis.document = { createElement: (t) => new El(t) };

test("renderDowngrades: 没降级不建任何元素; 有降级挂在 .turn-meta 之后; 重画覆盖不叠加", () => {
  const turn = new El("article");
  const bubble = turn.appendChild(new El("div")); bubble.className = "bubble";
  const meta = turn.appendChild(new El("div")); meta.className = "turn-meta";
  turn.appendChild(new El("div")).className = "turn-tools";
  renderDowngrades(turn, null);
  renderDowngrades(turn, []);
  assert.equal(turn.children.length, 3);
  renderDowngrades(turn, [{ capability: "web_tools", reason: "no_tool_calling" }]);
  assert.equal(turn.children.length, 4);
  assert.equal(turn.children[2].className, "turn-note downgrade");
  assert.ok(turn.children[2].textContent.includes("本次未联网"));
  renderDowngrades(turn, [{ capability: "vision", reason: "no_vision" }]);
  assert.equal(turn.children.filter((c) => c.className === "turn-note downgrade").length, 1);
  assert.ok(turn.children[2].textContent.includes("PDF"));
});

test("quotaText: 缺失 = 不显示; 免费题显示剩余/总数/重置; BYOK 显示不占额度", () => {
  assert.equal(quotaText(undefined), null);
  assert.equal(quotaText({ free_remaining: "3" }), null);
  const q = { free_remaining: 3, free_per_day: 10, reset_at: RESET, byok: false };
  assert.equal(quotaText(q, false, "zh"), `今日免费 3/10 题 · ${hhmm(RESET)} 重置`);
  assert.equal(quotaText(q, false, "en"), `Free today: 3/10 · resets ${hhmm(RESET)}`);
  assert.equal(quotaText({ ...q, reset_at: undefined }, false, "zh"), "今日免费 3/10 题");
  assert.ok(quotaText(q, true, "zh").includes("不占免费额度"));
  assert.ok(quotaText({ ...q, byok: true }, false, "zh").includes("不占免费额度"));
});
