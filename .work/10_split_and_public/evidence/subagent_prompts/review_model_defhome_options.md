# prompt: 审查 model_defhome_rule_options.md v2 (subagent_type oh-my-claudecode:architect, 2026-11-27)
独立审查者 (规则 D), 中文, 只读, 不花 API 费用。对象: model_defhome_rule_options.md 整份 (重点 v2, 推荐 R0→R4)。
依据: pedia t4_downstream_notes.md 第 5 点; 旧 KB vendor、新 KB scratchpad/rehearsal/kb00a2e93; 脚本 probes/defhome_rules.py、defverb_hits.py; 使用方 server/structured_lookup.py / meta_store.py / graph_engine.py:81, scripts/build_neo4j.py / reconcile_neo4j.py; 锚点测试 test_build_meta / test_structured_lookup / test_meta_store / test_build_neo4j / test_reconcile_neo4j。
重点: 1 实算数字与归属 (复跑 + 抽查 KB 原文), 脚本与文字规则一致; 2 R4 是否模式级、与 PDF 出处逐项一致, 全查 72 个映射找反例; 3 REFID/SPEC 只因 Notes 空的核实; 4 推荐理由与代价、遗漏风险、R4 锚点清单逐个核对; 5 E1-E4 完整中立; 6 140 题零影响论证。
输出: PASS / PASS-with-fixes / FAIL + 按严重度问题清单。
