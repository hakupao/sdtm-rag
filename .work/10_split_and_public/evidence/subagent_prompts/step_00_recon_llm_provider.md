# step_00 recon: llm_provider — Explore (opus), read-only

Repo: /Volumes/DevSSD/Project/sdtm-pedia/sdtm-rag (FastAPI RAG service, uses litellm). Read-only investigation, very thorough. Goal: inform a plan to (1) support many LLM answer providers (Anthropic, OpenAI, Google Gemini, DeepSeek, custom OpenAI-compatible base_url) and (2) per-request user-supplied API keys (BYOK) passed from the browser.

Report, with file:line references:
1. Every place an LLM is called (litellm.completion/acompletion, anthropic SDK direct, etc.): server/, scripts/ used at runtime. Which take model/api_key params; where keys come from (env vars, settings).
2. server/llm_config.py: selectable_models, fallback logic (fell_back, merge_reported_model), max_tokens handling. How a model list is defined and exposed to UI.
3. Provider-specific features in use and where: Anthropic prompt caching (cache_control), tool use / web_search tool (server/web_search.py, Tavily?), extended thinking, PDF/document content parts (server/pdf_context.py), study dossier "auto only opus" (server/study_dossier.py), CONTINUE_PROMPT auto-continue in router.py, HyDE / query rewriting / routing LLM calls, judges in compare.py. For each: would it break or degrade on OpenAI/Gemini/DeepSeek?
4. Embeddings: model, where called, whose key; reranker (Cohere?) — these are server-side and cannot be BYOK because the index is fixed; confirm.
5. How hard is threading a per-request api_key + api_base through the call chain (count call sites, any globals/caches keyed by model).
6. Existing tests covering llm_config / fallback (file names, rough count).
Keep the report under ~900 words, facts only, no recommendations padding.
