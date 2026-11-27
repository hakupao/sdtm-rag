# 独立审查派单: 「KB 更新」提交的暂存 diff (kb-2026.11.28, 2026-11-28)

你是独立审查者 (规则 D: 与写作者不同的 agent 类型、不同 session)。**只读**: 不改任何文件、不提交、不 push、不联网、不 ssh。
仓库: `/Volumes/DevSSD/Project/sdtm-rag` (分支 main)。待审对象: **暂存区** (`git diff --cached`), 共 12 个路径。

## 背景
上游知识库仓发了新 tag `kb-2026.11.28` (提交 `b2bd837`)。本仓这次提交把 submodule `vendor/sdtm-pedia` 升到该 tag, 并带上「只在新 KB 下成立」的一批改动。
允许改什么, 由清单规定: `.work/10_split_and_public/evidence/checkpoints/kb_upgrade_bundle_checklist.md`, **以最后一节「v6 更新」为准** (与前文冲突处以 v6 为准)。
gold (题集 `eval/test_set_v3.yml`) 的 5 处修订都由仓库主人逐条裁定过, 裁定原文在清单 v5 的表 (q39 / q117 / q120 / q126) 和 v6 第 1、2 条 (q76)。

## 要你判断的事 (逐条给结论和证据)
1. **有没有清单 v6 之外的期望值改动。** 逐个 hunk 对照 v6 第 3 条 (测试锚点 18 个 = 计数 4 + PC 示例 6 + R4 映射 8) 和第 2 条 (gold 5 处)、第 4 条 (README 的 tag 字样、`data/meta/meta.yaml`)。每个 hunk 归到清单的某一条; 归不上的列出来。
2. **gold 5 处与主人的裁定是否逐字一致** (字符串、放在哪个键下、是加 / 改 / 删)。特别看: q39 是加进 `expected_sources` (AND) 而不是 any-of; q126 是删掉成员而不是改名; q76 新标题的每个字符。并用新 KB (`vendor/sdtm-pedia/knowledge_base`, 已是新 tag) 核对: q117 / q120 的新 fact 在对应 gold 文件里逐字存在; q76 的新节标题在 `model/06_relationship_datasets.md` 里存在。
3. **测试断言有没有被改弱。** 重点是 `tests/test_examples.py` 的 PC 6 条: 改成「只约束合并例的 14 块」之后, 被排除的那 1 块是否仍被某条断言钉住; 用来区分两类块的条件会不会让断言对被筛掉的块恒成立; 「14 + 1」是否被断言。其余锚点: 是否只是数值 / 路径替换, 有没有顺带删断言、放宽比较符、加 skip / xfail。
4. **`data/meta/meta.yaml` 的差异是否与清单 v6 第 5 条数字总表一致** (`model_defhome` 62 → 75; 新增 / 移除 / 改归属的变量逐个对; 变量字段只应有 DM `RFSTDTC` / `RFENDTC` 的 type 变化)。
5. **范围**: 暂存区里有没有 `server/`、`scripts/`、`deploy/`、`.gitea/`、`pyproject.toml`、`uv.lock` 的改动 (应为零); README 两个文件是否各只改了一处 tag 字样。
6. **submodule 指针**: gitlink 是否为提交 `b2bd8376e51e4d9e751fc49834a87a103a722b2e` (不是 tag 对象); `git -C vendor/sdtm-pedia rev-parse HEAD:knowledge_base` 是否为 `63f857774a42cfaa71798705ad40ab51bc5e378a`。
7. 你自己发现的其他问题 (函数改名后别处有没有残留引用、docstring / 注释与断言是否矛盾等)。

## 可以用的只读命令 (示例)
```sh
cd /Volumes/DevSSD/Project/sdtm-rag
git diff --cached --stat; git diff --cached -- tests eval README.md README_CN.md; git diff --cached -- data/meta/meta.yaml
git diff --cached --submodule=short -- vendor/sdtm-pedia
grep -n "…" vendor/sdtm-pedia/knowledge_base/…
.venv/bin/python -m pytest -q -o addopts="" -p no:cacheprovider tests/test_examples.py tests/test_chapters.py   # 可以跑个别测试文件; 不要跑全量 (另一进程正在跑)
```
不要运行会写文件的命令 (ingest、build_meta、带 `--output` 写进仓库的评测等)。研究数据目录 `data/study/` 不要读、不要引用其中任何内容。

## 输出格式
- 结论: `PASS` / `PASS-with-fixes` / `FAIL`。
- 逐条 (1-7) 的判断 + 证据 (命令与关键输出、文件与函数名; 不引行号也行)。
- 问题清单: 每条标 CRITICAL / MAJOR / MINOR, 说明为什么、建议怎么改。
- 你没有核对到的部分, 明说。
