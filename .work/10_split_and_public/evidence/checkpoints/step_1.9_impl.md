# step 1.9 KB→RAG 同步 — 实现证据 (2026-11-26)

设计 v0.2 见 `p1_step1.9_design.md` 末节。派单: `../subagent_prompts/step_1.9_executor.md`。**未 push / 未 dispatch / 未 ssh。**

## 提交
| commit | 内容 |
|---|---|
| `e395140` | `deploy/kbsync/kbsync.py` + `.gitea/workflows/kb-sync.yml` + `tests/test_kbsync.py` + `scripts/ingest.py --no-backup` |
| `51cba77` | `.gitea/workflows/sdtm-rag.yml` 部署扩展 (KB 指纹对齐 / 换数据 / 失败连数据退回 / `force_data_mismatch`) |
| `689dc38` | deploy/README「KB 同步」+ 回滚; CLAUDE.md「KB 更新」行; 设计 v0.2; 本文件 |
| `3c5a10b` | 审阅修: 候选复制**整个** `meta/` (原只拷 meta.yaml → 换上后丢 `implicit_relations.json`); finish 后 prune 失败不致命 (否则退镜像不退数据); freshness 只在 swap 时跑 (same = 原行为) |

`ingest.py` 备份问题: `backup_existing_chroma` 写 `chroma_dir.parent/chroma_backup_<ts>` = 容器内 `/app/data` (候选设计里只读 → mkdir 崩), 且整份复制 = 磁盘翻倍 → 加 `--no-backup`, kbsync 必带 (候选本身即生产副本)。

