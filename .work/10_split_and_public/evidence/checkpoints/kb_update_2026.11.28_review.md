# 审查: 「KB 更新」提交的暂存 diff (kb-2026.11.28, 规则 D)

- 审查者: subagent_type `oh-my-claudecode:critic` (写作者为主会话, 不同 agent 类型、不同 context), 2026-11-28。只读; 对暂存区 (提交前) 审查, 审查通过后原样提交为 `f798709`。
- prompt 存档: `evidence/subagent_prompts/review_kb_update_commit.md` (只给了 diff 的位置、清单 v6 和裁定出处, 没有给写作者的结论)。
- **结论: PASS** (CRITICAL 0 / MAJOR 0 / MINOR 3)。

## 审查者核实成立的 (自己读 diff、自己跑命令)
1. **没有清单 v6 之外的期望值改动**: 12 个路径的每个 hunk 都归到 v6 的某一条 (计数 4 / PC 示例 6 / R4 映射 8 / gold 5 处 / README 与 meta)。`test_build_neo4j.py` 两条行内注释同步成「1523 IG + 23」「全量 75 / 23 个」, 属 v6 第 3 条「顺带更新」。
2. **gold 5 处与主人的裁定逐字一致**: q39 加在 `expected_sources` (AND) 末尾, 没有新建 any-of 组; q117 / q120 的新 fact 在新 KB 的 `chapters/ch08_relationships.md`、`model/06_relationship_datasets.md` (6.3 节) 里逐字存在; q126 是删成员不是改名; q76 新标题逐字节核对, 新 KB 里有 `## 6.6 Associated Persons Relationships (APRELSUB)`。`tests/test_section_gold_exists.py` 本机 2 passed。
3. **测试断言没有改弱**: PC 的 5 条用 `section != 'PC – Examples'` 区分 (没有用 `sub_label is not None`), 每条都先断言「14 + 1」; 被排除的那 1 块由 `test_pc_examples_all_have_cdisc_section_id` 的三元组等式 `== [(None, None, None)]` 钉住 (同时要求这类块正好 1 个)。其余锚点只是数值 / 路径替换, 没有删断言、放宽比较符或加 skip / xfail。相关 7 个测试文件 188 passed。
4. **`meta.yaml` 与 v6 第 5 条一致**: `model_defhome` 75 (02: 18 / 03: 31 / 04: 4 / 05: 10 / 06: 12); 新增 15、移除 2 (REFID / SPEC)、改归属 4 (APID 06 → 04; EPOCH / MIDS / TAETORD 03 → 02); 1917 个变量里只有 DM `RFSTDTC` / `RFENDTC` 的 type 变成 Char (新 KB 的 `DM/spec.md` 就是这么写的)。
5. **范围**: `server/`、`scripts/`、`deploy/`、`.gitea/`、`pyproject.toml`、`uv.lock` 改动为零; 两个 README 各只改 1 处 tag 字样, 没有旧 tag 残留。
6. **submodule 指针**: gitlink = 提交 `b2bd8376e51e4d9e751fc49834a87a103a722b2e` (不是 tag 对象); `HEAD:knowledge_base` = `63f857774a42cfaa71798705ad40ab51bc5e378a`。
7. 改名的测试函数 (`…ta_returns_20`、`…produces_47_chunks`、`…produces_14_chunks`) 在代码、测试、workflow 里没有残留引用, 只在历史文档里出现。

## 问题与处置
| # | 严重度 | 问题 | 处置 |
|---|---|---|---|
| 1 | MINOR | `scripts/build_neo4j.py` 文件头与 DEFHOME 注释里的 1541 / 18 / 62 过期 (现为 1546 / 23 / 75)。清单 v6 把它列为可选的顺带更新 | 本次不改: 派单规定这次提交不动 `scripts/` (kb-sync 候选由不含本提交的 main 构建, 保持运行时代码零差异)。记入 `_progress.json` 的 `todo_later`, 随下一个会部署的提交改 |
| 2 | MINOR (既有) | `python -m eval.tests_support.gold_semantics_diff` 直接跑会失败: `load_old_impl` 用 `cwd=ROOT.parent` 执行 `git show`, 拆仓后 `ROOT.parent` 不是 git 仓库 | 没有改代码。写作者用环境变量绕过: `GIT_DIR=$PWD/.git .venv/bin/python -m eval.tests_support.gold_semantics_diff`, 改 gold 前后各一趟, 都是 15620 格 / 0 mismatch / docstring 33 行不变。工具本身的修复 (把 `cwd` 改成 `ROOT`) 记入 `todo_later` |
| 3 | MINOR (风格) | PC 的 5 条测试里重复写了同样两行 (筛出 `merged` + 断言 14 + 1), 可以抽成 fixture | 不改: 与预演 probe 验证过的写法逐行一致, 这次以「提交 = 预演验过的那一套」为先 |

## 审查者没有核对到的部分 (由写作者的实测覆盖, 见 `kb_update_2026.11.28.md`)
- 本机 `meta.yaml` 与 kb-sync 候选 meta 逐字节相同 (要 ssh, 审查者不能做): 写作者比了 sha256, 两边都是 `b484d49e…`。
- 两条检索闸、全量 pytest、`test_create_app_boots_through_lifespan` 在新 KB 下首跑: 写作者本机跑过。
- q39 的 FA 来源在新 KB 下能否召回: 本机改后的 140 题里 q39 = 1.0 (3/3)。
- `eval/lint_gold.py`: 对 CDISC 题集不适用 (节级 gold 会抛 `ValueError`, 该工具只建模 study 卡); CDISC 侧同一职责由 `tests/test_section_gold_exists.py` 承担。study 题集这次没有改动。
