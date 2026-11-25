# step 1.3 reviewer — code-reviewer (opus), independent of the writer

Read-only. A new repo B was extracted with git filter-repo from monorepo /Volumes/DevSSD/Project/sdtm-pedia into /Volumes/DevSSD/Project/sdtm-rag (flattened: monorepo `sdtm-rag/**` → B root; RAG docs/history relocated). Mapping used: /Volumes/DevSSD/Project/sdtm-pedia/.work/10_split_and_public/evidence/checkpoints/p1_step1.3_manifest.md. Intended split: .work/10_split_and_public/PLAN.md and evidence/recon_2026-11-25.md §1.

Independently verify (run your own commands, do not trust the manifest):
1. Completeness: anything RAG-related in the monorepo (HEAD and history) that did NOT land in B and should have — grep monorepo for files that mention sdtm-rag / RAG / 07_rag_kg / KG / study track / Plan B / dossier / C2R etc. in docs/, .work/, milestones/, root; judge each: B, A, or both. Check docs/superpowers classification file by file (58 to B, 5 A-only, restructure-v3 in both).
2. Leakage: anything in B (HEAD or any commit) that belongs to A only (knowledge_base, web, release, ai_platforms, jp_delivery, 06_deep_verification, root README/LICENSE/DISCLAIMER/METHODOLOGY).
3. History integrity: spot-check 5 random B files with `git log --follow` vs the monorepo's history of the corresponding path(s); commit metadata (author/date/message) preserved; that 771 commits is plausible (monorepo commits touching mapped paths).
4. Things in B that will break because they referenced repo-root-relative paths of the monorepo (../knowledge_base is expected and handled via SDTM_RAG_KB_ROOT_OVERRIDE; look for ../.work, ../docs, ../milestones, ../README, CLAUDE.md, .githooks pointing at sdtm-rag/ prefix, .gitea workflow paths, Dockerfile COPY sdtm-rag/...). List them as inputs for step 1.5 (do not fix).
5. Anything sensitive in B's history (secrets patterns: sk-, AKIA, BEGIN PRIVATE KEY, password=; .env files) — B will be private on Gitea, but report.

Output: verdict PASS / PASS-with-fixes / FAIL; numbered findings with evidence; separate list "inputs for 1.5". Under 700 words. English.
