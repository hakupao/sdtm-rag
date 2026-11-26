import test from "node:test";
import assert from "node:assert/strict";
import { parseSSE, streamAsk } from "../js/stream.js";

test("parseSSE 解析 event/data; 坏 JSON 返回 null", () => {
  assert.deepEqual(parseSSE('event: token\ndata: {"text":"hi"}'), { event: "token", data: { text: "hi" } });
  assert.equal(parseSSE("event: token\ndata: {bad"), null);
  assert.equal(parseSSE("event: token"), null);
});

// ── streamAsk 的 sources 回调: 第三参 = 整个事件体 (新字段从这里取, 不改形参列表) ──

function fakeResponse(frames) {
  const enc = new TextEncoder();
  let i = 0;
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: async () => (i < frames.length
          ? { value: enc.encode(frames[i++]), done: false }
          : { value: undefined, done: true }),
      }),
    },
  };
}

async function runStream(frames, handlers, args = {}) {
  const orig = globalThis.fetch;
  let sent = null;
  globalThis.fetch = async (_url, opts) => { sent = JSON.parse(opts.body); return fakeResponse(frames); };
  try {
    await streamAsk({ question: "q", history: [], corpus: "auto", web: false, ...args },
                    { onToken: () => {}, onDone: () => {},
                      onError: (m) => { throw new Error(`unexpected onError: ${m}`); },
                      ...handlers });
  } finally { globalThis.fetch = orig; }
  return sent;
}

const SOURCES_FRAME = 'event: sources\ndata: {"sources":[{"chunk_id":"c1"}],"routed_corpus":"both",'
  + '"dossier":{"attached":true,"reason":"forced_on","sections":["4","5"],"chars":10,"sha":"abc"}}\n\n';
const DONE_FRAME = 'event: done\ndata: {"model_id":"m1"}\n\n';

test("sources 回调拿得到整个事件体 ⇒ dossier 有处可取", async () => {
  let got = null;
  const sent = await runStream([SOURCES_FRAME, DONE_FRAME],
    { onSources: (s, routed, ev) => { got = { s, routed, ev }; } },
    { dossier: "on" });
  assert.equal(got.routed, "both");
  assert.equal(got.s.length, 1);
  assert.equal(got.ev.dossier.attached, true);
  assert.equal(got.ev.dossier.reason, "forced_on");
  assert.deepEqual(got.ev.dossier.sections, ["4", "5"]);
  // 控件的三态必须真的进请求体 —— 不进的话界面上选了"关", 后端照样挂
  assert.equal(sent.dossier, "on");
});

test("只声明两个形参的老回调逐字节不受影响", async () => {
  let got = null;
  await runStream([SOURCES_FRAME, DONE_FRAME],
    { onSources: (s, routed) => { got = { n: s.length, routed }; } });
  assert.deepEqual(got, { n: 1, routed: "both" });
});

test("研读包答案闸: grounding / regenerate 事件按序交给各自回调, token 照旧流", async () => {
  const seen = [];
  await runStream([
    SOURCES_FRAME,
    'event: token\ndata: {"text":"a"}\n\n',
    'event: grounding\ndata: {"ok":false,"reasons":["r1"]}\n\n',
    'event: regenerate\ndata: {"reasons":["r1"]}\n\n',
    'event: token\ndata: {"text":"b"}\n\n',
    'event: grounding\ndata: {"ok":true,"reasons":[]}\n\n',
    DONE_FRAME,
  ], {
    onSources: () => {},
    onToken: (t) => seen.push(`token:${t}`),
    onGrounding: (d) => seen.push(`grounding:${d.ok}`),
    onRegenerate: (d) => seen.push(`regenerate:${d.reasons[0]}`),
    onDone: () => seen.push("done"),
  });
  assert.deepEqual(seen, ["token:a", "grounding:false", "regenerate:r1", "token:b",
                          "grounding:true", "done"]);
});

test("老调用方不传 onGrounding / onRegenerate 也不抛", async () => {
  let done = false;
  await runStream([SOURCES_FRAME, 'event: regenerate\ndata: {}\n\n',
                   'event: grounding\ndata: {}\n\n', DONE_FRAME],
                  { onSources: () => {}, onDone: () => { done = true; } });
  assert.equal(done, true);
});

// ── P2 §2.1 / §2.3 / §2.4: BYOK 头、拒绝文案 ──

async function capture(args, resp, handlers = {}) {
  const orig = globalThis.fetch;
  let sent = null;
  globalThis.fetch = async (_url, opts) => { sent = opts; return resp; };
  const errs = [];
  try {
    await streamAsk({ question: "q", history: [], corpus: "auto", web: false, ...args },
                    { onSources: () => {}, onToken: () => {}, onDone: () => {},
                      onError: (m, d) => errs.push({ m, d }), ...handlers });
  } finally { globalThis.fetch = orig; }
  return { headers: sent.headers, body: JSON.parse(sent.body), raw: sent.body, errs };
}

