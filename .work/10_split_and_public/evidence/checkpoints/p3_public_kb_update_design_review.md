# 审查: p3_public_kb_update_design.md v0.1 (规则 D)

- 审查者: subagent_type `oh-my-claudecode:security-reviewer` (写作者为主会话 Claude, 不同 agent 类型、不同 context), 2026-11-27, 只读。
- prompt 存档: `evidence/subagent_prompts/review_public_kb_design.md`
- **结论: PASS-with-fixes** (HIGH 2 / MED 4 / LOW 5)。修订见设计文档 v0.2 节。

## 审查意见 (原文摘录, 按严重度)

**核心安全性质成立**: 每条 kbsync 命令只在同一个数据根里复制和改名 (`prepare` 只复制 `data_root/chroma` 与 `data_root/meta`, `kbsync.py:97-110`), A1 没有私有根 → 公开根的数据路径。候选镜像不含数据 (`Dockerfile:5,25-30`), 两条腿共用安全。公开腿误用私有 `.env` 不会泄露红线数据 (挂载的是公开根, ingest 集合名写死, eval 不带 study 参数), 只是费用记到私有账上。

- **HIGH-1 `--kb-only` 位置**: `gate` 是 `--via` 文件系统子命令, 兄弟容器里调不了 docker, 做不了集合检查; 部署时 `predeploy_check` 也可能选 `chroma_prev_*` (不经 gate); 现有 `deploy_swap` 守卫只比较「生产 == 换入源」, 公开线上已被污染或 `PUBLIC_DATA_ROOT` 指错私有根时照样通过。→ 两层: (a) `candidate` 编排里, 候选 eval 后、gate 前断言集合恰为 `{sdtm_kb_v1}`, 不符则 `fail(kb_only_violation)`; (b) `deploy-swap --kb-only` 对守卫副本上的线上 chroma 与换入源都断言 `non_kb == {}` (主闸)。chroma 删除不回收空间在 A1 也存在, 但残留只是旧版 CDISC, 不碰红线; 物理层面靠「公开 chroma 唯一来源 = 公开根」, 要明说并加测试 (kbsync 无子命令同时接受两个数据根)。
- **HIGH-2 失败路径缺状态**: ① 公开容器原本 stopped (当前实况): 照搬私有 job 的「换数据被拒 → compose start」会把停着的公开站拉起; D2(b) 未定义「原本停止」时退回到什么; `deploy_public` 不记录部署前镜像与运行状态。② job 取消 / 超时: 私有退回步骤只认 `failure()`, 公开停机认 `failure() || cancelled()`, 设计没说取消时退不退数据; `timeout-minutes: 20` 未重估。③ restore 失败 → journal 残留 → 下次 deploy_public 与 kb-sync 公开腿 `journal_pending` 失败, 是否把私有腿也变红未说明。④ 私有 swap 成功 + 公开 swap 失败的组合应写进 §3.5。→ 预检记 `prev_image` / `prev_running`; 退回一律先查 journal-state (0 继续, 2/3 停机); 退数据后容器回到 `prev_running`; 取消时只停机不碰数据, 交给下次 `journal_pending` 拦。
- **MED-3** 公开数据根路径三处写死 (`compose.public.yml:19`、`sdtm-rag.yml:258`、kb-sync 新增), 无一致性断言 → 断言 `PUBLIC_DATA_ROOT` / `ENV_FILE` 与 `docker compose -f compose.public.yml config` 解析的挂载源一致, 且 ≠ 私有根。
- **MED-4** 两条腿失败隔离交给「实现时选」: 同 job 串行时私有腿失败 (`journal_pending`、私有容器不存在) 会挡住公开腿; 候选镜像构建条件要改成「任一腿 changed」, 删除放最后加 `always()` → 写明两个 job (`needs: private` + `if: always()`), 或列为裁定点。
- **MED-5** §4「两者都在部署路径过滤内」不准: 过滤 (`sdtm-rag.yml:10-25`) 不含 `deploy/kbsync/**` 与 `kb-sync.yml`; `kbsync.py` 从 checkout 运行、不在镜像里, 改了不需部署、下次 workflow 运行即生效; 只改 `tests/` 不跑 CI。
- **MED-6** A2 否决的主理由应是「引入私有根 → 公开根的数据通道, 破坏单一来源不变量」, sqlite 残留为次要理由; 漏列方案: 公开候选**从空目录全新入库** (基线在旧副本上跑, 候选写新目录), 物理文件只有一版 KB。
- **LOW-7** `chroma_failed_*` / `chroma_prev_*` / `kbsync_eval` 都在公开容器挂载范围内, `prune` 不删 failed → 列为裁定点 (归档位置与保留份数)。
- **LOW-8** 基线镜像回退私有线上镜像: 可接受。
- **LOW-9** 公开根 `meta/` 只由 `build_meta` 生成 (P3.3); `implicit_relations.json` server 不读; 安全, 建议在 §3.2 写明。
- **LOW-10** D1-D5 基本中立; 该列未列: D6 全新入库 vs 复制后重置、D7 公开根失败归档、D8 两条腿隔离、D2 补「原本停止」子问题。
- **LOW-11** 漏列文件: `tests/test_deploy_public_compose.py` (`test_public_job_gated_and_separate` 检查 deploy_public 结构)、一致性断言与两条腿隔离的测试、`kb-sync.yml` / `kbsync.py` 文件头注释、`docs/PROGRESS.md` 与 `_progress.json` 的 `decisions_p3.open`。

## 处置
全部接受, 在设计文档追加「v0.2 修订 (审查后)」节, 不删 v0.1 原文 (便于对照)。
