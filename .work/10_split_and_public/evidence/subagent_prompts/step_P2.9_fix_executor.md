# P2.9 fix round — executor (opus)

Work in the MAIN worktree /Volumes/DevSSD/Project/sdtm-rag, branch `p2` @ bacd29a (all lines merged; main session idle; do not touch sdtm-rag-wt/*). No push/dispatch/ssh, no paid calls. Commits end with:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DWp6VzSeRHNMrtwDa6ynE6
Hook must pass; never --no-verify. Never print keys/.env/study OID/label. Read: CLAUDE.md, docs/RULES.md, `docs/design/P2_request_context.md` (v1.1; you may bump to v1.2 with changelog if contract changes, e.g. new code `site_busy`), PLAN `.work/10_split_and_public/PLAN.md` §1/§2/§5, checkpoints p2.0_seam / p2_l1..l4 (in `.work/10_split_and_public/evidence/checkpoints/`). Ownership map no longer applies (integration); private-tier behaviour must stay identical (characterization golden unchanged).

Two independent reviews (code-reviewer CR, security-reviewer SR) on `main..p2` → both PASS-with-fixes. Fix:

**Pre-P3 must**
1 (SR1/CR3) aborted/failed calls charged full max_output reservation → 5-6 aborts drain $3 free pool. In `_metered`: count streamed text; when usage missing settle at prompt_est + ceil(1.5 × streamed tokens); an open that fails before first chunk = prompt-only; the narrow stream_options retry must not double-charge. Plus public check (below #4) on per-round estimate.
2 (CR1) public can boot unmetered (`QUOTA_ENABLED=false`/typo): `check_startup` refuses public unless quota enabled. Strict bool parsing for all quota/instance-related bools (raise on unknown strings: `ture`, `y`…) — kill switch typo must not fail open.
3 (CR2) startup `quota.validate(s)`: parse every `_DEFAULTS` key (raise on malformed / unknown `SDTM_RAG_QUOTA_*`-style misspellings where detectable), log effective values (no secrets). Prefer promoting to typed Settings fields if clean.
4 (SR9/CR7) public `check_startup` also requires: explicit `SDTM_RAG_SELECTABLE_MODELS` set; every public model has explicit max_output_tokens and single-round estimate ≤ free_pool/10; `security_headers_enabled=True`.
5 (CR4) open-reservation saturation (settled < cap) → new code `site_busy` with short Retry-After, not `site_cap_reached`; webchat notice text zh/en (L4 files) + contract v1.2.
6 (SR2) trusted proxies: refuse broad CIDRs on public (prefix < /24 v4, < /120 v6 — justify); document in deploy notes for P3 that public must bind 127.0.0.1 / dedicated network and trust only cloudflared (compose is P3.2 — don't change compose now, write the requirement into `docs/design/P2_request_context.md` §5 "P3 readiness").
7 (SR3) global RateLimitMiddleware: on public key on `resolve_client_ip(scope, trusted, v6)`; refuse `rate_limit_trust_forwarded` on public.
8 (SR8) dependency CVEs: bump litellm ≥1.88.6, aiohttp ≥3.14.4, urllib3 ≥2.8.0, anyio ≥4.14.2, pydantic-settings, certifi to fixed versions via `uv lock --upgrade-package …` (minimal set); re-run full gates; record `uvx pip-audit` before/after (command in report).
9 CR test gap: one public end-to-end module driving `create_app(public)` with quota on through ask + ask_stream: L3/L1 refusal doesn't consume a free question; BYOK on public charges BYOK pool not free count; quota off → refuse start; abort charges per #1.

**Should-fix**
10 (SR5) per-IP in-flight cap (default 3) via admit/finalize. 11 (SR6) `/api/flag`: per-IP daily byte cap + file size cap (429/507). 12 (SR7) stdlib logging filter applying `providers.redact_text` on root/litellm/httpx handlers; litellm/httpx ≥ WARNING on public. 13 (CR5) sync /api/ask refusal on a continue round keeps parts (truncated + code) like continue_error; update the pinned test deliberately and say so. 14 (CR6) single owner for free-web policy (drop the L2 key or have L1 read it). 15 (SR14 + CR q2) count byok_key_invalid per IP/day → refuse after N; BYOK Tavily per-IP/day already 30 — ensure the $2 pool can't be drained by one IP in a day (per-IP share of BYOK side budget, e.g. ≤ $0.5/IP/day; justify).

**Nits**
16 SR10 prune quota_store rows older than N days. 17 SR11 trust_env=False on pinned clients. 18 SR12 `/api/info` Cache-Control: no-store. 19 SR13 DOMPurify → latest 3.x (vendor file + provenance note) and FORBID_TAGS form/input/button/textarea/select/style. 20 CR8 compare: cancel siblings on first refusal. 21 CR9 untake BYOK web counter on cap refusal. 22 CR10 ruff clean on new code.

**Decision recorded (no code)**: per-IP free limit 30/day vs "10 per visitor" — accepted; total bounded by the $3 free pool; record in PLAN §1 as "已裁 (主会话, 2026-11-26)" line and in design §5.

Rule 5: mutation for every new check (#1,2,4,5,6,7,10,11,15 at least). Gates: full pytest 0 failed, node pass, characterization golden unchanged, CDISC 140q NOT needed (main session runs), oidscan CLEAN, ruff clean on changed files, git clean. Write `.work/10_split_and_public/evidence/checkpoints/p2.9_fix.md` (finding → commit → test → mutation). Failure → `.work/10_split_and_public/evidence/failures/p2.9_fix_attempt_1.md`. Report < 450 words, English.