## 命令与退出码
| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/test_kbsync.py -q -o addopts=""` (`3c5a10b`) | 26 passed, rc 0 |
| `.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs` (`3c5a10b`) | 2636 passed, 2 skipped (playwright), 0 failed |
| `actionlint -ignore 'undefined variable "gitea"' -ignore SC2034 .gitea/workflows/*.yml` (`3c5a10b`) | rc 0 (SC2034 = 健康检查循环变量 `i`, 改动前已有) |
| `.venv/bin/python - detect --data-root <tmp> --fp <64hex> < deploy/kbsync/kbsync.py` (= `--via` 的 stdin 执行形) | 输出 JSON, rc 0 |
| `.venv/bin/python scripts/oidscan_evidence.py` (无参) | CLEAN |
| `python3 deploy/kbsync/kbsync.py fingerprint --kb-root vendor/sdtm-pedia/knowledge_base` (系统 python 3.9) | `f863e45445a6…` = `scripts.kb_freshness` 结果 |

## 规则 5 变异 (`3c5a10b` 上重跑; 脚本按原文 sha 前置闸, `finally` 还原, 还原后 `git diff --quiet` rc 0 + 测试 rc 0)
| 变异 | 打法 | 目标测试 | 结果 |
|---|---|---|---|
| (a) 闸阈值 | `len(reg) > max_regressions` → `> max_regressions + 1` | `test_gate_two_regressions_fail_and_archive` | 1 failed, `assert 'PASS' == 'FAIL'` (**更正**: 该轮仅跑了这 1 个目标测试; 审阅方全量跑为 2 failed。v3 起变异一律跑整个 `tests/test_kbsync.py`, 见下) |
| (b) 候选指纹断言 | `if got != fp:` → `if False:` | `test_gate_fingerprint_mismatch_…`, `test_candidate_pipeline_old_kb_image_fails` | 2 failed, `assert 'PASS' == 'FAIL'` |
| (c) 非 KB 集合守卫 | `if prod_cols != src_cols:` → `if False:` | `test_deploy_swap_refuses_on_non_kb_collection_mismatch`, `…_missing_non_kb_collection` | 2 failed, `assert 0 == 1` |

## 反例演练测量 (本机, 临时 worktree + KB 副本 + chroma 副本; 仓内 data/ vendor/ 未动; 2 次 re-ingest)
命令 (cwd = `git worktree add --detach <scratch>/wt HEAD`, 拷入 KB / `data/chroma`, `.env` 软链):
`.venv/bin/python -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output <run>.json`;
损坏后 `-m scripts.ingest --no-backup` + `-m scripts.build_meta` 再 eval; 比对用 `kbsync.regressions`。

| 运行 | source recall avg | 相对基线 1 逐题回退 |
|---|---|---|
| 基线 1 / 基线 2 (无改动, 噪声底) | 99.2% / 99.2% | 0 (双向) |
| A: 删 `domains/DM/spec.md` (gold 引用最多: 10 处) | 93.8% | **9** (q02 q08 q135 q20 q43 q45 q92 s01 s03) → gate FAIL |
| B: 删 `VARIABLE_INDEX.md` | — | eval **崩溃** rc 1 (`VARIABLE_INDEX section map 不完整`, 实测) → kbsync 判 `candidate_eval_rc1` FAIL + 归档 (由 `test_candidate_eval_crash_fails_and_archives` 假 docker 覆盖, 非真跑) |

A 的真实产物喂 `kbsync.py gate` (临时数据根): `verdict=FAIL, reason="regressions 9 > 1"`, 候选改名 `chroma_failed_*`/`meta_failed_*`; 之后 `detect`=changed、`predeploy-check`=missing (部署会拦)。
结论: 现实损坏远超 ≤1 阈值; 阈值未调。

## 开放风险 (未端到端验证)
- **docker / workflow 路径全未真跑** (本机无 docker): `--mount` 嵌套只读+可写覆盖、兄弟容器 root 写数据根、Gitea `schedule`、job 镜像里 `python3` 可用性均待首次 dispatch 验证 (stdin 执行形本机已验)。kbsync.py 已确认兼容 python 3.9。
- `meta/implicit_relations.json` (KB 派生, LLM 挖掘, 只给 KG 查看器用, server 不读) kb-sync **不重生成**, 换数据时原样沿用。
- 手动回滚时若 `chroma_prev_*` 存在但非 KB 集合核对不过 → 部署失败, `force_data_mismatch` 救不了 (决定已是 swap); 需人工处理。
- 噪声底只测了 2 遍 (0 差); 生产 VM 上的 embedding 非确定性未测, ≤1 余量仅 1 题。
- 复制生产 chroma 时生产在跑 (sqlite 热拷); 若出现不一致, 基线 eval 会先暴露。
- 被跳过的旧 tag 候选 `chroma_cand_<旧fp>` 与 `chroma_failed_*` 不自动清理, 每份约 260-330M (VM 45G 空余)。
- job 被取消/超时 (非 failure) 时 journal 残留: 下次部署 swap 会拒绝 (fail closed), 需人工 `restore` 或 `finish`。
- 候选 eval 与生产 api/ui 同时占内存 (1536m + 1536m + 512m), VM 总内存未核。
- 正例演练 (A 仓真改一行 → kb-sync → 部署换上) 与生产 dispatch 留给主会话。

## 审阅修复轮 (review: code-reviewer opus, dd903a3..26c18b6 → PASS-with-fixes)

派单 `../subagent_prompts/step_1.9_fix_executor.md`。提交 `c2cdc2c` (修复) + `f9dd61c` (补测试)。

| # | 发现 | 处置 |
|---|---|---|
| 1 | deploy-swap 失败后盲目 `compose start` | 先 `swap-status`; journal 在 → `restore` (失败则保持停止交人工) → 再 start。仅 yaml, 未真跑 |
| 2 | job 取消/超时残留 journal | `predeploy_check` 首判 `journal_pending`; kbcheck 对它一律失败 (same/force 也拦) |
| 3 | 旧测试因错误原因得 SystemExit, journal 闸变异存活 | swap 内重复的 journal 闸删掉, 统一由 predeploy_check 判; 新测试 leftover journal + 合格 chroma_prev → 拒换且 `match="journal_pending"`; 变异 d 已杀 |
| 4 | 非 KB 守卫只比 名+条数 | 加内容摘要 sha256(按 id 排序 [id, document, metadata]); 只输出摘要。本机两份 chroma 副本实测摘要一致 (非 KB 2 个集合) |
| 5 | 闸只有相对判据 | + 题号集合相同, ≥140 题, 候选满分 ≥ 基线−1, 候选 `summary.source_recall_avg` ≥ 0.95 (缺键 = FAIL) |
| 6 | restore 不校验终态 | 终态 (stamp == old_fp, prev 已无, source/live 在) 不符 → 保留 journal, 非零 |
| 7 | image-fp 失败静默 | stderr 打末 5 行 |
| 8 | README 口径 | 改: 失败步打 stderr 末 20 行; force 救不了 swap 决定下的集合核对失败 |
| 9 | kbcheck 失败也会退镜像 | 部署步首行写 `started=true`, 退镜像步加该条件 |
| 10 | 目标镜像 chromadb 读写生产原件 | 集合核对改在 `kbsync_guard_<ts>/` 副本上 (always-copy, 比"版本不同才拷"少一条分支), 原件换入前不被任何 chromadb 打开; marker 记候选镜像 chromadb 版本, predeploy 与目标镜像版本不等则不选该候选 (旧 `chroma_prev` 不做此钉, 见风险) |
| 11 | 本文件变异 (a) 计数 | 已更正 (上表) |

### 重跑 (HEAD `f9dd61c`)
| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/test_kbsync.py -q -o addopts=""` | 39 passed |
| `.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs` | 2649 passed, 2 skipped, 0 failed |
| `actionlint -ignore 'undefined variable "gitea"' -ignore SC2034 .gitea/workflows/*.yml` | rc 0 |
| `.venv/bin/python scripts/oidscan_evidence.py` (无参) | CLEAN |
| 真实产物过新闸: 基线1 vs 基线2 / 基线1 vs 损坏 A | PASS (140 题, 满分 138/138, avg 0.9917) / FAIL (回退 9; 满分 129 < 137; avg 0.9381 < 0.95) |

### 规则 5 变异 (每个跑整个 `tests/test_kbsync.py`; sha 前置闸 + `finally` 还原 + 还原后 `git diff --quiet` rc 0 且测试全绿)
| 变异 | 结果 |
|---|---|
| a 阈值 `> max+1` | 首轮**存活** (满分地板掩护了 2 题回退的旧测试) → 补 `test_gate_two_partial_regressions_fail_on_threshold_alone` (回退在非满分题) → 1 failed, 已杀 |
| b 候选指纹断言 `if False` | 2 failed |
| c 非 KB 守卫 `if False` | 3 failed |
| d journal 闸 (predeploy_check) `if False` | 2 failed |
| e1 题号集合 / e2 ≥140 / e3 满分地板 / e4 avg 地板 | 2 / 1 / 1 / 1 failed |
| f chromadb 钉 `if True` | 1 failed |
| g restore 终态 `if False` | 1 failed |
| h 守卫读原件而非副本 | 4 failed |

### 新增开放风险
- 守卫副本 = 生产 + 候选各一份 (~600M) 临时占盘, 停服务期间拷贝 (停机时间变长)。
- 回滚到 `chroma_prev_*` 不做 chromadb 版本钉 (prev 可能已被更新版 chromadb 迁移过); 依赖健康检查 + freshness 兜底。
- 第 1 / 9 项 yaml 路径与以前一样未真跑。

## 复审修复轮 (re-review PASS-with-fixes) — 提交 `20a2c1e`
| # | 发现 | 处置 |
|---|---|---|
| N1 | restore 失败后退镜像步仍 `compose up PREV` → 旧镜像 + 半换数据 | 新 `kbsync.py journal-state --image` (0 无 / 3 在 / 2 判不出); 退镜像步首判, ≠0 即退出交人工 |
| N2 | `"unknown" == "unknown"` 绕过 chromadb 钉 | 目标版本 `""`/`"unknown"` 一律不选候选 |
| N3 | guard-copy 在 try 外 → 残留副本 | 移入 try (finally 清); prune 顺带清残留 `kbsync_guard_*` |
| N4 | `swap-status | grep` 把 via 失败当"无 journal" | 部署步分支与退数据步都改用 `journal-state`; 2 (判不出) 按未清处理 |
| N5 | detect 不看 journal | 返回 `journal_pending`, kb-sync 响亮失败 |
| N6 | 换数据停机时长 (守卫副本 ~600M) | 未测, **首次真实 swap 时记录停机时长** |

附带风险: 退镜像步现在也依赖 `journal-state` (经目标镜像 `--via`); 该调用判不出时健康检查失败的普通退镜像也会被拦 (fail closed, 需人工)。

### 重跑 (HEAD `20a2c1e`)
| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/test_kbsync.py -q -o addopts=""` | 44 passed |
| `.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs` | 2654 passed, 2 skipped, 0 failed |
| `actionlint -ignore 'undefined variable "gitea"' -ignore SC2034 .gitea/workflows/*.yml` | rc 0 |
| `.venv/bin/python scripts/oidscan_evidence.py` (无参) | CLEAN |

### 变异 (15 个, `PYTHONDONTWRITEBYTECODE=1`, 每个跑整个 test_kbsync.py; 全杀, 还原后 git diff --quiet rc 0 + 44 passed)
a 1 / b 2 / c 3 / d 2 / e1 2 / e2 1 / e3 1 / e4 1 / f 2 / g 1 / **n1 1 / n2 1 / n3 1 / n5 1** / h 4 failed。
⚠ 变异框架自身缺陷 (规则 5 补充第 4 种的变体): 首次不带 `PYTHONDONTWRITEBYTECODE` 时, n1 (`return 3`→`return 0`, **等长**) 还原后测试红 1 次 ——
同秒内等长改写使 `__pycache__` 的 mtime+size 校验失效, 加载了陈旧字节码。等长变异也可能因此**假存活**。对策: 变异一律关字节码缓存并先清 `__pycache__`; 本表为该对策下的重跑结果。
