# 「KB 更新」上线私有站: kb-2026.11.28 (2026-11-28; 1.9 私有正例) — PASS

**结论: 全程走的是正常路径, 没有触发任何「必须停下来」的情况。** 私有站现在跑镜像 `f798709` + 新 KB 数据 (指纹 `477bac3ce565…`, 4333 条); 公开实例未动。
时间: 下文 Gitea / 目录名里的时间戳是 UTC (2026-11-27T16:21–16:45Z = 日本时间 11-28 01:21–01:45)。

## 授权
主人 2026-11-27 在协调方的待办项上亲自选定 (**经待办项转达的选择**, 不是在本会话里说的):
- 问题:「pedia 打 tag 之后，rag 这边一路做完（kb-sync 过闸 → KB 更新提交 → push → 部署私有站），可以吗？」
- 主人选的 (原话):「可以，一路做完」; 该选项的说明是「手动触发 kb-sync，不等凌晨定时；过闸后先只构建、测试端口验证，再正式部署；每步汇报」。
- 这份同意只覆盖正常路径。没有用到的: q76 双标题补救、`force_data_mismatch`、人工回滚、重试部署。

## 第 0 步: 起点
| 项 | 结果 |
|---|---|
| 线上镜像 | `2b24d53…` (api / ui), 公开容器 Exited |
| Gitea Actions | 无排队 / 进行中的运行; 仓库变量为空 (`SDTM_RAG_PUBLIC_DEPLOY` 未开) |
| pedia tag | GitHub `hakupao/sdtm-pedia` 的 `kb-2026.11.28` → 提交 `b2bd8376e51e4d9e751fc49834a87a103a722b2e`; `knowledge_base` 树哈希 `63f857774a42cfaa71798705ad40ab51bc5e378a` (= 第二次预演那棵树) |
| 数据根 | 只有 `chroma` / `meta` / `study` 和 2026-11-26 演练留下的 `*_failed_c5ef769965fd_*`; 无 cand / prev / journal |
| 本仓 | main 比 origin 多 5 个文档提交, 工作区干净 |

## 第 1 步: kb-sync — PASS (Gitea run 210 / job 449)
- 派发: 工作流在 `main` 上运行, pedia 的 tag 放在名为 `ref` 的输入里 (`{"ref":"main","inputs":{"ref":"kb-2026.11.28"}}`)。job 7 步全部 success, 没有被跳过。
- 日志: KB ref `kb-2026.11.28`, A 仓提交 `b2bd837…`, 指纹 `477bac3ce565`, 检测结果 changed → 构建候选。
- 判定 (日志的 gate 行与候选目录里的 `kbsync_gate.json` 一致):

| 判据 | 基线 (线上镜像 `2b24d53` + 线上数据副本) | 候选 | 预演 |
|---|---|---|---|
| 题数 | 140 | 140 | 140 |
| 满分题数 | 138 | 137 | 137 |
| avg | — | 0.9881 | 0.9881 |
| 逐题回退 | — | 1 题: q76 | q76 |
| 上升 | — | 无 | 无 |
| verdict | | **PASS** (chromadb 1.5.9) | PASS |

- 回退的 q76 就是预演里那一题 (model/06 的 6.6 节标题按 PDF 改名, 节级 gold 用 `$` 精确匹配旧标题)。结果与预演完全一致, 余量为零但没有出现第二题波动。
- 候选: `chroma_cand_477bac3ce565` (stamp 4333 条) / `meta_cand_477bac3ce565` (`meta.yaml` sha256 `b484d49e…`, `model_defhome` 75 条)。线上未动。

## 第 2 步: 「KB 更新」提交 `f798709` (带 `[skip ci]`)
- submodule → `kb-2026.11.28`: gitlink = 提交 `b2bd837…` (不是 tag 对象), 树哈希相符; `kbsync.py fingerprint` = `477bac3ce565aa810c38aeb14a35bf22f2c760c13a7e0b5f7d3bcf6ee24e3236`; `check_index_freshness` 升级后先报 STALE。
- 本机 `scripts.ingest` (自动备份旧索引到 gitignored 的 `data/chroma_backup_20261127T162542Z`) + `scripts.build_meta`: 4333 chunks (assumptions 487 / chapter 87 / examples 201 / spec 2164 / terminology 1128 / variable_index 234 / model 32), 2,607,334 token, embedding ≈ $0.052; 被截断的超长 chunk 18 个 (都是 terminology, 与旧 KB 相同)。之后 freshness OK。
- **`data/meta/meta.yaml` 与 kb-sync 候选逐字节相同**: 两边 sha256 都是 `b484d49ef76cc8d5246f68ff2761c49ba70976ca8071fcce78ab922c3078f5c5`。
- 改动清单 (12 个路径, 对照清单 v6):

