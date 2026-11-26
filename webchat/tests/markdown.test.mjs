import test from "node:test";
import assert from "node:assert/strict";
import { prepareStreaming, mdToSafeHTML, SANITIZE_CONFIG } from "../js/markdown.js";

test("奇数个 ``` 围栏 → 末尾补闭合", () => {
  assert.equal(prepareStreaming("a\n```py\nx = 1"), "a\n```py\nx = 1\n```");
});
test("偶数个围栏不动", () => {
  const s = "a\n```py\nx\n```\nb";
  assert.equal(prepareStreaming(s), s);
});
test("~~~ 围栏用 ~~~ 闭合", () => {
  assert.equal(prepareStreaming("~~~\nx"), "~~~\nx\n~~~");
});
test("行内三反引号不算围栏; 缩进 ≤3 空格算", () => {
  assert.equal(prepareStreaming("say ```x``` ok"), "say ```x``` ok");
  assert.equal(prepareStreaming("  ```\nx"), "  ```\nx\n```");
});
test("空/null 安全", () => {
  assert.equal(prepareStreaming(""), "");
  assert.equal(prepareStreaming(null), "");
});

test("净化调用带 FORBID_TAGS (表单类 + style), 不是默认配置", () => {
  const seen = [];
  globalThis.marked = { parse: (md) => `<p>${md}</p>` };
  globalThis.DOMPurify = { sanitize: (html, cfg) => { seen.push(cfg); return html; } };
  try {
    mdToSafeHTML("x");
  } finally {
    delete globalThis.marked;
    delete globalThis.DOMPurify;
  }
  assert.equal(seen.length, 1);
  assert.deepEqual([...seen[0].FORBID_TAGS].sort(),
    ["button", "form", "input", "select", "style", "textarea"]);
  assert.equal(seen[0], SANITIZE_CONFIG);
});
