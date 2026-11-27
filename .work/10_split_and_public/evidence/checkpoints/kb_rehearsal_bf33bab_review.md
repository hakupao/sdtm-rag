# 审查: kb_rehearsal_bf33bab.md (规则 D)

- 审查者: subagent_type `oh-my-claudecode:critic` (写作者为主会话 Claude, 不同 agent 类型、不同 context), 2026-11-27, 只读, 零 API 费用 (复核产物只在 scratchpad `critic_review/`)。
- prompt 存档: `evidence/subagent_prompts/review_kb_rehearsal.md`
- **结论: PASS-with-fixes** (MAJOR 4 / MINOR 6)。主结论 (6 题回退根因 = CT 码正则; 反事实成立) 站得住。修订见报告文末「v2 修订」。

## 已核实成立
- 归因闭合: 候选 meta 与反事实 meta 只差 `ct_codes` / `ct_dict` (变量级其他字段差 0, `model_defhome` 相同); KB 与 chroma 两边相同; 新 KB 的 `terminology/`、`VARIABLE_INDEX.md` 与旧 KB 逐字节相同 → chunk / BM25 变化可排除。补丁 meta 的 (domain, var, ct) 三元组与旧 tracked meta 相同 (542 对 / 588 码)。
- cf 评测所用 meta: 日志无直接记录; 审查者用钉版本 KB + 补丁代码重新生成, 与 `meta_cf_newkb.yaml` 逐字节一致, 时间顺序吻合; 即便误用旧 meta, CT 对相同, 结论不变。
- gold 漂移: fact 466 条丢 3 (q39 / q117 / q120); 节级用 `eval.run_eval.source_matches` 重算只有 q126 一条。
- 数字: 指纹、4329 → 4332、各类 chunk 增减、31 failed / 2866 passed、ct_dict +188 (`*` 129 + DOMAIN 59) 均无误。

## 问题与处置 (全部接受)
| # | 问题 | 处置 |
|---|---|---|
| MAJOR-1 | pytest 分类错 4 个: `test_node_counts`、`test_variable_model_only_split`、`test_edge_counts` (补丁后报 DEFHOME 64≠59)、`test_reconcile_neo4j` 应属 ②; `test_class_and_chapter_nodes` = ② (model/04 新增 ModelChapter)。修正后 ① 16 / ② 9 / ③ 5。审查者用补丁 meta + 补丁 build_meta 重跑 31 个失败: 15 failed / 16 passed | 表格已改; v2 修订第 1 条 |
| MAJOR-2 | 对照组失败不是临时树问题: `test_p2_seam_characterization` 主仓 p3 同样失败, `server/web_search.py` 的 `date.today()` 进了 `messages_sha`, golden 11-26 录、今天 11-27 → 日期依赖; CI 测试步会因此对所有运行时 push 报红 | 主会话复核成立 (冻结日期 → 2/2 通过); v2 修订第 2 条, 列为一切推 main 的前置条件 |
| MAJOR-3 | 向后兼容论证外推: 旧 KB 无新写法, `cmp` 一致是必然; 没覆盖 `is_ct_code` 与 defhome 规则改动 | 结论收窄; v2 修订第 3 条 |
| MAJOR-4 | 反事实 / cmp / fact / 节级 / pytest 缺可复跑命令, 节级匹配脚本没留 | 命令补进 v2 修订第 4 条; 脚本拷入 `evidence/probes/kb_rehearsal_*.py` |
| MINOR-1 | 「63 个 spec.md」照抄提交说明, 实际含 `(X) Cnnnnn` 的是 59 个 | 已改 |
| MINOR-2 | 漏影响面: 29 题 top5 丢了排第 2 的 terminology 席位, 闸只见 6 道 | v2 修订第 5 条 |
| MINOR-3 | 「逐题一致」只对 source_recall 成立 (top5 排序 67 题不同; cand / cf 有 ~1e-3 query embedding 噪声) | 已改顶部结论 |
| MINOR-4 | failures「下一 attempt 输入」漏 ② / ③ / p2_seam / pytest 全绿验收 | 已补 |
| MINOR-5 | fact 核对局限 (只查 gold 文件不查回答; 拼接无分隔符) | v2 修订第 4 条注明 |
| MINOR-6 | `44fb042` 已含 "KB note on C-codes", 反馈第 2 条应先读它 | v2 修订第 6 条 |
