# 独立审查任务书: 守卫用例 `test_this_file_leaves_no_sdtm_rag_env_behind` 的修正 (2026-11-28, 窄范围)

你是独立审查者 (规则 D: 与写这处修改的会话不同的 agent 类型)。只读审查, **不改仓库里的任何文件**; 要做实验就把仓库复制到你自己用 `mktemp -d` 建的临时目录里做 (见「怎么做实验」)。用中文回答。

## 要审的东西
本仓工作区里一处**未提交**的改动, 只涉及一个文件:

```sh
git diff -- tests/test_p3_4_public_https.py        # 就是全部要审的 diff (基于 HEAD = c3c13ee)
```

## 背景事实 (不含结论)
- 这个文件末尾有一条守卫用例 `test_this_file_leaves_no_sdtm_rag_env_behind`, 是上一个提交系列新加的。它要防的事: 文件里有几条用例调用
  `load_dotenv`, 那会绕过 monkeypatch 直接写 `os.environ`; 曾经有一条用例把小写的 `sdtm_rag_quota_trusted_proxies` 留给了后面的测试文件,
  导致 `pytest tests/test_p3_4_public_https.py tests/test_p2_l3_instance.py tests/test_p2_9_public_e2e.py` 59 条失败 (那处泄漏已修:
  `_absent_now_and_after`)。
- HEAD 上的守卫写法: 一个模块级 autouse 夹具在文件开始时取一次 `SDTM_RAG_*` 环境的快照, 守卫用例断言「现在的环境 == 那份快照」。
- HEAD 上观察到的现象: 检出目录里有一个含 `SDTM_RAG_*` 键的 `.env` 时 (`server/config.py` 导入时会 `load_dotenv` 它), 守卫用例失败;
  没有 `.env` 时通过。本文件用到的模块级夹具 `engines` (定义在 `tests/test_p2_l2_integration.py`) 会用它自己的 `MonkeyPatch` 删掉全部
  `SDTM_RAG_` 开头的环境变量, 模块收尾时还原。
- 这次改动把守卫改成: 每条用例前后各取一次快照 (函数级 autouse 夹具), 把有变化的用例记下来, 文件末尾的守卫用例读这份记录。
- 协调方给这次修改定的范围: 只改这一条守卫用例及它的夹具所在的这个测试文件; 不动被测代码, 不动别的测试文件。
- 本仓没有装 pytest-xdist 或乱序插件 (`grep -n "xdist\|randomly" uv.lock` 无命中); CI 的命令是
  `.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs`。

## 请回答的问题
1. **守卫是否仍然有效?** 原来那种泄漏 (把 `_absent_now_and_after(monkeypatch, KEY.lower())` 那一行换回
   `monkeypatch.delenv(KEY.lower(), raising=False)`) 现在还抓不抓得住? 还有没有你能想到的、这个文件里的用例把 `SDTM_RAG_*`
   (不分大小写) 留下或删掉不还原、而新守卫抓不住的写法? 请自己设计变异并实际跑, 不要只读代码下结论。
2. **有没有靠放宽断言变绿?** 新写法相对旧写法, 有没有哪一类原来会红、现在不红的情形 (除了「检出目录里有 `.env`」这个误报)?
   守卫里的三条断言, 各拿掉一条, 分别会让什么漏过去? 有没有哪条是摆设 (拿掉后任何你能构造的问题都照样被别的断言抓住, 或者它永远为真)?
3. **会不会引入新的顺序依赖或新的误报?** 例如: 只选跑一部分用例 (`-k`、指定 node id)、`--lf`、`-x`、同一进程里这个文件被跑两遍、
   别的测试文件 import 了这个模块、夹具建立与收尾的先后 (函数级 autouse 夹具相对 `monkeypatch`、相对模块级 `engines` 的顺序是否真的如
   文档字符串所说)。哪些情形下会误报红、哪些情形下会漏报, 各自是否是改之前就有的。
4. **文档字符串里的说法与实际行为是否一致?** 逐句核对 `_record_sdtm_rag_env` 和守卫用例的文档字符串 (尤其是关于 pytest 夹具建立 / 收尾顺序的那几句、
   「为什么不受本机 `.env` 影响」的解释)。说错、说旧、说大了的都请指出。