| 路径 | 改动 | 清单 v6 |
|---|---|---|
| `vendor/sdtm-pedia` | `7819398` → `b2bd837` | 第 6 条第 4 步 |
| `data/meta/meta.yaml` | `model_defhome` 62 → 75 (新增 15 / 移除 REFID、SPEC / 改归属 APID、EPOCH、MIDS、TAETORD); DM `RFSTDTC`、`RFENDTC` type → Char | 第 4、5 条 |
| `tests/test_base.py` | TA Mermaid 20 → 24 (函数名、docstring、断言) | 第 3 条 计数 |
| `tests/test_chapters.py` | ch02 H2 9 → 8; ch04 47 → 45 (两处, 其一连函数名) | 第 3 条 计数 |
| `tests/test_examples.py` | PC 6 条: 块数 14 → 15; 4 条只约束合并例 14 块 (按 `section != 'PC – Examples'` 区分, 先断言 14 + 1); `PC – Examples` 块三元组 == (None, None, None) | 第 3 条 PC |
| `tests/test_build_neo4j.py` | Variable 1546、ModelChapter 5、model-only 23、DEFHOME 75、ModelChapter 集合加 `model/04`、APID → `model/04` + 行数 75; 两条行内注释同步 | 第 3 条 R4 |
| `tests/test_reconcile_neo4j.py` | Variable 1546、ModelChapter 5、DEFHOME 75 | 第 3 条 R4 |
| `tests/test_meta_store.py`、`tests/test_structured_lookup.py` | EPOCH → `model/02` | 第 3 条 R4 |
| `eval/test_set_v3.yml` | gold 5 处: q39 `expected_sources` 加 `domains/FA/assumptions.md`; q117 / q120 fact; q126 删 any-of 成员; q76 换新节标题 | 第 2 条 (都已由主人裁定) |
| `README.md`、`README_CN.md` | 第一节里写死的 KB tag `kb-2026.11.25` → `kb-2026.11.28`, 各 1 处 | 第 4 条 |

- 与预演 probe 对照: gold 文件与 `kb_rehearsal_gold_variants.py` 生成的 goldnext 题集**逐字节相同**; 测试文件与 `kb_rehearsal_apply_anchors.py` 打出的版本相比, 断言行逐行相同, 只多了函数名 / docstring / 注释的同步 (清单要求的)。
- 清单列为可选而**没有做**的: `scripts/build_neo4j.py` 文件头与 DEFHOME 注释里的过期数字 (1541 / 18 / 62)。原因: 这次提交不动 `scripts/` (候选由不含本提交的 main 构建, 保持运行时代码零差异)。已记入 `todo_later`。
- gold 工具: `gold_semantics_diff` 改前、改后各一趟, 都是 15620 格 / 0 mismatch / docstring 33 行不变。该工具拆仓后直接跑会失败 (`cwd=ROOT.parent` 不再是 git 仓库), 这次用环境变量绕过, 没有改代码 (见「发现」第 2 条)。`eval/lint_gold.py` 对 CDISC 题集不适用 (节级 gold 抛 `ValueError`; 它只建模 study 卡), CDISC 侧同一职责由 `tests/test_section_gold_exists.py` 承担 (通过); study 题集这次没有改。
- 本机验收:

| 项 | 结果 |
|---|---|
| `pytest -m "not slow"` | **2995 passed / 0 failed / 2 skipped** (与 `2b24d53` 时的总数相同)。预演里没法跑的 `test_validate_study_endpoint.py::test_create_app_boots_through_lifespan` 首跑通过 |
| CDISC 140 题 | 138 满分 / avg 0.9917, 非满分 q38 (0.333)、q126 (0.5); q39 = 1.0 (3/3)、q76 = 1.0。与预演「全部修订」一行逐题 recall 全同; top5 有 2 题不同 (q39、q105), 是两次入库各自算 embedding 的波动 |
| study 51 条 | avg 0.875, 满分 45; 与升级前本机那一趟逐题 recall 全同 |

