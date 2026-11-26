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

## v0.2 修订（2026-11-26，实现版；与 v0.1 不一致之处以本节为准）
- **身份**：每个 chroma 目录的身份由 stamp 中的 `kb_fingerprint` 和候选 marker `kbsync_gate.json`（记录指纹、ref、A 仓 commit、镜像、基线与候选计数、回退题号、时间和 verdict）确定；判定时不使用任何 SHA。
- **检测源**：检测 A 仓最新的 `kb-*` tag（通过 `git ls-remote --tags`），而不是 `main`；手动 dispatch 时可以指定 `ref`（tag 或 40 位 commit，会校验格式）。比对对象是**生产 stamp**，不是当前钉住的 submodule。如果已有过闸候选，则不做任何操作（no-op）。kb-sync 与部署使用同一个 `concurrency` 组。
- **候选**：在本机构建候选镜像 `sdtm-rag-kbcand:<fp12>`（不推送，结束后即删除；KB 位于原生路径，无需覆盖挂载），而不是采用"当前镜像 + 挂载新 KB"的方式；候选目录为 `chroma_cand_<fp12>` 和 `meta_cand_<fp12>`。容器内 `data/` 只读，候选 chroma/meta 以原生路径可写挂载覆盖（`--mount` 的源目录不存在时直接报错），内存限制为 `--memory 1536m`。
- **基线**：基线每次重新运行（用当前生产镜像在入库前的副本上运行），不保存历史基线。闸条件：逐题 `source_recall` 回退（候选低于基线，或缺题）不超过 1 题，并且候选 stamp 指纹与检测到的指纹一致；评测崩溃或结果为空时判为 FAIL。FAIL 时把候选改名为 `chroma_failed_<fp12>_<ts>`（不删除）。只运行 CDISC 评测。
- **`ingest.py --no-backup`**：R-16 备份会写到 `chroma_dir.parent`，即只读的 `/app/data`（会导致崩溃），而且会使磁盘占用翻倍；候选本身就是生产数据的副本，因此跳过备份。
- **job 无法访问数据根**（runner 的 valid_volumes 只放行 CA）：所有文件操作都通过 `kbsync.py --via <镜像>` 在兄弟容器中执行（数据根按原路径挂载，脚本通过 stdin 传入）。chromadb 无法打开只读目录（实测报 sqlite readonly），因此集合核对使用可写挂载，此时生产服务已停止。
- **部署**：换数据前，核对候选与生产的非 KB 集合（名称和条数）是否一致，不一致则拒绝换入；换入后要求 `check_index_freshness` 返回 rc=0。失败时，先按 journal 退回数据（不受 `prev != tag` 条件限制），再退回镜像。prune 旧副本时保留 2 份，不处理 `chroma_failed_*`。如果无法确定旧镜像的指纹，或没有匹配的副本，默认部署失败；`force_data_mismatch` 可放行部署，但不换数据。
- 演练与实现证据见 `step_1.9_impl.md`。
