# 独立安全审查任务书 (第 4 轮, 窄范围): 你审完之后又改的一处测试 (2026-11-28)

审查者: 同一位 `oh-my-claudecode:security-reviewer`。只读, 限制与前三轮相同。

## 要看的
提交 `0e9e985` (`git diff e4b33d3 0e9e985`)。它只改了两个文件, 没有动 `deploy/kbsync/kbsync.py` 和三份 kbsync 测试 (请用 `git diff --stat e4b33d3 0e9e985` 确认):
1. `tests/test_workflow_conditions.py` 的 `test_the_schedule_check_sees_every_way_of_writing_it`: 原先只断言「两道判据 (解析 / 文本) 至少一个抓到」。你第 2 轮的 R11 (去掉测试加载器的重复键检查) 没有红, 实现者自己的变异 W6 (同 R11)、W7 (文本检查退回只看行首) 也存活。现在改成逐个写法分别核对两道判据各自怎么判, 并补了一种只有「键重复就报错」抓得到的写法、一种写在别的层级的写法。
2. `.work/10_split_and_public/evidence/checkpoints/pre_switch_fixes_mutations.py`: 一个写错的变异 (Z16, 缩进错导致语法错误) 改对; 拒跑条件改成「不设 `PSF_MUT_ROOT`、或它指的目录里有 `.git` 都拒跑」; 新增 `PSF_MUT_ONLY` 只跑指定编号。

## 请判断
1. 改过的那条测试是不是真的把两道判据分别钉住了: 请自己复做 R11 / W6 (加载器不拒绝重复键) 和 W7 (文本检查只看行首), 以及你认为还该试的 (例如把表里某一种写法的期望值改反、把 `_mentions_schedule` 改成恒假 / 恒真)。
2. 表里 9 种写法的期望值 (解析怎么判、文本怎么判) 是否与这两个函数的实际行为一致、是否有写错期望而恰好通过的; `test_no_workflow_has_a_schedule_trigger` 对真实的两个 workflow 文件的结论有没有因此变弱。
3. 变异脚本的两处改动有没有让它在某种情况下「该拒跑时照跑」或「没跑却报通过」(例如 `PSF_MUT_ONLY` 写了不存在的编号、写成空串、`.git` 是文件而不是目录的工作区)。
4. 这次有没有动到不该动的文件。

## 回报
结论 (PASS / PASS-with-fixes / FAIL; 是否阻止合并); 逐条判断; 你做过的变异及结果; 核实不了的事项。
