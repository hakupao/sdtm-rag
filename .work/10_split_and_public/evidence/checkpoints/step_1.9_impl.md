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
| (a) 闸阈值 | `len(reg) > max_regressions` → `> max_regressions + 1` | `test_gate_two_regressions_fail_and_archive` | 1 failed, `assert 'PASS' == 'FAIL'` |
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
