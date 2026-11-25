# step_00 recon: api_ui_quota — Explore (opus), read-only

Repo: /Volumes/DevSSD/Project/sdtm-pedia/sdtm-rag (FastAPI RAG service + webchat/ frontend + ui/ Streamlit?). Read-only, very thorough. Goal: inform a plan to make the service publicly accessible on the internet (anyone can try) with per-visitor and global usage quotas, optional Cloudflare Turnstile, and a UI settings panel where users enter their own API key (BYOK, stored in browser only) and pick provider/model.

Report with file:line refs:
1. All HTTP endpoints in server/main.py (and routers): method, path, purpose, whether they cost LLM money, whether they should be exposed publicly (e.g. /api/flag writes dogfood_failures.md, /api/validate-study, compare endpoints, admin/debug endpoints, file upload).
2. server/auth.py: what exists (shared password gate, TokenBucketLimiter, fail lockout, sanitize_errors, security headers, trust_forwarded), settings names, defaults, tests. What's missing for daily per-visitor question quotas and global daily cost caps.
3. Is there any token/cost accounting already (usage logging, cost calc, archive/存档 of answers)? Where are answers/logs persisted (files, sqlite)? Any PII/keys that could leak into logs (request bodies logged? headers logged?).
4. webchat/ frontend: structure, framework (vanilla?), how it calls the API (SSE /api/ask_stream), model selector, existing settings UI, localStorage use. Where a BYOK/provider settings panel would go. ui/ (Streamlit) — still used?
5. Study-specific UI/endpoints (study selector, st01) and how a "study disabled" instance would behave (does code fail if data/study missing? config flags federation_enabled/study_lookup_enabled/study_docs_enabled/dossier).
6. CORS, cookie/session, HTTPS assumptions.
Under ~900 words, facts only.