- 独立审查 (规则 D): `oh-my-claudecode:critic` 对暂存 diff 审查, **PASS** (MINOR 3, 都不涉及本次提交), 见 `kb_update_2026.11.28_review.md`。
- pre-commit 红线闸: 11 个文件 CLEAN。

## 推送前检查
范围: `git diff e26db1d..f798709` 的新增行 (36 个文件, 30955 行, 大头是预演的评测 JSON) + 6 个待推送提交的提交信息。
| 口径 | 命中 |
|---|---|
| home 路径 (`/Users/`、`/home/<名>`) | 0 |
| 邮箱 (提交信息正文与新增行; `noreply@anthropic.com` 除外) | 0 |
| 本机账号名、`pyproject.toml` authors 里的名字 | 0 |
| 密钥形状 (`sk-` / `sk-ant-` / `tvly-` / `ghp_` / `github_pat_` / `AKIA` / `xox*-` / `PRIVATE KEY` / `Bearer …`) | 0 |
| 口令赋值 (`password=` / `token=` / `secret=` / `api_key=` 后跟字面量)、`curl -u 名:字面量` | 0 |
| Gitea 登录口令原值 (从凭据库取出后只比对、不打印) | 0 |
| 不拦截、只计数: 不含用户名的机器路径 9 行 (都在另一会话写的预演文档里); 内网 IP 0 行; `bojiang.org` 1 行 | — |
- 说明: 提交**元数据**里的作者邮箱与已公开的全部历史提交相同, 不在提交信息正文里, 没有当作拦截项; 已在阶段汇报里向协调方说明。
- 最后那次文档提交 push 前按同一口径再扫一遍 (结果见文末)。

## 第 3 步: push
- `git push origin main`: Gitea 与 GitHub 都是 `e26db1d..f798709` (非强推); 两个远端的 main = `f798709476b75bfb8959cd1d0ca4b252cc122c5e`。
- 推后观察 85 秒: 没有被这次 push 触发的 `sdtm-rag` 运行 (顶端提交带 `[skip ci]`)。

## 第 4 步: 只构建 + 测试端口
- 只构建: run 211 / job 450 (tag 空, deploy=false) success; CI 测试 2936 passed / 61 skipped (CI 无研究数据与索引); 镜像 `f798709…` digest `sha256:8d1ce749…`; 部署类步骤全 skipped; `deploy_public` (job 451) skipped。
- 测试端口 (`kb_update_testport_f798709.sh`): 新镜像 + **候选 chroma / meta 的副本** (挂法照 `kbsync._app_run`), 对照是线上镜像 `2b24d53` + 线上数据的副本。候选原件和线上目录只被 `cp` 读, 没有被任何 chromadb 打开; 副本放在数据根之外, 结束后删除。

| 判据 | 新镜像 + 候选数据 | 线上镜像 + 线上数据副本 (对照) |
|---|---|---|
| freshness | OK, 指纹 `477bac3ce565…`, 4333 条 | OK, `f863e45445a6…`, 4329 条 |
| 容器里读到的 meta | `model_defhome` 75, EPOCH → `model/02` (副本与候选原件 sha256 相同) | 59, EPOCH → `model/03` |
| CDISC 140 题 (各用镜像里的题集) | 138 满分 / avg 0.9917, 非满分 q38、q126; **与预演「全部修订」逐题 recall 全同** | 138 / 0.9917, 与预演基线逐题全同 |
| study 51 条 | avg 0.875, 满分 45 | 相同; **新旧逐题 recall 全同** |
| 集合条数 | `sdtm_kb_v1` 4333, `study_st01` 959, `study_st01_docs` 125 | 4329 / 959 / 125 |
| `/api/ask` | 正常 (有回答、来源、路由) | — |
| `/api/info` | 19 个键, 与对照的键集相同; 无 tier / providers / quota | 同 |

- 线上不受影响: 验证前后线上容器都是 `2b24d53`、启动时间不变, 线上 stamp 不变。
- study 的 top5 (不是判据, 如实记录): 新旧两边有 3 题的 `top5_sources` 不同, recall 相同。对照实验见「发现」第 1 条, 结论是趟间波动, 不是这次升级引入的。预登记判据 (PLAN P0.2: recall 相差不超过 1 题) 满足。

