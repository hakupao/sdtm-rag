# 隧道 + 公开腿合并: 只构建 attempt 1 失败 (Gitea run 214, 2026-11-28)

## 输入
- main = `5556687` (4 个合并 / 整合提交, 都带 `[skip ci]`), 手动派发 `sdtm-rag` 工作流: tag 留空, deploy=false。
- 派发前的本机验证: 本机全量 3542 passed / 0 failed; 深度 1 克隆 + 独立 venv (macOS) 3483 passed / 0 failed。

## 产物
- run 214 / job 455 (`deploy`): checkout success → **测试 failure** → 登录 / 标签 / 构建并推送 / 部署类步骤全部 skipped。job 456 (`deploy_public`) skipped。
- 没有构建镜像, 线上没有任何变化。没有重试。
- CI 测试: **1 failed** / 3482 passed / 61 skipped。失败的是
  `tests/test_kbsync_deploy_public.py::test_abort_first_ends_a_deploy_process_that_is_still_alive`:
  `AssertionError: 编排进程起的子进程还活着: 它会在兜底之后继续动正式容器`; 同时打印
  `deploy-public 进程 <pid> 可能还没有结束（也可能只是没被回收）`。

## 技术判定
- CI 的 job 容器 1 号进程是 `/bin/sleep 3600` (日志: `docker create … entrypoint=["/bin/sleep" "3600"]`), 不回收孤儿进程。
  兜底对整个进程组发信号之后, 子进程已经被结束, 但没人回收, 停在僵尸状态; `kill(pid, 0)` 对僵尸仍然成功, 测试的 `alive()` 就一直返回真。
- 复现 (部署机上的一次性容器, 不联网, 不挂数据): 1 号进程是 `sleep` 时, 被结束的子进程 `kill(0)` 成功、`/proc/<pid>/stat` 状态 `Z`;
  `docker run --init` (1 号进程会回收) 时 `kill(0)` 报不存在。
- 在与 CI 相同的镜像 (`docker.gitea.com/runner-images:ubuntu-latest`, 1 号进程 `/bin/sleep`, 按 workflow 的命令装依赖) 里重跑原测试: 1 failed, 报错相同。
- macOS 上系统会回收孤儿, 所以本机和浅克隆模拟都测不出来。公开腿分支的测试合并前从没有在 Linux runner 里跑过 (workflow 只在 main 上执行)。

## 业务判定
- 测试判断「活着」的方式有问题, 不是兜底没有把进程结束 (子进程确实已经死了)。
- 产品侧的连带现象 (没有改, 记入 `todo_later`): 在这个 runner 上, 真正的 `public-abort` 结束进程组之后, 组里只要有成了僵尸的孤儿,
  `killpg(pgid, 0)` 就一直成功, `_end_process_group` 会等满约 10 秒并打印「可能还没有结束」, 然后照常停机复查。方向安全。
- 之前预判会红的 4 条 (快照两用 2 条、浅克隆取不到基点 2 条) 在这次真实 CI 里都通过。

## 下一 attempt 的输入
- 协调方裁定 (受托代裁): 只改这一条测试 —— `alive()` 里把僵尸 (`/proc/<pid>/stat` 状态 `Z`) 算作已结束; 没有 `/proc` 的系统上判断不了就算「不是僵尸」(行为与改之前相同)。
  同一位独立审查者做窄范围确认 → 提交 (`[skip ci]`) → push → 重新派发只构建 → 整份 CI 测试结果与 run 214 逐条对照。
- 修法的验证 (同一个 runner 镜像): 原测试 1 failed → 修后 1 passed → 变异「只结束组长、不整组结束」后 1 failed → 还原后合并带来的 8 个测试文件 648 passed。
- 没有做成的一项: 想在那个容器里跑完整的 CI 测试命令, 但放进去的是不带 `.git` 的归档, 收集阶段报 2 个错, 那一趟不算数。

## 复跑
```sh
# 取日志 (账号口令取自 git credential, 不写进任何文件)
curl -u <账号>:$P https://git.bojiang.org/api/v1/repos/bojiang/sdtm-rag/actions/runs/214/jobs
curl -u <账号>:$P https://git.bojiang.org/api/v1/repos/bojiang/sdtm-rag/actions/jobs/455/logs
# runner 镜像里重跑 (在 VM 内; 仓库经标准输入送进容器)
sudo docker run -d --name sdtm-rag-citest --entrypoint /bin/sleep docker.gitea.com/runner-images:ubuntu-latest 3600
git archive 5556687 | <ssh 到 VM> sudo docker exec -i sdtm-rag-citest sh -c 'mkdir -p /w && tar -x -C /w'
sudo docker exec sdtm-rag-citest bash -c 'cd /w && curl -LsSf https://astral.sh/uv/0.11.17/install.sh | sh; export PATH=$HOME/.local/bin:$PATH; uv sync --frozen --extra dev;
  .venv/bin/python -m pytest tests/test_kbsync_deploy_public.py -q -o addopts="" -p no:cacheprovider -k abort_first_ends'
sudo docker rm -f sdtm-rag-citest
```
