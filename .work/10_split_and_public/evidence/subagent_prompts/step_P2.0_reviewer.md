# P2.0 seam — independent review (read-only)

Repo /Volumes/DevSSD/Project/sdtm-rag, branch `p2`; review `git diff main p2` (4 commits after 8fa8397). READ-ONLY: no edits/commits/push. Never print study OID/label, .env values or keys.

Context: brief `.work/10_split_and_public/evidence/subagent_prompts/step_P2.0_executor.md`; design `docs/design/P2_request_context.md`; checkpoint `.work/10_split_and_public/evidence/checkpoints/p2.0_seam.md`; BYOK spike `.../checkpoints/p2_byok_spike.md`; PLAN `.work/10_split_and_public/PLAN.md` §2 P2 + §6.

Judge:
1. **Private default unchanged**: is the characterization test strong enough (does it record every outbound call incl. streaming, federation, reviewer, HyDE, dossier gate, web search, embedding; is the golden recorded on pre-refactor code — check git history order)? Any behaviour change on default path: exception handling (ServiceRefusal re-raise ahead of 15 broad excepts), SSE event ordering/shape, finalize-on-disconnect, ContextVar leakage across requests/threads (sync endpoints in threadpool, generators, asyncio tasks).
2. **Seam completeness**: does every paid outbound call from the inventory go through `outbound.*`? grep yourself for litellm/Router/Tavily/httpx/cohere outside outbound.py. Can L1 (providers/BYOK), L2 (quota), L3 (instance), L4 (webchat) each finish without editing router.py/rag.py? Name concrete gaps (e.g. history trimming, endpoint registration per tier, /api/info shape, per-request model whitelist, BYOK header parsing, redaction).
3. **Contract v1** (design §2): complete and unambiguous enough for L4 to build from alone? Consistent with existing SSE contract tests? Security: key never in logs/repr/exceptions path designed in?
4. **BYOK spike** conclusions supported by the probe code/commands (esp. Router fallback leaks user key; mid-stream cut usage fabrication)?
5. Worktree setup (design §4) workable for 4 parallel lines; ownership map has no overlapping files.

Run: `.venv/bin/python -m pytest tests/test_p2_seam_characterization.py tests/test_p2_seam_hooks.py -q -o addopts=""`. Output findings table (#, blocker/should-fix/nit, file:line, issue, fix) + verdict PASS / PASS-with-fixes / FAIL. < 700 words, English.
