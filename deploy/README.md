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
| `../.gitea/workflows/kb-sync.yml` + `kbsync/kbsync.py` | KB→RAG 同步（step 1.9）：每天检测 A 仓最新的 `kb-*` tag，在生产数据副本上入库并运行 CDISC 闸；详见下文「KB 同步」 |
| `deploy.sh` + `.env.service.template` | **遗留** (launchd 时代服务目录同步), 删除候选 |

宿主侧: 数据 `/Volumes/DevSSD/deploy-data/sdtm-rag/data` (chroma / study / 反馈记录); 密钥 虚拟机 `/opt/sdtm-rag/.env` (600)。
两个挂载都设 `create_host_path: false`: 挂载缺失直接起不来, 不会带着空数据「健康」启动。

## 发版

push 到 Gitea `main` (路径过滤见 workflow) → 自动部署, 镜像标签 = commit SHA。

改了 `webchat/`: 发版后让同事 `Cmd+Shift+R` (Win `Ctrl+F5`) 强刷一次 —— 修 `Cache-Control` 之前存进浏览器的
旧条目 (启发式新鲜期实测 ≈3 天) 不回源, 症状是"新控件整排消失", 不是后端问题。回归闸:
`tests/test_webchat_cache_headers.py` 常驻; `tests/test_webchat_cache_browser.py` (真浏览器, 默认 skip) 改前端后手动跑。

## KB 同步 (kb-sync)

目录身份只由 chroma stamp 中的 `kb_fingerprint` 确定（候选目录另加 `kbsync_gate.json`），不使用 SHA。数据根（`deploy-data/sdtm-rag/data`）下的目录如下：

| 目录 | 含义 |
|------|------|
| `chroma/` `meta/` | 生产数据 |
| `chroma_cand_<fp12>/` `meta_cand_<fp12>/` | 通过 kb-sync 闸的候选（marker 中为 `verdict=PASS`），等待部署时换入 |
| `chroma_prev_<fp12>_<ts>/` `meta_prev_*` | 被换下的旧生产数据，用于回滚；部署成功后保留最新 2 份 |
| `chroma_failed_<fp12>_<ts>[_stale]/` `meta_failed_*` | 未通过闸或中途中断的候选，**永不自动删除**（规则 B）；磁盘空间紧张时人工清理 |

1. **kb-sync**（每天 03:17 定时运行，也可手动指定 `ref`）：如果 A 仓 KB 指纹与生产 stamp 相同，或该指纹已有过闸候选，
   则不做任何操作（no-op）。否则，先在本机构建候选镜像（不推送），再复制生产 chroma/meta 作为副本；用**当前生产镜像**
   在副本上运行 CDISC 140 题 retrieval-only 评测，结果作为基线；然后用候选镜像运行 `scripts.ingest --no-backup`
   （只重建 `sdtm_kb_v1`）和 `scripts.build_meta`，再运行同一评测。
   闸条件：候选 stamp 指纹与检测到的指纹一致；两边题号集合相同，且不少于 140 题；逐题 `source_recall` 回退
   （缺题也算回退）不超过 1 题；候选满分题数不低于基线减 1；候选 `summary.source_recall_avg` ≥ 0.95。
   评测崩溃或结果为空时判为 FAIL。
   闸结果只输出计数和题号。但如果某一步（eval、ingest 或 build_meta）以非零状态退出，会输出该步 stderr 的最后 20 行
   （只涉及 CDISC 题集，不含研究数据）。marker 中记录候选镜像的 chromadb 版本；部署时如果目标镜像的 chromadb 版本
   与之不同，则不选用该候选。
2. **「KB 更新」**：在本地升级 submodule 并 push，触发**部署**。如果目标镜像的 KB 指纹与生产 stamp 不同，部署按以下
   顺序换数据：停止服务；在**副本**（`kbsync_guard_<ts>/`，用完即删）上核对候选与生产的非 KB 集合（名称、条数、
   内容摘要）是否一致；通过改名换入候选（journal 记在 `kbsync_swap.json`）；启动服务；健康检查；确认
   `check_index_freshness` 返回 rc=0；最后删除 journal 并执行 prune。
   如果非 KB 集合不一致，说明候选建好后 study 集合发生过变化，此时拒绝换入，需要重新运行 kb-sync。
   换到一半失败时，先按 journal 回退数据，再启动原容器。
   找不到过闸候选或保留副本时，部署失败，**生产保持不变**。
   如果数据根残留 journal（上次 job 被取消或超时），任何部署（包括 force）都会在一开始失败，需要人工执行 `restore`
   （或在确认换入已生效后执行 `finish`）。
3. 人工排查：`python3 deploy/kbsync/kbsync.py --via <镜像> detect|predeploy-check|swap-status --data-root <数据根> ...`
   （job 容器无法访问数据根，所有文件操作都在兄弟容器中执行）。

## 回滚

- **自动**：健康检查失败（或换数据后的 freshness 检查失败）时，workflow 先按 journal 退回 chroma/meta，再退回部署前正在运行的镜像（按该镜像的 WorkingDir 挂载）。
- **数据随镜像回滚**：手动指定 `tag=` 回滚时，同样会比较 KB 指纹；指纹不同时，换入保留的 `chroma_prev_<fp12>_*`。
  如果没有匹配的副本，或无法确定旧镜像的指纹（旧镜像没有 `scripts.kb_freshness`），默认部署失败；勾选
  `force_data_mismatch` 后不换数据，照常部署（日志中告警，回答可能基于不匹配的索引）。
  ⚠ force 只对 unknown 和 missing 两种决定生效。如果决定已经是 swap（存在匹配副本），但非 KB 集合核对不通过，
  force **也无效**，部署失败。此时需要人工处理该副本：将其改名移走后，决定变为 missing，才能使用 force。
  人工退回数据：先停止服务，再执行 `kbsync.py --via <镜像> restore --data-root <数据根>`（仅在 journal 仍存在时有效）。
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