## 第 5 步: 正式部署 — run 212 / job 452 success
- 派发: tag = `f798709476b75bfb8959cd1d0ca4b252cc122c5e` (取自 run 211 的 `head_sha`), deploy=true, 没有用 `force_data_mismatch`。只构建与部署之间没有 push。
- 预检: `{"prod_fp12": "f863e45445a6", "target_fp12": "477bac3ce565", "decision": "swap", "source_chroma": "chroma_cand_477bac3ce565", "source_meta": "meta_cand_477bac3ce565"}` —— 是「换入候选」, 不是 same。部署前线上镜像 `2b24d53`。
- 换数据: `swapped: true`, ts `20261127T164455Z`; 健康检查 200; 新鲜度检查 OK; 收尾 `finished: true`, prune 保留 1 份旧副本、没有删除任何东西。失败退回类步骤都 skipped。
- `deploy_public` (job 453) skipped; `sdtm-rag-public-api` 仍 Exited (镜像 `099c2c9`)。

部署后核查 (`kb_update_snapshot.sh` 部署前后各一次 + 容器内检查):
| 项 | 结果 |
|---|---|
| 线上镜像 | api / ui = `f798709…`, api healthy |
| `check_index_freshness` (容器内) | OK, `477bac3ce565…` |
| 线上 stamp | 指纹 `477bac3ce565aa81…` / 4333 条 = 候选 (目录 inode 就是原候选目录) |
| 集合条数 | `sdtm_kb_v1` 4333; `study_st01` 959、`study_st01_docs` 125 (不变) |
| 线上 meta | `meta.yaml` sha256 `b484d49e…` (= 候选 = 仓库里提交的那份), `model_defhome` **75**, EPOCH → `model/02`; `implicit_relations.json` 不变 (`c3dbe292…`) |
| 旧数据 | `chroma_prev_f863e45445a6_20261127T164455Z` (stamp `f863e454…` / 4329) + `meta_prev_f863e45445a6_20261127T164455Z` (`abfa9815…`, 59 条) |
| 数据根 | 无 `kbsync_swap.json`、无 `kbsync_guard_*`; 2026-11-26 的 `*_failed_c5ef769965fd_*` 原样保留 |
| LAN | `/api/health` 200; `/api/info` 无 tier / providers / quota, `chunk_count` 4333, `index_fresh` True |
- 备注: 线上 `chroma/` 里带着候选时期的 `kbsync_gate.json` 与 `kbsync_eval/` (闸的两份评测结果)。这是换入的正常结果; 下次 kb-sync 复制生产 chroma 时会跳过这两项 (`prepare` 的 ignore)。

## 第 6 步: 回滚办法
- **整体回滚到升级前**: 手动运行 `sdtm-rag` 工作流, `tag=2b24d53ec7047ed37070b9e53f54995f091fcf76`, deploy=true。该镜像的 KB 指纹 (`f863e454…`) 与线上不同, 预检会选中 `chroma_prev_f863e45445a6_20261127T164455Z` / `meta_prev_f863e45445a6_20261127T164455Z` 换回 (study 集合没变过, 非 KB 集合核对应通过); 当前数据会被留成 `chroma_prev_477bac3ce565_<ts>`。不需要 `force_data_mismatch`。
- 旧副本保留规则: 部署成功后只留最新 2 份 `chroma_prev_*`。再发两次会换数据的版本之后, 上面这份会被清掉, 届时回滚到 `2b24d53` 需要重新对 `kb-2026.11.25` 跑 kb-sync。
- 本仓回退: `git revert f798709` (会连同 submodule 指针、meta、锚点、gold 一起退回), 再走只构建 → 测试端口 → 部署。
- 本机开发索引: 升级前的备份在 gitignored 的 `data/chroma_backup_20261127T162542Z`。

