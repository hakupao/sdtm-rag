# PLAN v0.1 审查 (critic, opus, 独立 context) — 2026-11-25

**Verdict: REVISE** (2 CRITICAL / 7 MAJOR / 4 MINOR)。主控已亲自复核 #2 (router.py:256 history 条数无上限; rag.py:1107 原样拼接) 与 #3 (llm_config.py:144 known_model_groups 含 INTERNAL_GROUPS), 属实。

| # | 级别 | 问题 | v0.2 处置 |
|---|---|---|---|
| 1 | CRIT | 1.1 推 main 自动部署, 生产 chroma 仍是绝对路径 → 私有站起不来 | 1.1 兼容新旧 + 新增 1.2 有序切换+回滚演练 |
| 2 | CRIT | 免费题无单次成本上界 (history 条数无限) | 新增 2.2 裁剪+估算+预留计费 |
| 3 | MAJ | 内部组 hard/light/fallback 可被访客直选 | 2.3 公开模型白名单 |
| 4 | MAJ | BYOK 请求仍耗服务器 key (embedding/Tavily/light/hard) 未计入 | 2.7 封顶覆盖全部服务器 key 调用; BYOK 独立联网额度 |
| 5 | MAJ | 重新 embedding 非确定, "逐题一致"不现实且无必要 | 1.1 改原地改写 source 元数据; 重 ingest 处判据 ≤1 题 |
| 6 | MAJ | SSRF 解析后校验有 DNS rebinding 窗口 | 公开站不开自定义地址 (Q6); 私有站 IP 钉死+禁重定向 |
| 7 | MAJ | 上传接口解析不可信二进制 | 公开档不注册 /api/validate* |
| 8 | MAJ | 8501 Streamlit 与端口全接口暴露被忽略 | 3.2 公开实例只绑 127.0.0.1, 不起 ui |
| 9 | MAJ | Q5 与隐私模型矛盾 (RAG 历史已公开) | Q5 改写为明确二选一 |
| 10 | MIN | 联网 prompt 注入 | 免费层关联网 + 轮数上限 |
| 11 | MIN | compare 白名单过度设计 | 公开档直接不注册 |
| 12 | MIN | 验收不可验证 | 2.4/3.5/3.6/1.7 加数值判据 |
| 13 | MIN | 双实例容器名冲突 + 容量未核 | 新增 3.1 容量核对 |
| 补 | — | ASGI 体积上限 / WAF / 紧急开关 / provider 账户上限 / 1.6 回滚 | 均已加入 |

勘误: recon 称 `_client_ip` XFF 可伪造 — 仅在 trust_forwarded=True 时 (默认 False); 真问题是无 Cloudflare 感知路径。
