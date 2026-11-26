# step 1.9 wording pass — executor (opus)

Repo /Volumes/DevSSD/Project/sdtm-rag (main). User feedback: the Chinese text added in step 1.9 is too colloquial ("太口语化"); make it standard written technical Chinese (规范书面技术中文). DO NOT push/dispatch/ssh. Commit locally once, message contains `[skip ci]`, ends with:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DWp6VzSeRHNMrtwDa6ynE6
Hook must pass; never --no-verify.

First read and follow: /Users/bojiangzhang/.claude/skills/simplify-zh-cn-tech-docs/SKILL.md and its references/style-guide.md, references/examples.md. Content invariant is strict: change expression only, never facts/conditions/numbers/modality.

Scope = only text introduced/changed in step 1.9 (`git diff dd903a3 HEAD -- <file>` to locate it):
1. `deploy/README.md` — the「KB 同步」section and the data-related parts of「回滚」.
2. `.gitea/workflows/kb-sync.yml` and `.gitea/workflows/sdtm-rag.yml` — comments, step `name:`s, `echo` messages added in 1.9. Do not change any logic, quoting, variable names, step ids, `if:` expressions.
3. `CLAUDE.md` — the「KB 更新」table row (keep CLAUDE.md ≤ 80 lines).
4. `deploy/kbsync/kbsync.py` — module/function docstrings, comments, printed/raised message text. Do NOT change JSON keys/values, decision strings (same/changed/gated/journal_pending/swap/...), CLI names, or any string tests assert on (grep tests/test_kbsync.py for `match=` and literal comparisons first).
5. Design doc v0.2 section in `.work/10_split_and_public/evidence/checkpoints/p1_step1.9_design.md`.
Out of scope: evidence/failure/checkpoint logs, prompts, commit history, other files.

Typical problems to fix: 口语词 (搞/弄/先人工/判不出/退不干净/起不来/换上/拦下/对得上), 箭头 "→" 当谓语串句, 括号套括号, 中英混杂可用中文的词, 过长一行多条件。Keep protected content (code, paths, identifiers, commands, inputs like `force_data_mismatch`) unchanged. Bilingual: keep Chinese; don't translate to English.

After: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_kbsync.py -q -o addopts="" -p no:cacheprovider` pass; full `-m "not slow"` 0 failed; `actionlint -ignore 'undefined variable "gitea"' -ignore SC2034 .gitea/workflows/*.yml` rc 0; `python3 -c "import ast;ast.parse(open('deploy/kbsync/kbsync.py').read())"`; verify with `git diff --word-diff` that no non-text token changed in .yml/.py (report how you checked). Report < 250 words, English, plus 5 before→after examples.
