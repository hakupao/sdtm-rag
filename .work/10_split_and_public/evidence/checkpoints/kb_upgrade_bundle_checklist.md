# 随 KB 升级一起提交的改动清单 (目标 KB = pedia `00a2e93`, 指纹 `bf33bab…`; 2026-11-27, 只列清单, 未改)

这些改动**只在新 KB 下成立**: 提前合进 main, 旧 KB 下的测试 / 评测会反过来失败。全部放进「KB 更新」那一次提交 (submodule 升级 + meta.yaml + 本清单), 不单独提前合。
pedia 如果在 `00a2e93` 之后再改 KB, 打 tag 后要按新指纹重跑预演, 再核对本清单 (数字可能变)。
依据: `kb_rehearsal_bf33bab.md` (预演与 pytest 分类)、`model_defhome_rule_options.md` (类别 ②, 本清单按推荐规则 R0 写; 用户若选 R1/R2, ② 一节要重写)。

## 0. 不在本清单里、应**提前**单独合的代码修复 (向后兼容, 另一会话在做)
**前置 (挡住一切推 main)**: `tests/test_p2_seam_characterization.py` 从 2026-11-27 起失败 (日期依赖: `server/web_search.py:85` `date.today()` 进了 golden 的 `messages_sha`), CI 测试步会因此失败、不部署。p3 合并和下面的修复推 main 之前要先修它 (冻结日期或把日期排除出哈希), 详见 `kb_rehearsal_bf33bab.md` v2 修订第 2 条。

| 修复 | 理由 |
|---|---|
| `scripts/build_meta.py` `_split_ct` + `scripts/spec_loader.py` `is_ct_code` 兼容 `(短名) Cnnnnn` | 预演已证明旧 KB 下 meta.yaml 逐字节不变; 审查者实测: 补丁 meta + 补丁 build_meta 下类别 ① 的 16 个测试转绿; 完整修复 (含 `is_ct_code`) 仍要在新旧 KB 下各重跑 pytest |
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

## v2 更新 (2026-11-27, 依据 pedia 答复 `sdtm-pedia/.work/10_tier_b_repair/evidence/checkpoints/t4_downstream_notes.md`; 与上文冲突处以本节为准)

### A. gold 与 pedia 节变动清单的对照 (只读, 未改 eval)
- **结论: 除已知的 fact 3 处 (q39 / q117 / q120) 和节级 1 处 (q126) 外, 没有别的 gold 引用被移走或改名的节。**
- 方法 1 (节级, 覆盖表 B 全部改名): 用新旧 KB 的 chunk section 全集按 `eval.run_eval` 的 `路径#节[$]` 语义重算每条 gold (`probes/kb_rehearsal_secdump.py` + `kb_rehearsal_secmatch.py`, 预演时已跑, 审查者用 `source_matches` 复核): 只有 q126 失效。表 B 里 ch04 / ch08 / model/0x 的改名都没有被节级 gold 引用 (例如 q38 引用的 `4.1.6 Additional Guidance on Dataset Naming` 与 q39 引用的 `8.6.3 Guidelines …` 两版都在)。
- 方法 2 (路径级, 覆盖表 A 的 16 组跨文件移动): 对每条 gold 路径落在表 A 旧位置文件 (46 处) 或表 B 改名文件 (49 处) 的引用, 逐**单个 gold 文件**比较新旧 KB 下该文件含该题多少条 fact (`probes/gold_vs_moved.py`, 用法见文件头; 文件之间加了分隔符, 避免跨文件拼出假命中)。只标出 3 处, 即已知的 q39 (`model/02` 少了 FAOBJ, 表 A1)、q117 (`ch08` 省略号, S-TYPO, 不属节变动)、q120 (`model/06` 重写, 表 B model/06 行)。
- 路径级 gold 引用 EC / SC / MB / CP / GF / IS / CO / MS / PP 文件的共 6 处, 全是 `spec.md` 或 `assumptions.md` 中未被移走的部分; 没有 gold 引用表 A 里被删的示例副本 (EC examples、MB 顶层副本、SC Specification、CP / GF / IS 的示例附录)。
- 局限: 方法 2 只能看到 fact 的变化; 某个 gold 文件的「主题内容」被移走、但该题 fact 恰好还在的情况它看不到。140 题 retrieval 闸没有出现 CT 以外的回退, 作为旁证。

