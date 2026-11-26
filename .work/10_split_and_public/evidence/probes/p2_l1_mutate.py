"""Rule-5 mutation runner for P2 L1: apply one mutation, run the L1 tests, expect >=1 failure, restore."""
import os, shutil, subprocess, sys, pathlib
ROOT = pathlib.Path("/Volumes/DevSSD/Project/sdtm-rag-wt/l1")
P, N, R = "server/providers.py", "server/provider_registry_net.py", "server/provider_registry.py"
M = [
 ("M1 redaction processor removed", P, "return [_redact_processor]", "return []"),
 ("M2 exc_info not rendered before scrub", P, "    if event_dict.get(\"exc_info\"):\n        event_dict = structlog.processors.format_exc_info(logger, method_name, event_dict)\n", ""),
 ("M3 exact-key scrub off (patterns only)", P, "    for s in secrets:\n        if s:\n            text = text.replace(s, REDACTED)\n", ""),
 ("M4 BYOK answer goes through server Router", P, "    if ctx is not None and ctx.credentials is not None and purpose in BYOK_PURPOSES \\\n            and kind != \"embedding\":", "    if False:"),
 ("M5a user key on route calls", P, "BYOK_PURPOSES = (\"answer\", \"continue\", \"regen\")", "BYOK_PURPOSES = (\"answer\", \"continue\", \"regen\", \"route\")"),
 ("M5b user key on embedding (kind guard bypassed)", P, " purpose in BYOK_PURPOSES \\\n            and kind != \"embedding\":", " (purpose in BYOK_PURPOSES or kind == \"embedding\"):"),
 ("M22 cache rewrite ignores kill switch", P, "            and getattr(_settings(ctx.request), \"dossier_prompt_cache\", False)):", "            ):"),
 ("M6 no fail-closed without checked target", P, "            raise ServiceRefusal(400, \"provider_required\", \"BYOK 请求缺少 provider 校验\")", "            return getattr(llm_router, kind), kw"),
 ("M7 row key+null provider not refused", P, "    if ctx.provider is None:\n        raise ServiceRefusal(400, \"provider_required\"", "    if False:\n        raise ServiceRefusal(400, \"provider_required\""),
 ("M8 row no key+provider not refused", P, "        if ctx.provider is not None:\n            raise ServiceRefusal(400, \"byok_key_missing\"", "        if False:\n            raise ServiceRefusal(400, \"byok_key_missing\""),
 ("M9 BYOK-off attempt not refused", P, "        if ctx.provider is not None or has_key_hdr or has_base_hdr:", "        if False:"),
 ("M10 base header allowed on public/non-custom", P, "    if has_base_hdr and (public or ctx.provider != CUSTOM):", "    if False:"),
 ("M11 custom provider visible on public", P, "    if prov is None or (prov.private_only and public):", "    if prov is None:"),
 ("M12 BYOK model not checked vs registry", P, "        if entry is None:\n            _refuse_model(", "        if entry is None and False:\n            _refuse_model("),
 ("M13 key shape check off", P, "    if len(key) > _MAX_KEY_LEN or not key.isprintable():", "    if False:"),
 ("M15 401 not mapped to byok_key_invalid", P, "    if status in (401, 403):", "    if False:"),
 ("M16 answer 5xx not mapped to byok_provider_error", P, "    if purpose != \"answer\" or \"stream_options\" in kw:", "    if True:"),
 ("M17 downgrade free_tier_no_web off", P, "        if default and ctx.tier == \"public\" and ctx.credentials is None:", "        if False:"),
 ("M18 downgrade no_tool_calling off", P, "        if default and caps is not None and not caps.tools:", "        if False:"),
 ("M19 downgrade no_vision off", P, "        if default and caps is not None and not caps.vision:", "        if False:"),
 ("M21 custom base not SSRF-validated", P, "        pin = validate_custom_base(ctx.credentials.api_base)", "        from server.provider_registry_net import PinnedBase; pin = PinnedBase(ctx.credentials.api_base, 'x', 443, '127.0.0.1')"),
 ("N1 address check accepts all", N, "def _address_ok(addr: str) -> bool:\n", "def _address_ok(addr: str) -> bool:\n    return True\n"),
 ("N3b denylist half dropped (is_global only)", N, "    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_unspecified\n                                 or ip.is_loopback or ip.is_link_local or ip.is_private)", "    return ip.is_global"),
 ("N3 is_global dropped (denylist only)", N, "    return ip.is_global and not (", "    return not ("),
 ("N4 http allowed", N, "    if parts.scheme != \"https\":", "    if parts.scheme not in (\"https\", \"http\"):"),
 ("N5 userinfo allowed", N, "    if parts.username is not None or parts.password is not None or \"@\" in parts.netloc:", "    if False:"),
 ("N6 only first DNS answer checked", N, "    for a in addrs:", "    for a in addrs[:1]:"),
 ("N7 no IP pin (connects to hostname)", N, "    request.url = request.url.copy_with(host=pin.ip)\n", ""),
 ("N8 foreign host not refused by transport", N, "    if (request.url.scheme != \"https\" or request.url.host.rstrip(\".\").lower() != pin.host\n            or (request.url.port or 443) != pin.port):", "    if False:"),
 ("N9 sync redirect not refused", N, "        _check_redirect(resp, request)\n", ""),
 ("N10 async redirect not refused", N, "        if 300 <= resp.status_code < 400:\n            await resp.aclose()", "        if False:\n            await resp.aclose()"),
 ("N11 header-injection chars allowed", N, " or any(c in url for c in \"\\r\\n\\t \"):", ":"),
 ('M14 public server-model allowlist off', P, '        if ctx.model not in allowed:\n            _refuse_model(allowed, "该模型在公开站不可用。")', '        if False:\n            _refuse_model(allowed, "该模型在公开站不可用。")'),
 ("M14b public allowlist not L3's (internal groups allowed)", P, '        allowed = public_model_ids(s)', "        allowed = public_model_ids(s) + ['default', 'hard', 'light', 'default-fallback']"),
 ('M20 BYOK dossier auto-attach on', P, '            # dossier="on" / corpus=study stay allowed (no provider whitelist for study data).\n            return False', '            # dossier="on" / corpus=study stay allowed (no provider whitelist for study data).\n            return True'),
 ('M25 preset api_base not passed (env can redirect)', P, '    out["api_base"] = t["api_base"]   #', '    0 and t["api_base"]   #'),
 ('M26 BYOK on compare/validate not refused', P, '    if ctx is not None and ctx.credentials is not None and ctx.endpoint in _NON_BYOK_ENDPOINTS:', '    if False:'),
 ('M27 dict keys not scrubbed', P, '        return {_scrub(k, secrets): _scrub(x, secrets) for k, x in v.items()}', '        return {k: _scrub(x, secrets) for k, x in v.items()}'),
 ('M27b event keys not scrubbed', P, '    return {_scrub(k, secrets): _scrub(v, secrets) for k, v in event_dict.items()}', '    return {k: _scrub(v, secrets) for k, v in event_dict.items()}'),
 ('M28 GLM key pattern removed', P, '    re.compile(_LB + r"[0-9a-fA-F]{32}', '    re.compile(r"NEVERMATCH" + r"[0-9a-fA-F]{32}'),
 ('M31 sync per-call client not closed', P, '            if k.get("client") is not None:\n                k["client"].close()', '            if False:\n                k["client"].close()'),
 ('M32 async per-call client not closed', P, '            if not k.get("stream"):\n                await _aclose_client(client)', '            if not k.get("stream"):\n                pass'),
 ('M33 registry_cost ignores provider_registry_path', R, '    e = (reg or _current_registry()).entry_for_model(model)', '    e = (reg or load()).entry_for_model(model)'),
 ('M34 preset without https api_base accepted', R, '        if not custom and not (isinstance(base, str) and base.startswith("https://")):', '        if False:'),
 ('N12 async transport _pin() call removed', N, '    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:\n        _pin(request, self.pin)\n', '    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:\n'),
 ('N13 sync transport _pin() call removed', N, '    def handle_request(self, request: httpx.Request) -> httpx.Response:\n        _pin(request, self.pin)\n', '    def handle_request(self, request: httpx.Request) -> httpx.Response:\n'),
 ('M23 sk- pattern without left boundary', P, '    re.compile(_LB + r"sk-', '    re.compile(r"sk-'),
 ('M24 mid-stream errors not translated', P, '            return _translating_stream(resp, purpose, provider, client)', '            return resp'),
 ('M29 boundary ignores %XX / escapes', P, '_LB = r"(?:(?<![A-Za-z0-9])|(?<=%[0-9A-Fa-f]{2})|(?<=\\\\[ntrbf])|(?<=\\\\u[0-9A-Fa-f]{4})|(?<=\\\\x[0-9A-Fa-f]{2}))"', '_LB = r"(?<![A-Za-z0-9])"'),
 ('M30 sk- tail digit requirement removed', P, 'sk-(?=[A-Za-z_\\-]*[0-9])', 'sk-'),
]
TESTS = ["tests/test_p2_l1_providers.py", "tests/test_p2_l1_byok_wire.py", "tests/test_p2_l3_instance.py"]
env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
rows, bad = [], 0
for name, f, old, new in M:
    path = ROOT / f
    orig = path.read_text(encoding="utf-8")
    if orig.count(old) != 1:
        rows.append((name, "MUTATION-NOT-APPLIED")); bad += 1; continue
    try:
        path.write_text(orig.replace(old, new), encoding="utf-8")
        for d in ROOT.rglob("__pycache__"):
            if ".venv" not in d.parts: shutil.rmtree(d, ignore_errors=True)
        r = subprocess.run([str(ROOT/".venv/bin/python"), "-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider", *TESTS],
                           cwd=ROOT, env=env, capture_output=True, text=True)
        last = [l for l in r.stdout.splitlines() if " passed" in l or " failed" in l or "error" in l][-1:]
        failed = [l.split("::",1)[1].split(" ")[0] for l in r.stdout.splitlines() if l.startswith("FAILED")]
        ok = r.returncode != 0
        bad += not ok
        rows.append((name, ("RED " if ok else "GREEN(!) ") + (last[0] if last else r.stdout[-200:]) + " | " + ", ".join(failed[:4])))
    finally:
        path.write_text(orig, encoding="utf-8")
for n, res in rows: print(f"{n} => {res}")
print("mutations not caught:", bad)
sys.exit(1 if bad else 0)
