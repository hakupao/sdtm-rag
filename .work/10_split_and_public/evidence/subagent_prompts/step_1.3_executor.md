# step 1.3 writer — executor (opus): extract repo B (sdtm-rag) with git filter-repo

Context: monorepo /Volumes/DevSSD/Project/sdtm-pedia (DO NOT modify it, its working tree, refs, or remotes). Read: .work/10_split_and_public/PLAN.md (§2 P1, §6), .work/10_split_and_public/evidence/recon_2026-11-25.md §1-§2. B = the RAG service + its docs/history; A = everything else (KB, website, releases...). History must be preserved.

Produce B at /Volumes/DevSSD/Project/sdtm-rag (must not exist yet; abort if it does). Method: `git clone --no-local /Volumes/DevSSD/Project/sdtm-pedia <scratch>` (scratchpad: /private/tmp/claude-501/-Volumes-DevSSD-Project-sdtm-pedia/58914670-fcad-439e-b68e-c96b616605a2/scratchpad/), run git filter-repo there, then move/clone the result to the final path. Only branch `main` matters; drop all tags (they belong to A) and remote-tracking refs.

Target layout of B (flattened):
- `sdtm-rag/**` → `**` (repo root). Historical location `branches/07_rag_kg/sdtm-rag/**` → `**` as well.
- `milestones/07_rag_kg/**` and the non-sdtm-rag parts of historical `branches/07_rag_kg/**` → `docs/history/07_rag_kg/**` (check how restructure v3 mapped branches/07_rag_kg/X → milestones/07_rag_kg/X so both eras land on the same paths; see .work/09_repo_refactor_v3/ and docs/superpowers/*/2026-07-21-repo-restructure-v3*).
- `docs/DESIGN_RAG_KG.md` → `docs/design/DESIGN_RAG_KG.md`
- RAG-related files under `docs/superpowers/{plans,specs}/` and the 2 RAG RETROSPECTIVEs in `docs/superpowers/` → same relative path under `docs/superpowers/`. Decide per file from its content (recon says 28/31 plans, 26/30 specs are RAG; A-side are the phase6.5, sdtm-release-website and website-motion-design ones; repo-restructure-v3 is ambiguous → include in BOTH, i.e. keep it in B too; A will keep its copy).
- `.work/05_rag_kg/**` → `docs/history/05_rag_kg/**`
- `.work/meta/{study_rag_handoff_2026-08-04.md,verified_spotcheck_handoff_2026-09-04.md,workflow_events_handoff_2026-08-26.md}` → `docs/history/handoffs/`
- `.work/meta/worklog/phase_07_rag_kg.md` → `docs/worklog/phase_07_rag_kg.md`
- `.gitea/**` → `.gitea/**`, `.githooks/**` → `.githooks/**` (content fixes come in step 1.5, not now)
- Include renamed-from historical paths of every kept file (use `git log --all --name-status -M` over the monorepo to find earlier names), so history of each kept file is continuous.
- Must NOT contain any A content at HEAD (knowledge_base/, web/, milestones other than 07_rag_kg, release, ai_platforms, jp_delivery, 06_deep_verification, source/, tools/, root README/LICENSE etc.). sdtm-rag/ has its own README.md which becomes B's root README — fine.
- Watch path collisions after flattening (sdtm-rag/docs/ already exists → merges with docs/; report any same-path collision and stop if one occurs).

Verification (report each with the exact command and output):
1. For every file at monorepo HEAD that maps into B, its blob hash at B HEAD under the mapped path is identical; and B HEAD has no file outside the mapping. Report counts.
2. `git -C B log --oneline | wc -l`, earliest commit date, `git log --follow` works for 3 sample files (server/rag.py, docs/design/DESIGN_RAG_KG.md, docs/worklog/phase_07_rag_kg.md) back to their first commit.
3. No secrets/data ever in B history: `git -C B log --all --name-only --format=` has no path matching `data/study/|data/chroma|\.env$|dogfood_failures` (`.env.example` / `.env.service.template` are fine).
4. Pack size of B.
5. In B: create .venv with `uv sync` and run `pytest -m "not slow" -q -o addopts=""` with `SDTM_RAG_KB_ROOT_OVERRIDE=/Volumes/DevSSD/Project/sdtm-pedia/knowledge_base` and `SDTM_RAG_CHROMA_DIR_OVERRIDE=/Volumes/DevSSD/Project/sdtm-pedia/sdtm-rag/data/chroma` (read-only use) — tests depending on data/study will need data: symlink B/data/study → monorepo sdtm-rag/data/study is acceptable for this check (data/ is gitignored). Report pass/fail counts vs baseline (2603 passed / 2 skipped at commit 33ac656). Failures caused by moved paths (e.g. code that referenced ../.work or ../docs or repo-root-relative paths) must be listed, not fixed — fixing is step 1.5.

Hard constraints: do not push anywhere; do not add remotes; do not touch the monorepo; do not commit to the monorepo. Write a manifest of the path mapping you actually used to /Volumes/DevSSD/Project/sdtm-pedia/.work/10_split_and_public/evidence/checkpoints/p1_step1.3_manifest.md (paths only, no study OIDs). If anything fails, record it in .work/10_split_and_public/evidence/failures/step_1.3_attempt_1.md and stop.

Final report < 600 words, English.
