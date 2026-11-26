# P1 step 1.9 KB→RAG 同步 — 设计 v0.1 (2026-11-25, 待实现)

**用户裁定 (2026-11-25)**: CI 检测 + 闸 + 报告; submodule 升级提交由本地「KB 更新」完成并双推 (Gitea 不存 GitHub token, CI 不写 main → 两远端不分叉)。

## 事实 (已读代码)
- 服务启动对陈旧索引只告警不拒启 (`server/main.py:358-368`); 工作流路径过滤含 `vendor/sdtm-pedia` → 今天推一个 submodule 升级 = 新 KB 镜像 + 旧 chroma, 静默漂移。
- `scripts/ingest.py` 默认只重置 `sdtm_kb_v1` 集合 (study 集合同目录不动); `--full-reset` 才清整个目录; CHROMA_DIR 写死仓内 `data/chroma` (容器内 = 挂载的生产 data/)。
- KB 派生物: chroma `sdtm_kb_v1` + stamp (`kb_fingerprint`); `data/meta/meta.yaml` (git 跟踪, `scripts/build_meta.py` 生成; 生产读 deploy-data 里的副本, 不在镜像里); BM25 / S1 section map 启动时内存构建 (无需落盘)。
- 判据用内容指纹 `kb_fingerprint` 而非 SHA: 现钉 ebf0c8a vs A 1c0495a KB diff 为空 → 必须判 no-op (首个免费测试)。

## 流程
1. **检测** (Gitea 定时 workflow, 每天): `git ls-remote https://github.com/hakupao/sdtm-pedia main` → 浅拉 → 算 `kb_fingerprint` vs 当前钉的 KB 指纹; 相同 → 退出 (no-op)。
2. **候选 + 闸** (同 workflow, 指纹不同时): 用当前镜像 + 新 KB 挂载, 在 `deploy-data/sdtm-rag/chroma_candidate` (= 生产 chroma 副本) 上只重建 `sdtm_kb_v1`; 重新生成 meta.yaml 候选; 跑 CDISC 140q retrieval-only, 与基线比 recall 差 ≤ 1 题; 结果 (只含计数 / 题号) 写到 workflow 日志 + 摘要。不达标 → 失败, 不换任何东西。
3. **本地「KB 更新」** (人): 升 submodule → 本机 build_meta (meta.yaml 有 diff 则一并提交) → 本机两条检索闸 + pytest → 提交 + 双推。
4. **部署** (现有 workflow 扩展): 若镜像 KB 指纹 ≠ 生产 stamp → 换上已过闸的候选 chroma + meta.yaml (stop → 换目录 → start → 健康检查 + freshness rc=0); 回滚 = 镜像 **和** chroma/meta 一起退回; 旧 chroma 保留最近 2 份 (VM 盘曾满)。
5. 公开实例: P3.3 才建, 1.9 只演练私有实例 (登记 deferral)。

## 演练 (验收)
- 正例: A 仓改一行 KB (用户确认后推 A) → 检测触发 → 候选过闸 → 「KB 更新」→ 部署后 freshness rc=0。
- 反例 (规则 5): 损坏的 KB 副本 (如删掉一个域 spec) → 闸拦下、归档 failures/、生产未换。
- 前置: 重组后 HEAD 先 build-only → 测试端口 (生产仍 ee41a3c, 否则演练失败归因不清); 生产 freshness 需用户在 mini 上跑。

## 未决
- 定时 workflow 与候选目录需在 VM 上有写权限 (runner 与部署同机, 已能 docker compose); 细节实现时核对 runner 挂载。
- failures 归档在公开仓: study 结果只写计数 / 题号。

## v0.2 修订 (2026-11-26, 实现版; 与 v0.1 不同处以此为准)
- **身份**: 每个 chroma 目录 = stamp `kb_fingerprint` + 候选 marker `kbsync_gate.json` (指纹/ref/A commit/镜像/基线与候选计数/回退题号/时间/verdict); 不用任何 SHA 判定。
- **检测源**: A 仓最新 `kb-*` tag (`git ls-remote --tags`), 不是 `main`; 手动 dispatch 可给 `ref` (tag 或 40 位 commit, 格式校验)。比对对象 = **生产 stamp** (不是当前钉的 submodule)。已有过闸候选 → no-op。与部署同 `concurrency` 组。
- **候选**: 本机候选镜像 `sdtm-rag-kbcand:<fp12>` (不推送, 结束即删; KB 在原生路径, 无覆盖) 而非"当前镜像 + 挂新 KB"; 目录 `chroma_cand_<fp12>` + `meta_cand_<fp12>`。容器里 `data/` 只读、候选 chroma/meta 以原生路径可写覆盖 (`--mount` 源缺失即报错), `--memory 1536m`。
- **基线**: 每次现跑 (当前生产镜像 × 灌库前的副本), 不存历史基线。闸 = 逐题 `source_recall` 回退 (候选 < 基线, 或缺题) ≤ 1, 且候选 stamp 指纹 == 检测指纹; eval 崩/空 = FAIL。FAIL → 改名 `chroma_failed_<fp12>_<ts>` (不删)。只跑 CDISC。
- **`ingest.py --no-backup`**: R-16 备份写 `chroma_dir.parent` = 只读的 `/app/data` (会崩) 且磁盘翻倍; 候选本身即生产副本, 故跳过。
- **job 看不到数据根** (runner valid_volumes 只放行 CA): 文件操作全部经 `kbsync.py --via <镜像>` 在兄弟容器里执行 (数据根按原路径挂载, 脚本走 stdin)。chromadb 打不开只读目录 (实测 sqlite readonly) → 集合核对用可写挂载、生产已停。
- **部署**: 换数据前核对非 KB 集合 (名 + 条数) 候选 == 生产, 否则拒换; 换后 `check_index_freshness` rc=0; 失败先按 journal 退数据 (不受 `prev != tag` 限制) 再退镜像; 旧副本 prune 留 2 份, `chroma_failed_*` 不碰。旧镜像判不出指纹 / 无匹配副本 → 默认失败, `force_data_mismatch` 放行不换数据。
- 演练与实现证据: `step_1.9_impl.md`。
