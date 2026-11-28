# sdtm-rag — SDTM 知识库 RAG + KG 服务

FastAPI (`server/`) + Chroma + BM25 + Chat UI (`webchat/`) + Streamlit 调试 UI (`ui/`)。CDISC KB = submodule `vendor/sdtm-pedia`
(KB 根 `vendor/sdtm-pedia/knowledge_base`; clone 后 `git submodule update --init --depth 1`)。生产 = mini 虚拟机容器, 见 `deploy/README.md`。
2026-11 从 monorepo `sdtm-pedia/sdtm-rag/` 拆出; 旧路径 → 新路径见 `docs/history/PATH_MAP.md`, 旧 SHA 用 `docs/history/monorepo_commit_map.txt`。

## Session Startup

1. `docs/PROGRESS.md` — 唯一当前状态源
2. `docs/RULES.md` — 规则 5-6 (红线改动变异验证 / 闸失效按成因选对策)
3. 按任务读 Key Paths 里对应文档; 动部署先读 `deploy/README.md`; 架构总览 `docs/architecture.md`

然后向用户汇报: 当前状态、未决问题、建议下一步。

## 跨会话路由词

| 用户说 | 新会话先做 |
|---|---|
| 「拆仓 继续」 | 读 `.work/10_split_and_public/_progress.json` 的 `next_step`, 再读 PLAN 对应 step |
| 「P2 开始」 | 读 `.work/10_split_and_public/PLAN.md` §2 P2 + §6 并行分线 (先 P2.0 接缝, 再 L1-L4) |
| 「收尾」 | 执行下方收尾清单 |
| 「部署」 | 按 `deploy/README.md`: 只构建 (deploy 取消勾选) → 测试端口验证 → 正式部署 |
| ⚠ 自动部署 | 改 server/ui/webchat/scripts/eval/README.md/pyproject 等运行时路径的 push 即部署; 只改文档/测试的提交加 `[skip ci]` |
| 「KB 更新」 | 等待 Gitea `kb-sync` 对 A 仓新 tag `kb-YYYY.MM.DD` 判定 PASS (每天定时运行, 也可手动 dispatch 指定 `ref`; 过闸的候选 chroma 保留在数据根) → 升级 submodule (`cd vendor/sdtm-pedia && git fetch --depth 1 origin tag <tag> && git checkout <tag>`) → 运行 `.venv/bin/python -m scripts.check_index_freshness`; 结果为 STALE 时在本机运行 `-m scripts.ingest` 和 `-m scripts.build_meta` (meta.yaml 有改动时一并提交) → 运行两条检索闸和 pytest → push (部署时自动换入过闸的 chroma/meta; 没有过闸候选时部署失败, 生产保持不变; 详见 `deploy/README.md`)。公开站 (变量 `SDTM_RAG_PUBLIC_DEPLOY`, 默认关): 开着时 kb-sync 的 `public` 腿另建公开候选, 部署时 `deploy_public` 先用临时容器验收再换 (README「公开实例」) |

## 规则 (每条必守)

- **A 语义抽检**: 压缩/改写 >50% 的步骤做 N 样本独立抽检 (N 预登记), 结果留 evidence。
- **B 失败归档不删**: 失败 attempt 写 `docs/evidence/failures/<step>_attempt_N.md` (输入/产物/判定/下一步)。
- **C Retro**: 多 step 单元收尾写 `docs/retrospectives/RETROSPECTIVE_<unit>.md` (保留做法 / 缺口 / 关键决策)。
- **D 审阅隔离**: writer 与 reviewer 不同 agent 类型、不同 session; 自审 = 无审。
- **实测附命令**: 写"实测"必附可复跑命令。
- **红线**: 真实研究 OID / label / 真名不进 git (含代码、测试、证据、提交信息)。研究数据只在 gitignored `data/study/`。
- **新文档位置**: 设计 `docs/design/`, 计划/spec `docs/plans/`, 证据 `docs/evidence/`, 历史 `docs/history/`; 仓根不放文档。

## 红线 pre-commit 闸

