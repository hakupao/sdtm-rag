# 窄范围确认: 一条只在 Linux runner 里才红的测试的修正 (2026-11-28)

接上一份任务书 `review_tunnel_leg_merge.md` (同一位审查者)。只读, 不改工作目录, 不 push, 不碰部署机。只看下面这一处改动。

## 事实

- 上一轮审过的 4 个提交已经 push (main = `5556687`)。手动派发的「只构建」(Gitea run 214) 在测试步骤失败: 1 failed / 3482 passed / 61 skipped。
  失败的是 `tests/test_kbsync_deploy_public.py::test_abort_first_ends_a_deploy_process_that_is_still_alive`, 报
  `AssertionError: 编排进程起的子进程还活着: 它会在兜底之后继续动正式容器`。之前修的 4 条在真实 CI 里都通过。
- CI 的 job 容器 1 号进程是 `/bin/sleep 3600` (run 214 日志里的 `docker create … entrypoint=["/bin/sleep" "3600"]`), 不回收孤儿进程。
- 待审的改动在工作目录里, 还没有提交: `git diff -- tests/test_kbsync_deploy_public.py` (只有这一个文件, +8 行)。
  做法: 测试里判断「子进程还活着」的 `alive()` 增加一个 `zombie()` 判断 —— `/proc/<pid>/stat` 里的状态是 `Z` 就算已经结束。
  产品代码 (`deploy/kbsync/kbsync.py` 的 `_end_process_group` / `public_abort`) 没有改。

## 写的人做的三组实验 (在部署机的一次性容器里: 与 CI 相同的镜像 `docker.gitea.com/runner-images:ubuntu-latest`, 1 号进程 `/bin/sleep`, 按 workflow 的命令装 uv 与依赖)

| 组 | 做法 | 结果 |
|---|---|---|
| 机制 | 最小脚本: 新会话里起「组长 + 子进程」, `killpg(SIGTERM)`, 等组长退出, 再看子进程 | 1 号进程是 `sleep` 时: `kill(pid, 0)` 成功, `/proc/<pid>/stat` 状态 `Z`; `docker run --init` 时: `kill(pid, 0)` 报不存在 |
| 原测试 | `5556687` 的测试文件, `-k abort_first_ends` | `1 failed`, 报错与 run 214 相同 |
| 修后 | 换上工作目录里的测试文件 (容器内外 sha256 相同) | `1 passed` |
| 变异 | `kbsync.py` 里 `whole = pgid == pid and pgid != os.getpgrp()` 改成 `whole = False` (只结束组长, 不整组结束; 改完用 `cmp` 确认文件变了, 1 处) | 修后的测试 `1 failed`, 报错同上 (子进程真的还在跑) |
| 还原 | `kbsync.py` 还原 (sha256 与仓库相同), 合并带来的 8 个测试文件 | `648 passed` |

这些结果请当作线索, 不要直接采信; 你没法进那个容器, 但可以读代码推理, 也可以在本机 (macOS, 没有 `/proc`) 跑这个测试文件。

## 请确认并明确回答

1. **检出能力有没有被削弱**: 这条测试要抓的缺陷是「兜底之后, 编排进程起的子进程还在运行, 会继续动正式容器」。把僵尸算作已结束之后:
   - 有没有哪种「子进程实际上还在运行 (或还能继续执行)」的情形, 会被 `zombie()` 误判成已结束? (例如: 读 `/proc/<pid>/stat` 的解析在进程名含 `)` 或空格时会不会取错字段; pid 被复用; 多线程进程的主线程退出后的状态; 状态 `X` / `T` / `t` 等。)
   - 上面那个变异够不够说明问题, 还缺哪个方向?
2. **对非 Linux 平台安全**: 没有 `/proc` 的系统 (本机 macOS) 上, `zombie()` 会不会报错; 会不会把活着的进程误判为已结束 (即让测试在 macOS 上变成永远通过)。请在本机实际验证一次, 例如在仓库的**副本**里做同一个变异 (`whole = False`), 看 macOS 上这条测试是否仍然变红。
3. 这处改动有没有别的问题 (例如 `rsplit(")", 1)` 的 `IndexError` 是否都被接住, 5 秒等待的语义有没有变)。

可以运行: `git` 只读命令; `.venv/bin/python -m pytest tests/test_kbsync_deploy_public.py -q -o addopts="" -p no:cacheprovider` (在工作目录里只跑这个文件可以; 变异在临时目录的副本里做, 用完删除)。

## 输出
结论 (PASS / PASS-with-fixes / FAIL) + 对上面 1、2、3 的逐条回答 (附你运行的命令和真实输出) + 你没法确认的部分。用中文。报告里不要出现用户名或 home 路径。
