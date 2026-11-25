# P1 step 1.6b — A 重写历史推送 GitHub (2026-11-25) — PASS

用户确认 (两仓都公开; A 仍推重写版; B 内网信息接受公开)。推送前 verifier (security-reviewer) GO-with-conditions。
- 追平: monorepo `c2d396b..main` 无新提交
- `git push --force-with-lease=refs/heads/main:36c54d9… GH main` → `36c54d9...ebf0c8a (forced update)`; 10 个 tag 各自带 lease 原地强更 (C3)
- 核对: GH main = ebf0c8a; 10 tag SHA 与 a_rewritten_v2 一致; release v1.0/v1.1/v1.4 isDraft=false, 资产名+大小与推送前记录逐一相同; `curl -sI https://sdtm-pedia.pages.dev/zh/` → 200 (Pages 面板构建记录未核, web/ 内容未变)
- C1: monorepo `origin`/`gitea` push URL 均设 `no_push`
- **未做 (按 C2 推迟)**: Gitea `bojiang/sdtm-pedia` 强推 — 待 B 仓接管部署后
- 已知局限: GitHub 上旧提交 (含 192.168.100.24/28/32、bojiang.local) 在 GC 前仍可按 SHA 访问; 彻底清除需 GitHub 支持
