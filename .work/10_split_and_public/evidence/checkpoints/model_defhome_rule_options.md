# `_model_defhome` 多文件归属规则 — 方案比较 (2026-11-27, 只出方案, 未实现, 待用户裁定)

来源: `kb_rehearsal_bf33bab.md` 类别 ②。现规则 (`scripts/build_meta.py:134`): 只收 model/*.md 里「`| # | VAR | Label | Type | Role | Notes |` 6 列、序号为数字、Notes 非空」的行; 同一变量这种行**只出现在一个文件**才收, 否则丢弃; `--` 前缀变量排除。
用途: `server/structured_lookup.py:419` 概念定义通道 (问句匹配 `_DEFVERB_RE` 即 "what does/is X identify/mean/represent/define…" 时, 并集补上 X 的 def-home 文件); `server/graph_engine.py:81` DEFHOME 边; `scripts/build_neo4j.py` / `reconcile_neo4j.py` 计数。

## 1. 新 KB 下发生了什么 (数据)

旧 KB 59 个 → 新 KB 64 个。home 分布: 旧 `03:34 06:15 05:7 02:3` → 新 `03:31 06:12 02:11 05:7 04:3` (新增 model/04 这一章节节点)。

| 变量 | 旧 6 列行所在 | 新 6 列行所在 | 现规则结果 | 原因 (pedia 提交) |
|---|---|---|---|---|
| EPOCH / TAETORD | 03 (DM/SE 表) | 02 `Visit and Epoch Variables` + 03 | **丢** | model/02 表重建 (S-MOD2 `6f2c38a`) |
| MIDS | 03 | 02 `Disease Milestone Variables` + 03 | **丢** | 同上 |
| APID | 06 | 04 `Variables Used in Associated Persons Data` + 06 | **丢** | model/04 按 PDF 加 6 列表 |
| REFID / SPEC | 06 (RELSPEC) | 06, 但 Notes 为空 | **丢** | B-model06 `cbc6b75` 按 PDF 清空 Notes; **不是多文件问题** |
| VISIT / VISITNUM / VISITDY / RPPLDY / RPPLSTDY / RPPLENDY / MIDSDTC / RELMIDS | 无 6 列行 | 只在 02 | 新增 → 02 | S-MOD2 |
| RSUBJID / RDEVID / SREL | 无 | 只在 04 | 新增 → 04 | model/04 |
| DOMAIN / RPHASE | 02+03+05 / 03+05 | 02+03+05 / 02+03+05 | 丢 (不变) | — |
| USUBJID / POOLID | 02+06 | 02+06 | 丢 (不变) | — |
| RPATHCD / RSTGCD / RSTAGE | 03+05 | 03+05 | 丢 (不变) | — |

要点: 冲突全部来自「model/02 的通用类表」或「model/04」与专章并存。model/02 里 EPOCH 那一行就是 SDTM 模型对通用 timing 变量的正式定义, 所以「两处都是定义」在内容上成立, 不是 KB 写错。

## 2. 候选规则 (均为模式级规则, 不按具体变量写例外)

用新 KB 实算 (算法同 `_model_defhome`, 只改归属判定):

| 规则 | 说明 | 映射数 | EPOCH / TAETORD / MIDS | APID | REFID / SPEC | 新增 11 个 | USUBJID / POOLID | DOMAIN / RPHASE | RPATHCD 等 3 个 |
|---|---|---|---|---|---|---|---|---|---|
| **R0 维持现规则** | 只认唯一文件 | 64 | 丢 | 丢 | 丢 | 02 / 04 | 丢 | 丢 | 丢 |
| **R1 专章优先于 model/02** | 恰好两个文件且其一是 02 → 归另一个; 其余多文件仍丢 | 69 | → 03 | 丢 (04+06 都不是 02) | 丢 | 02 / 04 | **→ 06** | 丢 | 丢 |
| **R2 多归属 (≤2 个文件)** | 值改为文件列表; 1-2 个文件全收, ≥3 个丢 | 73 | → [02, 03] | → [04, 06] | 丢 | 02 / 04 | → [02, 06] | 丢 | → [03, 05] |
| R3 放宽 Notes 非空 | 空 Notes 的 6 列行也算 | 94 | 丢 | 丢 | → 06 | **VISIT / VISITNUM / VISITDY 反而丢** (03 的 SV 空 Notes 行变成第二个文件) + 另多出 30 个 03 变量 | 丢 | 丢 | 丢 |

R3 让 VISIT 等核心变量变成多文件冲突, 还把 30 个 DM/SE/SV/SM 变量拉进映射, 可直接排除; 它只用来说明 REFID/SPEC 的丢失和多文件规则无关。REFID/SPEC 在 R0-R2 下都会丢: 要找回它们得另定「定义行是否必须带 Notes」, 这是独立问题。

### 对概念定义通道的影响
- 通道只在问句形如 "what does EPOCH represent / identify…" 时触发, 并集补文件 (不替换原有检索)。
- 140 题里没有题对 EPOCH / TAETORD / MIDS / APID / REFID / SPEC 用这种句式 (只有 q73 对 RDOMAIN 用, RDOMAIN 在所有规则下都 → 06)。预演的反事实 eval 用的正是新 KB + R0 的 meta, 140 题与基线逐题 0 差。**任何规则选择对 140 题闸零影响**, 差别只在闸外的真实问答。
- R0: "what does EPOCH represent" 不再补 model 文件, 只靠 dense/BM25 召回 (EPOCH 在 VARIABLE_INDEX、ch04 都有, 大概率仍能答, 但失去确定性补位)。新增 11 个变量 (VISITNUM 等) 获得补位, 是净收益。
- R1: EPOCH / TAETORD / MIDS 补 model/03 (与旧行为一致); 副作用是 USUBJID / POOLID 被归到 06。USUBJID 的正式定义在 02 `3.1.4 Identifiers for All Classes`, 06 只是在关系表里列出 → **语义上是错的归属**; POOLID 归 06 (Pool Definition) 尚可接受。
- R2: EPOCH 类补 02 + 03 两个文件, 定义 (02) 和 DM/SE 语境 (03) 都给到; USUBJID 补 02 + 06。每次最多多 2 个文件进上下文, 精度略降、召回更全。它推翻了原设计「有歧义就丢、宁缺毋滥」的保守取舍。

## 3. 各规则要改的锚点测试 / 代码

| 文件 | R0 | R1 | R2 |
|---|---|---|---|
| `tests/test_build_meta.py:152 test_model_defhome` (`"EPOCH" in mdh`) | 换一个仍唯一归属的变量 (如 RDOMAIN 已有; 可选 VISITNUM→02) | 不改 | 断言改为列表 |
| `tests/test_structured_lookup.py:209` EPOCH 金丝雀 (6 列隔离不变量) | 换金丝雀变量: 需要「有 6 列定义行 + 别处有 5 列使用行」且仍唯一归属, 实现时现查 | 不改 | 改为 `in` 列表 |
| `tests/test_structured_lookup.py:217 test_defhome_map_hygiene` (DOMAIN/USUBJID/POOLID 必须不在) | 不改 | **USUBJID、POOLID 那两条要改** (=推翻原设计) | 只保留 DOMAIN; 改断言 |
| `tests/test_meta_store.py:178` (`m["EPOCH"]`) | 换变量 | 不改 | 改列表 |
| `tests/test_build_neo4j.py:50,85` (DEFHOME 59、`APID`→06) / `:74` ModelChapter 集合 | 64、换 APID 断言、集合加 model/04 | 69、APID 断言换掉、加 04 | 边数按列表展开 (约 82)、加 04 |
| `tests/test_reconcile_neo4j.py:18` (DEFHOME 59、ModelChapter 4) | 64 / 5 | 69 / 5 | 按展开数 / 5 |
| 代码 | 无 (只改测试锚点) | `build_meta._model_defhome` 加一条判定 | `build_meta` 输出列表 + `meta_store` / `structured_lookup:427` / `graph_engine:81` / `build_neo4j:92-95` / `reconcile_neo4j` 跟着改, meta.yaml schema 变 |
| 旧 KB 下 meta.yaml 是否逐字节不变 (能否先于 pedia tag 上线) | 是 (不改代码) | **否**: 旧 KB 下 USUBJID/POOLID 也是 02+06 → 会新增 2 条 | 否 (schema 变) |

另: `test_build_neo4j::test_class_and_chapter_nodes` 失败也属于这一类 (ModelChapter 集合多了 `model/04_associated_persons.md`), 预演报告里标的「待确认」由此结案。

## 4. 推荐与待裁定

**推荐 R0 (维持规则, 只随 KB 升级更新锚点)**, 理由:
1. 不改代码, 与 CT 解析修复解耦; 锚点更新放进「随 KB 升级」那一批提交即可 (见 `kb_upgrade_bundle_checklist.md`)。
2. 新 KB 下净变化是 −6 / +11, 新增的 VISIT / VISITNUM 等是使用频率更高的变量; 丢的 6 个在 140 题里零影响。
3. R1 会把 USUBJID 归到错误的文件; R2 推翻原设计的保守取舍, 改动跨 5 个模块, 不符合「少维护」。

**留给用户裁定**:
- **E1** 选 R0 / R1 / R2 (或别的规则)。若看重「EPOCH 是什么」这类问题的确定性补位, R2 更完整, 代价是 schema 改动和精度略降。
- **E2** REFID / SPEC 因 Notes 为空而丢: 接受 (推荐, 与 PDF 一致), 还是另定「无 Notes 的定义表也算」(R3 已证明全局放宽不可行, 只能做更窄的规则)。
- **E3** EPOCH 金丝雀 (6 列隔离不变量) 在 R0 下需要换一个变量, 是否接受由实现时现查挑选。

## v2 更新 (2026-11-27, 依据 pedia 答复 `sdtm-pedia/.work/10_tier_b_repair/evidence/checkpoints/t4_downstream_notes.md` 第 5 点; 与上文冲突处以本节为准)

### pedia 给出的新事实
1. model 文件 6 列表的**第 6 列 (Notes / Key Notes) 是 KB 自写的**, 不是 PDF 的 Definition (PDF 的 Definition / Notes / C-code 等 7 列按 pedia 用户规则不收)。所以现规则里「Notes 非空」这个判别条件是 KB 排版特征, 不是 PDF 语义。
2. 按 SDTM v2.0 PDF, 这些变量本来就出现在多张表里: TAETORD / EPOCH / MIDS 的**通用定义**在 §3.1.5 Timing Variables for All Classes (`model/02`); §3.2.3 (`model/03`) 和 §5.1.1.2 (`model/05`, 5 列) 是数据集内用法。APID 的定义表在 §4 (`model/04`); `model/06` 的 RELREC / SUPP-- / POOLDEF / APRELSUB 里它只是关系数据集的列。REFID / SPEC 只在 §6.7 RELSPEC (`model/06`)。
3. `REFID` 与 `--REFID`、`SPEC` 与 `--SPEC` 是不同变量。pedia 猜预演可能去掉了 `--` 前缀。**已核实: 没有。** `_model_defhome` 和本文件实算都排除 `--` 开头的变量名 (`build_meta.py` 末尾 `not var.startswith("--")`); REFID / SPEC 丢失的原因只有一个: `model/06:177-178` 那两行 Notes 为空 (旧 KB 放的是 C-code `C82531` / `C70713`, B-model06 重写后清空)。上文 §1 已写「不是多文件问题」, 与此一致。pedia 把这点记成观察项 ⑥ (与 model/03 SE 表仍在 Notes 放 C-code 的做法不一致), 解冻后可能改。
4. 旧 KB 规则能用, 是因为旧 model/02 时间变量表只有 5 列 (缺 Role), 6 列行恰好只在 model/03; 不是规则本身对。

### 新增模式级规则 R4「按 PDF 定义出处归属」
规则 (只依赖 model 文件的章节分工, 不点名任何变量):
1. 变量的 6 列行出现在 `model/02` (SDTM §3.1 一般观测类的通用变量表) → 归 02;
2. 否则把 `model/06` (关系数据集, 只把标识变量当列) 从候选里去掉;
3. 剩下恰好一个文件 → 归它; 否则丢弃。

R4n = R4 + 不要求 Notes 非空 (依据第 1 条: Notes 是 KB 自写列)。

实算 (脚本 `evidence/probes/defhome_rules.py`, 只读; `python defhome_rules.py <旧KB> <新KB>`):

| 变量 | 旧 KB 现规则 | 新 KB R0 | 新 KB **R4** | 新 KB R4n | PDF 定义出处 (pedia) |
|---|---|---|---|---|---|
| EPOCH / TAETORD / MIDS | 03 | 丢 | **02** | 02 | §3.1.5 → model/02 ✓ |
| APID | 06 | 丢 | **04** | 04 | §4 → model/04 ✓ |
| REFID / SPEC | 06 | 丢 | 丢 (Notes 空) | 06 | §6.7 → model/06 (R4n ✓) |
| VISIT / VISITNUM / VISITDY 等新增 8 个 | — | 02 | 02 | 02 | §3.1.5 ✓ |
| RSUBJID / RDEVID / SREL | — | 04 | 04 | 04 | §4 ✓ |
| USUBJID / POOLID / DOMAIN | 丢 | 丢 | **02** | 02 | §3.1.4 Identifiers for All Classes ✓ |
| RPHASE | 丢 | 丢 | 02 | 02 | §3.1.5 |
| RPATHCD / RSTGCD / RSTAGE (03 + 05) | 丢 | 丢 | 丢 | 丢 | 只有数据集内用法, 无通用定义 → 丢弃合理 |
| RDOMAIN (q73 / q83 依赖) | 06 | 06 | 06 | 06 | — |
| 映射总数 | 59 | 64 | **72** | 107 | |
| 旧 KB 下相对现状的变化 | — | 0 | **+3** (DOMAIN / USUBJID / POOLID → 02) | +39 (另加 STUDYID、SPDEVID 和 34 个 DM / SE / SV / SM 变量 → 03) | |

- R4 在新 KB 上与 pedia 给的 PDF 出处**逐项一致**; R1 (专章优先于 02) 方向恰好相反 (把通用定义让给了数据集内用法), 所以原来指出的「R1 把 USUBJID 归错」根源也在这里。
- R4n 能找回 REFID / SPEC, 但同时把 34 个 DM / SE / SV / SM 专属变量拉进来 (它们的定义确实在 §3.2, 归 03 本身不算错), 概念定义通道的触发面扩大近一半, 行为变化大。
- **140 题影响: 所有规则都是零。** 140 题里匹配 `_DEFVERB_RE` 的只有 q73 / q83 (RDOMAIN, 所有规则都 → 06) 和 q33 (RELSPEC, 不是映射里的变量)。复跑: 在 B 仓根 `.venv/bin/python .work/10_split_and_public/evidence/probes/defverb_hits.py` (输出 q33 RELSPEC / q73 RDOMAIN / q83 RDOMAIN)。
- 概念定义通道的回答变化 (闸外): R4 下 "what does EPOCH / TAETORD / MIDS represent" 补 model/02 (通用定义, 旧行为补的是 model/03 的 SE / DM 语境); "what does APID identify" 补 model/04; "what does USUBJID / DOMAIN / POOLID identify" 从「不补」变成补 model/02。

### 推荐变化: R0 → **R4**
理由:
1. pedia 的答复说明现规则在旧 KB 上能用是排版巧合, 新 KB 下的 6 个丢失不是「歧义」, 而是规则没按 PDF 的章节分工判断。R4 用的是章节分工本身, 和 PDF 出处逐项一致, 也是模式级规则 (不点名任何变量)。
2. 改动小: 只改 `_model_defhome` 的归属判定, 输出仍是「变量 → 单个文件」, meta.yaml schema 不变, `meta_store` / `structured_lookup` / `graph_engine` / `build_neo4j` 不用改。
3. 代价: ① 推翻原设计「多文件即丢」, `test_defhome_map_hygiene` 里 DOMAIN / USUBJID / POOLID 必须不在映射的断言要改 (语义从「歧义丢弃」变成「按出处归属」); ② **旧 KB 下 meta.yaml 会变 (+3 条)**, 所以 R4 不能作为「对生产零影响」的修复提前合, 要么放进「随 KB 升级」那一批, 要么提前合并接受这 3 条行为变化 (USUBJID 等的定义问题开始补 model/02); ③ 规则依赖 model 文件编号与 SDTM 章节的对应 (02 = §3.1, 04 = §4, 06 = §6), pedia 若重排 model 文件要先通知 (建议并入 pedia 答复里「下游格式约定」的变更约定)。
4. REFID / SPEC 暂不追: 是否找回取决于 pedia 对观察项 ⑥ 的处理 (若把 C-code 放回 Notes, R4 自动找回); 不为两个变量引入 R4n 的大范围变化。

R4 下的锚点 (替换上文 §3 的 R0 列; 数字以实现后重跑为准):
| 测试 | R4 下 |
|---|---|
| `tests/test_build_meta.py:152-157` | `EPOCH in mdh` 保留; `DOMAIN not in mdh`、`USUBJID not in mdh` 两条改为 `== model/02…` (或删去, 改测「数据集内用法不胜过 02」) |
| `tests/test_structured_lookup.py:209-215` EPOCH 金丝雀 | 期望值 model/03 → model/02; 6 列隔离不变量仍成立 (EPOCH 在 `model/05:64` 有 5 列用法行, 被 len==6 排除) |
| `tests/test_structured_lookup.py:217-225` hygiene | DOMAIN / USUBJID / POOLID 改为 → 02; 「多文件丢弃」的守卫改用 RPATHCD / RSTGCD / RSTAGE (03 + 05, 无 02) |
| `tests/test_meta_store.py:181` | `m["EPOCH"]` → model/02 |
| `tests/test_build_neo4j.py:50,85` / `test_reconcile_neo4j.py:18` | DEFHOME 59 → 72 |
| `tests/test_build_neo4j.py:84` | `rows["APID"]` → model/04 |
| `tests/test_build_neo4j.py:27,30,34,77-80` / `test_reconcile_neo4j.py:16` | ModelChapter 4 → 5 (加 model/04); Variable / model_only 计数按重跑结果 |

### 待裁定 (替换上文 E1-E3)
- **E1** 选规则: R4 (推荐) / R0 / R2 / R4n / 其他。
- **E2** R4 的落地时机: 放进「随 KB 升级」批 (推荐, 旧 KB 生产行为完全不变), 还是提前合并并接受旧 KB 下 +3 条 (DOMAIN / USUBJID / POOLID → 02)。
- **E3** REFID / SPEC: 等 pedia 对观察项 ⑥ 的裁定 (推荐), 还是现在就用 R4n 或更窄的规则找回。
- **E4** 是否请 pedia 把「model 文件编号 ↔ SDTM 章节」也写进下游格式约定。

## v3 修订 (2026-11-27, 独立审查后; 与 v2 冲突处以本节为准)
审查: `model_defhome_rule_options_review.md` (`oh-my-claudecode:architect`, PASS-with-fixes)。

1. **R4 规则文字更正 (H1)**: 第 2 条改为「**变量出现在多个文件时**, 才把 model/06 从候选里去掉」。只出现在 model/06 的变量 (RDOMAIN、IDVAR、IDVARVAL、QNAM、QLABEL、QVAL、QORIG、QEVAL、RELID、RELTYPE、PARENT、LEVEL 共 12 个) 仍归 06。照 v2 的字面去实现会丢掉 RDOMAIN, q73 / q83 回归。`probes/defhome_rules.py` 本来就是这样实现的, 实算结果不变。锚点加一条: 只在 06 的变量仍归 06 (以 RDOMAIN 为例)。
2. **第 2 条的支撑数 (L2)**: 现有数据里需要「多文件时剔除 06」才能归属的只有 APID 一个 (n=1)。背后的通则: SDTM §6 关系数据集 (RELREC / SUPP-- / POOLDEF / APRELSUB) 只把别处定义的标识变量列为列, 不是定义处。若用户认为 n=1 不足以立规则, 去掉这一条后 APID 会丢 (其余结果不变)。
3. **出处归因收窄 (L1)**: pedia 第 5 点只列了 TAETORD / EPOCH / MIDS / APID / REFID / SPEC 这 6 个变量。v2 表里 USUBJID / POOLID / DOMAIN / RPHASE 的「PDF 出处」是按 pedia 的通则 (一般观测类通用变量在 §3.1.x) 推断的。「与 PDF 出处逐项一致」只对这 6 个成立; 审查者对 72 个映射全查, 没有发现冲突。
4. **R4 仍依赖 Notes 是否为空 (M2)**: Notes 是 KB 自写列, R4 仍拿它判定定义行。所以除了 REFID / SPEC, 同一张 §3.1.4 表 (`model/02:291-298`) 里 Notes 为空的 **STUDYID、SPDEVID** 也进不了映射; DOMAIN / USUBJID / POOLID 能进, 只因为它们的 Notes 非空。pedia 处理观察项 ⑥ (只涉及 model/06) 也找不回 STUDYID / SPDEVID。**R4 的结果会随 pedia 改动任何 Notes 单元格而变**, 每次 KB 升级都要重跑 `defhome_rules.py`。
5. **EPOCH 金丝雀 (M1)**: R4 下 EPOCH 在 02 和 03 都有 6 列行, 又是 02 优先。即使有人放宽 len==6 过滤, EPOCH 仍归 02, 测试照样通过, 守不住「6 列隔离」不变量。改法: `test_defhome_canary_epoch_six_col_isolation` 降为普通断言 (EPOCH → model/02); 隔离金丝雀改用 **ETCD**。ETCD 的 6 列行在 model/03 (新 KB `:133`、旧 KB `:111`), 5 列行在 model/05 (新 `:39`、`:60`, 旧 `:35`、`:54`)。放宽过滤后它会变成 {03, 05} 多文件而被丢弃, 测试就会报错。ARMCD 也可以。RDOMAIN 金丝雀在 R4 下仍有效。
6. **使用方补列 (L3)**: `eval/prod_wirein/sp4_cookbook_golden.py:142-150` 的 defhome:ch06 闸比较图谱与 MetaStore, 两边一起变, 不会失败, 但 APID 会移出 ch06, 闸的期望集合要核对; `scripts/build_neo4j.py:13,89-91` 与 `tests/test_structured_lookup.py:199` 的注释 / docstring 写死了 59 / 18; 原设计依据 `docs/evidence/checkpoints/d_channel_concept_definition.md` 的「宁缺毋滥」(多文件即丢) 需要补一条修订说明。
7. **兜底检查 (L4)**: 实现 R4 时加启动 / 构建期检查: 找不到 `model/02_*`、`model/06_*`, 或它们的首个编号标题不再是 §3 / §3.1、§6, 就让 `build_meta` 报错, 防止 pedia 重排 model 文件后映射悄悄变化 (E4 的「请 pedia 通知」只是约定, 这一条是机器兜底)。

### 待裁定 (替换 v2 的 E1-E4)
- **E1** 选规则: R4 (推荐, 按本节第 1 条修正后) / R0 / R2 / R4n / 其他。
- **E2** R4 的落地时机: 放进「随 KB 升级」批 (推荐) 还是提前合并 (旧 KB 下 +3 条)。
- **E3** Notes 为空的定义行: REFID / SPEC (model/06) 和 STUDYID / SPDEVID (model/02 §3.1.4) 都进不了映射。可选: 接受; 等 pedia 处理 ⑥ (只能找回 REFID / SPEC); 或者换一条比 R4n 更窄的规则。
- **E4** 是否请 pedia 把「model 文件编号 ↔ SDTM 章节」写进下游格式约定 (第 7 条的机器兜底照做)。
- **E5** 6 列隔离金丝雀换成 ETCD (推荐) 还是 ARMCD。
- **E6** 「多文件时剔除 06」只有 APID 一个样本 (n=1), 是否保留这一条。
