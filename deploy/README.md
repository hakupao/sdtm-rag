# 部署 (容器, mini 虚拟机)

> 2026-11-04 起生产跑在 mini 的 Lima 虚拟机 `deploy` 里的 Docker, 取代 launchd 版 (plist 模板 2026-11
> 已删, 见 git 历史)。运维 (虚拟机 / 端口转发 / 监控 / 日志 / `svc`) 见 lan-services 仓库 README。

## 组成

| 文件 | 作用 |
|------|------|
| `container/Dockerfile` | 构建上下文 = 本仓根 (checkout 须含 submodule: `git submodule update --init --depth 1`); 代码 `/app`, KB `/app/vendor/sdtm-pedia/knowledge_base` (只拷 KB, sdtm-pedia 其余不进镜像) |
| `container/Dockerfile.dockerignore` | 只放镜像需要的目录 |
| `container/compose.yml` | `api` 8000 + `ui` Streamlit 8501 (只转发到 mini 本机); `data/` → `$APP_DIR/data`, `.env` → `$APP_DIR/.env` (只读; `APP_DIR` 缺省 `/app`) |
| `../.gitea/workflows/sdtm-rag.yml` | push main → 测试 → 构建 → 推镜像 → 部署 → 健康检查; checkout `submodules: true` (公开 GitHub 仓, 无需凭据) |
| `deploy.sh` + `.env.service.template` | **遗留** (launchd 时代服务目录同步), 删除候选 |

宿主侧: 数据 `/Volumes/DevSSD/deploy-data/sdtm-rag/data` (chroma / study / 反馈记录); 密钥 虚拟机 `/opt/sdtm-rag/.env` (600)。
两个挂载都设 `create_host_path: false`: 挂载缺失直接起不来, 不会带着空数据「健康」启动。

## 发版

push 到 Gitea `main` (路径过滤见 workflow) → 自动部署, 镜像标签 = commit SHA。

改了 `webchat/`: 发版后让同事 `Cmd+Shift+R` (Win `Ctrl+F5`) 强刷一次 —— 修 `Cache-Control` 之前存进浏览器的
旧条目 (启发式新鲜期实测 ≈3 天) 不回源, 症状是"新控件整排消失", 不是后端问题。回归闸:
`tests/test_webchat_cache_headers.py` 常驻; `test_webchat_cache_browser.py` (真浏览器, 默认 skip) 改前端后手动跑。

## 回滚

- **自动**: 健康检查失败时, workflow 会退回部署前正在跑的镜像 (按其 WorkingDir 挂载)。
- **只构建不部署**: 手动运行 workflow, tag 留空、取消勾选 deploy → 只构建+推送镜像, 用于切换前在测试端口验证。
- **.env**: ⚑ 记录默认写 `data/dogfood_failures.md` (挂载卷内), 无需 `SDTM_RAG_DOGFOOD_LOG_OVERRIDE`; 旧 `.env` 里若有指向旧绝对路径的该键, 注释掉即可 (新旧镜像都不受影响)。

Actions 页面手动运行 `sdtm-rag` 工作流, `tag` 填已有镜像的完整 commit SHA → 跳过测试与构建, 直接部署该版本。

跨 step 1.5a 边界: 之前 (monorepo 时代) 的镜像 WorkingDir = `/Volumes/DevSSD/Project/sdtm-pedia/sdtm-rag`, 代码按
`__file__` 找 `data/` `.env`, KB 打在镜像内同一绝对路径下。部署步骤 pull 后取
`APP_DIR=$(docker image inspect -f '{{.Config.WorkingDir}}' <镜像>)` (空则 `/app`) 传给 compose, 挂载目标随之切换,
新旧镜像都能挂对。手工回滚同理: `APP_DIR=<WorkingDir> IMAGE_TAG=<sha> docker compose -f deploy/container/compose.yml up -d`。

⚠ chroma 的 `source` 元数据在 step 1.2 (2026-11) 已改写为 KB 相对路径。回滚到 1.2 之前的镜像须**同时**恢复迁移前的
chroma 副本 (旧代码只按绝对路径过滤 → 启动失败); 备份 `/Volumes/DevSSD/backups/sdtm-pedia-pre-split-2026-11/`。

## 启动失败常见原因

- KB 与 chroma 对不上 → S1 VARIABLE_INDEX section 映射为空 → lifespan 预热 raise (有意: 旧版本同样错配会静默退化成纯 cosine)。
  旧索引先停服务, 再 `.venv/bin/python -m scripts.migrate_source_relative <chroma_dir> --kb-root <旧前缀> --apply`
  (`<旧前缀>` = 索引里 `source` 实际存的绝对 KB 根, 如 `/Volumes/DevSSD/Project/sdtm-pedia/knowledge_base`, **不是**新 KB 位置)。
  `python -m scripts.check_index_freshness` 会抽样报出这类索引 (BAD SOURCE PATHS)。
- 画面 PDF 旁路 (`SDTM_RAG_PDF_CONTEXT_ENABLED`, 默认 false) 开着而 pdftoppm / 页索引 / PDF 缺失或 sha256 不符 ⇒ 启动失败; 键见 `.env.example` 末节。
- `.env` 写了旧变量名 `SDTM_RAG_KB_ROOT` / `SDTM_RAG_CHROMA_DIR` → 静默不生效, 须用 `*_OVERRIDE`; 路径类覆盖须是容器内路径 (`/app/...`)。

## 其他

- 登录门口令哈希 + session secret: `.venv/bin/python -m scripts.gen_password_hash`。
- Neo4j 探索层 2026-11-07 退役 (dump 在 dev `~/Backups/neo4j-retired-20261107/`); 原安装步骤见本文件 git 历史。
