# 审查: kb_rehearsal_477bac3.md + kb_upgrade_bundle_checklist.md v6 (规则 D)

- 审查者: subagent_type `oh-my-claudecode:critic` (写作者为主会话 Claude, 不同 agent 类型、不同 context), 2026-11-27。对仓库与 pedia 零写入; 复核产物只在临时目录。费用: 在候选树上跑过两次小评测 (4 题、1 题) 的 query embedding, 可忽略; 没有重跑入库。
- prompt 存档: `evidence/subagent_prompts/review_kb_rehearsal_477bac3.md`
- **结论: PASS-with-fixes** (MAJOR 2 / MINOR 7)。闸的结论、指纹、q76 归类、18 个失败的分类、清单 v6 的数字都经得起复核, 没有发现算错的数字。两条 MAJOR 都在给主人裁定用的「做法 B」上。

## 已核实成立 (审查者自己跑的)
- **闸**: 用 `kbsync._load_recall` / `_load_avg` / `regressions` 加 `gate()` 的五项判据重算: 回退只有 q76, 满分 138 → 137, avg 0.9881, PASS; 回退 ≤ 1 与满分 ≥ 137 两项都踩线。入库的 `baseline.json`、`candidate.json` 与临时目录里的 sha256 相同。「top5 有 71 题不同」「候选 5 趟之间只有 q78 有差别」复算一致。
- **候选跑在新 KB 上**: 树哈希 `63f857774a42…`、KB 指纹 `477bac3ce565…`、候选 stamp 同指纹、4333 chunks; 重新 `git archive d46f8af` 后与写作者的展开目录 `diff -r` 完全相同; pedia `d46f8af..HEAD` 之间没有 KB 改动。
- **q76 = gold 漂移, 没有第二个原因**: 在候选树导出 q76 每一席的 (source, section), 第 2 席就是 `model/06…| 6.6 Associated Persons Relationships (APRELSUB)`; 新节含 APID / RSUBJID / SREL。
- **pytest**: 三份日志的数字属实 (0 / 18 / 0 failed); 18 个失败的 `E` 行与报告表格逐条一致; 锚点替换都是绝对值或等式, PC 的几条是「先断言恰好 14 + 1 块再过滤」, 没有把断言改弱 (不属于规则 6 的 A / B / D)。反向验证: 套了锚点的测试放回旧 KB, 那 18 条全部失败 (170 条通过)。另跑了「锚点 + 候选 chroma + 五处全改题集」: 2941 passed / 0 failed / 56 skipped。
- **清单 v6 数字** (抽查约 15 个): chunk 4329 / 4333 及各类数、超长 chunk 18 / 0 (最大 MB 7878、CP 7296)、PC 15 块、ct_codes 588 / 570 / 147、ct_dict 176、codelists 1005、`model_defhome` 62 → 75 (新增 15 / 移除 2 / 改归属 4, 按文件 18 / 31 / 4 / 10 / 12)、DM 两个变量的 type 变化、KB 单元格 570 / 129 / 59 个 spec.md、覆盖率 306 → 302。相对 `00a2e93`: 用真实 `scripts.build_meta` 跑出 72 条, 正好比新 KB 少 TSVALCD / TSVCDREF / TSVCDVER。
- **gold**: 节级用另一种方法 (直接取新旧 chroma 的全部 (source, section), 用 `eval.run_eval.source_matches` 判全部 202 条) 重算, 新 KB 失效的只有 q76、q126; fact 按 chunk 粒度查, 真正丢失的只有 q39 / q117 / q120 三条; q39 召回的是 `domains/FA/assumptions.md` 的 `item_3` 块 (含 §6.4.3 与 FAOBJ), 5 趟都在第 4 席; q117 / q120 的新 fact 逐字存在; kb-sync 机制的描述与 `kbsync.candidate()`、`kb-sync.yml` 一致; 「做法 B 0 回退」成立。
- **范围**: `git status` 只有 `.work/`; 开发数据三个 sha256 前缀与报告一致; 长效文档没有引行号。

