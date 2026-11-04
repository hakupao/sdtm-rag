# sdtm-rag 容器（mini 虚拟机部署，lan-services 第 6 步，2026-11-04）。构建上下文 = sdtm-pedia 仓库根目录。
# 代码和 knowledge_base 放在和 mac mini 上**完全相同的绝对路径**：chroma 元数据里存的是
# knowledge_base 文件的绝对路径（/Volumes/DevSSD/Project/sdtm-pedia/...），启动时 S1 映射会核对，
# 路径对不上会启动失败（见 server/main.py 的 s1_vi_section_map 注释）。
# data/（chroma、study、反馈记录）和 .env（密钥）不进镜像，运行时由 compose 挂进来。
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
LABEL org.opencontainers.image.source="https://192.168.100.58/bojiang/sdtm-pedia" \
      org.opencontainers.image.title="sdtm-rag"
WORKDIR /Volumes/DevSSD/Project/sdtm-pedia/sdtm-rag

# 先只装依赖（按 uv.lock 锁定版本，和 mini 本机的 .venv 一致），代码改动不会让这一层失效
COPY sdtm-rag/pyproject.toml sdtm-rag/uv.lock sdtm-rag/README.md ./
RUN uv sync --frozen --no-install-project

COPY knowledge_base /Volumes/DevSSD/Project/sdtm-pedia/knowledge_base
COPY sdtm-rag/server ./server
COPY sdtm-rag/ui ./ui
COPY sdtm-rag/webchat ./webchat
COPY sdtm-rag/scripts ./scripts
COPY sdtm-rag/eval ./eval

EXPOSE 8000 8501
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