### B. PC examples 切块修复方案 (不实现; **依赖 pedia 对观察项 ⑦ 的裁定**)
pedia 的说法: `## PC – Examples` 照 PDF (p269) 不带节号, 节号应从所属域节继承 (PC 自己的例属于 §6.3.5.9.1); 旧 KB 把 PC Example 1 挂在 `## §6.3.5.9.3` 下是挂错了。pedia 把「PC 示例层级与其他域不一致」记为观察项 ⑦, 等用户裁定, 所以打 tag 前 PC 结构还可能变 (例如改成和其他域一样的 `## Example N` 平铺, 或保持现状)。

可能出现的三种结构:
- S1 旧 KB: 只有 `## §6.3.5.9.3 …` → `### Example 1..4` → `#### Method A-D`;
- S2 现 KB: `## PC – Examples` → `### Example 1` (无 H4), 再 `## §6.3.5.9.3 …` → `### Example 1..4` → `#### Method A-D`;
- S3 观察项 ⑦ 若改成与其他域一致: `## Example N` 平铺 + 合并例 (形态未定)。

方案 (对三种结构都成立, 按「节」而不是「文件」分派):
1. **分派**: 现在是按整个文件判定「H4 嵌套模式」(≥2 个 H4 且有 `Method ` 开头) 后, 只为 H4 出块。改为在每个 H3 范围内判定: 该 H3 下有 H4 → 每个 H4 一块 (保持现行 Method 粒度与 `example_index` / `sub_label`); 没有 H4 → 整个 H3 一块; H2 下没有 H3 的正文 (如导语) → 一块。这样 S2 的 PC Example 1 有了自己的块, S1 的输出不变, S3 退化为按 H2 / H3 平铺。
2. **节号**: 每块取「向上最近的、带 `§` 编号的 H2 / H3」; 没有带编号的祖先标题 (S2 的 `PC – Examples`, 以及其他域的 `## Example N`) 时, 从所属域的节号继承: 读同域 `assumptions.md` 第一个形如 `## 6.3.5.9 …` / `## §6.x …` 的标题, 或由 meta 的「域 → 节号」映射得到。注意: PC 的 `assumptions.md` 第一个编号标题是 `## 6.3.5.9 Pharmacokinetics Domains` (PC 与 PP 共用的父节), 不是 §6.3.5.9.1, 所以「域 → 节号」要能区分父节与本域节, 实现时先确认数据源能否给出 §6.3.5.9.1。
3. **兼容性**: S1 下每块的 § 祖先都是 `## §6.3.5.9.3`, 输出与现行逐字段相同 (实现时用旧 KB 跑 `test_examples.py` 与全量 chunk 比对验证)。其他域目前 `cdisc_section_id` 普遍为 None (AE / TU / PP 等), 第 2 条的「从域继承」如果对所有域生效, 会改变全部 examples chunk 的元数据, 影响面需要单独评估, 可以先只在「文件里至少有一个带 § 的标题」时启用。
4. **测试期望**: `test_pc_examples_all_have_cdisc_section_id` (全部 == §6.3.5.9.3) 在 S2 下要拆成两条: 合并例 Method 块 == §6.3.5.9.3; PC 自己的 Example 1 块 == 继承值 (§6.3.5.9.1 或用户认可的值)。块数 14 → 15。
5. **依赖**: 观察项 ⑦ 若在打 tag 前改了结构, 第 1-2 条的规则不用变, 只需重跑覆盖率扫描 (`probes/kb_rehearsal_coverage.py`) 和第 4 条的期望。因此建议 **PC 修复等 pedia 对 ⑦ 裁定后再实现**, 或者先实现方案 1-3 (对 S1 / S2 都成立), 期望值随 tag 定。

