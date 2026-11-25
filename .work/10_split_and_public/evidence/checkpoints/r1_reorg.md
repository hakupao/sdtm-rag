# R1 目录重组 (2026-11-25)

> 状态: **writer 完成, 待独立审查 (规则 D)**。派单: `evidence/subagent_prompts/step_R1_rag_reorg_executor.md`。
> 旧 → 新路径: `docs/history/PATH_MAP.md`。

## 改了什么
- `git mv` 491 文件: `scripts/tests/`→`tests/`; `evidence/**`→`docs/evidence/**`; 仓根 `failures/`→`docs/evidence/failures/`;
  仓根 `PLAN_*`+`docs/superpowers/plans`→`docs/plans/` (specs→`docs/plans/specs/`); `RETROSPECTIVE_*`→`docs/retrospectives/`;
  `DESIGN_*`/`SP1_*`/`SP2_*`/`KG_*`→`docs/design/`; `DEPLOY_PLAN.md`→`docs/history/`; `kg_viewer.html`→`viewer/dist/`;
  `_progress_*.json` (实为已跟踪, 非派单所说未跟踪; oidscan CLEAN)→`docs/history/progress/`。
- 红线闸: ALLOWLIST 键 `scripts/tests/…`→`tests/…`; DEFAULT_TARGETS 去 `evidence` (已在 `docs` 内) 加 `tests` (扫描面不缩)。
- 代码: tests `parents[2]`→`[1]`、`scripts.tests.`→`tests.`、probe `.mjs` 相对路径; eval/scripts 默认输出 → `docs/evidence/…`;
  `build_kg_viewer` 输出 `viewer/dist/` (+ `.gitignore` `!viewer/dist/`); pyproject testpaths + license MIT。
- 文档: README.md (英) / README_CN.md / LICENSE / `docs/architecture.md` 新写; CLAUDE.md 改路径 + 路由词 + B 仓收尾清单。

## 闸 (全部本机, cwd = 仓根)
| # | 命令 | 结果 |
|---|---|---|
| 1 | `.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs` | 2609 passed / 2 skipped (playwright ×2) — 与 HEAD 前基线逐数一致 |
| 2a | `.venv/bin/python -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output .work/10_split_and_public/evidence/checkpoints/r1_runs/cdisc140.json` | 0.9917; 对 `p0_runs/cdisc140.json`: 140/140 recall 同, hits/misses 同, top5 同 |
| 2b | study 48q (命令同 CLAUDE.md, 输出 `data/study/st01/eval/runs/split10_r1/study48.json`, gitignored) | 0.875; 51/51 逐题 recall 同 P0。top5 有 3 题与 P0 不同 —— 改动前 (8ad678b worktree) 复跑与 P0 也差 2 题, 同树连跑两次互差: 既有排序抖动, 非本次引入 |
| 3 | `.venv/bin/python scripts/oidscan_evidence.py` (默认面) + `git ls-files` 全量 | 见下方 |
| 6 | 相对链接检查 (tracked .md) | 改前 17 链 10 断 (README 3 + 历史 7); 改后见下方 |
| — | `node --test webchat/tests/*.test.mjs` | 73/73 |
| — | `scripts/build_kg_viewer.py` 重生成 | `git diff --stat viewer/dist/kg_viewer.html` 空 |
| — | 红线闸变异 (规则 5) | 删 DEFAULT_TARGETS 的 tests → `test_default_targets_include_source_trees` 红; ALLOWLIST 键改回旧路径 → `tests/test_build_field_cards.py:204` 报命中; 还原后 47/47 + CLEAN |

## 已知
- pre-commit hook 只扫 `--diff-filter=ACM`: 改名提交 (R) 不扫, 改名+改内容也不扫 (既有行为, 本次未改)。全仓审计靠闸 3。
- workflow 路径过滤不含 `tests/**` (tests 不进镜像): 只改 tests 的 push 不跑 CI。
- 历史文档正文裸路径未改写 (按 PATH_MAP 换算); `docs/RULES.md` 自述沿用 monorepo 路径写法, 亦未改。
