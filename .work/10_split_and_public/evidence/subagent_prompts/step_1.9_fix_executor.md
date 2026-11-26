# step 1.9 fix — executor (same writer, opus)

Same constraints as step_1.9_executor.md (no push/dispatch/ssh, `[skip ci]` + trailers, hook must pass, no OID/label/.env values). Review findings (code-reviewer, opus) on dd903a3..26c18b6 — fix all:

1. sdtm-rag.yml:152-154 — on `deploy-swap` failure, don't `compose start` blindly: check `swap-status`; if journal pending run `restore` first (or skip start and leave it to failure steps). Test/explain.
2. Leftover journal after cancelled/timed-out job: `predeploy_check` returns `journal_pending`; `kbcheck` fails loudly on it in ALL decisions (same/forced too).
3. tests/test_kbsync.py:199-200 asserts SystemExit for the wrong reason (journal-guard mutation `if False` at kbsync.py:204 survived). Add a test: leftover journal + valid `chroma_prev_<fp>` source → swap refused. Re-run that mutation: must be killed.
4. Non-KB guard (kbsync.py:361-367) compares names+counts only → compare a per-collection content digest (sorted ids + hash of documents/metadatas; no values printed).
5. Gate (kbsync.py:130-156) is relative only → also require identical question-id sets, n_questions ≥ 140, candidate full-hit count ≥ baseline − 1, and candidate avg source recall ≥ 0.95. Tests for each.
6. `restore`: assert end state (`stamp_fp(chroma) == old_fp`, no stray dirs) before unlinking journal; else keep journal, non-zero.
7. `image_fp`: emit stderr tail on failure (to stderr).
8. deploy/README.md: fix "logs only counts + ids" wording (failing step prints stderr tail); document that `force_data_mismatch` can't override a `swap` decision whose collection guard fails.
9. sdtm-rag.yml:203-213: gate image rollback on the deploy step having actually started (kbcheck failure → prod untouched).
10. Open question → fix: `collections()` opens prod chroma rw with the TARGET image's chromadb. Compare chromadb version (target vs running image); if different, run the guard on a copy (or fail with clear message) so no schema migration touches prod before swap. Also the candidate pipeline: record chromadb version in the gate marker; predeploy refuses a candidate built with a different chromadb version than the target image.
11. Correct step_1.9_impl.md: mutation (a) killed 2 tests not 1; add review findings + dispositions table.

Re-run rule-5 mutations for (a),(b),(c) + journal guard + new gate floors; full pytest; actionlint; no-arg oidscan CLEAN; git status clean. Append results to step_1.9_impl.md. Report < 400 words, English.