`git config core.hooksPath .githooks` (每个 clone 一次; 或 `sh .githooks/install.sh`)。hook 用 `.venv/bin/python -m scripts.precommit_oidscan`
扫暂存文件 (A/C/M/R, 改名含纯改名也扫); venv / catalog / KB 任一缺失 → 拦下 (fail-closed)。全仓审计: 不带参数跑 `scripts/oidscan_evidence.py`。
命中先 `scripts/oidscan_evidence.py <文件> --show-values` 本机排查; 撞车加 ALLOWLIST 并附理由。禁止 `--no-verify`。

## 测试 / 评测

```bash
git submodule update --init --depth 1 && uv sync --extra dev
.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs      # CI 同款 (tests/); -rs 列出 skip 原因
.venv/bin/python -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output <out>   # CDISC 140q
.venv/bin/python -m eval.run_eval data/study/st01/eval/test_set_study_v2.yml --retrieval-only --hybrid --study-lookup \
  --collection study_st01 --kb-root data/study/st01/cards --output data/study/st01/eval/runs/<tag>/study48.json  # 输出含 OID, 只放 gitignored 处
node --test webchat/tests/*.test.mjs
```

CI 有 KB (submodule) 无 data/: `local_data` 测试 (见 `-rs`) 在 CI skip; 两条检索闸 CI 不跑, 改检索须本机跑。只改 `tests/` 不触发 CI (workflow 路径过滤不含 tests)。
改 `eval/run_eval.py` 判据前后跑 `python -m eval.tests_support.gold_semantics_diff`; study gold 改动跑 `eval/lint_gold.py`。

## Key Paths

| What | Where |
|------|-------|
| 部署 / CI | `deploy/README.md`, `deploy/container/`, `.gitea/workflows/sdtm-rag.yml` |
| 拆仓 + 对外开放 (进行中) | `.work/10_split_and_public/{PLAN.md,_progress.json}` |
| 公开站: 隧道 / 网络隔离 / 上线步骤 (未上线) | `deploy/README.md`「公开实例与隧道」; `deploy/public-net/`; `docs/plans/P3_4_tunnel_{owner_steps,drill}.md` |
| 历史总 PLAN / 检索 TODO / 旧部署规划 | `docs/history/07_rag_kg/`, `docs/history/DEPLOY_PLAN.md` |
| 检索收口 (q126 永久 known limit) | `docs/evidence/checkpoints/{s4_full_eval_closure,d_channel_concept_definition}.md` |
| 答题护栏 + CT 码闸 | `docs/evidence/checkpoints/guardrail_v2_summary.md`; `eval/prod_wirein/check_code_grounding.py` |
| Chat UI + 自动续写 | `webchat/`, `server/router.py`; `docs/design/DESIGN_chat_ui.md` |
| C2R PDF 画面通道 (默认 OFF) | `docs/plans/PLAN_c2r_pdf_bypass.md`; `server/pdf_{context,trigger}.py` |
| KG 路线 / 图校验器 | `docs/design/KG_ROADMAP.md`; `server/graph_validator.py` |
| KG 查看器 (勿手改产物) | `viewer/*` → `scripts/build_kg_viewer.py` → `viewer/dist/kg_viewer.html` |
| study 轨 / golden v2 | `scripts/study/`; `docs/evidence/checkpoints/study_golden_v2.md`; `eval/lint_gold.py` |
| 联邦路由 / study 直查 | `server/{federation,study_lookup}.py`; `docs/evidence/checkpoints/planb_phase*.md` |
| 联网参考 / 多模型单一事实源 | `server/web_search.py`; `server/llm_config.py` (`selectable_models`) |
| DM2 研读包 + 答案闸 | `server/{study_dossier,dossier_gate}.py`; `docs/retrospectives/RETROSPECTIVE_dossier.md` |
| spec / plan / retro | `docs/plans/` (spec 在 `docs/plans/specs/`); `docs/retrospectives/` |

## 收尾 (用户说「收尾」/ wrap up)

1. 看 `git diff` + 新文件; 2. 更新 `docs/PROGRESS.md` (只写当前状态); 3. 拆仓线: 更新 `.work/10_split_and_public/_progress.json`
(+ 同目录 `evidence/trace.jsonl`); 4. 新 key path 才加一行; 剪掉本文件过期状态 (≤ 80 行, 不写进度数字);
5. 过 pre-commit 闸提交; 6. push (origin 双 push URL = Gitea + GitHub; Gitea push main 会触发部署, 先确认路径过滤与 Actions 状态); 7. 一行汇报。
