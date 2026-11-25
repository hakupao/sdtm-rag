# step 1.8 P1 审查修复 (2026-11-25)

派单 `evidence/subagent_prompts/step_1.8_fix_executor.md`; 审查 `step_1.8_reviewer.md`。代码提交 dcdee7f。

## 1. pre-commit 闸 ACM → ACMR (规则 5 变异验证)
纯改名也纳入: 内容在旧路径进 git 时可能早于闸存在, 重扫只多 1 个文件, 不值得留盲区。
```sh
S=<scratchpad>/fix18; MAIN=/Volumes/DevSSD/Project/sdtm-rag
git worktree add --detach $S/old d563a56            # 旧代码 (ACM)
# $S/repo: git init + diff.renames=true; 提交 a.md → git mv a.md b.md → 追加 1 个真 OID needle
#   (从 load_needles 程序化取, 不打印, len=7) → git add -A  ⇒ name-status: R098 a.md b.md
cd $S/repo && PYTHONPATH=$S/old SDTM_RAG_KB_ROOT_OVERRIDE=$MAIN/vendor/sdtm-pedia/knowledge_base \
  $MAIN/.venv/bin/python -m scripts.precommit_oidscan --catalog $MAIN/data/study/st01/catalog.json --repo-root $S/repo
#   → rc=0 "无可扫文件" (漏扫)
cd $S/repo && PYTHONPATH=$MAIN ... (同上)          # 新代码 (ACMR)
#   → rc=1 拦下, 输出 1 条 <OID len=7>, 输出不含真值 (程序化比对 False)
```
pytest `test_staged_files_include_rename_with_edit`: 旧过滤 → 1 failed; ACMR → pass。

## 4. 全仓审计默认面
补 `.work/ ui/ webchat/ deploy/ viewer/ .gitea/` + 仓根文件 (不含 .env); 不含 vendor/ data/ .venv。
`/usr/bin/time -p .venv/bin/python scripts/oidscan_evidence.py`: 前 970 文件 17.7s CLEAN → 后 1090 文件 19.5s CLEAN (rc=0)。

## 5. 测试计数 (dcdee7f)
- 本机: `.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs` → 2610 passed / 2 skipped
- 全新 clone (`git clone` 本仓 + `submodule update --init --depth 1`, 无 data/) 同命令 → 2551 passed / 61 skipped
