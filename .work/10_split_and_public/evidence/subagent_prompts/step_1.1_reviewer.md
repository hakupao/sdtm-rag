# step 1.1 reviewer — code-reviewer (opus), independent of the writer

Review the UNCOMMITTED working-tree changes in /Volumes/DevSSD/Project/sdtm-pedia/sdtm-rag (`git -C /Volumes/DevSSD/Project/sdtm-pedia diff` + new files scripts/migrate_source_relative.py, scripts/tests/test_source_relative.py). Read-only; do not edit.

Intent (from .work/10_split_and_public/PLAN.md step 1.1/1.2 and evidence/checkpoints/p1_source_consumers.md): remove dependence on the absolute path /Volumes/DevSSD/Project/sdtm-pedia so sdtm-rag can later move to its own repo with knowledge_base mounted elsewhere, without re-embedding. Requirements: (1) the same code must work against BOTH the current production chroma (absolute `source` metadata) and a migrated chroma (KB-relative `source`) because pushing to main auto-deploys before production chroma is migrated; (2) migration rewrites metadata only, idempotent, dry-run default, refuses out-of-root sources; (3) ingest writes relative sources going forward; (4) KB root resolves through one setting honoring SDTM_RAG_KB_ROOT_OVERRIDE with default behavior unchanged; (5) env template var names fixed.

Check especially:
- Any remaining code path that filters/compares on absolute `source` (grep server/ scripts/ eval/), incl. BM25 index build, study lookup, federation, dossier, reviewer, check_index_freshness / kb_freshness stamps, ingest dedupe/delete-by-source logic.
- The `$in` where-clause: correctness when kb_root is a symlink or not resolved, Windows-style paths irrelevant; behavior when abs == rel edge cases.
- migrate script: partial failure mid-batch (atomicity/resume), metadata keys preserved exactly, chroma_dir argument safety (could it ever hit the live dir by default?).
- Tests: do they actually fail if dual-compat is removed (writer claims 3 fail)? Were existing test fakes changed in a way that weakens what they assert?
- Production deploy implications: Dockerfile still copies KB to /Volumes/... path — does the new code still start in the current container image layout against unmigrated prod chroma? Would the .env.service.template rename break the CURRENT container deploy (does compose/container use that template?).
- Scope creep or missing items (writer intentionally left: root docker-compose.yml var name, oidscan_evidence.py GIT_ROOT, _smoke_batch_b.py, eval/validation_scenarios.py, eval/error_test_set.py, eval/prod_wirein/dm2_e2e_run.py, stale main.py:~203 comment) — are any of these blocking for the split?

Output: verdict PASS / PASS-with-fixes / FAIL; findings ranked by severity with file:line and concrete fix. Under 700 words. English.
