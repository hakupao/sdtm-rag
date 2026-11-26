# P3.3 公开 CDISC-only chroma + 两实例并跑 (2026-11-26)

用户 2026-11-26 授权: 在 VM 建公开数据根 / .env, ingest, 试跑公开容器; 模型用 Anthropic, 选便宜的。

## 配置 (VM)

- `/opt/sdtm-rag-public/` root 700, `.env` root 600。键 (不含值): ANTHROPIC_API_KEY, OPENAI_API_KEY (embedding 必须
  OpenAI `text-embedding-3-small`, 与索引一致; Anthropic 无 embedding), SDTM_RAG_EMBEDDING_MODEL/DIM (拷自私有),
  DEFAULT/HARD/LIGHT/FALLBACK_MODEL = `anthropic/claude-haiku-5-5`, FALLBACK_MAX_OUTPUT_TOKENS=16000,
  SELECTABLE_MODELS = 仅 `haiku-5-5` (max_output_tokens 16000), WEB_SEARCH_ENABLED=false, RERANK_ENABLED=false,
  VISITOR_SECRET (随机 32 字节), QUOTA_TRUSTED_PROXIES=127.0.0.1 (3.4 改 cloudflared 地址; 见 failures/p3_step3.3_attempt_1.md)。
  key 在 VM 内从 `/opt/sdtm-rag/.env` grep 拷贝, 未经对话/日志。
- Haiku 5.5 官方价 $0.10 / $0.50 每 MTok (prompt ≤100K; >100K 为 $0.50 / $2.50), 2026-11-26 核对
  platform.claude.com/docs/en/models/haiku-5-5/overview; litellm 同值。⚠ quota 按 ≤100K 档估, 公开档 history 裁到 2 万字符, 不会超 100K。
  原 Q3 (免费题 = DeepSeek v4-pro) 由用户改为 Anthropic。
- 数据根 `/Volumes/DevSSD/deploy-data/sdtm-rag-public/data`: chroma / meta / quota.sqlite。

## 验收 (命令均在 VM `limactl shell deploy` 内跑, 进入方式见 p3_step3.1_capacity.md)

| 项 | 命令 | 结果 |
|---|---|---|
| ingest | `docker run --rm <数据根 + .env 挂载> <img 099c2c9> sh -c "python -m scripts.ingest --no-backup && python -m scripts.build_meta"` | 4329 chunks, 94.5s, 86.6 MB |
| study 集合 = 0 | `chromadb.PersistentClient('/app/data/chroma').list_collections()` | `[('sdtm_kb_v1', 4329)]` |
| CDISC 140q | `python -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output /p33/p33.json` | recall 0.9917, <1 = q126, q38 — 与基线逐题一致 (差 0) |
| 公开实例启动 | `IMAGE_TAG=<sha> docker compose -f deploy/container/compose.public.yml up -d` | healthy |
| 档位 / 收口 | `docker exec -i sdtm-rag-public-api python -` (urllib) | `/api/info` tier=public, models=[haiku-5-5]; `/openapi.json` `/docs` `/api/ask_compare` `/api/validate-study` 全 404 |
| 真答题 | POST `/api/ask` `{"question":"What is the DM domain in SDTM?","model":"haiku-5-5"}` | 200, model_used=claude-haiku-5-5, 15 sources |
| 新鲜度 | `docker exec sdtm-rag-public-api python -m scripts.check_index_freshness` | OK, rc=0 |
| 无宿主端口 | `docker inspect ... .NetworkSettings.Ports` | `8000/tcp: null`; 网络仅 `sdtm-rag-public` |
| 两实例并跑 | `docker inspect` / `docker stats` / `free -m` | 私有 api healthy (镜像未变); api 468M + public 429M; VM available 4399M |

收尾: 公开实例已 `stop` (未删), 3.4 接隧道时再起。PASS。
