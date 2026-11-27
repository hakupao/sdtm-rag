# P3.3 attempt 1 — 公开实例首次启动被拒 (2026-11-26)

- 输入: 镜像 099c2c9, compose.public.yml (分支 p3), `/opt/sdtm-rag-public/.env` 初版 (无 `SDTM_RAG_QUOTA_TRUSTED_PROXIES`)。
- 产物: 容器启动时 `server/auth.py:_install_quota` raise `public tier requires SDTM_RAG_QUOTA_TRUSTED_PROXIES`,
  `restart: unless-stopped` 进入重启循环, 随即 `docker compose stop`。
- 技术判定: 设计内的失效安全 (公开档无可信代理 ⇒ 所有访客都算隧道 IP), 不是缺陷。
- 业务判定: .env 漏项。无隧道阶段先填 `127.0.0.1` (只信任回环, 等于不信任任何代理头)。
- 下一 attempt 输入: .env 追加 `SDTM_RAG_QUOTA_TRUSTED_PROXIES=127.0.0.1` → attempt 2 PASS (见 checkpoints/p3_step3.3.md)。
- 3.4 必做: 改为 cloudflared 容器固定地址 (compose 给 sdtm-rag-public 网络固定子网 + cloudflared 静态 IP)。
