# P2 per-line review (read-only) — line given in the invocation (l1/l2/l3/l4)

Worktree /Volumes/DevSSD/Project/sdtm-rag-wt/<line>, branch `p2-<line>`; review `git -C <worktree> diff p2 p2-<line>`. READ-ONLY: no edits/commits/push; never print keys, .env values, study OID/label.
Context: line brief `.work/10_split_and_public/evidence/subagent_prompts/step_P2_<LINE>_executor.md` + `step_P2_lines_common.md`; contract + ownership `docs/design/P2_request_context.md` (v1.1, §2/§3 binding); PLAN `.work/10_split_and_public/PLAN.md` §2 P2 row for the line; line checkpoint `.work/10_split_and_public/evidence/checkpoints/p2_<line>.md`.
Judge, by severity:
1. Ownership: only owned files changed? Any contract deviation (§2) or seam-rule violation (§3: ctx None pass-through, settings from ctx.request.app.state, ServiceRefusal only, no ctx serialisation, BYOK no Router fallbacks, settle-after-finalize no-op)?
2. Private tier (default) behaviour unchanged — any observable change? (characterization golden untouched?)
3. Security / abuse for public tier relevant to the line (bypasses, header trust, key leakage, SSRF, quota races, DoS, XSS for UI).
4. Acceptance items from PLAN each truly tested (not vacuous); spot-check ONE mutation yourself in a scratch copy under /private/tmp/claude-501/-Volumes-DevSSD-Project-sdtm-rag/db71eca0-5a2d-4881-bb3e-493886e1aee3/scratchpad/rev_<line>/ (not the worktree).
5. Merge risk with the other lines (L3→L1→L2→L4 order).
Run the line's new tests from the worktree with its venv (`SDTM_RAG_CHROMA_DIR_OVERRIDE=/Volumes/DevSSD/Project/sdtm-rag/data/chroma`). Output findings table (#, blocker/should-fix/nit, file:line, issue, fix) + verdict PASS / PASS-with-fixes / FAIL. < 600 words, English.
