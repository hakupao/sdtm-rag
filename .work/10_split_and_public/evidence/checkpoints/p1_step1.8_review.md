# P1 step 1.8 整体独立审查 — PASS-with-fixes → fixed (2026-11-25)

- 审查: `oh-my-claudecode:code-reviewer` (opus), 派单 `subagent_prompts/step_1.8_reviewer.md`, 只读。
- 修复: `oh-my-claudecode:executor` (opus), 派单 `subagent_prompts/step_1.8_fix_executor.md`, 提交 dcdee7f / 1eedfc4; 明细 `step_1.8_fix.md`。
- 主会话复核: `tests/test_precommit_oidscan.py tests/test_oidscan_evidence.py` 55 passed; 把过滤改回 ACM → 新测试 1 failed (变异有效), 已还原。
- 全新 clone (修复前 d563a56): `git clone https://github.com/hakupao/sdtm-rag.git && cd sdtm-rag && git submodule update --init --depth 1 && uv sync --frozen --extra dev && .venv/bin/python -m pytest -m "not slow" -q -o addopts=""` → 2550 passed / 61 skipped / 0 failed。

## 审查已验证 (无问题)
B 自立 (parents[N] 均到仓根, KB 全走 vendor/ 或 settings.kb_root); 部署链 (路径过滤 / Dockerfile COPY / dockerignore 一致, 移动的 tests/ docs/ viewer/dist/ 运行时不读; APP_DIR 回滚对新旧镜像都对); submodule 钉 ebf0c8a 是 A 1c0495a 的祖先且 `git diff ebf0c8a 1c0495a -- knowledge_base` 为空; ingest 写 kb_fingerprint, 本地 freshness rc=0; 红线: B 全部 tracked 861 文件 CLEAN, 两仓提交信息 CLEAN, 两仓无密钥; A 仓 `git log --all -- sdtm-rag` / `branches/07_rag_kg` / `.gitea` 全空。

## 发现与处置
| # | 级别 | 内容 | 处置 |
|---|---|---|---|
| 1 | should-fix | pre-commit `--diff-filter=ACM` 漏扫改名+改内容 (R) | ACMR + 变异验证 + 测试 (dcdee7f) |
| 2 | should-fix | r1_reorg.md 状态行过时; _progress R1 两条 | 已改 (1eedfc4) |
| 3 | should-fix | lan-services 引用旧路径 | `~/lan-services` README 已改 (本地 84ff8e3, 未推); Dockerfile:13 注释留到下次 caddy 改动; `/Volumes/DevSSD/mini-home/lan-services` = 无远端老副本, 待用户定 |
| 4 | should-fix | 全仓审计 DEFAULT_TARGETS 不全 | 补 .work/ ui/ webchat/ deploy/ viewer/ .gitea/ + 仓根, 1091 文件 CLEAN (dcdee7f) |
| 5 | nit | README 测试计数只给本机数 | 补 CI/全新 clone 计数 (1eedfc4) |
| 6 | nit | webchat/vendor/README.md 旧路径 | 已改 (1eedfc4) |
| 7 | nit | deploy/deploy.sh + .env.service.template 为 launchd 遗留 | P4 删 (todo_later) |
| 8 | nit | pyproject.toml:12 作者真名 vs LICENSE hakupao | 待用户定 |

## 未决 (非阻断)
- 生产 chroma stamp 是否含 kb_fingerprint (1.2 是改元数据非重灌): 需用户在 mini 上跑 `docker exec sdtm-rag-api python -m scripts.check_index_freshness` (本会话 ssh 被权限拦, 未绕)。
- 重组后首个非 [skip ci] 推送尚未跑过 CI; 生产仍为 ee41a3c → 1.9 前先 build-only → 测试端口。
- A 仓 GitHub `refs/pull/1/head` 仍可达旧历史 — 1.6b 已登记的已知局限。

# P1 phase report

P1 (1.1–1.8 + R1/R2 目录整理) 完成。两仓公开: A `hakupao/sdtm-pedia` (历史重写, 10 tag) / B `hakupao/sdtm-rag` (Gitea 部署 + GitHub 双推)。生产跑 B 镜像 ee41a3c。失败归档 3 份 (1.4 ×1, 1.5 CI ×2)。剩 1.9 KB→RAG 同步 (设计待用户裁定提交方), 之后 P2。