## 发现 (都没有在本次处理, 记入 `todo_later`)
1. **先例测试端口脚本的 top5 比较是空比较。** `step_1.9_testport_36499a7.sh`、`p3_merge_seg{1,2}_testport_*.sh` 里用 `r.get("top5") or r.get("retrieved_sources")` 取检索列表, 而评测结果的键是 `top5_sources`, 两边取到的都是 `None`。所以前三次上线记录的「逐题 0 差」实际只比了 `source_recall` (规则 6 成因 A: 抽取端取空)。recall 层面的结论不受影响。这次的脚本已改用 `top5_sources` (`r["…"]` 取值, 键不存在会直接报错)。我第一趟跑的也是错键版本, 改正后重跑了一趟, 上文数字取自第二趟。
   - 改正后看到的真实情况: CDISC 新旧 KB 之间 top5 有 71 题不同 (与预演相同, KB 内容变化后的正常重排); study 新旧之间 3 题不同。
   - study 的对照实验 (本机, 输出只在 gitignored 的 `data/study/st01/eval/runs/kb_update_20261128_{pre,post}/`): 8 趟 (升级前 1 趟、升级后 3 趟、只换回旧 chroma 1 趟、只换回旧 KB 1 趟、新旧都换回 2 趟) 的 recall 逐题全同; `top5_sources` 两两之间有 0–5 题不同, **配置完全相同的两趟之间就有 4 题不同**, 差异不跟 chroma 也不跟 KB 走, 出现过差异的共 6 题。域码扩写器 (它读 CDISC 的 meta 与 KB) 对 51 题追加的后缀新旧完全相同, 已排除。机制没有再往下查 (疑似 query embedding 的微小波动经 RRF 融合放大), 留作后续。对照实验用的旧索引副本与 study 评测日志 (含题目文本) 放在会话临时目录, 做完已删除; 评测结果 JSON 留在上面那两个 gitignored 目录。
2. `eval/tests_support/gold_semantics_diff.py` 拆仓后直接跑会失败: `load_old_impl` 在 `cwd=ROOT.parent` 下执行 `git show`, 那里已不是 git 仓库。绕过办法见复跑命令; 修法是把 `cwd` 改成 `ROOT`。
3. `scripts/build_neo4j.py` 文件头与 DEFHOME 注释里的 1541 / 18 / 62 过期 (现为 1546 / 23 / 75)。
4. kb-sync 的闸这次余量为零地通过。gold 5 处修订已随本次部署进入线上镜像, 下一次 kb-sync 的基线题集就是新 gold (基线满分 138, q76 不再占用容错名额)。

## 一并登记 (已经发生的事实, 由协调方转述; 本会话没有核实)
- **公开站地址**: 主人 2026-11-27 定为 `sdtm.bojiang.org` (取代此前文档里举例的 `ask.<域名>`; 域名仍是 `bojiang.org`)。
- **公开站的 key**: 主人 2026-11-27 已把公开站 `.env` 里的 Anthropic key 和 OpenAI key 都换成单独的新 key。协调方只读核对过两者与私有站不同, 没有验证可用性; 主人说 Anthropic 的 workspace 月上限和 OpenAI 的项目硬上限都已设 (金额没说, 协调方看不到后台)。
- **Cloudflare Pages 的 watch paths** (原 `todo_later` 一项): 已完成。主人让协调方直接设置, 2026-11-27 通过 Cloudflare API 把 `sdtm-pedia` 项目的 Include paths 从 `release/v1.0/**`、`*`、`web/**` 改成 `web/*`、`releases/v1.4/*`, Exclude 为空; 2026-11-28 pedia 的一个纯文档推送已被这条规则跳过构建 (验证生效)。

