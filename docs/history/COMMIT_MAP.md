# monorepo → sdtm-rag 提交 SHA 对照

`monorepo_commit_map.txt`: git filter-repo 生成 (2026-11-25 step 1.3), 每行 `<sdtm-pedia 旧 SHA> <本仓新 SHA>` (新 SHA 全 0 = 该提交在本仓为空被剔除)。证据文档里引用的 7 位 SHA 都是 sdtm-pedia 时代的, 用 `grep ^<sha> docs/history/monorepo_commit_map.txt` 换算。
