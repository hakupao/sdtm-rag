# step 1.4 + 1.5b writer — executor (opus): KB submodule + 1.5a review fixes (repo B, local only)

Repo B: /Volumes/DevSSD/Project/sdtm-rag (branch main; origin = Gitea, Actions DISABLED — keep disabled; do not push). Read: .work/10_split_and_public/PLAN.md, evidence/checkpoints/p1_step1.3.md, p1_step1.6b_github.md, and the 1.5a review findings summarized below. Repo A (KB) is now PUBLIC on GitHub with rewritten history: https://github.com/hakupao/sdtm-pedia.git, main = ebf0c8a (KB lives at `knowledge_base/` inside A). Monorepo /Volumes/DevSSD/Project/sdtm-pedia must NOT be modified (its push URLs are disabled; read-only use OK).

1.4 Submodule:
- `git submodule add https://github.com/hakupao/sdtm-pedia.git vendor/sdtm-pedia`, pin to ebf0c8a, `.gitmodules` with `shallow = true` (and document `git submodule update --init --depth 1`). Default KB root becomes `<B root>/vendor/sdtm-pedia/knowledge_base` (server/config.py ~403 + its test). Verify the pinned KB tree equals the monorepo knowledge_base blob-for-blob.
- Dockerfile: `COPY vendor/sdtm-pedia/knowledge_base ./vendor/sdtm-pedia/knowledge_base` (only the KB, never the whole of A); dockerignore `!vendor/sdtm-pedia/knowledge_base/**` (everything else under vendor excluded); workflow path filter: the gitlink path `vendor/sdtm-pedia` + `.gitmodules`; add `eval/**` and `README.md` to the path filter (they are copied into the image). Checkout `submodules: true` works for a public GitHub URL (no auth needed) — note it.
- Update all wording that says `<root>/knowledge_base` (CLAUDE.md, deploy/README.md, Dockerfile header, oidscan_evidence.py docstring + its ABORT hint, deploy/deploy.sh).
1.5b Review fixes:
- HIGH rollback across the 1.5a boundary: compose mount targets `${APP_DIR:-/app}/data` and `${APP_DIR:-/app}/.env`; in the workflow deploy step set `APP_DIR=$(docker image inspect -f '{{.Config.WorkingDir}}' "$IMAGE:$TAG")` after pull, export it for compose (old monorepo-era images have WorkingDir /Volumes/DevSSD/Project/sdtm-pedia/sdtm-rag and expect KB at the old absolute path baked into the image — that still works because their KB is inside the image). Document in deploy/README "回滚".
- CI pytest: add `-rs` so skip reasons show; note in CLAUDE.md which KB/index gates skip in CI.
- precommit_oidscan.py: on rc=2 print the "KB 缺失 → git submodule update --init --depth 1" hint instead of the collision/ALLOWLIST hint.
- Narrow BILI: replace the global KNOWN_PUBLIC_COLLISIONS entry with a path-scoped ALLOWLIST entry for ("eval/error_test_set.py","BILI") with reason (CDISC LBTESTCD C38037, synthetic LB data) — only if the gate still passes on all tracked files; otherwise keep global and explain.
- docs/PROGRESS.md: Phase 7 row → ≤ 3 lines (containers on the Lima VM since 2026-11-04, Neo4j retired 2026-11-07; pointers to checkpoints); move the long "近 30 天" history text verbatim into docs/history/progress_phase7_snapshot_2026-11-25.md and leave a pointer.
- eval/prod_wirein/judge_workflow{,_v2}.js hardcode /Users/<user>/MyProject/sdtm-pedia... → make paths relative/derived (repo is going public).
- Fix commit message count claim is historical — just note 53 in docs where you mention it.
Gates (exact commands + numbers):
1. Fresh: `git submodule update --init --depth 1`; WITHOUT any SDTM_RAG_KB_ROOT_OVERRIDE: `.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs` → 0 failed (expect ≈2605 passed / 2 skipped locally with data).
2. CDISC 140q and study 48q retrieval-only per-question identical to baselines (p0_baseline.md commands; baselines: .work/10_split_and_public/evidence/checkpoints/p0_runs/cdisc140.json in THIS repo, and data/study/st01/eval/runs/split10_p0/study48.json in the MONOREPO path /Volumes/DevSSD/Project/sdtm-pedia/sdtm-rag/data/study/st01/eval/runs/split10_p0/study48.json); outputs with OIDs under B/data/study/st01/eval/runs/split10_p14/.
3. Bare clone simulation: `git clone --recurse-submodules --shallow-submodules` B HEAD into scratchpad (/private/tmp/claude-501/-Volumes-DevSSD-Project-sdtm-pedia/58914670-fcad-439e-b68e-c96b616605a2/scratchpad/), `uv sync --frozen --extra dev`, run the exact CI test command → 0 failed; report counts.
4. Docker static check again (all COPY sources exist; image contains only vendor/sdtm-pedia/knowledge_base from A).
5. All commits through the pre-commit hook (CLEAN), no --no-verify; no env override needed anymore for commits.
Constraints: local commits only, no push, Actions stay disabled, do not touch production or the monorepo. Failures → failures/step_1.4_attempt_1.md and stop. Trailer lines on every commit:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DWp6VwgUn7w9cMEki8hgQv
Final report < 600 words, English.
