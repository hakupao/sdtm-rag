# step 1.9 KB→RAG sync — independent review (read-only)

Repo /Volumes/DevSSD/Project/sdtm-rag. Review commits dd903a3..26c18b6 (`git diff dd903a3 26c18b6`). READ-ONLY: no edits, commits, push, dispatch, ssh. Never print study OID/label or .env values.

Context: brief `.work/10_split_and_public/evidence/subagent_prompts/step_1.9_executor.md`; design `.work/10_split_and_public/evidence/checkpoints/p1_step1.9_design.md` (v0.2 section); impl notes `.work/10_split_and_public/evidence/checkpoints/step_1.9_impl.md`. Runtime facts: Gitea act_runner 0.6.1, jobs in `docker.gitea.com/runner-images:ubuntu-latest` on the same docker daemon as prod; `valid_volumes` only the CA cert; job mem 2g; prod data root `/Volumes/DevSSD/deploy-data/sdtm-rag/data` (virtiofs into Lima VM); nothing here was run end-to-end on the VM.

Focus, by severity (production data safety first):
1. Can any path (detect, candidate, predeploy, swap, restore, auto-revert, manual `tag=` rollback, `force_data_mismatch`, cancelled job, prune) mutate or lose prod `chroma/` or `meta/` wrongly, or leave prod running with an image/data fingerprint mismatch without failing loudly? Walk each `sdtm-rag.yml` step's `if:` conditions for push vs dispatch(deploy=false / tag=) cases — fingerprints-equal case must behave exactly as before.
2. Candidate isolation: mounts really prevent writes to prod data; `--no-backup` in scripts/ingest.py does not change default behaviour; fingerprint assert; gate definition (≤1 per-question regression) is correctly computed from run_eval output and can't pass vacuously (empty/crashed eval, missing questions, mismatched question sets).
3. Shell/YAML injection (dispatch inputs, ref names from ls-remote), quoting, `set -e` gaps, step output plumbing.
4. Test adequacy: do tests in tests/test_kbsync.py exercise the real code paths or mostly the fake? Re-run the rule-5 mutations claim spot-check yourself for one of them (in a scratch copy under /private/tmp/claude-501/-Volumes-DevSSD-Project-sdtm-rag/db71eca0-5a2d-4881-bb3e-493886e1aee3/scratchpad/rev19/, not the repo).
5. Docs accuracy (deploy/README.md, CLAUDE.md row) vs code.

Run: `.venv/bin/python -m pytest tests/test_kbsync.py -q -o addopts=""`. Output a findings table (#, severity blocker/should-fix/nit, file:line, issue, concrete fix) + verdict PASS / PASS-with-fixes / FAIL. < 700 words, English.
