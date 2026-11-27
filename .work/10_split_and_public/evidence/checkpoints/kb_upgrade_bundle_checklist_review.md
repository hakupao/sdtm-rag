# 审查: kb_upgrade_bundle_checklist.md v2 (规则 D)

- 审查者: subagent_type `oh-my-claudecode:verifier` (写作者为主会话 Claude, 不同 agent 类型、不同 context), 2026-11-27, 只读, 零 API 费用 (复核脚本在 scratchpad `rev/`)。
- prompt 存档: `evidence/subagent_prompts/review_kb_upgrade_checklist.md`
- **结论: PASS-with-fixes** (高 2 / 中 3 / 低 2)。§A gold 结论独立复核成立 (chunk 级核对 49 条节级 + 153 条路径级 gold: 只有 q39 / q117 / q120 三条 fact 与 q126 节级); §1 / §2 / §3 的行号与新值逐条吻合 (§1 新值实跑 24 / 8 / 45); 新 KB 全量 pytest 31 failed = 清单 30 + p2_seam。修订见清单「v3 修订」。

| # | 问题 | 处置 |
|---|---|---|
| H1 | §B.1「每个 H3 内判定, 无 H4 则整个 H3 一块」会误伤 CP / FA / MB / PP / RELREC / RS / TA / TE / TV 共 9 个「H2 下挂 H3、无 H4」的 examples 文件 (如 `test_ta_examples_produces_8_chunks` 会坏, PP 的 `### Method A —` 会被拆) | 改为按 H2 分派: H2 内含 `#### Method` 走嵌套, 否则整个 H2 一块 (现状); 补「新旧 KB 全部 examples 改前后 chunk 全字段 diff, 只允许 PC +1 块」验证 |
| H2 | 没写明: 改变 chunk / meta 产物的代码 (CT 修复、PC chunker、R4) 必须在 kb-sync 构建候选**之前**合进 main。候选的 ingest / build_meta 用 main 当时代码 (`kbsync.py:369-385`), swap 把 `chroma_cand_*` / `meta_cand_*` 整个换成生产 (`:241-257`); 已 gated 的指纹 no-op, 晚合的代码不会触发重建 → 线上代码与数据静默不一致。仓库里的 `data/meta/meta.yaml` 只供 CI / 测试, 线上 meta 来自候选 | 主会话复核成立。§5 加硬约束; 晚合时须删已过闸候选或重打 tag 再跑 kb-sync; 「R4 + 随 KB 提交」组合排除, defhome E2 同步改 |
| M1 | §B.4 漏列 PC 测试: `test_pc_examples_all_have_sub_label_method`、`sub_labels_are_valid_methods` 会因 Example 1 块无 Method 失败; `produces_14_chunks` → 15; `example_index` 两条取决于 Example 1 块的取值 | 逐条列出; PC 测试改动只能随 KB 提交, 先合的 chunker 代码要让旧 KB 下原测试仍过 |
| M2 | §B.2 的「域节号」数据源不存在: KB 里 `6.3.5.9.1` 零命中, meta 无节号映射; PC assumptions 第一个带 § 的是 `§6.3.5.9.3` (挂错的值); 「向上最近带 § 的标题」还会让 EX / TU 的 `## Example N` 继承 §6.1.3.3 / §6.3.12.3。`cdisc_section_id` server 不消费, 只影响元数据 | 写明数据无法给出 §6.3.5.9.1; 按 H2 分派后 Example 1 块保持 None 并在测试里写明, 不做继承 (继承需硬编码映射或请 pedia 提供) |
| M3 | §C 末行「超 8191 会让 ingest 出问题」错: `ingest.py:230-301` 截断并 WARNING; 新旧 KB 各已有 18 个 terminology chunk 超 8191 (最大 19975)。CP Example 6 由 <5784 涨到 7296 | 改为「非 terminology 中超 8191 的 chunk 数 (现为 0), 出现新增时检查截断」 |
| L1 | §A 可更扎实: 节级 gold 命中 chunk 正文有变但 fact 全在的: q38 `ch04#4.1.6`、q39 `ch08#8.6.3`、q19 / q91 `DS/spec#DSDECOD` 与 `DS/assumptions#item_3`、q76 `model/06#6.6`、q115 `ch08#8.4.1` 与 `SUPPQUAL/assumptions#overview`、q117 `ch04#4.5.4`; q10 `RS/assumptions.md#item_4$` 1 → 2 chunk (新增 QRS 文字, fact 仍在); q126 两个 any-of 成员新旧 KB 都不单独覆盖全部 facts (既有问题) | 写进 §A |
| L2 | §5 第 1 步没区分 chunker 修复里「旧 KB 行为不变」可先合的部分与要等新 KB 才定的测试期望; S1 下 H3 导语约 4 行被丢是现状, 不是回归 | 改措辞 |
