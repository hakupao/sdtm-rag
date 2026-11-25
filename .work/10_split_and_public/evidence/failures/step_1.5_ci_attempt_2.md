# step 1.5 CI attempt 2 — FAIL (2026-11-25)

- 输入: af5f480, run (workflow_dispatch, deploy=false); 测试 2550 passed / 61 skipped ✅; dockerignore 嵌套放行实测有效 (COPY vendor/sdtm-pedia/knowledge_base 成功)
- 产物: `构建并推送` 失败 — `failed to extract layer ... no space left on device`
- 技术判定: Lima VM `deploy` 根盘 38G 用 34G (89%); docker build cache 8.19GB (0 active), 镜像 44 个 18.9GB (6.7GB 可回收)
- 处置: `docker builder prune -af` 只清构建缓存 (不动镜像/容器/卷, 不影响任何服务与回滚镜像) → 27G/38G, 余 11G
- 业务判定: 共享 VM 磁盘是长期风险 (每次构建都留缓存, 每个服务都保留历史镜像) → P4 收尾时建议: 构建后自动 `builder prune --filter until=72h` + 每服务只保留最近 N 个镜像 (须先与 lan-services 约定)
- 下一 attempt: 同提交重跑 build-only