### C. pedia 解冻改 KB 后要在新指纹上重跑的数字
pedia 还会按用户裁定改 KB (至少观察项 ⑥ REFID / SPEC 的 Notes、⑦ PC 层级), 指纹会变。打 tag 后以 tag 的指纹重跑, 下表的数字全部以重跑为准:

| 数字 | 本清单 / 预演里的值 (指纹 `bf33bab…`) | 重跑方法 |
|---|---|---|
| 140 题闸: 逐题回退、满分题数、avg | 6 / 132 / 0.9702 (修 CT 后 0 / 138 / 0.9917) | `kb_rehearsal_bf33bab.md` 复跑命令 (约 $0.05 embedding) |
| chunk 总数与各类数 | 4332 (chapter 87 / assumptions 487 / examples 200 / model 32 …) | ingest 日志 |
| 计数锚点: TA Mermaid、ch02 H2 数、ch04 chunk 数 | 24 / 8 / 45 | §1 各测试; 或 `scripts.chunkers` 直接跑 |
| PC 块数与节号 | 14 块, 节号 None (修后预期 15 块) | §B 第 4 条 |
| `model_defhome` 映射与 neo4j 计数 | R0 64 / R4 72; ModelChapter 5; Variable 1544; model_only 21 | `probes/defhome_rules.py`; `tests/test_build_neo4j.py` / `test_reconcile_neo4j.py` 重跑 |
| meta: ct_codes / ct_dict / `*` / DOMAIN 单元格 | 588 / 952 (修 CT 前) / 129 / 59 | `build_meta` 后统计 |
| fact 级与节级 gold 漂移 | fact 3 / 节级 1 | `probes/kb_rehearsal_factcheck.py`、`kb_rehearsal_secmatch.py`、`gold_vs_moved.py` |
| 新 KB 下 pytest 的 KB 相关失败数 | 30 (① 16 / ② 9 / ③ 5) | `kb_rehearsal_bf33bab.md` v2 修订第 4 条 |
| 覆盖率扫描: 丢内容的文件 | 只有 PC (4 → 47 行) | `probes/kb_rehearsal_coverage.py` |
| 最大 chunk token 数 | MB `§6.3.5.7.3` 7878 (旧 KB 8087), CP Example 6 7296 | 覆盖率扫描同法统计; **embedding 上限 8191**, 超过会让 ingest 出问题, pedia 补内容后要首先看这一项 |

### D. 对上文的修正
- §2 的 `_model_defhome` 锚点按 R0 写; `model_defhome_rule_options.md` v2 已把推荐改为 R4, R4 下的锚点见该文件 v2 节「R4 下的锚点」。用户裁定 E1 后, 二选一。
- §0 PC chunker 一行: 「修法需同时兼容旧结构」的具体方案见上面 §B; 修复时机依赖观察项 ⑦。
- §3 q126: pedia 表 A3 / 表 B 确认 SE 节改为 `### 3.2.3.1 Subject Elements`, 位于 `## 3.2.3 Subject Summary Domains` 下; 建议值不变。

## v3 修订 (2026-11-27, 独立审查后; 与上文冲突处以本节为准)
审查: `kb_upgrade_bundle_checklist_review.md` (`oh-my-claudecode:verifier`, PASS-with-fixes)。

