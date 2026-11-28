# 独立安全审查任务书 (第 3 轮, 窄范围): 新发现 A 的修正 (2026-11-28)

审查者: 同一位 `oh-my-claudecode:security-reviewer`。只读, 限制与前两轮相同。

## 要看的
提交 `e4b33d3` (`git diff b24dc21 e4b33d3`)。它处理你第 2 轮的新发现 A (先隐名后脱敏时, 值里带 `study` 的凭据只被盖住一部分)。
做法照你验证过的那一种, 收进了一个函数 `_sanitize_log` (`deploy/kbsync/kbsync.py`): key 片段先换成不含分隔符的占位符 `_KEY_MASK` → `_hide_study_names` → 占位符换回 `<已隐去>`。`accept_check` 只调它。
测试: `test_a_secret_containing_the_word_study_is_scrubbed_whole` (5 种写法, 假值运行时拼接)、`test_sanitize_log_keeps_both_guarantees_in_one_text`; `test_a_name_with_a_key_shaped_fragment_is_hidden_whole` 的断言改成不核对具体的指纹值。

## 请判断
1. 新发现 A 是否到位; 第 1 轮的 MEDIUM (名字被切成两段) 在新写法下是否仍然挡得住。
2. 三步之间还有没有新的缝:
   - 占位符 `"\x00K\x00"`: 原始日志里本来就有这串字节时会怎样; 占位符与 `study` 相邻时 (前后各种位置) 切词结果是什么; 占位符落在一个会被白名单 / 配置项名单放行的词里会怎样。
   - 脱敏规则 `SECRET_RE` 只匹配到凭据的一部分时 (比如值里有它不认的字符), 剩下的部分紧跟着 `study…` 会怎样 —— 与 `ce9c884` (改之前的顺序) 相比是不是更糟。
   - `scrub()` 本身没有改, 其它调用点 (`_probe`、`ACCEPT_PY` 的 stderr、`deploy_public` 各处的 `scrub(str(e))`) 仍然只脱敏不隐名: 这是不是与改之前相同 (不属于这次的范围, 确认没有变差即可)。
3. 断言放宽之后 (不再核对具体的指纹值) 那条回归测试还抓不抓得住第 1 轮的问题; 新加的变异 (脚本里的 L2c / L3h / L3n / L3o / L3p) 请自己复做其中关键的几个。
4. 进程收尾相关的代码这次没有动 (`git diff b24dc21 e4b33d3 -- deploy/kbsync/kbsync.py` 只有日志处理那一段), 请确认。

## 补充信息
`b24dc21` 已在 runner 镜像里跑过 (完整 CI 命令 3558 passed / 0 failed / 61 skipped; 去掉僵尸排除 / 不补发 SIGKILL / 只发 SIGTERM / 只结束组长 四个变异都红), 记录会写进 `.work/10_split_and_public/evidence/checkpoints/pre_switch_fixes.md`。

## 回报
结论 (PASS / PASS-with-fixes / FAIL; 是否阻止合并; 打开开关之前还剩什么); 逐条判断; 你做过的变异及结果; 核实不了的事项。
