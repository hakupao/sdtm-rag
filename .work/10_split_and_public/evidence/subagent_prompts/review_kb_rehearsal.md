# prompt: 审查 kb_rehearsal_bf33bab.md (subagent_type oh-my-claudecode:critic, 2026-11-27)
独立审查者 (规则 D), 中文, 只读不改不提交, 不跑 ingest / embedding / retrieval eval。
对象: kb_rehearsal_bf33bab.md + failures/kb_rehearsal_bf33bab_attempt_1.md (pedia 本地新 KB 预演入库 + CDISC 140 题 retrieval-only 闸)。
背景: B 仓 p3 只读; pedia KB 绝对只读, git 命令加 GIT_OPTIONAL_LOCKS=0; 旧 KB = vendor (kb-2026.11.25), 新 KB 钉 00a2e93; 临时产物在 scratchpad/rehearsal/ (baseline/candidate/counterfactual.json、*.log、pytest_ci_newkb_rf.log、pytest_ci_oldkb.log、base/cand/cf/ci/ci_old 代码树、kb00a2e93); cf/data/meta/meta.yaml 后被旧 KB 重新生成过, cand/data/meta/meta.yaml 是新 KB 未修补产物。闸函数 deploy/kbsync/kbsync.py; gold 语义 eval/run_eval.py check_source_recall; CT 解析 scripts/build_meta.py:43 / spec_loader.py:69; _model_defhome build_meta.py:134。
重点: 1 归因是否闭合 (6 题是否全因 CT 正则; 漏掉的其他解释; 反事实对照设计; 从日志/时间核实 cf meta 当时是新 KB+补丁); 2 向后兼容论证; 3 30 个 pytest 失败分类 ①②③ 逐个核对, test_class_and_chapter_nodes 结论, 对照组 1 个失败是否与 KB 无关; 4 fact 3 / 节级 1 gold 漂移结论与方法缺陷; 5 事实、数字、复跑命令准确性, 夸大或未核实断言。
输出: PASS / PASS-with-fixes / FAIL + 按严重度问题清单 (位置、问题、证据、建议)。
