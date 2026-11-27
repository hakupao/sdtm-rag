# PC examples 切块修复：报告

- 分支：`hakupao/fix-pc-examples-chunker`（工作区 `/Users/bojiangzhang/orca/workspaces/sdtm-rag/fix-pc-examples-chunker`）
- 提交：`d22b5bf`（按 H2 分派）、`43e1aea`（审查后补修：首个 H2 之前的 Method H4）、`b7d2664`（只改测试：补上复审发现的 N3 缺口），基线是 `647fb9c`。三个提交都在本地，没有 push
- 改动文件：`scripts/chunkers/examples.py`、`tests/test_examples.py`，只改了这两个
- 未 push、未合并、未开 PR，submodule 指针没动，没有写主仓文件夹和 pedia 仓
- `d22b5bf` 和 `43e1aea` 改了运行时路径 `scripts/`，消息里没有加 `[skip ci]`。是否推、何时推由主人决定，按 v3 第 1 条，必须在 pedia 打 tag 之前进 main

## 实现
- 每个 H2 管到下一个 H2 之前为止。范围里有以 `Method ` 开头的 H4，就进嵌套模式：每个 H4 一块，结尾截在本 H2 的末尾，父 H3 只在本 H2 里找，`sub_label` 取自 H4。范围里没有这样的 H4，整个 H2 就是一块，行为与原来的平铺分支一致。
- `cdisc_section_id` 只取本 H2 自己的 `§` 编号，没有就是 None。没有硬编码映射，也不向前面的 H2 继承。
- 首个 H2 之前的区域（包括整个文件都没有 H2 的情况）只在含 Method H4 时按嵌套切块，节号为 None，否则照旧丢弃。这一条来自审查的 MEDIUM 意见：如果只按 H2 遍历，没有 H2 的文件会整篇丢失。
- `chunk_index` 按文档顺序在整个文件里连续编号。

## 验收结果

### 1. 两版 KB 全部 `domains/*/examples.md`，修复前后全字段比较
- **旧 KB**（`f863e45445a6`）：63 个文件，修复前后都是 209 块，**0 差**。
- **新 KB**（`bf33babcfd29`，pedia `00a2e93`）：只有 PC 变了，从 14 块变成 15 块。
  - 新增 1 块：`section='PC – Examples'`，`chunk_index=0`，`cdisc_section_id=None`，`example_index=None`，`sub_label=None`，`has_table=True`，4946 tokens。
  - 原来的 14 块正文不变，但有两个字段变了，所以严格的全字段比较不只是「新增 1 块」：
    - `chunk_index` 从 0..13 变成 1..14，因为新块排在文档最前面。块 ID 由 `source#chunk_index` 拼成（`scripts/ingest.py:337`），所以 ID 会跟着平移。审查者查过，eval、data、tests 里没有任何 gold 引用 `examples.md#<n>`，入库时也是整体重建。
    - `cdisc_section_id` 从 None 变成 `§6.3.5.9.3`。修复前的代码只看第一个 H2，在新 KB 下这 14 块的节号已经悄悄丢了，修复后取回了与旧 KB 相同的值。
  - 不计 `chunk_index`、`kb_commit_sha` 时，这 14 块与旧 KB 的 14 块相比，只有 3 块正文不同（例 1 Method D、例 2 Method D、例 3 Method A），差异是上游对 KB 内容本身的修订（`PPSEQ values "1" through "7"`、`DY1DRGX_A`），与切块无关。

### 2. 旧 KB 下 `pytest -m "not slow"`
- 修复前：1 failed / 2890 passed / 61 skipped
- 修复后（`43e1aea`）：1 failed / 2899 passed / 61 skipped
- 两次失败的都只有 `test_p2_seam_characterization.py::test_p2_seam_outbound_calls_and_responses_unchanged`，是已知的日期问题。多出的 9 条通过都是新加的合成测试，没有新失败。

### 3. 覆盖率扫描（只读借用主仓 p3 的 `probes/kb_rehearsal_coverage.py`）

| | PC 行数 | PC 缺失行数 |
|---|---|---|
| 旧 KB，修复前 / 后 | 347 | 4 / 4 |
| 新 KB，修复前 | 390 | **47** |
| 新 KB，修复后 | 390 | **3** |

- 两版 KB 里，除 PC 外没有任何文件的覆盖率变化。
- 剩下的 3 行是 KB note、`## §6.3.5.9.3` 标题和 H3 导语，修复前就没有进任何块，不是这次带来的。

### 4. 变异验证（规则 5）
- 每个变异都在工作区文件上替换且只命中一处。替换前先比对 sha，确认文件仍是冻结的快照；替换后回读确认 sha 已经变了；`finally` 里用快照的原始字节写回，不用 `git checkout`。运行时设 `PYTHONDONTWRITEBYTECODE=1`。
- 脚本在会话临时目录（未入库）的 `tools/mutate.py`，输出在同目录下的 `mutation_output.txt`。

| 变异 | 结果（全部杀死） |
|---|---|
| M1 嵌套判定改回看整个文件的 H4 | 3 条测试变红：s2、swallow、methods_before_first_h2 |
| M2 节号一律取 `h2s[0]` | 4 条变红 |
| M3 H4 的结尾不截在 H2 末尾 | 2 条变红 |
| M4 父 H3 不限在本 H2 内找 | 1 条变红 |
| M5 平铺块的 `example_index` 置为 None | 1 条变红 |
| M6 首个 H2 之前的区域永远不切块 | 2 条变红 |
| M7 嵌套判定要求至少 2 个 H4 | 2 条变红 |
| M8 平铺 H2 继承前一个 H2 的节号 | 2 条变红 |
| M0 用修复前的原代码跑新测试 | 4 failed / 24 passed |