test("BYOK: key 只进请求头, provider + 该家模型进请求体, key 不进请求体", async () => {
  const byok = { provider: "deepseek", model: "deepseek-v4-pro", headers: { "X-LLM-Api-Key": "sk-SECRET" } };
  const r = await capture({ model: "opus-5", byok }, fakeResponse([DONE_FRAME]));
  assert.equal(r.headers["X-LLM-Api-Key"], "sk-SECRET");
  assert.equal(r.headers["Content-Type"], "application/json");
  assert.equal(r.body.provider, "deepseek");
  assert.equal(r.body.model, "deepseek-v4-pro");
  assert.ok(!r.raw.includes("sk-SECRET"), "key 进了请求体");
  assert.ok(!("X-LLM-Api-Base" in r.headers), "一期从不发自定义地址头");
});

test("非 BYOK: 请求头只有 Content-Type, 请求体没有 provider 字段 (与 P2 前逐字节一致)", async () => {
  for (const byok of [undefined, null]) {
    const r = await capture({ model: "opus-5", byok }, fakeResponse([DONE_FRAME]));
    assert.deepEqual(r.headers, { "Content-Type": "application/json" });
    assert.ok(!("provider" in r.body));
    assert.equal(r.body.model, "opus-5");
  }
});

test("开流前 429: 按 code 出文案, 第二参交出 detail; Retry-After 头兜底", async () => {
  const resp = { ok: false, status: 429,
    headers: { get: (k) => (k === "Retry-After" ? "9" : null) },
    json: async () => ({ detail: { code: "rate_limited", message: "频繁" } }) };
  const r = await capture({}, resp);
  assert.equal(r.errs.length, 1);
  assert.ok(r.errs[0].m.includes("9 秒"), r.errs[0].m);
  assert.equal(r.errs[0].d.code, "rate_limited");
});

test("开流前错误的旧形态: 无 json / 无 headers 的响应 ⇒ 「服务错误 N」原样, detail=null", async () => {
  const r = await capture({}, { ok: false, status: 502 });
  assert.deepEqual(r.errs, [{ m: "服务错误 502", d: null }]);
});

test("流内 error 事件带 code ⇒ 拒绝文案 + detail; 旧的无 code 形态 ⇒ 原 message", async () => {
  const a = await capture({}, fakeResponse([
    'event: token\ndata: {"text":"半截"}\n\n',
    'event: error\ndata: {"code":"site_cap_reached","message":"封顶","reset_at":"2026-11-27T00:00:00Z"}\n\n']));
  assert.ok(a.errs[0].m.includes("本站今日免费总额度"), a.errs[0].m);
  assert.equal(a.errs[0].d.code, "site_cap_reached");
  const b = await capture({}, fakeResponse(['event: error\ndata: {"message":"LLM stream failed"}\n\n']));
  assert.deepEqual(b.errs, [{ m: "LLM stream failed", d: undefined }]);
});

test("sources / done 的 downgrades 与 quota 原样交给回调 (第三参 / data)", async () => {
  let ev = null, done = null;
  await capture({}, fakeResponse([
    'event: sources\ndata: {"sources":[],"downgrades":[{"capability":"web_tools","reason":"free_tier_no_web"}]}\n\n',
    'event: done\ndata: {"quota":{"free_remaining":2,"free_per_day":10,"reset_at":"x","byok":false},"downgrades":[]}\n\n']),
    { onSources: (_s, _r, e) => { ev = e; }, onDone: (d) => { done = d; } });
  assert.equal(ev.downgrades[0].reason, "free_tier_no_web");
  assert.equal(done.quota.free_remaining, 2);
});

test("byok 对象缺 provider ⇒ 不发 key 头也不发 provider (§2.1: 不猜 provider)", async () => {
  for (const provider of ["", undefined, null]) {
    const r = await capture({ model: "opus-5", byok: { provider, model: "m", headers: { "X-LLM-Api-Key": "sk-X" } } },
                            fakeResponse([DONE_FRAME]));
    assert.deepEqual(r.headers, { "Content-Type": "application/json" });
    assert.ok(!("provider" in r.body));
    assert.equal(r.body.model, "opus-5");
  }
});

test("读错误体时被用户中止 ⇒ onAbort, 不是 onError", async () => {
  const ctrl = new AbortController();
  const resp = { ok: false, status: 429, headers: { get: () => null },
    json: async () => { ctrl.abort(); const e = new Error("aborted"); e.name = "AbortError"; throw e; } };
  let aborted = 0;
  const r = await capture({}, resp, { signal: ctrl.signal, onAbort: () => { aborted++; } });
  assert.equal(aborted, 1);
  assert.deepEqual(r.errs, []);
});