## 复跑命令
```sh
R=<本仓根>; cd $R; PY=.venv/bin/python
# Gitea API (账号与口令取自 git credential, 不写进任何文件; 下面用占位符)
API=https://git.bojiang.org/api/v1/repos/bojiang/sdtm-rag
curl -u <账号>:$P -H 'Content-Type: application/json' -X POST $API/actions/workflows/kb-sync.yml/dispatches -d '{"ref":"main","inputs":{"ref":"kb-2026.11.28"}}'
curl -u <账号>:$P -H 'Content-Type: application/json' -X POST $API/actions/workflows/sdtm-rag.yml/dispatches \
  -d '{"ref":"main","inputs":{"tag":"<空或40位SHA>","deploy":"false|true","force_data_mismatch":"false"}}'
curl -u <账号>:$P $API/actions/runs/<run>/jobs; curl -u <账号>:$P $API/actions/jobs/<job>/logs
# 本机「KB 更新」
(cd vendor/sdtm-pedia && git fetch --depth 1 origin tag kb-2026.11.28 && git checkout kb-2026.11.28)
$PY deploy/kbsync/kbsync.py fingerprint --kb-root vendor/sdtm-pedia/knowledge_base      # 477bac3ce565…
$PY -m scripts.check_index_freshness; $PY -m scripts.ingest; $PY -m scripts.build_meta; shasum -a 256 data/meta/meta.yaml
GIT_DIR=$PWD/.git $PY -m eval.tests_support.gold_semantics_diff                          # 改 gold 前后各一趟
$PY -m pytest -m "not slow" -q -o addopts="" -rs
$PY -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output <临时目录>/cdisc.json
$PY -m eval.run_eval data/study/st01/eval/test_set_study_v2.yml --retrieval-only --hybrid --study-lookup --collection study_st01 \
  --kb-root data/study/st01/cards --output data/study/st01/eval/runs/<tag>/study48.json   # 输出只放 gitignored 处
# 与预演对照 (临时目录路径里要含 scratchpad, probe 才肯写)
git archive e26db1d tests eval/test_set_v3.yml | tar -x -C <临时树>
$PY -I .work/10_split_and_public/evidence/probes/kb_rehearsal_apply_anchors.py <临时树>; diff -r <临时树>/tests tests
$PY -I .work/10_split_and_public/evidence/probes/kb_rehearsal_gold_variants.py <临时树>/eval/test_set_v3.yml <输出目录>; diff <输出目录>/test_set_v3_goldnext.yml eval/test_set_v3.yml
# 「发现」第 1 条的对照实验 (本机; study 输出只放 gitignored 的 data/study/st01/eval/runs/<tag>/, 做完删掉临时副本)
OLDC=<临时目录>/chroma_old_copy; cp -c -R data/chroma_backup_20261127T162542Z $OLDC        # 升级前索引的副本 (含 study 集合, 不要留在临时目录)
OLDK=<临时目录>/kb_old; mkdir -p $OLDK; git -C vendor/sdtm-pedia archive 78193989f384661512f1d98defbf54db44b2bdeb knowledge_base | tar -x -C $OLDK
ST() { $PY -m eval.run_eval data/study/st01/eval/test_set_study_v2.yml --retrieval-only --hybrid --study-lookup --collection study_st01 \
  --kb-root data/study/st01/cards --output data/study/st01/eval/runs/<tag>/$1.json; }
ST study48; ST study48_r2; ST study48_r3                                                    # 升级后同配置 3 趟
SDTM_RAG_CHROMA_DIR_OVERRIDE=$OLDC ST factor_oldchroma_newkb                               # 只换回旧索引
SDTM_RAG_KB_ROOT_OVERRIDE=$OLDK/knowledge_base ST factor_newchroma_oldkb                   # 只换回旧 KB
for i in 1 2; do SDTM_RAG_CHROMA_DIR_OVERRIDE=$OLDC SDTM_RAG_KB_ROOT_OVERRIDE=$OLDK/knowledge_base ST ctl_old_old_r$i; done   # 新旧都换回, 同配置 2 趟
# 比较: 每份结果按题取 source_recall 与 top5_sources, 两两数不同的题数 (升级前那一趟 = 升级 submodule 之前用同一条命令跑的)
$PY - <<'PYEOF'
import json, itertools, glob
R = {p.split('/')[-1][:-5]: {x['id']: x for x in json.load(open(p))['results']} for p in sorted(glob.glob('data/study/st01/eval/runs/<tag>/*.json'))}
for a, b in itertools.combinations(R, 2):
    print(a, b, 'recall 不同', sum(R[a][q]['source_recall'] != R[b][q]['source_recall'] for q in R[a]), 'top5_sources 不同', sum(R[a][q]['top5_sources'] != R[b][q]['top5_sources'] for q in R[a]))
PYEOF
# 域码扩写器后缀比对 (新旧 meta × 新旧 KB; 只比追加的 CDISC 域名后缀, 不打印题目)
git show e26db1d:data/meta/meta.yaml > <临时目录>/meta_old.yaml
$PY - <<'PYEOF'
from pathlib import Path
from server.meta_store import MetaStore
from server.structured_lookup import StructuredLookup
from server.domain_expand import DomainExpander
from server.config import settings
from eval.run_eval import load_test_set
qs = {q['id']: q['question'] for q in load_test_set('data/study/st01/eval/test_set_study_v2.yml')}
def ex(meta, kb):
    st = MetaStore(Path(meta)); e = DomainExpander(st, StructuredLookup(Path(kb), st))
    return {i: e.expand(q)[len(q):] for i, q in qs.items()}
new = ex(settings.meta_path, settings.kb_root)
for name, m, k in (('旧 meta + 新 KB', '<临时目录>/meta_old.yaml', settings.kb_root), ('旧 meta + 旧 KB', '<临时目录>/meta_old.yaml', '<临时目录>/kb_old/knowledge_base'), ('新 meta + 旧 KB', settings.meta_path, '<临时目录>/kb_old/knowledge_base')):
    print(name, '后缀不同的题:', [i for i, s in ex(m, k).items() if s != new[i]])      # 实测三组都是 []
PYEOF
# 测试端口 / 快照 (在 VM 内执行)
cat .work/10_split_and_public/evidence/checkpoints/kb_update_testport_f798709.sh | ssh <mini 主机> 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- bash -s'
cat .work/10_split_and_public/evidence/checkpoints/kb_update_snapshot.sh         | ssh <mini 主机> '…同上…'
```

