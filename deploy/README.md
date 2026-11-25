# 部署 (容器, mini 虚拟机)

> 2026-11-04 起生产跑在 mini 的 Lima 虚拟机 `deploy` 里的 Docker, 取代 launchd 版 (plist 模板 2026-11
> 已删, 见 git 历史)。运维 (虚拟机 / 端口转发 / 监控 / 日志 / `svc`) 见 lan-services 仓库 README。

## 组成

| 文件 | 作用 |
|------|------|
| `container/Dockerfile` | 构建上下文 = 本仓根 (checkout 须含 `knowledge_base` submodule); 代码 `/app`, KB `/app/knowledge_base` |
| `container/Dockerfile.dockerignore` | 只放镜像需要的目录 |
| `container/compose.yml` | `api` 8000 + `ui` Streamlit 8501 (只转发到 mini 本机); `data/` → `/app/data`, `.env` → `/app/.env` (只读) |
| `../.gitea/workflows/sdtm-rag.yml` | push main → 测试 → 构建 → 推镜像 → 部署 → 健康检查 |
| `deploy.sh` + `.env.service.template` | **遗留** (launchd 时代服务目录同步), 删除候选 |

宿主侧: 数据 `/Volumes/DevSSD/deploy-data/sdtm-rag/data` (chroma / study / 反馈记录); 密钥 虚拟机 `/opt/sdtm-rag/.env` (600)。
两个挂载都设 `create_host_path: false`: 挂载缺失直接起不来, 不会带着空数据「健康」启动。

## 发版

push 到 Gitea `main` (路径过滤见 workflow) → 自动部署, 镜像标签 = commit SHA。

改了 `webchat/`: 发版后让同事 `Cmd+Shift+R` (Win `Ctrl+F5`) 强刷一次 —— 修 `Cache-Control` 之前存进浏览器的
旧条目 (启发式新鲜期实测 ≈3 天) 不回源, 症状是"新控件整排消失", 不是后端问题。回归闸:
`scripts/tests/test_webchat_cache_headers.py` 常驻; `test_webchat_cache_browser.py` (真浏览器, 默认 skip) 改前端后手动跑。

## 回滚

Actions 页面手动运行 `sdtm-rag` 工作流, `tag` 填已有镜像的完整 commit SHA → 跳过测试与构建, 直接部署该版本。

⚠ chroma 的 `source` 元数据在 step 1.2 (2026-11) 已改写为 KB 相对路径。回滚到 1.2 之前的镜像须**同时**恢复迁移前的
chroma 副本 (旧代码只按绝对路径过滤 → 启动失败); 备份 `/Volumes/DevSSD/backups/sdtm-pedia-pre-split-2026-11/`。

## 启动失败常见原因

- KB 与 chroma 对不上 → S1 VARIABLE_INDEX section 映射为空 → lifespan 预热 raise (有意: 旧版本同样错配会静默退化成纯 cosine)。
  旧索引先停服务, 再 `.venv/bin/python -m scripts.migrate_source_relative <chroma_dir> --kb-root <KB> --apply`。
- 画面 PDF 旁路 (`SDTM_RAG_PDF_CONTEXT_ENABLED`, 默认 false) 开着而 pdftoppm / 页索引 / PDF 缺失或 sha256 不符 ⇒ 启动失败; 键见 `.env.example` 末节。
- `.env` 写了旧变量名 `SDTM_RAG_KB_ROOT` / `SDTM_RAG_CHROMA_DIR` → 静默不生效, 须用 `*_OVERRIDE`; 路径类覆盖须是容器内路径 (`/app/...`)。

## 其他

- 登录门口令哈希 + session secret: `.venv/bin/python -m scripts.gen_password_hash`。
- Neo4j 探索层 2026-11-07 退役 (dump 在 dev `~/Backups/neo4j-retired-20261107/`); 原安装步骤见本文件 git 历史。
