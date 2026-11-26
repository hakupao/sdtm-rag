"""P2 step 2.5 BYOK probe — zero spend, zero real keys.

A loopback stub speaks the OpenAI / Anthropic / Gemini wire formats; every provider key env var
is set to a sentinel BEFORE litellm is imported (litellm runs load_dotenv() at import, which does
not override already-set vars, and we run from a cwd without .env anyway). If a per-call
api_base were ignored, the request would hit the real provider with a sentinel key (401, no spend).

Run:  cd /tmp && /Volumes/DevSSD/Project/sdtm-rag/.venv/bin/python -I \
        /Volumes/DevSSD/Project/sdtm-rag/.work/10_split_and_public/evidence/probes/p2_byok_probe.py
Prints one JSON line per case; exit 0 always (it is a probe, not a gate).
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

for _k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY",
           "COHERE_API_KEY", "TAVILY_API_KEY", "DASHSCOPE_API_KEY", "MOONSHOT_API_KEY"):
    os.environ[_k] = f"env-sentinel-{_k.split('_')[0].lower()}"
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)
os.environ["LITELLM_LOG"] = "ERROR"

SEEN: list[dict] = []


def _usage_openai():
    return {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # quiet
        pass

    def _rec(self, body):
        hdr = {k.lower(): v for k, v in self.headers.items()}
        auth = hdr.get("authorization") or hdr.get("x-api-key") or hdr.get("x-goog-api-key")
        q = self.path.split("?", 1)[1] if "?" in self.path else ""
        if not auth and "key=" in q:
            auth = "query:" + q.split("key=", 1)[1].split("&", 1)[0]
        SEEN.append({"path": self.path.split("?", 1)[0], "auth": auth,
                     "stream": body.get("stream"), "stream_options": body.get("stream_options"),
                     "max_tokens": body.get("max_tokens") or body.get("max_output_tokens")})

    def _sse(self, events, abort_after=None):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        for i, ev in enumerate(events):
            if abort_after is not None and i >= abort_after:
                self.wfile.flush()
                self.connection.shutdown(2)  # hard cut mid-stream
                return
            self.wfile.write(ev.encode())
            self.wfile.flush()

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        self._rec(body)
        p = self.path
        if p.startswith("/fail500"):
            return self._json(500, {"error": {"message": "stub 500", "type": "server_error"}})
        abort = 2 if p.startswith("/abort") else None
        if p.split("?")[0].endswith("/chat/completions"):
            if not body.get("stream"):
                return self._json(200, {"id": "x", "object": "chat.completion", "created": 1,
                                        "model": body.get("model"),
                                        "choices": [{"index": 0, "finish_reason": "stop",
                                                     "message": {"role": "assistant", "content": "Hi"}}],
                                        "usage": _usage_openai()})
            def c(delta, fr=None, usage=None, choices=True):
                o = {"id": "x", "object": "chat.completion.chunk", "created": 1, "model": body.get("model"),
                     "choices": [{"index": 0, "delta": delta, "finish_reason": fr}] if choices else []}
                if usage:
                    o["usage"] = usage
                return f"data: {json.dumps(o)}\n\n"
            evs = [c({"role": "assistant", "content": "Hel"}), c({"content": "lo"}), c({}, "stop")]
            if (body.get("stream_options") or {}).get("include_usage"):
                evs.append(c({}, usage=_usage_openai(), choices=False))
            evs.append("data: [DONE]\n\n")
            return self._sse(evs, abort)
        if p.split("?")[0].endswith("/v1/messages"):
            if not body.get("stream"):
                return self._json(200, {"id": "m", "type": "message", "role": "assistant",
                                        "model": body.get("model"), "stop_reason": "end_turn",
                                        "content": [{"type": "text", "text": "Hi"}],
                                        "usage": {"input_tokens": 11, "output_tokens": 5}})
            def e(t, d):
                return f"event: {t}\ndata: {json.dumps({'type': t, **d})}\n\n"
            evs = [e("message_start", {"message": {"id": "m", "type": "message", "role": "assistant",
                                                   "model": body.get("model"), "content": [],
                                                   "stop_reason": None, "stop_sequence": None,
                                                   "usage": {"input_tokens": 11, "output_tokens": 1}}}),
                   e("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
                   e("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "Hello"}}),
                   e("content_block_stop", {"index": 0}),
                   e("message_delta", {"delta": {"stop_reason": "end_turn", "stop_sequence": None},
                                       "usage": {"output_tokens": 5}}),
                   e("message_stop", {})]
            return self._sse(evs, abort)
        if "GenerateContent" in p:
            u = {"promptTokenCount": 11, "candidatesTokenCount": 5, "totalTokenCount": 16}
            if "streamGenerateContent" not in p:
                return self._json(200, {"candidates": [{"content": {"parts": [{"text": "Hi"}], "role": "model"},
                                                        "finishReason": "STOP", "index": 0}],
                                        "usageMetadata": u})
            def g(text, fr=None, usage=None):
                o = {"candidates": [{"content": {"parts": [{"text": text}], "role": "model"}, "index": 0,
                                     **({"finishReason": fr} if fr else {})}]}
                if usage:
                    o["usageMetadata"] = usage
                return f"data: {json.dumps(o)}\n\n"
            return self._sse([g("Hel"), g("lo"), g("", "STOP", u)], abort)
        return self._json(404, {"error": {"message": f"stub: no route {p}"}})


async def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    import litellm
    from litellm import Router
    litellm.telemetry = False
    litellm.suppress_debug_info = True

    async def consume(resp, stop_after=None):
        text, usage, n, err = "", None, 0, None
        try:
            async for ch in resp:
                n += 1
                if ch.choices and getattr(ch.choices[0].delta, "content", None):
                    text += ch.choices[0].delta.content
                if getattr(ch, "usage", None):
                    usage = {k: getattr(ch.usage, k, None) for k in ("prompt_tokens", "completion_tokens")}
                if stop_after and n >= stop_after:
                    break
        except Exception as exc:  # noqa: BLE001
            err = type(exc).__name__
        return {"text": text, "usage": usage, "chunks": n, "error": err}

    def last(k=1):
        return SEEN[-k:]

    msgs = [{"role": "user", "content": "hi"}]
    out = []

    async def case(name, coro_fn):
        before = len(SEEN)
        try:
            res = await coro_fn()
        except Exception as exc:  # noqa: BLE001
            res = {"raised": type(exc).__name__, "msg": str(exc)[:160]}
        # never print anything that is not a sentinel (all keys here are sentinels / byok-*)
        out.append({"case": name, "result": res, "stub_hits": SEEN[before:]})

    # (a) Router path. Deployments exactly as server/llm_config.py builds them: model string +
    # max_tokens only, no api_base/api_key (keys come from env).
    r = Router(model_list=[
        {"model_name": "default", "litellm_params": {"model": "openai/gpt-4o-mini", "max_tokens": 64}},
        {"model_name": "claude", "litellm_params": {"model": "anthropic/claude-sonnet-5-5", "max_tokens": 64}},
        {"model_name": "prim", "litellm_params": {"model": "openai/gpt-4o-mini", "max_tokens": 64,
                                                  "api_base": base + "/fail500/v1"}},
        {"model_name": "default-fallback", "litellm_params": {"model": "deepseek/deepseek-v4-pro",
                                                              "max_tokens": 32,
                                                              "api_base": base + "/fb/v1"}},
    ], fallbacks=[{"prim": ["default-fallback"]}], num_retries=1, timeout=10)

    await case("router_openai_percall_key_base_nonstream", lambda: r.acompletion(
        model="default", messages=msgs, api_key="byok-openai", api_base=base + "/v1"))
    async def _rs():
        resp = await r.acompletion(model="default", messages=msgs, stream=True,
                                   stream_options={"include_usage": True},
                                   api_key="byok-openai", api_base=base + "/v1")
        return await consume(resp)
    await case("router_openai_percall_stream_include_usage", _rs)
    async def _ra():
        resp = await r.acompletion(model="claude", messages=msgs, stream=True,
                                   stream_options={"include_usage": True},
                                   api_key="byok-anthropic", api_base=base)
        return await consume(resp)
    await case("router_anthropic_percall_stream", _ra)
    await case("router_fallback_percall_key_follows?", lambda: r.acompletion(
        model="prim", messages=msgs, api_key="byok-primary"))

    # (b) direct litellm calls (compare.py / reviewer fallback / rag._llm shape)
    async def _d(model, key, b, stream=True, stop_after=None, prefix=""):
        resp = await litellm.acompletion(model=model, messages=msgs, stream=stream, api_key=key,
                                         api_base=b, max_tokens=64,
                                         **({"stream_options": {"include_usage": True}} if stream else {}))
        return await consume(resp, stop_after) if stream else {"usage": dict(resp.usage)}
    await case("direct_openai_nonstream", lambda: _d("openai/gpt-4o-mini", "byok-openai", base + "/v1", False))
    await case("direct_openai_stream", lambda: _d("openai/gpt-4o-mini", "byok-openai", base + "/v1"))
    await case("direct_anthropic_stream", lambda: _d("anthropic/claude-sonnet-5-5", "byok-anthropic", base))
    await case("direct_gemini_stream", lambda: _d("gemini/gemini-2.5-flash", "byok-gemini", base + "/v1beta"))
    await case("direct_deepseek_stream", lambda: _d("deepseek/deepseek-v4-pro", "byok-deepseek", base + "/v1"))
    # domestic OpenAI-compatible preset (e.g. Qwen/Kimi/GLM/SiliconFlow) = openai/<model> + fixed api_base
    await case("direct_openai_compatible_domestic_stream",
               lambda: _d("openai/qwen-max", "byok-domestic", base + "/compatible-mode/v1"))
    # aborted streams
    await case("abort_upstream_cut_openai", lambda: _d("openai/gpt-4o-mini", "byok-openai", base + "/abort/v1"))
    await case("abort_upstream_cut_anthropic", lambda: _d("anthropic/claude-sonnet-5-5", "byok-anthropic",
                                                          base + "/abort"))
    await case("abort_client_stops_early_openai",
               lambda: _d("openai/gpt-4o-mini", "byok-openai", base + "/v1", stop_after=1))
    # embedding with per-call key/base (rag._embed_query shape)
    async def _emb():
        return {"n": len((await litellm.aembedding(model="text-embedding-3-small", input=["x"],
                                                   api_key="byok-openai", api_base=base + "/v1")).data)}
    await case("direct_embedding_percall", _emb)

    for o in out:
        print(json.dumps(o, ensure_ascii=False, default=lambda x: {"model": getattr(x, "model", None), "usage": dict(getattr(x, "usage", {}) or {})}))
    srv.shutdown()


class _Emb(H):
    pass


# embeddings route (added here to keep the handler above readable)
_orig_post = H.do_POST


def _post_with_emb(self):  # noqa: N802
    if self.path.endswith("/embeddings"):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        self._rec(body)
        return self._json(200, {"object": "list", "model": body.get("model"),
                                "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
                                "usage": {"prompt_tokens": 1, "total_tokens": 1}})
    return _orig_post(self)


H.do_POST = _post_with_emb

if __name__ == "__main__":
    asyncio.run(main())
