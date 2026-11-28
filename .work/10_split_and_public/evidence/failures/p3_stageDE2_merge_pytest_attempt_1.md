# 阶段 D / E 第二次, 第一段: 合并后主仓全量测试 attempt 1 —— 1 failed (2026-11-28)

完整记录在 `../checkpoints/p3_stageDE_second_attempt.md`「合并后才红的 1 条测试」; 这里是规则 B 的归档。

## 输入
- 本地 main 快进到 `c3c13ee` (分支 `hakupao/public-price-pin` 的 12 个提交), 还没有 push; origin/main = `45fc1c6`。
- 主仓文件夹 (有本机 `.env`, 里面 18 个 `SDTM_RAG_` 键; 有 `data/`): `.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs -p no:cacheprovider`。
- 判据 (任务书): 0 failed。

## 产物
- `1 failed, 3700 passed, 2 skipped, 3 deselected` (104 秒)。失败: `tests/test_p3_4_public_https.py::test_this_file_leaves_no_sdtm_rag_env_behind`,
  `AssertionError: assert {} == {…}` (右边是 18 个键)。单独跑这个文件同样 `1 failed, 46 passed`。
- 同一个提交在深度 1 的克隆 + 独立 venv (没有 `.env`、没有 `data/`) 里: `3642 passed, 61 skipped`, 0 failed。

## 技术判定
- 守卫用例拿「模块级夹具在文件开始时取的一次快照」和「用例里看到的环境」比。模块级夹具 `engines` 在两者之间用自己的 `MonkeyPatch` 删掉全部 `SDTM_RAG_*`, 模块收尾时还原。
  检出目录的 `.env` 里有这类键时 (`server/config.py` 导入时 `load_dotenv`; litellm 在默认模式下也会读), 快照里有、用例里没有 → 必红; 没有任何用例真的留下东西
  (逐条看环境键数: 第一条用到 `engines` 的用例 18 → 0, 最后一条之后 0 → 18)。
- 对照实验 (临时目录的深度 1 克隆): 没有 `.env` → `47 passed`; 放一个只含一行 `SDTM_RAG_AUTH_ENABLED=false` 的 `.env` → 同一条红; 删掉 → `47 passed`。
- 是测试自身的缺陷 (成因: 基准与观测不在同一层), 不是被测代码的问题。分支只在没有 `.env` 的检出里跑过, 所以没有暴露。

## 业务判定
- 对镜像、CI、线上都没有影响 (`tests/` 不进镜像; CI 的条件下 0 failed)。但主仓文件夹里 CLAUDE.md 写的那条测试命令会一直是红的, 「主仓全量 0 failed」这条判据不满足。
- 停在 push 之前, 问了协调方。没有 push, 没有派发任何运行。

## 下一 attempt 的输入
- 协调方 (bot) 的决定: 先修再 push, 由本会话修, 只改这一条守卫用例及它的夹具所在的测试文件; 变异验证 (把原泄漏放回去必红、拿掉断言必失效); 三种条件 + 一行 `.env` 都要绿; 独立审查通过后再 push。
- 结果: 提交 `66cb55d` (函数级逐条用例比较前后环境); 主仓全量 `3701 passed / 0 failed / 2 skipped`; 独立审查三轮, 最终 PASS。见 checkpoint。
- 留下的经验 (已记入 `_progress.json` 的 `todo_later`): 涉及环境变量的测试, 合并前要在带本机 `.env` 的检出里也跑一遍。

## 复跑
```sh
# 在 c3c13ee 的副本里复现 (不要在工作区里切文件): 深度 1 的克隆 + 独立 venv, 放 / 不放一行 .env
T=<临时目录>; git clone -q --depth 1 --no-tags file://<本仓根> $T/c && cd $T/c && git fetch -q --depth 1 origin c3c13ee && git checkout -q FETCH_HEAD \
  && git submodule update -q --init --depth 1 && uv sync --extra dev --frozen
env -u VIRTUAL_ENV .venv/bin/python -m pytest tests/test_p3_4_public_https.py -q -o addopts="" -p no:cacheprovider      # 47 passed
printf 'SDTM_RAG_AUTH_ENABLED=false\n' > .env
env -u VIRTUAL_ENV .venv/bin/python -m pytest tests/test_p3_4_public_https.py -q -o addopts="" -p no:cacheprovider      # 1 failed, 46 passed
rm .env
```
