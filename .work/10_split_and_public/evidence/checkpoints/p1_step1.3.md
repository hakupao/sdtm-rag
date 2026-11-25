# P1 step 1.3 抽 B 仓 — PASS-with-fixes (2026-11-25)

writer executor (opus) `subagent_prompts/step_1.3_executor.md`; reviewer code-reviewer (opus) `step_1.3_reviewer.md`; 映射清单 `p1_step1.3_manifest.md`。

- B = `/Volumes/DevSSD/Project/sdtm-rag`, 远端 `https://git.bojiang.org/bojiang/sdtm-rag` (**private**, Actions **已关** — 1.5 修好 workflow 再开); HEAD 5dd6ac1 (f9c4d01 = 33ac656 的重写 + SHA 对照表提交)
- 771 提交 (reviewer 对账: 路径限定 769 + 3 merge − 1 空提交 段3b), 最早 2026-04-16; HEAD 800 文件与 monorepo 映射 **800/800 blob 一致**; 0 个 A 路径 (含全历史 922 路径); 0 tag; 全历史 0 密钥模式、0 `.env`/data/study/chroma
- pytest (B, KB/chroma 用 override 指 monorepo, data/study 软链): 2584 passed / 2 skipped / 19 失败, 19 全部源于软链 (STUDY_DATA_ROOT 未 resolve; git check-ignore 越软链) — 非移动路径导致
- `docs/history/monorepo_commit_map.txt` 保留 filter-repo commit-map (1157 行), 用于换算证据文档里的旧 SHA

## 1.5 输入 (B 侧, reviewer 列)
workflow `sdtm-rag/` 前缀 (触发与 -f); Dockerfile/.dockerignore `COPY sdtm-rag/...`; compose 硬编码 `/Volumes/.../sdtm-rag/{data,.env}`; `.githooks/pre-commit` PY 路径 (fail-closed 会拦全部提交); `oidscan_evidence.py` GIT_ROOT/knowledge_base + `sdtm-rag/` 前缀 allowlist; `gold_semantics_diff.py:51`; 未走 override 的 KB 路径: deploy.sh:19-20, docker-compose.yml:20, eval/error_test_set.py, eval/validation_scenarios.py, eval/prod_wirein/dm2_e2e_run.py, _smoke_batch_b.py; `.gitignore` 的 `data/study/` 不匹配软链; `uv sync --extra dev`; B 自己的 CLAUDE.md/AGENT_GUIDE/PROGRESS; retrospective §4 规则 5-6 复制到 B; 未入库的本地文件 (`.superpowers/sdd/`, dogfood_failures.md, .env, data/, logs/) 按需拷
## 1.6 输入 (A 侧)
删 sdtm-rag/ 后 `.githooks` + core.hooksPath 会拦 A 的所有提交 → 1.6 同步拆掉/改; `tools/git-hooks/` 第二套 hook 待处理
## 顺序修订
1.4 (submodule 钉 A 的 commit) 依赖 1.6b (A 重写历史后 SHA 才稳定) → 实际顺序: [1.6 + 1.6b 准备] ‖ [1.5 非 CI 部分] → 用户确认 force-push → 1.6b 推送 → 1.4 → 1.5 CI 部分 → 切换部署来源 → 1.9