## 问题与处置 (全部接受)
| # | 严重度 | 问题 | 处置 |
|---|---|---|---|
| 1 | MAJOR | 做法 B 漏写一个代价: 打 tag 之前改 q76 的 gold, 会让本机 `tests/test_section_gold_exists.py::test_every_section_gold_exists_in_index` 变红 (any-of 组里总有一个成员在当前索引里不存在)。CI 无索引会跳过, 不挡部署; 但与清单开头「只在新 KB 下成立的改动不提前合」的原则冲突, v6 没说明为什么可以例外。两次预演的 pytest 树都没有 chroma, 这条测试从未被跑到 | 主会话复核成立 (旧 KB 索引 + q76dual 题集: 1 failed)。已写进报告「三种做法」表与清单 v6 第 1 条; 补了「有索引」的 pytest 组 (2941 / 0 / 56)。复核时另查出: 新 KB 索引 + 原题集下这条测试同样失败 (q76、q126), 靠 gold 修订消除, 已写进报告与清单 |
| 2 | MAJOR | 做法 B 和「全部修订在旧 KB 上」两组实测没有复跑命令 (与上一轮审查 MAJOR-4 同类): 题集变体脚本不生成 q76dual; 这几份 JSON 只在临时目录; 命令里的输出名与实际不一致 | `probes/kb_rehearsal_gold_variants.py` 补上 q76dual (重新生成后与实测用的题集逐字节相同); 复跑命令补全并统一文件名; 6 份评测 JSON 入库 `kb_rehearsal_477bac3_runs/` |
| 3 | MINOR | 漏了第三种做法: 打 tag 前只把 q76 换成新标题 (闸 0 回退, 不算放宽 gold; 本机同一条测试会红, 升级前 q76 在闸里不起保护作用) | 作为做法 C 列入报告与清单 |
| 4 | MINOR | 「7 趟评测」实为 8 趟 (基线树 3 + 候选树 5) | 已改 |
| 5 | MINOR | `sec_*_rel.json` 要手工去路径前缀, 没给命令 | 复跑命令补了一行 |
| 6 | MINOR | 「新增缺失行都是 `> Source text:` 指针行」不准确: 还有分组标题行、`> See …` 指针行、原本就缺而这轮改了措辞的行; 没有新丢的正文 | 报告与清单的措辞已改 |
| 7 | MINOR | 报告引用了还不存在的「独立审查」一节和本审查文件 | 已补 |
| 8 | MINOR | 没记录 q39 召回的是 FA 文件的哪个 chunk; FA 文件有两个 `item_3`, 改成节级 gold 会有歧义 | 报告已写明 chunk 与「保持路径级」的理由 |
| 9 | MINOR | pedia HEAD 已前进, 标题清单文件名里的「HEAD」未交代; 清单 v6 表里旧 KB 的 `model_defhome` 62 未注明线上是 59 | 各加了说明 (pedia 现 HEAD `c90cb61`, KB 树哈希不变) |

## 审查者没有独立核实、只读过的
线上 meta 59 条与虚拟机上的基线结果; DOMAIN 域码单元格 59 个; 开发数据「之前」的哈希 (只核了现值); `kb_rehearsal_secdump.py` / `secmatch.py` / `factcheck.py` 脚本本身 (用自己的方法得到相同结论, 未逐行审); pedia 的 `t4_downstream_notes.md` 正文。

## 待议 (不计分)
- q10 的 gold `RS/assumptions.md#item_4$` 在新 KB 匹配到 2 个同名块, 这些块两版里都不含 q10 的 fact, 与清单 v3 第 5 条「fact 仍在」不符。已记入报告, 下次修 gold 时一起看。
- 做法 A 余量为零: kb-sync 在虚拟机上会重新入库, 两次入库之间的波动这次预演量不到。已写进报告。