## 小结 (规则 C)
- **保留下来的做法**: 预演把每个数字和每处改动都预先定死 (清单 v6 + probe), 正式执行时用 probe 生成对照版本做 `diff`, 「提交 = 预演验过的那一套」可以机械核对; kb-sync 候选与本机 `meta.yaml` 用 sha256 对齐; 测试端口按 `kbsync._app_run` 的挂法同时换 chroma 与 meta, 并在容器里读回 stamp / 条数 / `model_defhome` 证明没有挂错; 部署前后用不含 mtime 的快照做 diff。
- **必须补上的缺口**: 比较脚本取值要用会报错的取法 (`r["键"]`), 不要 `get(...) or get(...)` —— 这次和前三次都被它骗过; study 检索 top5 的趟间波动机制没有查清; `gold_semantics_diff` 在拆仓后的路径假设要修; 公开实例的 KB 更新腿 (D1–D8) 还没实现, 公开 chroma 现在落后于私有。
- **关键决策复盘**: (1) `scripts/build_neo4j.py` 的过期注释没有随这次提交改, 换来候选与部署镜像的运行时代码零差异; (2) 把「KB 更新」做成单独一个提交先推, 文档放在部署之后的另一个提交, 镜像 tag 因此就是「KB 更新」提交本身; (3) 发现 top5 比较是空比较后, 改脚本重跑了一趟测试端口并做了对照实验, 而不是只在记录里注明 —— 多花约 10 分钟, 换来「study 那 3 题不同」有据可查。

## 收尾文档提交的推送前检查 (同一口径, 范围 = 本提交)
这次扫描是在追加本节之前做的: 1 个提交, 9 个文件, 新增 367 行。拦截类口径的命中共 3 行, **全部是本文件「推送前检查」一节里列举口径的那三行自己** (写着 `/Users/`、`sk-`、`curl -u 名:字面量` 这些模式名), 没有真实的 home 路径、密钥或口令; Gitea 口令原值 0 命中; 账号名 / 真名 0 命中; 提交信息正文里没有邮箱。追加本节后对已推送的提交复扫 (新增 376 行): 多出来的命中只有本段这一行 (同样是在引用模式名), 结论不变。
不拦截、只计数: 内网 IP 2 行 (脚本里的镜像仓库地址, workflow 里早已公开); 不含用户名的机器路径 15 行; `bojiang` 11 行 (公开站地址 `sdtm.bojiang.org`、域名、Gitea API 地址与镜像仓库路径)。

## 结束状态
- `git status -sb`: `## main...origin/main`, 工作区干净; main = origin/main (Gitea 与 GitHub 相同), sha 见本提交。
- 线上镜像对应提交 `f798709476b75bfb8959cd1d0ca4b252cc122c5e`; 其后只有带 `[skip ci]` 的文档提交。
- submodule `vendor/sdtm-pedia` = `b2bd837` (`kb-2026.11.28`)。