- 还原后文件 sha 为 `c94c1df5e9a52f99`，与 `43e1aea` 一致。
- 审查者在自己的拷贝上又独立做了 7 个变异，也全部被杀死。

复跑命令（在工作区根目录执行）：
```sh
S=<会话临时目录>   # 未入库
OLD=/Volumes/DevSSD/Project/sdtm-rag/vendor/sdtm-pedia/knowledge_base
NEW=$S/newkb/knowledge_base   # git -C /Volumes/DevSSD/Project/sdtm-pedia archive 00a2e93 knowledge_base | tar -x -C $S/newkb
export PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=. .venv/bin/python $S/tools/dump_examples.py $OLD $S/after_old.json && .venv/bin/python $S/tools/diff_dumps.py $S/before_old.json $S/after_old.json
PYTHONPATH=. .venv/bin/python $S/tools/dump_examples.py $NEW $S/after_new.json && .venv/bin/python $S/tools/diff_dumps.py $S/before_new.json $S/after_new.json
SDTM_RAG_KB_ROOT_OVERRIDE=$NEW PYTHONPATH=. .venv/bin/python $S/tools/kb_rehearsal_coverage.py $NEW $S/cov_new_after.json
cp scripts/chunkers/examples.py $S/examples_fixed.py && SDTM_RAG_KB_ROOT_OVERRIDE=$OLD .venv/bin/python $S/tools/mutate.py $S/examples_fixed.py
SDTM_RAG_KB_ROOT_OVERRIDE=$OLD .venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rf -p no:cacheprovider
```
- `before_*.json` 是用 `647fb9c` 的代码导出的修复前快照。

## 新 KB 下 PC 相关测试需要的期望值（未提交，随 KB 升级一起提交）
用 `SDTM_RAG_KB_ROOT_OVERRIDE=$NEW` 跑 `tests/test_examples.py`，结果是 6 failed / 22 passed。需要改的值如下：

| 测试 | 新 KB 下的实际值 / 需要的改法 |
|---|---|
| `test_pc_examples_produces_14_chunks` | 改为 15 |
| `test_pc_examples_all_have_sub_label_method` | 只约束 `section` 以 `Method ` 开头的 14 块。Example 1 块的 `sub_label` 是 None |
| `test_pc_examples_sub_labels_are_valid_methods` | 同上 |
| `test_pc_examples_all_have_example_index` | Example 1 块的 `example_index` 是 **None**（按 H2 标题解析，平铺行为不变），只约束那 14 块 |
| `test_pc_examples_example_indices_range_1_to_4` | **也会失败**：`1 <= None` 抛 TypeError。v3 第 3 条的表格写的是「仍过」，那只在按 H3 取值时成立，这条也要改为只约束那 14 块 |
| `test_pc_examples_all_have_cdisc_section_id` | 那 14 块等于 `§6.3.5.9.3`；Example 1 块（`chunk_index=0`，`section='PC – Examples'`）等于 **None**，除非主人另行裁定节号 |
| `test_pc_examples_example_4_has_only_method_a_and_d` | 不变，新 KB 下通过 |

- 其他可选锚点：Example 1 块 `has_table=True`，4946 tokens；`chunk_index` 为 0，那 14 块是 1..14。

## 审查（规则 D）
- writer 是主会话（本 worker）；reviewer 是独立子代理 `oh-my-claudecode:code-reviewer`（opus），只拿到 diff、方案路径和验收条款。
- 第一轮审 `d22b5bf`，结论 **PASS-with-fixes**：5 条验收全部 PASS。MEDIUM 意见是没有 H2 的文件会整篇丢失，已在 `43e1aea` 修复。
- 第二轮复审 `43e1aea`，结论 **PASS**：旧 KB 0 差，新 KB 仍只有 PC +1 块，旧 KB pytest 为 1 failed / 2899 passed（只有已知的日期问题）。审查者另做了 3 个变异，N1 和 N2b 被杀死；N3（H2 之前的块继承第一个 H2 的 §）没被杀死。`b7d2664` 把对应用例里的 H2 改成带 § 编号，并断言 H2 之前那块的节号是 None。N3 复跑结果为 1 failed，即已被杀死，记录在 `mutation_output.txt`。
- 以下几条没有修，属于既有行为或范围外：
  - 非 mermaid 代码块里的 `#### Method` 会被当作标题（现有 KB 不触发）。
  - 嵌套 H2 / 第一个 H3 的导语不进块，后续 H3 的导语会并进前一个 Method 块（新旧代码相同）。
  - SS/examples.md 用的是 `#####` 标题，新旧代码都切出 0 块（范围外，建议另开单元）。
  - 历史文档 `scripts/chunkers/_batch_b_done.md` 仍描述旧的两个方法，没有改。
- 审查者的脚本和日志在会话临时目录（未入库）的 `rv_pcchunk/`。

## 环境说明
- 工作区 `.venv`（gitignore 只忽略目录，所以这个软链显示为 `?? .venv`）和 `.env` 都软链到主仓，没有提交。
- 提交时，为了让 pre-commit 闸按 fail-closed 正常扫描，临时把主仓的 `data/study/st01/catalog.json` 以只读软链挂进工作区，提交后立即删除。两次扫描都是 CLEAN。
