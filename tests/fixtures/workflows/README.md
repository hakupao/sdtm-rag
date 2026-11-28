# tests/fixtures/workflows

`base_9a8ad43_sdtm-rag.yml`、`base_9a8ad43_kb-sync.yml` 是基点提交 `9a8ad43` 里两个 workflow 的原文冻结
(与 `git show 9a8ad43:.gitea/workflows/<名>.yml` 逐字相同, 所以文件里不加任何注释)。

用途: `tests/test_workflow_conditions.py` 里两条对照测试的基准 ——
`test_private_deploy_job_changed_only_where_intended` (私有部署 job 只在预期处有改动) 和
`test_kb_sync_private_leg_changed_only_where_intended` (kb-sync 私有腿只在预期处有改动)。
CI 的 checkout 深度是 1, 取不到基点提交, 所以基准冻在这里; 测试先核对这两个文件的 git blob 号等于写在测试里的基点 blob 号 (`BASE_BLOBS`), 不依赖 git 历史。

以后有意改动这两个 job 时: 改测试里「预期有改动的步骤」清单; 需要换基点时, 用新基点的 `git show` 输出重新生成这两个文件,
并同步改文件名、测试里的提交号和 `BASE_BLOBS` (`git rev-parse <新基点>:.gitea/workflows/<名>.yml`)。不要手工编辑文件内容。
