# step 1.8 fix — executor (opus)

Repo /Volumes/DevSSD/Project/sdtm-rag (main, HEAD d563a56). DO NOT push. Commit locally; every message contains `[skip ci]` and ends with:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DWp6VzSeRHNMrtwDa6ynE6
Pre-commit hook must pass; never --no-verify. Never print study OID/label values. Read CLAUDE.md + docs/RULES.md (rule 5: red-line changes need mutation validation).

Fix these findings from the P1 review (.work/10_split_and_public/evidence/subagent_prompts/step_1.8_reviewer.md):
1. `scripts/precommit_oidscan.py:45` `--diff-filter=ACM` skips renames-with-edits (R). Change to ACMR (consider also pure renames: scanning them is fine and cheap — decide, justify). Update CLAUDE.md line about "只扫 A/C/M, 纯改名不扫" accordingly. **Mutation validation (rule 5)**: in a throwaway clone/worktree under /private/tmp/claude-501/-Volumes-DevSSD-Project-sdtm-rag/db71eca0-5a2d-4881-bb3e-493886e1aee3/scratchpad/fix18/, stage a rename-with-edit of a file whose new content contains a value that the scanner flags (use a synthetic token the scanner is known to flag — e.g. pick one from catalog programmatically without printing it, or construct per the scanner's own test fixtures in tests/), show old filter → not scanned (exit 0), new filter → blocked (non-zero). Add a pytest for the rename case if tests for precommit_oidscan exist (tests/); it must fail on the old code. Record commands + exit codes (no values).
2. `.work/10_split_and_public/evidence/checkpoints/r1_reorg.md:3` status → reviewed PASS-with-fixes → fixed (reviewer prompt step_R1_reviewer.md, fix commit d563a56). In `_progress.json` mark the earlier R1 `DONE_PENDING_REVIEW` entry superseded (keep it, add `"superseded_by"`), and fix stale `decisions_2026_11_25_late` (actual setup = origin with dual push URLs Gitea+GitHub, NOT a Gitea push-mirror).
4. `scripts/oidscan_evidence.py:116-131` DEFAULT_TARGETS misses `.work/ ui/ webchat/ deploy/ viewer/ .gitea/` + root files. Add them (exclude vendor/ submodule, data/, .venv). Measure runtime before/after (report). Run the no-arg audit: must be CLEAN (if a hit, investigate with --show-values locally, never echo; known collision → ALLOWLIST with reason; real OID → stop and report). Keep CLAUDE.md "全仓审计" sentence true.
5. README.md:83 + README_CN.md equivalent: note that a fresh clone / CI (no data/) gives 2550 passed / 61 skipped (local_data tests skip) vs 2609/2 locally with data.
6. `webchat/vendor/README.md:29` stale path → `docs/evidence/checkpoints/chat_ui_redesign_2026-09.md` (verify exists).

Gates after commits: `.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs` 0 failed (report counts); no-arg oidscan CLEAN; `git status` clean. Failure → .work/10_split_and_public/evidence/failures/step_1.8_fix_attempt_1.md and stop. Report < 400 words, English, with exact commands + exit codes.
