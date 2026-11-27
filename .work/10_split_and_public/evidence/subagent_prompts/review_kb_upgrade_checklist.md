# prompt: 审查 kb_upgrade_bundle_checklist.md v2 (subagent_type oh-my-claudecode:verifier, 2026-11-27)
独立审查者 (规则 D), 中文, 只读, 不花 API 费用 (pytest 子集 / 脚本只在 scratchpad 临时树跑)。对象: kb_upgrade_bundle_checklist.md 整份 (重点 v2 A-D)。
依据: pedia t4_downstream_notes.md 第 6 点表 A / 表 B、第 7 点; 旧 / 新 KB; eval/test_set_v3.yml 与 run_eval 匹配语义; probes/ 下 gold_vs_moved / secdump / secmatch / factcheck / coverage; scratchpad/rehearsal/ci 临时树; scripts/chunkers/examples.py; 部署路径过滤 sdtm-rag.yml:9-25; kb-sync.yml / kbsync.py。
重点: 1 独立核对「除已知 4 处外无别的 gold 引用被移走 / 改名的节」; 2 PC 切块方案对 S1/S2/S3 是否成立、S1 是否输出不变、误伤其他文件、域节号数据源; 3 §1-§3 每条锚点 / gold 位置与新值; 4 提交顺序与生效时机; 5 §C 重跑数字表完整性与数值。
输出: PASS / PASS-with-fixes / FAIL + 按严重度问题清单。
