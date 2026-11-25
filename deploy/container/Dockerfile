# sdtm-rag 容器（mini 虚拟机部署，见 lan-services）。构建上下文 = 本仓根目录（checkout 须含 vendor/sdtm-pedia submodule：
# git submodule update --init --depth 1）。只拷 submodule 里的 knowledge_base/，sdtm-pedia 仓其余内容不进镜像。
# chroma 元数据存的是 KB 相对路径（step 1.2 起），代码和 KB 位置不再需要与构建机一致：
# 代码在 /app，KB 在 /app/vendor/sdtm-pedia/knowledge_base（settings.kb_root 默认值）。
# data/（chroma、study、反馈记录）和 .env（密钥）不进镜像，运行时由 compose 挂到 /app/data、/app/.env。
FROM ghcr.io/astral-sh/uv:0.11.17 AS uv

FROM python:3.14.4-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH
LABEL org.opencontainers.image.source="https://192.168.100.58/bojiang/sdtm-rag" \
      org.opencontainers.image.title="sdtm-rag"
WORKDIR /app

# 先只装依赖（按 uv.lock 锁定版本），代码改动不会让这一层失效
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project

COPY vendor/sdtm-pedia/knowledge_base ./vendor/sdtm-pedia/knowledge_base
COPY server ./server
COPY ui ./ui
COPY webchat ./webchat
COPY scripts ./scripts
COPY eval ./eval

EXPOSE 8000 8501
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