### 1. 硬约束: 改变 chunk / meta 产物的代码必须在 kb-sync 构建候选之前进 main (H2)
- 线上的 chroma **和 meta 都来自 kb-sync 候选**: 候选的 `ingest` / `build_meta` 用的是 kb-sync 运行时 main 上的代码 (`deploy/kbsync/kbsync.py:369-385`, 候选镜像由 main checkout 构建); 部署时 `swap()` 把 `chroma_cand_*` / `meta_cand_*` 整个换成生产的 `chroma/` / `meta/` (`:241-257`)。仓库里提交的 `data/meta/meta.yaml` 只供 CI 和测试, **不是**线上数据。
- 所以 CT 解析修复、PC chunker 修复、`_model_defhome` 规则改动, 只要会改变 chunk 或 meta, 都必须在 **pedia 打 tag、kb-sync 构建候选之前** 合进 main。上文 §5 第 3 步「本地 KB 更新一次提交」里只能放测试锚点、gold、submodule 指针和与候选一致的 meta.yaml, 不能放这类代码。
- 如果代码晚于候选构建才合: 该指纹已是 gated, kb-sync 对它 no-op, 不会重建; 部署会换入用旧代码建的数据, 代码与数据静默不一致。补救: 先把已过闸的 `chroma_cand_<fp12>` / `meta_cand_<fp12>` 移走 (按规则 B 改名归档, 不删), 或让 pedia 重新打 tag, 再跑 kb-sync。
- 对 `_model_defhome` 的含义: 「R4 + 随 KB 提交」这个组合排除。可选的只有「R4 提前合并 (接受旧 KB 下 +3 条)」或「R0 + 随 KB 只改锚点」。`model_defhome_rule_options.md` 的 E2 已同步。
- 对 PC chunker 的含义: 修复代码要先合; 它在旧 KB 下必须让原有测试全过 (见第 3 条), 新 KB 下的测试期望随 KB 提交。若 pedia 对观察项 ⑦ 的裁定在 tag 前改了 PC 结构, 代码按第 2 条的分派规则本来就兼容, 只需重跑验证。

### 2. PC 切块方案改为按 H2 分派 (替换 §B 第 1-3 条; H1 / M2)
- **分派**: 逐个 H2 判定。H2 范围内含 `#### Method` → 嵌套模式 (每个 H4 一块, 保持现行 `example_index` / `sub_label`); 否则整个 H2 一块 (就是现在平铺分支的行为)。
  - S1 (旧 KB): 只有 `## §6.3.5.9.3`, 其中有 Method → 与现行完全相同, 14 块。
  - S2 (现 KB): `## PC – Examples` 无 H4 → 1 块 (PC 自己的 Example 1 有了块); `## §6.3.5.9.3` 照旧 14 块 → 共 15 块。
  - S3 (若改成平铺): 退化为平铺。
  - 其他 9 个「H2 下挂 H3、无 H4」的 examples 文件 (CP / FA / MB / PP / RELREC / RS / TA / TE / TV) 不进嵌套模式, 输出不变。v2 里「每个 H3 内判定」的写法会把它们拆开 (如 `test_ta_examples_produces_8_chunks` 会坏、PP 的 `### Method A —` 被拆), 已作废。
- **节号**: 现有数据**给不出 §6.3.5.9.1**: KB 里 `6.3.5.9.1` 零命中, meta 没有节号映射, PC `assumptions.md` 第一个带 § 的标题恰是挂错的 `§6.3.5.9.3`。「向上最近带 § 的标题」还会让 EX / TU 的 `## Example N` 误继承 §6.1.3.3 / §6.3.12.3。所以: 每块只取**本 H2 自己**的 `§` 编号, 没有就是 None (与其他域现状一致); S2 的 Example 1 块 `cdisc_section_id = None`, 在测试里写明。要给它 §6.3.5.9.1, 只能硬编码一张小映射或请 pedia 在 PC 文件里提供, 列为待裁定。`cdisc_section_id` 目前只在 chunker 与测试里使用, server 不消费, 影响限于元数据。
- **验证**: 对新旧两版 KB 的**全部** `domains/*/examples.md`, 比较修复前后的 chunk (全字段 diff)。旧 KB 必须 0 差; 新 KB 只允许 PC 新增 1 块。再跑覆盖率扫描 (`probes/kb_rehearsal_coverage.py`), PC 的缺失行数应回到旧 KB 的水平。S1 下 H3 导语约 4 行没进 chunk, 这是现状, 不是回归。

