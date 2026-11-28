# 窄范围确认 (第三次): 测试里的假密钥改成运行时拼接 (2026-11-28)

同一位审查者。只读, 不改工作目录, 不 push。只看这一处: `git diff -- tests/test_kbsync_public.py` (工作目录里未提交; 基线 = main `613f048`)。

## 事实
- 密钥扫描器对已推送的提交报了两处 (JWT 形状、Bearer 形状), 都是 `test_scrub_hides_key_shapes` 的参数化假值, 不是真密钥。已推送的历史不改。
- 协调方要求: 把这个 parametrize 里完整密钥形状的假值改成运行时拼出来的, **传给 `ks.scrub` 的最终字符串与现在逐字相同, 测试语义不变**; 只改这一处。
- 写的人的核对脚本: `.work/10_split_and_public/evidence/checkpoints/p3_tunnel_leg_merge_scrub_equiv.py` (用 AST 取出 `613f048` 里的字面量列表求值, 与导入当前模块得到的参数逐个比较)。输出只当线索。

## 请确认
1. 改前改后 13 个参数是否逐字相同、顺序相同 (请用你自己的办法独立核对一次, 不要只跑写的人的脚本)。
2. 测试语义有没有变: 断言没动; pytest 收集到的用例数与 id 是否不变; 新加的模块级名字 (`_b64url`、`FAKE_SECRETS`、`import base64`) 会不会与文件里别的名字冲突或被别的测试误用。
3. 这次改写有没有让测试变得更容易「静默失效」(例如列表为空时 parametrize 不报错只是 0 个用例)。
4. 文件里是否还留有完整密钥 / token 形状的字面量。

可以运行: `git` 只读命令; `.venv/bin/python -m pytest tests/test_kbsync_public.py -q -o addopts="" -p no:cacheprovider`; 上面的核对脚本。
输出: PASS / PASS-with-fixes / FAIL + 逐条回答 (附命令和真实输出)。如果你认为等价性不好确认, 请直说。用中文; 报告里不要出现用户名或 home 路径。
