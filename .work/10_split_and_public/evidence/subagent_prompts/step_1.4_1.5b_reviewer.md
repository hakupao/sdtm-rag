# step 1.4+1.5b reviewer — code-reviewer (opus), independent of the writer

Read-only. Review local unpushed commits on /Volumes/DevSSD/Project/sdtm-rag from 50d8c76 (exclusive) to HEAD: `git log --oneline 50d8c76..HEAD` (submodule vendor/sdtm-pedia, deploy/workflow changes incl. APP_DIR rollback, oidscan rc=2 hint, docs, crossref test fix, red-line collision entries + eval/ scan target, kb_freshness source-path check). Brief: .work/10_split_and_public/evidence/subagent_prompts/step_1.4_1.5b_executor.md; failure/attempt history: .work/10_split_and_public/evidence/failures/step_1.4_attempt_1.md.
Next step after your review: enable Gitea Actions and push; CI builds an image from this HEAD and DEPLOYS it to production (Lima VM; current prod image is monorepo-era 20b8983 with WorkingDir /Volumes/DevSSD/Project/sdtm-pedia/sdtm-rag; prod chroma is already KB-relative; prod .env key SDTM_RAG_DOGFOOD_LOG_OVERRIDE holds an old absolute path and will be rewritten to /app/... before the switch). The orchestrator intends to verify on a test port first — but note: a push auto-deploys. Judge specifically:
1. Will the first CI run on this HEAD succeed end to end (submodule checkout of a public GitHub repo with shallow=true, uv install, tests in a bare runner, docker build context, compose with APP_DIR, health check)? Anything that would deploy a broken image or leave prod down?
2. Is there a safe way to get the image built and pushed WITHOUT auto-deploying (so the test-port check can happen first)? Look at the workflow: workflow_dispatch inputs, if-guards. Recommend the minimal change (e.g. a `deploy` boolean input / branch guard) if needed.
3. APP_DIR rollback logic correctness for both old (monorepo-era) and new images.
4. The two red-line collision additions (BILI global; the Japanese LB term) — does either weaken detection of real study OIDs? (catalog at data/study/st01/catalog.json; never print other OID/label values).
5. kb_freshness check_source_paths: false positives/negatives; side effects (opening chroma).
6. Anything else blocking the deploy switch.
Output: PASS / PASS-with-fixes / FAIL; findings with file:line and fix. < 600 words. English.
