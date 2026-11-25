# sdtm-rag

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.11-blue.svg)](pyproject.toml)
[![Knowledge base](https://img.shields.io/badge/knowledge%20base-sdtm--pedia-green.svg)](https://github.com/hakupao/sdtm-pedia)

**Grounded Q&A over the CDISC SDTM standard: hybrid retrieval, a structured knowledge graph, and deterministic answer gates.**

[中文版](README_CN.md)

## What it is

sdtm-rag is a retrieval-augmented question-answering service for CDISC SDTM (Study Data Tabulation Model). Its corpus is the Markdown knowledge base in [hakupao/sdtm-pedia](https://github.com/hakupao/sdtm-pedia), which covers 63 domains, controlled terminology, model concepts and implementation-guide chapters. This repo pins that knowledge base as the git submodule `vendor/sdtm-pedia`.

On top of plain RAG it adds a structured knowledge graph built from the same knowledge base (`data/meta/meta.yaml`), deterministic lookups for query types that embeddings miss, and gates that check answers after generation. It can also serve a second, private study corpus (EDC forms and study documents) next to the CDISC corpus. That data never enters git.

## Features

Each feature below is implemented in the module named next to it.

- **Hybrid retrieval**: Chroma dense search (OpenAI `text-embedding-3-small`) plus BM25 (`bm25s`) over the same chunks, fused with RRF (`server/rag.py`).
- **Structured lookup**: deterministic hits from `meta.yaml` for CT-code, codelist and variable-to-domain questions (`server/structured_lookup.py`).
- **Federated corpus routing**: an LLM picks the corpus (CDISC, study, or both), corrected by deterministic signals; errors fall back to "both" (`server/federation.py`).
- **Answer guardrails**:
  - a counting gate that appends a correction when an answer contradicts the graph counts (`server/grounding.py`);
  - a study-dossier answer gate that checks OIDs and coverage and regenerates once on failure (`server/dossier_gate.py`);
  - an offline CT-code grounding checker (`eval/prod_wirein/check_code_grounding.py`).
- **Multi-model selection with honest fallback**: you pick the model in the UI; when a fallback model answers instead, the UI says so (`server/llm_config.py`, `selectable_models` in `server/config.py`).
- **Auto-continue**: when an answer hits the output-token limit, the server continues it automatically, and any truncation that remains is shown in the UI (`server/router.py`).
- **Web reference channel**: optional Tavily search as a model tool, with a bounded number of rounds and visible failure status (`server/web_search.py`).
- **Knowledge graph tools**:
  - an advisory cross-domain validator for uploaded study datasets (`server/graph_validator.py`, `POST /api/validate-study`);
  - an offline single-file KG viewer (`viewer/` → `viewer/dist/kg_viewer.html`).
- **Evaluation harness**: gold question sets with retrieval-only scoring (no LLM answer calls) and LLM-judge modes (`eval/run_eval.py`).
- **Sharing hardening**: an optional shared-password login gate and rate limit (off by default), plus security headers such as CSP (on by default) (`server/auth.py`).

## Architecture

```
webchat/ ──SSE──▶ FastAPI (server/router.py)
                    ├─ federation: route to CDISC / study / both
                    ├─ hybrid retrieval (Chroma + BM25) + structured lookup
                    ├─ LiteLLM Router (selectable models, fallbacks, optional web tool)
                    └─ post-answer gates ──▶ streamed answer + provenance
```

Full request flow with a Mermaid diagram: [docs/architecture.md](docs/architecture.md).

## Quickstart

Requirements: Python ≥ 3.11, [uv](https://docs.astral.sh/uv/), an OpenAI API key for embeddings, and an Anthropic API key for the answer models (a DeepSeek key is optional and only used as the fallback; see `.env.example`).

```bash
git clone --recurse-submodules --shallow-submodules https://github.com/hakupao/sdtm-rag.git
cd sdtm-rag                      # in an existing clone: git submodule update --init --depth 1
uv sync --extra dev
cp .env.example .env             # fill OPENAI_API_KEY + ANTHROPIC_API_KEY (DEEPSEEK_API_KEY optional: fallback only)

# Build the Chroma index from the knowledge base (OpenAI embeddings, writes data/chroma/)
.venv/bin/python scripts/ingest.py

# Run the API + chat UI. The study corpus is private, so switch its features off:
SDTM_RAG_FEDERATION_ENABLED=false SDTM_RAG_DOSSIER_ENABLED=false \
  .venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000
```

Tests (the same command CI runs):

```bash
.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs
node --test webchat/tests/*.test.mjs
```

## Evaluation

Every number below comes from an evidence file in this repo and has a command to reproduce it.

| Measure | Result | Reproduce |
|---|---|---|
| CDISC gold set, 140 questions, retrieval-only source recall | **0.9917** (below 1.0: q126, q38) | `.venv/bin/python -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output <out.json>` |
| Private study gold set, 48 questions, retrieval-only source recall | **0.875** (needs the gitignored study data) | `.venv/bin/python -m eval.run_eval data/study/st01/eval/test_set_study_v2.yml --retrieval-only --hybrid --study-lookup --collection study_st01 --kb-root data/study/st01/cards --output <out.json>` |
| Unit tests (`-m "not slow"`) | With local `data/`: 2610 passed, 2 skipped (both need playwright). Fresh clone / CI (no `data/`): 2551 passed, 61 skipped (the `local_data` tests skip). Measured at `dcdee7f` | `.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs` |

Evidence: [p0_baseline.md](.work/10_split_and_public/evidence/checkpoints/p0_baseline.md) is the frozen baseline from 2026-11-25. [r1_reorg.md](.work/10_split_and_public/evidence/checkpoints/r1_reorg.md) records the re-run after the repo reorganization: identical per-question recall, and the test count above. Retrieval-only mode makes no LLM answer calls; it only needs the embedding key. q126 is a documented permanent limit ([s4_full_eval_closure.md](docs/evidence/checkpoints/s4_full_eval_closure.md)).

Design notes, plans, retrospectives and the full evidence trail are under [docs/](docs/).

## Deployment

Production runs as a container (`deploy/container/`). On pushes to `main` that touch runtime paths, CI tests, builds, deploys and health-checks the service, and rolls it back automatically if the check fails. Procedure and rollback: [deploy/README.md](deploy/README.md).

## Status and roadmap

- **Now**: running as a private, LAN-internal service. The repo was split out of the sdtm-pedia monorepo in 2026-11; see `docs/PROGRESS.md`.
- **Planned (P2)**: a public demo instance with per-visitor and site-wide quotas, bring-your-own-key (BYOK), and more answer-model providers. None of this is implemented yet.

## Repository layout

| Path | Contents |
|---|---|
| `server/` | FastAPI app: routing, retrieval, LLM config, gates, validators |
| `webchat/` | Chat UI (static, served by the API) |
| `ui/` | Streamlit debug UI |
| `scripts/` | Ingest, KG build, study pipeline, red-line scanner |
| `eval/` | Gold sets and evaluation harness |
| `tests/` | pytest suite |
| `viewer/` | KG viewer sources and generated `dist/kg_viewer.html` |
| `deploy/` | Container, compose, deploy runbook |
| `docs/` | Architecture, design, plans, retrospectives, evidence, history |
| `vendor/sdtm-pedia` | Knowledge base (git submodule) |

## License

[MIT](LICENSE) © 2026 hakupao. The knowledge base content has its own repository and terms: [hakupao/sdtm-pedia](https://github.com/hakupao/sdtm-pedia).
