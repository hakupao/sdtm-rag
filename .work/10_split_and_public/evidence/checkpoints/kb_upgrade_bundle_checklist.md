# 随 KB 升级一起提交的改动清单 (目标 KB = pedia `00a2e93`, 指纹 `bf33bab…`; 2026-11-27, 只列清单, 未改)

这些改动**只在新 KB 下成立**: 提前合进 main, 旧 KB 下的测试 / 评测会反过来失败。全部放进「KB 更新」那一次提交 (submodule 升级 + meta.yaml + 本清单), 不单独提前合。
pedia 如果在 `00a2e93` 之后再改 KB, 打 tag 后要按新指纹重跑预演, 再核对本清单 (数字可能变)。
依据: `kb_rehearsal_bf33bab.md` (预演与 pytest 分类)、`model_defhome_rule_options.md` (类别 ②, 本清单按推荐规则 R0 写; 用户若选 R1/R2, ② 一节要重写)。

## 0. 不在本清单里、应**提前**单独合的代码修复 (向后兼容, 另一会话在做)
| 修复 | 理由 |
|---|---|
| `scripts/build_meta.py` `_split_ct` + `scripts/spec_loader.py` `is_ct_code` 兼容 `(短名) Cnnnnn` | 预演已证明旧 KB 下 meta.yaml 逐字节不变; 修后类别 ① 的测试在新 KB 下预期恢复 (要在新 KB 下重跑 pytest 确认, USES_CT 542 等计数应不变) |
| `scripts/chunkers/examples.py` H4 嵌套分支兼容新 PC 结构 | 新 `domains/PC/examples.md` 在 `## §6.3.5.9.3` 之前多了 `## PC – Examples` + `### Example 1` (pedia `97e1895` / `f534395` 按 PDF 补回的 PC 浓度示例, 约 45 行含一张表)。现 chunker 只为 H4 Method 出块: 这段**不进任何 chunk** (全 KB 覆盖率扫描里唯一丢内容的文件), 且 `cdisc_section_id` 取第一个 H2 → None。修法需同时兼容旧结构 (旧 KB 只有一个 § H2), 修后 `test_pc_examples_all_have_cdisc_section_id` 的期望要在实现时定 (新增的 Example 1 块是否带 `§6.3.5.9.3`) |

## 1. `tests/` 计数锚点 (类别 ③, 已逐条核实是 KB 按 PDF 改动的正常变化)
| 位置 | 现值 → 新值 | 依据 (pedia 提交) |
|---|---|---|
| `tests/test_base.py:168-171` `test_find_mermaid_blocks_ta_returns_20` (函数名 + docstring + 断言) | 20 → 24 | `d33674e` B-TA "24 Mermaid vs PDF figures" |
| `tests/test_chapters.py:85-87` `test_ch02_splits_by_h2` (docstring「9 个 H2」+ 断言) | 9 → 8 | 去掉的是 KB 自加的 `## Findings About — Naming Findings About Domains (Reference Material)`, 内容移到 `domains/FA/assumptions.md §6.4.2` (`c8802bf` B-FA RELOCATE); §2.6 断言不受影响 |
| `tests/test_chapters.py:123-125` `test_ch04_produces_47_chunks` (函数名 + docstring + 断言) | 47 → 45 | 去掉的是 KB 自加的两节 `§6.1.3.3 Exposure/… (p115)` 与 `§6.3.5.7 … RELSPEC … (p261)`, 改成指向 `domains/EX/examples.md`、`domains/MB/examples.md` 的链接 (`42fecd3` S-CH4)。另有 3 个节名按 PDF 改写 (4.2.1 大小写、4.3.5 去掉括注、4.5.1 补全标题), 140 题 gold 未引用这 3 个节名 |
| `tests/test_chapters.py:128-130` `test_large_chapter_still_splits_by_h3` | 47 → 45 | 同上; `4.2.2` 断言仍成立 |

## 2. `tests/` 锚点 (类别 ②, 按规则 R0)
| 位置 | 改动 |
|---|---|
| `tests/test_build_meta.py:155` `assert "EPOCH" in mdh` | 换成新 KB 下仍唯一归属的变量 (实现时选, 如 `VISITNUM` → model/02) |
| `tests/test_meta_store.py:181` `m["EPOCH"] == model/03…` | 同上换变量 |
| `tests/test_structured_lookup.py:209-215` EPOCH 金丝雀 (6 列隔离不变量) | 换一个「有 6 列定义行 + 别处有 5 列使用行 + 仍唯一归属」的变量, 实现时现查 (见 `model_defhome_rule_options.md` E3) |
| `tests/test_build_neo4j.py:27` Variable 1541 | → 1544 (model-only 变量增加; 实现时以重跑结果为准) |
| `tests/test_build_neo4j.py:30` ModelChapter 4 | → 5 |
| `tests/test_build_neo4j.py:34` model_only 1523 / 18 | 按重跑结果更新 |
| `tests/test_build_neo4j.py:36-37` `APID` model_only 断言 | APID 不再有 def-home, 实现时确认节点是否仍在, 不在则换变量 |
| `tests/test_build_neo4j.py:50,85` DEFHOME 59 | → 64 |
| `tests/test_build_neo4j.py:77-80` ModelChapter 集合 | 加 `model/04_associated_persons.md` |
| `tests/test_build_neo4j.py:84` `rows["APID"] == model/06…` | 换变量 |
| `tests/test_reconcile_neo4j.py:16,18` | ModelChapter 4 → 5, DEFHOME 59 → 64, Variable 按重跑结果 |
| `tests/test_structured_lookup.py:200` docstring「59-var」 | → 64 |

