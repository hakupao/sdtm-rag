# P2 parallel lines — common constraints (all of L1–L4)

- Base: branch `p2` @ 0bc3e41 in /Volumes/DevSSD/Project/sdtm-rag. Create YOUR worktree exactly per `docs/design/P2_request_context.md` §4:
  `git -C /Volumes/DevSSD/Project/sdtm-rag worktree add -b p2-<line> /Volumes/DevSSD/Project/sdtm-rag-wt/<line> p2`, then submodule init, `uv sync --extra dev`, **copy** (not symlink) `data/study`. Work ONLY in that worktree; never touch the main worktree (/Volumes/DevSSD/Project/sdtm-rag) or other lines' worktrees. Do not remove your worktree at the end.
- Read: CLAUDE.md, docs/RULES.md, `.work/10_split_and_public/PLAN.md` (§0, §1, §2 P2, §3, §5), `docs/design/P2_request_context.md` (contract v1.1 — frozen; ownership §3 is binding).
- Edit only files your line owns (§3). If you truly need a change in a shared file (router.py, rag.py, outbound.py, request_context.py, compare.py, federation.py, reviewer.py, characterization golden) → STOP that part and report it as a seam gap; do not edit it.
- No push, no dispatch, no ssh, no real paid API calls (fakes/stubs only), never print .env values, keys, study OID/label. Commits on your branch; messages end with:
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01DWp6VzSeRHNMrtwDa6ynE6
  Hook must pass; never --no-verify; never OIDSCAN_NO_CATALOG.
- Private tier (default) behaviour must stay identical: `tests/test_p2_seam_characterization.py` golden unchanged (do NOT regenerate).
- Rule 5: every security/limit check you add gets a mutation check (break it → a test fails → restore; use PYTHONDONTWRITEBYTECODE=1 and clear __pycache__). Record commands + results.
- Do NOT run the CDISC 140q eval (shared chroma; main session runs it at merge).
- Gates on your branch: full `.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs` 0 failed; `node --test webchat/tests/*.test.mjs` pass; no-arg `scripts/oidscan_evidence.py` CLEAN; git status clean.
- Write `.work/10_split_and_public/evidence/checkpoints/p2_<line>.md` (commits, what each acceptance item maps to which test, mutation table, config keys you need added by L3 if any, open risks). Failure → `.work/10_split_and_public/evidence/failures/p2_<line>_attempt_1.md`. Report < 450 words, English.
