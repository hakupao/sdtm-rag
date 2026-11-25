# sdtm-rag

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.11-blue.svg)](pyproject.toml)
[![Knowledge base](https://img.shields.io/badge/knowledge%20base-sdtm--pedia-green.svg)](https://github.com/hakupao/sdtm-pedia)

**CDISC SDTM 标准问答服务：混合检索 + 结构化知识图谱 + 答后确定性校验，回答有出处可查。**

[English](README.md)

## 这是什么

sdtm-rag 是一个面向 CDISC SDTM（Study Data Tabulation Model，研究数据制表模型）的检索增强问答（RAG）服务。语料是 [hakupao/sdtm-pedia](https://github.com/hakupao/sdtm-pedia) 仓库里的 Markdown 知识库，覆盖 63 个 domain、受控术语、模型概念和实施指南各章。本仓把这个知识库作为 git submodule 固定在 `vendor/sdtm-pedia`。

在普通 RAG 的基础上，本服务还做了三件事：用同一份知识库构建结构化知识图谱（`data/meta/meta.yaml`）；对向量检索容易漏掉的几类问题，用确定性规则直接查找；回答生成后再做一轮确定性校验。服务还可以在 CDISC 语料之外，再挂一套私有的研究语料（EDC 表单和研究文档）。这部分数据从不进 git。

## 功能

下面每项功能都对应一个模块，模块名写在该项后面。

- **混合检索**：Chroma 向量检索（OpenAI `text-embedding-3-small`）和 BM25（`bm25s`）检索同一批 chunk，结果用 RRF 融合（`server/rag.py`）。
- **结构化直查**：遇到 CT 编码、码表、变量与 domain 关系这几类问题时，直接从 `meta.yaml` 查出结果（`server/structured_lookup.py`）。
- **联邦路由**：由 LLM 判断该查哪个语料（CDISC、研究语料或两者都查），再用确定性信号纠正；判断出错时按“两者都查”处理（`server/federation.py`）。
- **答案护栏**：
  - 计数闸：回答里的数字与图谱计数矛盾时，在回答后追加更正（`server/grounding.py`）；
  - 研读包答案闸：核对回答里的 OID 和覆盖情况，不通过就重新回答一次（`server/dossier_gate.py`）；
  - 离线 CT 编码溯源检查（`eval/prod_wirein/check_code_grounding.py`）。
- **多模型切换，回退如实显示**：用户在界面上选模型；如果实际由备用模型回答，界面会明确标出（`server/llm_config.py`，模型清单见 `server/config.py` 的 `selectable_models`）。
- **自动续写**：回答达到输出 token 上限时，服务端自动续写；仍被截断的，界面上会标出来（`server/router.py`）。
- **联网参考**：可选，让模型调用 Tavily 搜索，轮数有上限；搜索失败时界面会显示状态（`server/web_search.py`）。
- **知识图谱工具**：
  - 上传研究数据集后做跨 domain 校验，结果只作提示（`server/graph_validator.py`，`POST /api/validate-study`）；
  - 离线单文件 KG 查看器（源码在 `viewer/`，生成到 `viewer/dist/kg_viewer.html`）。
- **评测工具**：用标准题集评测，可以只评检索（不调用 LLM 回答），也可以用 LLM 当裁判评回答（`eval/run_eval.py`）。
- **共享部署加固**：可选的共享口令登录和限流（默认关闭），以及 CSP 等安全响应头（默认开启）（`server/auth.py`）。

## 架构

```
webchat/ ──SSE──▶ FastAPI (server/router.py)
                    ├─ 联邦路由: 查 CDISC / 研究语料 / 两者
                    ├─ 混合检索 (Chroma + BM25) + 结构化直查
                    ├─ LiteLLM Router (可选模型、回退、可选联网工具)
                    └─ 答后校验 ──▶ 流式返回答案 + 出处
```

完整的请求流程和 Mermaid 图见 [docs/architecture.md](docs/architecture.md)（英文）。

## 快速开始

需要：Python 3.11 及以上、[uv](https://docs.astral.sh/uv/)、一个 OpenAI API key（用于生成向量），以及回答模型用的 Anthropic API key（DeepSeek key 可选，仅作回退，见 `.env.example`）。

```bash
git clone --recurse-submodules --shallow-submodules https://github.com/hakupao/sdtm-rag.git
cd sdtm-rag                      # 已有 clone 的话: git submodule update --init --depth 1
uv sync --extra dev
cp .env.example .env             # 填 OPENAI_API_KEY 和 ANTHROPIC_API_KEY (DEEPSEEK_API_KEY 可选, 仅作回退)

# 用知识库建 Chroma 索引 (调用 OpenAI 生成向量, 写到 data/chroma/)
.venv/bin/python scripts/ingest.py

# 启动 API 和聊天界面。研究语料是私有数据, 需要把相关功能关掉:
SDTM_RAG_FEDERATION_ENABLED=false SDTM_RAG_DOSSIER_ENABLED=false \
  .venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000
# 浏览器打开 http://127.0.0.1:8000
```

测试（与 CI 相同的命令）：

```bash
.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs
node --test webchat/tests/*.test.mjs
```

## 评测

下表的数字都出自本仓的证据文件，每项都附了复现命令。

| 指标 | 结果 | 复现命令 |
|---|---|---|
| CDISC 题集 140 题，只评检索，出处召回率（source recall） | **0.9917**（未达 1.0 的是 q126、q38） | `.venv/bin/python -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output <out.json>` |
| 私有研究题集 48 题，只评检索，出处召回率 | **0.875**（需要本机的研究数据，不在 git 里） | `.venv/bin/python -m eval.run_eval data/study/st01/eval/test_set_study_v2.yml --retrieval-only --hybrid --study-lookup --collection study_st01 --kb-root data/study/st01/cards --output <out.json>` |
| 单元测试（`-m "not slow"`） | 2609 通过，2 跳过（都需要 playwright） | `.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs` |

证据：[p0_baseline.md](.work/10_split_and_public/evidence/checkpoints/p0_baseline.md) 是 2026-11-25 冻结的基线；[r1_reorg.md](.work/10_split_and_public/evidence/checkpoints/r1_reorg.md) 记录了目录重组后的复跑结果：逐题召回率与基线一致，测试数即上表数字。只评检索时不调用 LLM 回答，只需要向量模型的 key。q126 是已记录的永久局限（[s4_full_eval_closure.md](docs/evidence/checkpoints/s4_full_eval_closure.md)）。

设计文档、计划、复盘和全部证据都在 [docs/](docs/) 下。

## 部署

生产环境以容器方式运行（`deploy/container/`）。推送到 `main` 且改动涉及运行时路径时，CI 会依次测试、构建、部署和健康检查；健康检查不通过时自动回滚。具体步骤和回滚方法见 [deploy/README.md](deploy/README.md)。

## 现状与计划

- **现在**：作为私有服务在公司局域网内运行。本仓于 2026-11 从 sdtm-pedia 单体仓拆出，当前进度见 `docs/PROGRESS.md`。
- **计划中（P2）**：公开演示站，包括按访客和全站计的额度、用户自带 API key（BYOK），以及更多回答模型提供商。这些都还没有实现。

## 目录结构

| 路径 | 内容 |
|---|---|
| `server/` | FastAPI 应用：路由、检索、LLM 配置、校验闸、数据集校验 |
| `webchat/` | 聊天界面（静态文件，由 API 直接提供） |
| `ui/` | Streamlit 调试界面 |
| `scripts/` | 建索引、构建 KG、研究数据流水线、红线扫描 |
| `eval/` | 题集和评测工具 |
| `tests/` | pytest 测试 |
| `viewer/` | KG 查看器源码和生成的 `dist/kg_viewer.html` |
| `deploy/` | 容器、compose、部署手册 |
| `docs/` | 架构、设计、计划、复盘、证据、历史资料 |
| `vendor/sdtm-pedia` | 知识库（git submodule） |

## 许可证

[MIT](LICENSE) © 2026 hakupao。知识库内容另有仓库和使用条款：[hakupao/sdtm-pedia](https://github.com/hakupao/sdtm-pedia)。
