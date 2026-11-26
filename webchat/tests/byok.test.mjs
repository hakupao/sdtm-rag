import test from "node:test";
import assert from "node:assert/strict";

// localStorage shim 先装好 (byok.js 每次读写都现读, 不在 import 时读; 但与 store.test 同一写法)
const mem = new Map();
globalThis.localStorage = {
  getItem: (k) => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: (k) => mem.delete(k),
};
const B = await import("../js/byok.js");

const INFO = {
  tier: "public",
  web_search: true,
  quota: { free_remaining: 3, free_per_day: 10, reset_at: "2026-11-27T00:00:00Z", byok: false },
  providers: [
    { id: "deepseek", label: "DeepSeek", byok: true, base_fixed: true,
      models: [{ id: "deepseek-v4-pro", label: "DeepSeek v4 Pro", capabilities: { tools: true } },
               { id: "deepseek-v4-flash", label: "DeepSeek v4 Flash", capabilities: {} }] },
    { id: "anthropic", label: "Anthropic", byok: true, base_fixed: true,
      models: [{ id: "claude-sonnet-5-5", label: "Claude Sonnet 5.5" }] },
    { id: "custom", label: "Custom", byok: true, base_fixed: false, models: [{ id: "x", label: "x" }] },
  ],
};

test("normalizeInfo: 缺任何键都不抛; 缺 tier = private, 缺 providers/quota = 空/null", () => {
  for (const bad of [null, undefined, "junk", 42, [], {}]) {
    const v = B.normalizeInfo(bad);
    assert.equal(v.tier, "private");
    assert.deepEqual(v.providers, []);
    assert.equal(v.quota, null);
    assert.equal(v.webVisible, false);
  }
  // web_search 缺失 ⇒ 随 federation (改前联网勾选框跟着 #scope 显隐)
  assert.equal(B.normalizeInfo({ federation: true }).webVisible, true);
  assert.equal(B.normalizeInfo({ federation: true, web_search: false }).webVisible, false);
  assert.equal(B.normalizeInfo({ federation: false, web_search: true }).webVisible, true);
});

test("normalizeInfo: custom (base_fixed=false) 与无模型 / 畸形 provider 被滤掉", () => {
  const v = B.normalizeInfo({ ...INFO, providers: [...INFO.providers, { id: "nomodels", models: [] }, "junk", { id: 3 }] });
  assert.deepEqual(v.providers.map((p) => p.id), ["deepseek", "anthropic"]);
  assert.equal(v.tier, "public");
  assert.equal(v.quota.free_remaining, 3);
  assert.equal(B.normalizeInfo({ quota: { free_remaining: "3", free_per_day: 10 } }).quota, null);
});

test("key 存独立 localStorage 键, 绑 provider; clearKey 真删", () => {
  mem.clear();
  B.saveKey("deepseek", "  sk-AAA  ");
  assert.deepEqual(JSON.parse(mem.get(B.BYOK_KEY_LS)), { provider: "deepseek", key: "sk-AAA" });
  assert.equal(B.loadKey("deepseek"), "sk-AAA");
  assert.equal(B.loadKey("anthropic"), "", "换家后旧 key 不能被取出来发给另一家");
  assert.equal(B.loadKey(""), "");
  // 选择 (provider/model) 存另一个键, 里面没有 key
  B.saveSelection({ provider: "deepseek", model: "deepseek-v4-pro" });
  assert.ok(!mem.get(B.BYOK_SEL_LS).includes("sk-AAA"));
  assert.notEqual(B.BYOK_KEY_LS, "sdtm_chat_v1");
  assert.notEqual(B.BYOK_KEY_LS, "sdtm_ui_prefs");
  B.clearKey();
  assert.equal(mem.has(B.BYOK_KEY_LS), false);
  assert.equal(B.loadKey("deepseek"), "");
  // 空 key / 没 provider ⇒ 等于清除
  B.saveKey("deepseek", "sk-B"); B.saveKey("deepseek", "   ");
  assert.equal(mem.has(B.BYOK_KEY_LS), false);
  B.saveKey("", "sk-C");
  assert.equal(mem.has(B.BYOK_KEY_LS), false);
});

test("坏 JSON / localStorage 抛错都不抛出来", () => {
  mem.set(B.BYOK_KEY_LS, "{bad");
  assert.equal(B.loadKey("deepseek"), "");
  const orig = globalThis.localStorage;
  globalThis.localStorage = { getItem() { throw new Error("x"); }, setItem() { throw new Error("x"); }, removeItem() { throw new Error("x"); } };
  try {
    assert.equal(B.loadKey("deepseek"), "");
    B.saveKey("deepseek", "k"); B.clearKey(); B.saveSelection({ provider: "a" });
    assert.deepEqual(B.loadSelection(), { provider: "", model: "" });
  } finally { globalThis.localStorage = orig; }
});

test("byokRequest: key 头与 provider 同进同退 (§2.1 组合表)", () => {
  const v = B.normalizeInfo(INFO);
  const r = B.byokRequest(v, { provider: "deepseek", model: "deepseek-v4-flash" }, "sk-AAA");
  assert.equal(r.provider, "deepseek");
  assert.equal(r.model, "deepseek-v4-flash");
  assert.deepEqual(r.headers, { "X-LLM-Api-Key": "sk-AAA" });
  // 没 key ⇒ null (不发 provider, 否则 400 byok_key_missing)
  assert.equal(B.byokRequest(v, { provider: "deepseek", model: "" }, ""), null);
  // 没选 provider ⇒ null (不发 key, 否则 400 provider_required)
  assert.equal(B.byokRequest(v, { provider: "", model: "" }, "sk-AAA"), null);
  // provider 不在当前列表 (旧服务端 / 下架 / custom) ⇒ null, 存着的 key 不发
  assert.equal(B.byokRequest(v, { provider: "custom", model: "x" }, "sk-AAA"), null);
  assert.equal(B.byokRequest(B.normalizeInfo({}), { provider: "deepseek", model: "" }, "sk-AAA"), null);
  // model 不在该 provider 列表 ⇒ 取第一个, 绝不把本站模型 id 发给别家
  assert.equal(B.byokRequest(v, { provider: "deepseek", model: "opus-5" }, "sk-AAA").model, "deepseek-v4-pro");
});

test("webState: 公开档非 BYOK 置灰; 私有档 / BYOK 可用", () => {
  const pub = B.normalizeInfo(INFO);
  assert.deepEqual(B.webState(pub, false), { visible: true, disabled: true });
  assert.deepEqual(B.webState(pub, true), { visible: true, disabled: false });
  assert.deepEqual(B.webState(B.normalizeInfo({ federation: true }), false), { visible: true, disabled: false });
});
