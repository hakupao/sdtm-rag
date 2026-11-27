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
