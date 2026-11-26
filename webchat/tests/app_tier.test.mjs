// app.js 接线闸: 在 node 里真的跑 webchat 入口 (app.js + js/*.js), 驱动设置面板 → 发送 → 拒绝,
// 断言**实际发出去的** fetch 头与请求体、额度徽章、降级行、联网勾选框。纯函数各有单测
// (byok / notices / stream), 这里钉的是"它们被接上了" —— 接线断了纯函数照样全绿。
// 加载方式同 tests/fixtures/flag_attribution_probe.mjs: 每个场景一份磁盘副本 + 一次 import
// (store.js 在求值时读 localStorage, ESM 注册表按 URL 缓存)。
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, copyFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve, join } from "node:path";

const WEBCHAT = process.env.PROBE_WEBCHAT_DIR || resolve(dirname(fileURLToPath(import.meta.url)), "..");
const KEY_LS = "sdtm_byok_key_v1";
const SEL_LS = "sdtm_byok_sel_v1";

class El {
  constructor(tag) {
    this.tagName = tag; this.children = []; this.parentNode = null; this._text = ""; this._html = "";
    this._classes = new Set(); this.dataset = {}; this.style = {}; this.hidden = false; this.disabled = false;
    this.checked = false; this._value = ""; this._listeners = {}; this.scrollTop = 0; this.scrollHeight = 0;
    this.clientHeight = 0; this.title = "";
    const self = this;
    this.classList = {
      add: (c) => self._classes.add(c), remove: (c) => self._classes.delete(c), contains: (c) => self._classes.has(c),
      toggle: (c, f) => { const on = f === undefined ? !self._classes.has(c) : !!f; if (on) self._classes.add(c); else self._classes.delete(c); return on; },
    };
  }
  get options() { return this.children.filter((c) => c.tagName === "option"); }
  get value() {
    if (this.tagName !== "select") return this._value;
    const o = this.options; if (!o.length) return "";
    return o.some((x) => x._value === this._value) ? this._value : o[0]._value;
  }
  set value(v) { this._value = String(v); }
  get selectedOptions() { return this.options.filter((o) => o._value === this.value); }
  get className() { return [...this._classes].join(" "); }
  set className(v) { this._classes = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get innerHTML() { return this._html; }
  set innerHTML(v) { this._html = v; this.children = []; }
  get textContent() { return this._text || this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this._text = String(v); this.children = []; }
  get childElementCount() { return this.children.length; }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  append(...cs) { cs.forEach((c) => this.appendChild(c)); }
  prepend(c) { c.parentNode = this; this.children.unshift(c); return c; }
  insertAdjacentElement(_p, c) { const p = this.parentNode; c.parentNode = p; p.children.splice(p.children.indexOf(this) + 1, 0, c); return c; }
  remove() { const p = this.parentNode; if (p) { const i = p.children.indexOf(this); if (i >= 0) p.children.splice(i, 1); } this.parentNode = null; }
  addEventListener(t, fn) { (this._listeners[t] ||= []).push(fn); }
  fire(t) { (this._listeners[t] || []).forEach((fn) => fn({ target: this, stopPropagation() {}, preventDefault() {} })); }
  focus() {} select() {}
  setAttribute(k, v) { (this._attrs ||= {})[k] = String(v); }
  getAttribute(k) { return this._attrs && k in this._attrs ? this._attrs[k] : null; }
  querySelectorAll(sel) {
    const scoped = sel.startsWith(":scope >");
    const s = (scoped ? sel.slice(":scope >".length) : sel).trim();
    if (!s.startsWith(".")) return [];
    const want = s.slice(1).split(".");
    const hit = (c) => want.every((w) => c._classes.has(w));
    const out = [];
    if (scoped) { this.children.forEach((c) => { if (hit(c)) out.push(c); }); return out; }
    const walk = (n) => n.children.forEach((c) => { if (hit(c)) out.push(c); walk(c); });
    walk(this); return out;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}

const flush = () => new Promise((r) => setTimeout(r, 0));
const SELECTS = new Set(["model-select", "byok-provider", "byok-model", "scope-dossier"]);

function fakeStream(frames) {
  const enc = new TextEncoder(); let i = 0;
  return { ok: true, body: { getReader: () => ({ read: async () => (i < frames.length
    ? { value: enc.encode(frames[i++]), done: false } : { value: undefined, done: true }) }) } };
}

// info: /api/info 应答; stored: 预置 localStorage; askResp: (opts) => 响应
async function boot({ info, stored = {}, askResp }) {
  const byId = new Map(); const root = new El("body"); const calls = [];
  const document = {
    getElementById(id) {
      if (!byId.has(id)) {
        const el = new El(SELECTS.has(id) ? "select" : (id === "byok-key" ? "input" : "div"));
        // index.html 里这几个默认 hidden; 不预置的话 "没被打开" 与 "没被关上" 分不出来
        if (["byok-section", "quota-badge", "web-opt", "model-warning"].includes(id)) el.hidden = true;
        byId.set(id, el); root.appendChild(el);
      }
      return byId.get(id);
    },
    createElement: (t) => new El(t), querySelectorAll: (s) => root.querySelectorAll(s), addEventListener() {},
  };
  const mem = new Map(Object.entries(stored));
  Object.assign(globalThis, {
    document,
    localStorage: { getItem: (k) => (mem.has(k) ? mem.get(k) : null), setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) },
    DOMPurify: { sanitize: (s) => s }, marked: { parse: (s) => s || "" }, hljs: { highlightElement() {} },
    requestAnimationFrame: (fn) => setTimeout(fn, 0), cancelAnimationFrame: (id) => clearTimeout(id),
    async fetch(url, opts) {
      if (String(url).includes("/api/info")) { await flush(); return { ok: true, json: async () => info }; }
      if (String(url).includes("/api/ask_stream")) { calls.push(opts); return askResp(opts); }
      return { ok: true };
    },
  });
  const dir = mkdtempSync(join(tmpdir(), "webchat-tier-"));
  mkdirSync(join(dir, "js"));
  copyFileSync(join(WEBCHAT, "app.js"), join(dir, "app.js"));
  for (const f of readdirSync(join(WEBCHAT, "js"))) copyFileSync(join(WEBCHAT, "js", f), join(dir, "js", f));
  await import(pathToFileURL(join(dir, "app.js")).href);
  await flush(); await flush(); await flush();
  const $ = (id) => document.getElementById(id);
  const send = async (q) => {
    $("input").value = q;
    $("composer").onsubmit({ preventDefault() {} });
    for (let i = 0; i < 8; i++) await flush();
  };
  return { $, mem, calls, send, root, cleanup: () => rmSync(dir, { recursive: true, force: true }) };
}

const PUBLIC_INFO = {
  default_model: "deepseek/deepseek-v4-pro", federation: false, tier: "public", web_search: true,
  selectable_models: [{ id: "free-ds", label: "DeepSeek v4 Pro (free)", verified: false }],
  quota: { free_remaining: 3, free_per_day: 10, reset_at: "2026-11-27T00:00:00Z", byok: false },
  providers: [
    { id: "deepseek", label: "DeepSeek", byok: true, base_fixed: true,
      models: [{ id: "deepseek-v4-pro", label: "DeepSeek v4 Pro", capabilities: { tools: true } }] },
    { id: "anthropic", label: "Anthropic", byok: true, base_fixed: true,
      models: [{ id: "claude-sonnet-5-5", label: "Claude Sonnet 5.5", capabilities: { tools: true } }] },
  ],
};
const DONE_OK = 'event: done\ndata: {"model_id":"deepseek-v4-pro","quota":{"free_remaining":2,"free_per_day":10,"reset_at":"2026-11-27T00:00:00Z","byok":false}}\n\n';

test("公开档: 面板 / 额度 / 联网置灰 → 填 key → 请求带头 + provider → 清除 key → 请求回到服务器 key", async () => {
  const app = await boot({ info: PUBLIC_INFO, askResp: () => fakeStream([
    'event: sources\ndata: {"sources":[],"downgrades":[{"capability":"web_tools","reason":"no_tool_calling"}]}\n\n',
    'event: token\ndata: {"text":"答"}\n\n', DONE_OK]) });
  const { $ } = app;
  try {
    assert.equal($("byok-section").hidden, false, "有 providers 时 BYOK 面板要出来");
    assert.deepEqual($("byok-provider").options.map((o) => o.value), ["deepseek", "anthropic"]);
    assert.equal($("quota-badge").hidden, false);
    assert.ok($("quota-badge").textContent.startsWith("今日免费 3/10 题"), $("quota-badge").textContent);
    assert.equal($("web-opt").hidden, false, "web_search=true ⇒ 联网勾选框可见 (即使 federation=false)");
    assert.equal($("scope-web").disabled, true, "公开档免费题: 联网置灰");

    // 填 key
    $("byok-provider").value = "deepseek"; $("byok-provider").fire("change");
    $("byok-key").value = "sk-SECRET-1"; $("byok-key").fire("input");
    assert.deepEqual(JSON.parse(app.mem.get(KEY_LS)), { provider: "deepseek", key: "sk-SECRET-1" });
    assert.equal($("scope-web").disabled, false, "BYOK ⇒ 联网可用");
    assert.ok($("quota-badge").textContent.includes("不占免费额度"));
    assert.ok($("topbar-model").textContent.includes("DeepSeek"));
    assert.equal($("model-select").disabled, true);

    await app.send("问题一");
    assert.equal(app.calls.length, 1);
    const h = app.calls[0].headers, body = JSON.parse(app.calls[0].body);
    assert.equal(h["X-LLM-Api-Key"], "sk-SECRET-1");
    assert.equal(body.provider, "deepseek");
    assert.equal(body.model, "deepseek-v4-pro");
    assert.ok(!app.calls[0].body.includes("sk-SECRET"), "key 进了请求体");
    // key 不进会话存档 / 偏好 / 选择
    for (const [k, v] of app.mem) if (k !== KEY_LS) assert.ok(!v.includes("sk-SECRET"), `key 漏进了 ${k}`);
    // 降级行画出来且落盘
    const note = app.$("messages").querySelector(".turn-note.downgrade");
    assert.ok(note && note.textContent.includes("本次未联网"), "降级行没画");
    const saved = JSON.parse(app.mem.get("sdtm_chat_v1")).conversations[0].messages[1];
    assert.equal(saved.downgrades[0].reason, "no_tool_calling");

    // 换家: 旧 key 不显示也不发
    $("byok-provider").value = "anthropic"; $("byok-provider").fire("change");
    assert.equal($("byok-key").value, "");
    // 清除 key
    $("byok-provider").value = "deepseek"; $("byok-provider").fire("change");
    assert.equal($("byok-key").value, "sk-SECRET-1");
    $("byok-clear").fire("click");
    assert.equal(app.mem.has(KEY_LS), false, "清除 key 后 localStorage 还留着");
    assert.equal($("byok-key").value, "");
    assert.equal($("scope-web").disabled, true);
    $("scope-web").checked = true;   // 置灰的框哪怕残留勾选, 请求里也不能是 web=true
    await app.send("问题二");
    assert.equal(app.calls.length, 2);
    assert.ok(!("X-LLM-Api-Key" in app.calls[1].headers), "清除后仍发 key 头");
    assert.ok(!("provider" in JSON.parse(app.calls[1].body)));
    assert.equal(JSON.parse(app.calls[1].body).web, false);
    // L3: 公开档服务端默认是内部组 "default" ⇒ 422; 非 BYOK 也必须发公开模型 id
    assert.equal(JSON.parse(app.calls[1].body).model, "free-ds");
    // done.quota 更新徽章
    assert.ok($("quota-badge").textContent.startsWith("今日免费 2/10 题"), $("quota-badge").textContent);
  } finally { app.cleanup(); }
});

test("429 free_quota_exhausted: 气泡出拒绝文案, 额度徽章归零", async () => {
  const app = await boot({ info: PUBLIC_INFO, askResp: () => ({ ok: false, status: 429,
    headers: { get: (k) => (k === "Retry-After" ? "3600" : null) },
    json: async () => ({ detail: { code: "free_quota_exhausted", message: "x", remaining: 0, reset_at: "2026-11-27T00:00:00Z" } }) }) });
  try {
    await app.send("第 11 题");
    const err = app.$("messages").querySelector(".err");
    assert.ok(err && err.textContent.includes("今日免费额度已用完"), err && err.textContent);
    assert.ok(app.$("quota-badge").textContent.startsWith("今日免费 0/10 题"), app.$("quota-badge").textContent);
    // 额度类拒绝: 不给"重试" (照样被拒), 给"去设置填 key", 点了打开设置面板
    const btns = app.$("messages").querySelectorAll(".retry");
    assert.equal(btns.filter((b) => !b.classList.contains("open-settings")).length, 0, "额度拒绝不该有重试");
    const open = app.$("messages").querySelector(".open-settings");
    assert.ok(open, "缺「去设置」按钮");
    app.$("settings-panel").hidden = true;
    open.onclick({ stopPropagation() {} });
    assert.equal(app.$("settings-panel").hidden, false);
  } finally { app.cleanup(); }
});

test("私有档 / 旧服务端 (/api/info 无新键): 无面板无额度, 联网随 federation, 存着的旧 key 也不发", async () => {
  const app = await boot({
    info: { default_model: "anthropic/claude-opus-5", federation: true,
            selectable_models: [{ id: "opus-5", label: "Claude Opus 5", verified: true }] },
    stored: { [KEY_LS]: JSON.stringify({ provider: "deepseek", key: "sk-STALE" }),
              [SEL_LS]: JSON.stringify({ provider: "deepseek", model: "deepseek-v4-pro" }) },
    askResp: () => fakeStream(['event: done\ndata: {"model_id":"opus-5"}\n\n']) });
  try {
    assert.equal(app.$("byok-section").hidden, true);
    assert.equal(app.$("quota-badge").hidden, true);
    assert.equal(app.$("web-opt").hidden, false, "federation=true 且无 web_search 键 ⇒ 同改前: 可见");
    assert.equal(app.$("scope-web").disabled, false);
    assert.equal(app.$("model-select").disabled, false);
    await app.send("q");
    assert.deepEqual(app.calls[0].headers, { "Content-Type": "application/json" });
    const body = JSON.parse(app.calls[0].body);
    assert.ok(!("provider" in body));
    assert.equal(body.model, "opus-5");
    const saved = JSON.parse(app.mem.get("sdtm_chat_v1")).conversations[0].messages[1];
    assert.ok(!("downgrades" in saved), "没降级时存档形状要与改前一致");
    assert.equal(app.$("messages").querySelector(".turn-note.downgrade"), null);
  } finally { app.cleanup(); }
});

test("federation=false 且无 web_search 键 ⇒ 联网勾选框与改前一样隐藏", async () => {
  const app = await boot({ info: { default_model: "x/y", federation: false, selectable_models: [] },
                           askResp: () => fakeStream([]) });
  try { assert.equal(app.$("web-opt").hidden, true); } finally { app.cleanup(); }
});

test("federation=true 但 web_search=false ⇒ 联网勾选框隐藏 (新规则: 有 web_search 键时只看它)", async () => {
  const app = await boot({ info: { default_model: "x/y", federation: true, web_search: false, selectable_models: [] },
                           askResp: () => fakeStream([]) });
  try { assert.equal(app.$("web-opt").hidden, true); } finally { app.cleanup(); }
});

test("XSS: 降级 reason 与未知拒绝 message 里的 HTML 按字面显示, 不生成子元素", async () => {
  const XSS = "<img src=x onerror=alert(1)>";
  const a = await boot({ info: PUBLIC_INFO, askResp: () => fakeStream([
    `event: sources\ndata: ${JSON.stringify({ sources: [], downgrades: [{ capability: "web_tools", reason: XSS }] })}\n\n`,
    DONE_OK]) });
  try {
    await a.send("q");
    const note = a.$("messages").querySelector(".turn-note.downgrade");
    assert.ok(note.textContent.includes(XSS), note.textContent);
    assert.equal(note.children.length, 0);
    assert.equal(note.innerHTML, "");
  } finally { a.cleanup(); }
  const b = await boot({ info: PUBLIC_INFO, askResp: () => ({ ok: false, status: 403, headers: { get: () => null },
    json: async () => ({ detail: { code: "brand_new_refusal", message: XSS } }) }) });
  try {
    await b.send("q");
    const err = b.$("messages").querySelector(".err");
    assert.ok(err.textContent.includes(XSS), err.textContent);
    assert.equal(err.children.length, 0);
    assert.equal(err.innerHTML, "");
    // 非额度类拒绝照常给重试
    assert.ok(b.$("messages").querySelector(".retry"));
  } finally { b.cleanup(); }
});

test("非法 key (含空格 / 全角) ⇒ 不保存, 出提示, 请求不带 key 头", async () => {
  const app = await boot({ info: PUBLIC_INFO, askResp: () => fakeStream([DONE_OK]) });
  try {
    app.$("byok-provider").value = "deepseek"; app.$("byok-provider").fire("change");
    app.$("byok-key").value = "sk-有 空格"; app.$("byok-key").fire("input");
    assert.equal(app.mem.has(KEY_LS), false);
    assert.ok(app.$("byok-status").textContent.includes("未保存"), app.$("byok-status").textContent);
    await app.send("q");
    assert.ok(!("X-LLM-Api-Key" in app.calls[0].headers));
  } finally { app.cleanup(); }
});