## 3. `eval/test_set_v3.yml` gold 修订 (fact 级 3 处 + 节级 1 处)
按 `check_source_recall` docstring 纪律第 4 条, 放宽 gold 应由非受益方裁定; 下面给出建议值, 由用户或独立审查者定稿。改前后跑 `python -m eval.tests_support.gold_semantics_diff` 和 `eval/lint_gold.py`。

| 位置 | 现值 | 建议 | 说明 |
|---|---|---|---|
| q39 `:434` fact | `FAOBJ` | 二选一: (a) fact 保留不动, 接受它不再逐字出现在 gold 文件 (FAOBJ 仍是正确答案内容); (b) 改 sources, 把 FA 叙述的新位置 `domains/FA/assumptions.md` 加进 gold | FA 叙述从 model/02 移到 FA 域文件 (`c8802bf`)。(b) 会给 source recall 加一个要求, 是收紧不是放宽, 改前要用 140 题重跑确认不新增 miss |
| q117 `:1457` fact | `first 6 columns (STUDYID...QNAM) should be unique` | `should be unique for every record` | 原文三点改成省略号 `…` (`bc4e42e`); fact 是答案子串匹配, 模型输出 `...` 或 `…` 都可能, 去掉标点依赖的那段更稳。新旧 KB 都含这句 |
| q120 `:1500` fact | `Defines which subjects belong to each pool` | `individual subjects included in a pool` | model/06 按 PDF 重写 (`cbc6b75`), 新原文: "This dataset identifies individual subjects included in a pool of subjects…" |
| q126 `:1572` any-of 成员 | `model/03_special_purpose_domains.md#Subject Elements (SE)$` | `model/03_special_purpose_domains.md#3.2.3 Subject Summary Domains$` 或删掉该成员 | 标题改成 `3.2.3.1 Subject Elements`, 并入 chunk `3.2.3 Subject Summary Domains` (`ed7fd2b`)。新节覆盖 SE 以外的内容, 判别力下降; 同组 `domains/SE/assumptions.md` 仍可命中, 分数不变 |

## 4. 其他随升级提交的产物
- `vendor/sdtm-pedia` submodule 指针 → 新 tag。
- `data/meta/meta.yaml`: 本机 `-m scripts.build_meta` 重生成 (须在 §0 CT 修复合进后跑, 否则 ct_codes 为 0)。
- 本机按 CLAUDE.md「KB 更新」跑 `check_index_freshness`、`ingest`、两条检索闸、pytest。

## 5. 提交顺序与生效时机
1. **§0 两个代码修复先合 main** (都在 `scripts/**`, 推 main = 构建 + 部署私有站; 旧 KB 下 meta 不变, 生产行为不变)。部署后它们进入线上镜像, 也就是 kb-sync 的**基线镜像**。
2. **pedia 打 `kb-*` tag** → kb-sync 定时 (或手动 dispatch 该 ref): 基线 = 线上镜像 (含 §0 修复) + 线上题集; 候选 = 用 B 仓 **main 的 checkout** 构建的镜像, 题集也是 main 上的。此时 §3 的 gold 修订还不在 main 上, 候选按旧 gold 评分: 预演中 retrieval 闸的 source gold 不受 §3 影响 (fact 不参与闸; q126 改的是 any-of 成员, 分数不变), 所以闸结论不依赖 §3。
3. **本地「KB 更新」一次提交**: submodule 指针 + meta.yaml + §1 / §2 测试锚点 + §3 gold。推 main → CI 测试步用新 submodule 跑 pytest (所以 §1 / §2 必须在这次提交里, 否则测试步失败、部署中止) → 构建 → 换入过闸候选 chroma。
4. 这次部署后, 新 gold 才进入线上镜像, 成为下一次 kb-sync 的基线题集。
- 只改 `tests/` 的提交不触发 CI (路径过滤不含 `tests/`), 本清单的测试改动必须本机跑过再推。