### 3. PC 测试期望逐条 (替换 §B 第 4 条; M1)
`tests/test_examples.py`, 只能随 KB 升级提交 (旧 KB 下这些测试原样必须通过):
| 测试 | 新 KB (S2) 下 |
|---|---|
| `:75 test_pc_examples_produces_14_chunks` | → 15 |
| `:80 test_pc_examples_all_have_sub_label_method` | 改为只约束合并例的块 (Example 1 块没有 Method) |
| `:87 test_pc_examples_sub_labels_are_valid_methods` | 同上 |
| `:94 test_pc_examples_all_have_example_index` / `:100 …range_1_to_4` | 看实现给 Example 1 块的 `example_index`: 按 H3 取值是 1 (范围测试仍过); 按 H2 标题解析是 None (`all_have_example_index` 失败, 要改) |
| `:108 test_pc_examples_all_have_cdisc_section_id` | 合并例块 == §6.3.5.9.3; Example 1 块 == None (或用户裁定的值) |
| `:116 test_pc_examples_example_4_has_only_method_a_and_d` | 不变 |

### 4. §C 末行更正 (M3)
「embedding 上限 8191, 超过会让 ingest 出问题」是错的: `scripts/ingest.py:230-301` 对超限文本截断并打 WARNING, 不会失败。新旧 KB 各已有 18 个 terminology chunk 超过 8191 (最大 19975, 是既有情况)。改为监控: **非 terminology 的 chunk 中超过 8191 的个数** (现为 0; 最大是 MB `§6.3.5.7.3` 7878, 旧 KB 8087; CP `Example 6` 由旧 KB 的 <5784 涨到 7296)。出现新增时检查是否被截断。

### 5. §A 补充 (L1)
审查者另做了 chunk 正文比对, 补上了方法 2「只看 fact」的局限。节级 gold 命中 chunk 正文有变化、但 fact 全在的:
- q38 `ch04#4.1.6` (只是 URL 括注);
- q39 `ch08#8.6.3`;
- q19 / q91 `DS/spec#DSDECOD`、`DS/assumptions#item_3`;
- q76 `model/06#6.6` (重写, APID 表仍在);
- q115 `ch08#8.4.1`、`SUPPQUAL/assumptions#overview`;
- q117 `ch04#4.5.4`;
- q10 `RS/assumptions.md#item_4$` 由 1 个 chunk 变成 2 个 (新增 QRS 文字, fact 仍在)。

q126 的两个 any-of 成员在新旧 KB 下都不单独覆盖全部 facts (`actually passed through` 只在 `SE/assumptions`), 是既有问题, 不是这次引入的。**结论不变: 除已知 4 处外没有新的 gold 问题。**

### 6. 修订后的提交顺序 (替换 §5)
1. 先修 `test_p2_seam_characterization` 的日期依赖 (另一会话), 否则任何推 main 都卡在 CI 测试步。
2. 合进 main (推 main = 构建 + 部署私有站), **全部在 pedia 打 tag 之前**: CT 解析修复; PC chunker 修复 (旧 KB 下 0 差); 若选 R4, 也在这一步提前合 (旧 KB 下 meta +3 条, 接受该行为变化)。部署后这些代码进入线上镜像, 也就是 kb-sync 的基线镜像。
3. pedia 打 `kb-*` tag (若观察项 ⑥ / ⑦ 已按裁定改过 KB, 先按新指纹重跑预演与 §C 的数字)。
4. kb-sync 构建候选: 候选镜像由 main checkout 构建, 已含第 2 步的代码, 候选的 chroma 与 meta 都按新代码生成; 题集是 main 上的旧 gold (闸结论不依赖 §3 的 gold 修订, 见 §5 原第 2 条)。
5. 本地「KB 更新」一次提交: submodule 指针 + 与候选一致的 `data/meta/meta.yaml` (本机用同一份 main 代码重跑 `build_meta`) + §1 / §2 / 本节第 3 条的测试锚点 + §3 gold。推 main → CI 测试步用新 submodule 跑 pytest (锚点必须在这次提交里, 否则测试步失败、不部署) → 部署时换入过闸候选。
6. 部署后新 gold 进入线上镜像, 成为下一次 kb-sync 的基线题集。
