# 审查: model_defhome_rule_options.md v2 (规则 D)

- 审查者: subagent_type `oh-my-claudecode:architect` (写作者为主会话 Claude, 不同 agent 类型、不同 context), 2026-11-27, 只读, 零 API 费用。
- prompt 存档: `evidence/subagent_prompts/review_model_defhome_options.md`
- **结论: PASS-with-fixes** (高 1 / 中 2 / 低 4)。实算数字全部复现 (R0 59/64, R4 62/72, R4n 107; 25 个关注变量逐个一致); R4 全部 72 个映射全查, 没有与 PDF 出处冲突的; REFID/SPEC 只因 Notes 空、`--REFID`/`--SPEC` 被 `build_meta.py:162` 排除, 成立; 140 题零影响成立 (检索路径只有 `structured_lookup.py:427` 用映射, `GraphEngine` 高层方法不遍历 DEFHOME)。修订见文档「v3 修订」。

| # | 问题 | 处置 |
|---|---|---|
| H1 | R4 文字第 2-3 条与脚本不一致: 按字面「去掉 06」会让只在 06 的 12 个变量 (RDOMAIN、IDVAR、QNAM …) 被丢, q73/q83 回归; 脚本实际只在多文件时剔除 06 | 规则文字改为「多文件时才剔除 06」, 锚点加「只在 06 的变量仍归 06」 |
| M1 | R4 下 EPOCH 金丝雀失去检测力 (02 优先, 放宽 len==6 也照样归 02); RDOMAIN 金丝雀仍有效 | EPOCH 测试降为普通断言 (→ 02); 隔离金丝雀改用 ETCD (6 列行 model/03, 5 列行 model/05 ×2; 新旧 KB 主会话已复核) 或 ARMCD; 恢复「换金丝雀」裁定项 |
| M2 | R4 仍靠 Notes 是否为空判定: §3.1.4 同表里 STUDYID / SPDEVID (Notes 空) 被丢, pedia 处理 ⑥ 也找不回 | E3 补 STUDYID / SPDEVID, 写明 R4 结果随 pedia 改 Notes 而变 |
| L1 | 「PDF 出处 (pedia)」列过度归因: pedia 只列了 6 个变量, USUBJID / POOLID / DOMAIN / RPHASE 是按 pedia 通则推断 | 标注「按通则推断」, 「逐项一致」限定在 6 个 |
| L2 | 「剔除 06」这一条只有 APID 一个样本 (n=1), 易被看成对症下药 | 写明 n=1 与背后通则 (§6 关系数据集只把别处定义的标识变量当列) |
| L3 | 使用方漏列: `eval/prod_wirein/sp4_cookbook_golden.py:142-150` (defhome:ch06 闸, 两边一起变不会失败, 但 APID 移出 ch06)、`scripts/build_neo4j.py:13,89-91` 与 `tests/test_structured_lookup.py:199` 注释里写死的 59 / 18、`docs/evidence/checkpoints/d_channel_concept_definition.md` 的「宁缺毋滥」依据 | 补进清单 |
| L4 | 规则依赖 model 文件编号, 无兜底 | 实现时加检查: 找不到 02 / 06 或其首标题不再是 §3.1 / §6 → 报错 |
