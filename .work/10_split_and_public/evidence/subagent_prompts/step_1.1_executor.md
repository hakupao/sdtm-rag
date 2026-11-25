# step 1.1 writer — executor (opus)

You are implementing step 1.1 of a repo-split project. Work in /Volumes/DevSSD/Project/sdtm-pedia (git monorepo, branch main). The RAG service is in sdtm-rag/ (FastAPI + Chroma + litellm; venv at sdtm-rag/.venv; run python as `.venv/bin/python` from sdtm-rag/). Read first: .work/10_split_and_public/PLAN.md (§2 P1 rows 1.1/1.2), .work/10_split_and_public/evidence/checkpoints/p1_source_consumers.md, .work/10_split_and_public/evidence/checkpoints/p0_baseline.md.

Goal: remove the dependency on the absolute path /Volumes/DevSSD/Project/sdtm-pedia so sdtm-rag/ can later be extracted into its own repo with knowledge_base/ mounted elsewhere — WITHOUT re-embedding anything.

Do:
A. server/rag.py: add one helper that builds a Chroma `where` clause matching a source given as either the absolute path or the KB-relative path (e.g. `{"source": {"$in": [abs, rel]}}`; verify Chroma's `$in` works in our installed version, and that it composes inside `$and`). Route all 5 absolute-path filter sites through it (rag.py ~552, 595, 604, 659, 718). `_relative_source` must stay correct for both forms. Result: the SAME code works against the current chroma (absolute sources) and a migrated chroma (relative sources). This dual compatibility is mandatory: pushing to main auto-deploys while production chroma still has absolute paths.
B. New script sdtm-rag/scripts/migrate_source_relative.py: rewrites the `source` metadata of existing chunks to paths relative to their KB root via `collection.update(ids=..., metadatas=...)` (metadata only, embeddings untouched). Cover collection sdtm_kb_v1 (root = knowledge_base/) and the study collections study_st01 / study_st01_docs (check what their `source` currently holds and what root it is relative to; handle accordingly, or leave them and explain why). Default = dry run printing counts; `--apply` performs it; idempotent; refuses to run if any source is outside the root (report them); takes the chroma dir as an argument.
C. Ingest scripts (scripts/ingest.py, scripts/study/ingest_study.py) write relative `source` from now on.
D. Single source of truth for the KB root: config.py `_REPO_ROOT`/kb_root (~:16, :390-402) plus the ~17 `parents[2|3] / "knowledge_base"` sites in scripts/ and scripts/tests/ (grep it) resolve through one function/setting honoring SDTM_RAG_KB_ROOT_OVERRIDE. Keep the default behavior identical (KB at ../knowledge_base relative to sdtm-rag/).
E. Fix sdtm-rag/.env.service.template: it sets SDTM_RAG_KB_ROOT / SDTM_RAG_CHROMA_DIR but the code reads SDTM_RAG_KB_ROOT_OVERRIDE / SDTM_RAG_CHROMA_DIR_OVERRIDE (silently ignored today). Do not touch deploy/container/ or the .gitea workflow.
F. Tests for A/B/D (unit tests with a tiny temp Chroma are fine).

Gates you must run and report with exact commands and numbers (baseline in p0_baseline.md):
1. pytest `-m "not slow"`: 0 failed (baseline 2585 passed / 2 skipped).
2. Against the CURRENT chroma (unmodified, absolute sources): CDISC 140q and study 48q retrieval-only evals — per-question source_recall identical to baseline (CDISC baseline json: .work/10_split_and_public/evidence/checkpoints/p0_runs/cdisc140.json; study baseline: sdtm-rag/data/study/st01/eval/runs/split10_p0/study48.json).
3. Copy data/chroma to a scratch dir (/private/tmp/claude-501/-Volumes-DevSSD-Project-sdtm-pedia/58914670-fcad-439e-b68e-c96b616605a2/scratchpad/chroma_migrated), run the migration with --apply on the COPY, point the evals at the copy (SDTM_RAG_CHROMA_DIR_OVERRIDE or the eval's own flag — find out), and show per-question identity again. Also confirm the server starts against the copy (S1 `_vi_section_map` warm-up in main.py lifespan, entries count equal to the current one).

Hard constraints:
- NEVER modify sdtm-rag/data/chroma in place; never touch production; do not git push; do not commit (leave changes in the working tree for review).
- Any output file containing study OIDs/labels (study eval results) goes under sdtm-rag/data/study/st01/eval/runs/split10_p1/ (gitignored) — the repo has a pre-commit red-line gate.
- Keep diffs minimal; no refactors beyond the scope above; no new dependencies.
- If a gate fails, do not paper over it: stop, write the failure (inputs, output, diagnosis) to .work/10_split_and_public/evidence/failures/step_1.1_attempt_1.md, and report.

Final report (<500 words): files changed, what each gate printed (with the command), anything you could not do, open risks.
