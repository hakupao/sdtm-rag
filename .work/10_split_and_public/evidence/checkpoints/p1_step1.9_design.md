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
