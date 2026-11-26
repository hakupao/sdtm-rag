// BYOK (自带 API key) + 实例档位: /api/info 归一化、key 存储、请求头/字段组合。不碰 DOM。
// 契约: docs/design/P2_request_context.md §2 (v1.1)。
//
// ⚠ key 只存在这里的独立 localStorage 键 (不进会话存档 sdtm_chat_v1 / UI 偏好 sdtm_ui_prefs),
// 只经 §2.1 请求头发出, 绝不进请求体 / 日志 / ⚑ 上报。
// key 与 provider 绑定存: 切换 provider 后旧 key 不会被发给另一家 (猜错 = 把 A 家 key 发给 B 家)。

export const BYOK_KEY_LS = "sdtm_byok_key_v1";   // {provider, key} —— 唯一存 key 的地方
export const BYOK_SEL_LS = "sdtm_byok_sel_v1";   // {provider, model} —— 不含 key
export const KEY_HEADER = "X-LLM-Api-Key";

// /api/info → 前端只关心的几项。任何键缺失都要能跑 (旧服务端 / 私有档 / L3 裁掉的键, §2.6)。
// base_fixed === false 的 provider (私有档 custom, 要用户填地址) 一期不在 UI 提供 ⇒ 过滤掉,
// 于是 X-LLM-Api-Base 永远不发 (公开档发了是 400, 私有档自定义地址留给后续单元)。
export function normalizeInfo(info) {
  const i = info && typeof info === "object" ? info : {};
  const providers = Array.isArray(i.providers) ? i.providers.filter((p) =>
    p && typeof p === "object" && typeof p.id === "string" && p.id && p.base_fixed !== false
    && Array.isArray(p.models) && p.models.some((m) => m && typeof m.id === "string" && m.id)) : [];
  return {
    tier: i.tier === "public" ? "public" : "private",
    providers: providers.map((p) => ({
      id: p.id, label: typeof p.label === "string" && p.label ? p.label : p.id,
      models: p.models.filter((m) => m && typeof m.id === "string" && m.id)
        .map((m) => ({ id: m.id, label: typeof m.label === "string" && m.label ? m.label : m.id,
                       capabilities: m.capabilities && typeof m.capabilities === "object" ? m.capabilities : {} })),
    })),
    quota: validQuota(i.quota) ? i.quota : null,
    selectable: Array.isArray(i.selectable_models)
      ? i.selectable_models.filter((m) => m && typeof m.id === "string" && m.id).map((m) => m.id) : [],
    // web_search 缺失 ⇒ 沿用今天的规则 (联网勾选框随 #scope, 即随 federation 显隐)
    webVisible: typeof i.web_search === "boolean" ? i.web_search : !!i.federation,
  };
}

export function validQuota(q) {
  return !!q && typeof q === "object" && !Array.isArray(q)
    && Number.isFinite(q.free_remaining) && Number.isFinite(q.free_per_day);
}

// ── 存储 (每次读写都 try: 隐私模式 / 配额满时 localStorage 会抛) ──
function readJSON(k) {
  try { const v = JSON.parse(localStorage.getItem(k)); return v && typeof v === "object" ? v : null; }
  catch (_) { return null; }
}
// 只在 provider 对得上时返回 key —— 绑定存储的意义就在这一行。
export function loadKey(provider) {
  const s = readJSON(BYOK_KEY_LS);
  return s && provider && s.provider === provider && typeof s.key === "string" ? s.key : "";
}
// key 只许可见 ASCII (无空格 / 全角 / 换行): 放进 HTTP 头的非 ASCII 会让 fetch 直接抛,
// 而带空格的粘贴残片发出去只会换来一个看不懂的 401。不合法 ⇒ 不存且清掉旧的, 返回 false (UI 出提示)。
export const KEY_RE = /^[\x21-\x7e]+$/;
export function saveKey(provider, key) {
  const k = (key || "").trim();
  if (!provider || !k) { clearKey(); return true; }
  if (!KEY_RE.test(k)) { clearKey(); return false; }
  try { localStorage.setItem(BYOK_KEY_LS, JSON.stringify({ provider, key: k })); } catch (_) {}
  return true;
}
export function clearKey() { try { localStorage.removeItem(BYOK_KEY_LS); } catch (_) {} }
export function loadSelection() {
  const s = readJSON(BYOK_SEL_LS) || {};
  return { provider: typeof s.provider === "string" ? s.provider : "",
           model: typeof s.model === "string" ? s.model : "" };
}
export function saveSelection(sel) {
  try { localStorage.setItem(BYOK_SEL_LS, JSON.stringify({ provider: sel.provider || "", model: sel.model || "" })); }
  catch (_) {}
}

// §2.1 组合表: key 头与 provider 字段**同进同退**。返回 null = 服务器 key 模式
// (不发 provider、不发头, 请求与 P2 之前逐字节一致)。
//   - provider 不在当前 /api/info.providers 里 (旧服务端 / 被下架) ⇒ null, 存着的 key 不发
//   - 没 key / key 绑的是别家 ⇒ null (不发 provider, 否则 400 byok_key_missing)
//   - model 不在该 provider 的列表里 ⇒ 取第一个 (不把 server-key 的模型 id 发给别家)
export function byokRequest(view, sel, key) {
  if (!view || !sel || !sel.provider || !key) return null;
  const p = (view.providers || []).find((x) => x.id === sel.provider);
  if (!p) return null;
  const m = p.models.find((x) => x.id === sel.model) || p.models[0];
  return { provider: p.id, model: m.id, providerLabel: p.label, modelLabel: m.label,
           headers: { [KEY_HEADER]: key } };
}

// 发给服务端的 model。公开档: 服务端默认值是内部组 "default" ⇒ 422 (§2.3), 所以**永远**发一个
// selectable_models 里的显式 id (所选不在表里 / 为空 ⇒ 表里第一个)。私有档: 原样 (空 ⇒ 省略, 同改前)。
export function requestModel(view, selected) {
  if (!view || view.tier !== "public" || !view.selectable.length) return selected;
  return view.selectable.includes(selected) ? selected : view.selectable[0];
}

// 联网勾选框: 公开档免费题不联网 (PLAN Q2 / §2.4) ⇒ 非 BYOK 时置灰。服务端照样会按 web_tools
// 降级, 这里只是让用户发送前就看见。
export function webState(view, byokActive) {
  const disabled = view.tier === "public" && !byokActive;
  return { visible: !!view.webVisible, disabled };
}
