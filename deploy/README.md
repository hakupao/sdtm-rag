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
| `../.gitea/workflows/kb-sync.yml` + `kbsync/kbsync.py` | KB→RAG 同步 (step 1.9): 每天检测 A 仓最新 `kb-*` tag → 生产副本上灌库 + CDISC 闸; 见下「KB 同步」 |
| `deploy.sh` + `.env.service.template` | **遗留** (launchd 时代服务目录同步), 删除候选 |

宿主侧: 数据 `/Volumes/DevSSD/deploy-data/sdtm-rag/data` (chroma / study / 反馈记录); 密钥 虚拟机 `/opt/sdtm-rag/.env` (600)。
两个挂载都设 `create_host_path: false`: 挂载缺失直接起不来, 不会带着空数据「健康」启动。

## 发版

push 到 Gitea `main` (路径过滤见 workflow) → 自动部署, 镜像标签 = commit SHA。

改了 `webchat/`: 发版后让同事 `Cmd+Shift+R` (Win `Ctrl+F5`) 强刷一次 —— 修 `Cache-Control` 之前存进浏览器的
旧条目 (启发式新鲜期实测 ≈3 天) 不回源, 症状是"新控件整排消失", 不是后端问题。回归闸:
`tests/test_webchat_cache_headers.py` 常驻; `tests/test_webchat_cache_browser.py` (真浏览器, 默认 skip) 改前端后手动跑。

## KB 同步 (kb-sync)

目录身份只看 chroma stamp 的 `kb_fingerprint` (+ 候选里的 `kbsync_gate.json`), 不看 SHA。数据根 (`deploy-data/sdtm-rag/data`) 下:

| 目录 | 含义 |
|------|------|
| `chroma/` `meta/` | 生产 |
| `chroma_cand_<fp12>/` `meta_cand_<fp12>/` | kb-sync 过闸候选 (marker `verdict=PASS`), 等部署换上 |
| `chroma_prev_<fp12>_<ts>/` `meta_prev_*` | 被换下的旧生产, 部署成功后留最新 2 份 (回滚用) |
| `chroma_failed_<fp12>_<ts>[_stale]/` `meta_failed_*` | 闸不过 / 中断的候选, **永不自动删** (规则 B); 盘紧时人工清 |

1. **kb-sync** (定时每天 03:17 / 手动 `ref`): A 仓 KB 指纹 == 生产 stamp 或已有过闸候选 → no-op。否则本机建候选镜像
   (不推送) → 复制生产 chroma/meta → 基线 = **当前生产镜像**在副本上跑 CDISC 140q retrieval-only → 候选镜像
   `scripts.ingest --no-backup` (只重建 `sdtm_kb_v1`) + `scripts.build_meta` → 同一 eval。闸: 候选 stamp 指纹 ==
   检测指纹; 两边题号集合相同且 ≥ 140 题; 逐题 `source_recall` 回退 (含缺题) ≤ 1; 候选满分题数 ≥ 基线 − 1;
   候选 `summary.source_recall_avg` ≥ 0.95; eval 崩/空 = FAIL。闸结果只打计数与题号; 但某一步 (eval / ingest /
   build_meta) 非零退出时会打该步 stderr 末 20 行 (CDISC 题集, 不含研究数据)。marker 记录候选镜像的 chromadb 版本,
   部署时目标镜像 chromadb 版本不同则不选该候选。
2. **「KB 更新」** (本地) 升 submodule → push → **部署**: 目标镜像 KB 指纹 ≠ 生产 stamp → 停服务 → 在**副本**
   (`kbsync_guard_<ts>/`, 用完即删) 上核对非 KB 集合 (名 + 条数 + 内容摘要) 候选 == 生产 (不同 = study 集合在候选
   建好后变过, 拒换, 重跑 kb-sync) → 改名换入 (journal `kbsync_swap.json`) → 起服务 → 健康检查 →
   `check_index_freshness` rc=0 → 删 journal + prune。换到一半失败 → 先按 journal 退数据再起原容器。
   找不到过闸候选 / 保留副本 → **生产未动即失败**。数据根残留 journal (上次 job 被取消/超时) → 任何部署 (含
   force) 都先失败, 人工 `restore` (或确认已生效后 `finish`)。
3. 手工排查: `python3 deploy/kbsync/kbsync.py --via <镜像> detect|predeploy-check|swap-status --data-root <数据根> ...`
   (job 容器看不到数据根, 文件操作都在兄弟容器里做)。

## 回滚

- **自动**: 健康检查 (或换数据后的 freshness) 失败时, workflow 先按 journal 退回 chroma/meta, 再退回部署前正在跑的镜像 (按其 WorkingDir 挂载)。
- **数据跟着镜像走**: 手动 `tag=` 回滚时同样比 KB 指纹; 不同则换上保留的 `chroma_prev_<fp12>_*`。没有匹配副本、或旧镜像判不出指纹
  (无 `scripts.kb_freshness`) → 默认失败; 勾选 `force_data_mismatch` 则不换数据照常部署 (日志告警, 回答可能基于错配索引)。
  ⚠ force 只覆盖 unknown / missing: 决定已是 swap (有匹配副本) 而非 KB 集合核对不过时, force **救不了**, 部署失败;
  需人工处理该副本 (改名移开后即变 missing, 才能 force)。
  手工退数据: 停服务后 `kbsync.py --via <镜像> restore --data-root <数据根>` (只在 journal 还在时生效)。
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

- KG 查看器产物 2026-11-25 起在 `viewer/dist/kg_viewer.html` (原仓根 `kg_viewer.html`; 由 `scripts/build_kg_viewer.py` 生成, 不进镜像)。
  lan-services 的 Caddy 拷的是这个文件 —— 那边的源路径须同步改成 `viewer/dist/kg_viewer.html`。
- 登录门口令哈希 + session secret: `.venv/bin/python -m scripts.gen_password_hash`。
- Neo4j 探索层 2026-11-07 退役 (dump 在 dev `~/Backups/neo4j-retired-20261107/`); 原安装步骤见本文件 git 历史。