5. **失败信息会不会带出不该带的东西?** 检出目录的 `.env` 里可能有密钥; 守卫失败时 pytest 打印的内容里会不会出现环境变量的取值?
6. 其它你认为应该在合并前改的问题 (只限这个 diff)。

## 怎么做实验 (不要在本工作区里改文件, 也不要动本工作区的 `data/`、`.env`)
```sh
T=$(mktemp -d); git archive HEAD | tar -x -C "$T"; cp tests/test_p3_4_public_https.py "$T/tests/"     # 副本 = HEAD + 这次的改动
cd "$T" && <本仓根>/.venv/bin/python -c "import server, tests.test_p3_4_public_https as m; print(server.__file__, m.__file__)"   # 两个路径都必须在 $T 下
<本仓根>/.venv/bin/python -m pytest tests/test_p3_4_public_https.py -q -o addopts="" -p no:cacheprovider
# 「有 .env」的条件: 在 $T 里自己写一个 .env (例如一行 SDTM_RAG_AUTH_ENABLED=false); 不要读、不要复制本工作区的 .env
```
- 副本里没有 `vendor/sdtm-pedia` 的内容和 `data/`; 只跑这个文件和上面那条三文件命令够用。需要全量时说明你没有跑。
- 每做一个变异: 改完先回读确认变异真的打上了, 跑完把文件恢复成变异前的字节再做下一个; 记下 pytest 的 summary 行和失败信息, 不只记条数。
- 仓库里有一份实现者自己的变异脚本 `.work/10_split_and_public/evidence/checkpoints/p3_stageDE2_guard_mutations.py`。你可以读, 但请先自己想变异,
  不要只复跑它; 它本身有没有问题 (判定会不会把「红错了原因」记成通过) 也可以审。

## 输出格式
- 结论: PASS / PASS-with-fixes / FAIL, 一句话理由。
- 逐题回答 1–6, 每个发现标级别 (CRITICAL / HIGH / MEDIUM / LOW / 备注) 并附你实际跑过的命令与输出摘要 (summary 行 + 关键失败信息)。
- 你没能核实的事项单列。

---

## 发出之后的补记 (实现者; 以上是原样发给审查者的任务书, 没有改)
- **「怎么做实验」一节给的条件有一处不成立** (审查者发现): 让审查者在副本里用本仓根的 `.venv` 跑测试。litellm 在导入时会从它的安装位置往上找 `.env`
  (`LITELLM_MODE` 为默认值时), 找到的是本仓根的 `.env`, 于是副本里「没有 `.env`」的条件并不成立; 审查者发现后改设 `LITELLM_MODE=PRODUCTION`。
  发现之前的第一趟运行里, HEAD 版守卫的失败信息把本仓根 `.env` 里几个配置项的取值 (截断的; 审查者说看到的都是路径、数字这类非密钥值)
  显示在了审查者的工具输出里 —— 没有写进任何文件或报告。以后这类任务书: 用副本自带的 venv, 或写明 `LITELLM_MODE=PRODUCTION`。
- 第二轮 (修正送回同一位审查者复核) 的范围: 第一轮之后对同一个文件的改动 (断言 2 改成「每条用例都被记录到」、单独选中时 skip、
  断言 1 的失败信息、两段文档字符串), 以及变异脚本新增的 G10–G13。
- 第三轮 (更窄) 的范围: 第二轮之后的改动 —— 用例标识从用例名换成 node id; 带 `skip` / `skipif` / `xfail(run=False)` 标记的用例不要求被记录夹具看到
  (按标记是否存在判断, 用的是公开接口, 没有采用审查者给的私有 API 写法); 变异脚本的 G14–G17。
- 三轮的结论: 第一轮 PASS-with-fixes (四处小改) → 第二轮 PASS-with-fixes (第一轮建议的「每条用例都被记录到」带进两个问题: 带 skip 类标记的用例误报红、
  按用例名比对有同名盲区) → 第三轮 **PASS, 没有合并前必须改的**。审到的最终文件 sha256 前 16 位 `38b1971a5cfb8954` (= 提交的那一版)。
  逐条意见与处置见 `../checkpoints/p3_stageDE_second_attempt.md`。
