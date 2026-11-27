# KB 发版预演: pedia 本地 KB (Tier B) 入库 + CDISC 140 题闸 (2026-11-27)

**结论: 闸 FAIL (6 题回退 > 1); 另外新 KB 下 pytest 有 30 个与 KB 相关的失败 (见「新 KB 下的 pytest」)。根因不在检索、也不在 gold, 而在 B 仓 `scripts/build_meta.py` 的 CT 码解析与 pedia 新的 CT 单元格写法不兼容。**
反事实 (只在临时副本里给 `_split_ct` 加一行剥前缀) → 140 题 source_recall 与基线逐题一致 (top5 排序因 KB 变化有 67 题不同), 闸 PASS。
✅ 已独立审查 (oh-my-claudecode:critic, PASS-with-fixes, 见 `kb_rehearsal_bf33bab_review.md`; 修订见文末 v2 修订)。

## 输入与有效性

| 项 | 值 |
|---|---|
| 候选 KB | `/Volumes/DevSSD/Project/sdtm-pedia/knowledge_base` (只读), pedia HEAD `00a2e93`, 工作区 KB 无未提交改动 |
| KB 指纹 开始 / 结束 | `bf33babcfd29…` (2026-11-27T00:59:34Z) / `bf33babcfd29…` (01:03:48Z, 晚于全部评测) → **一致, 预演有效** |
| 基线 KB | submodule `kb-2026.11.25`, 指纹 `f863e45445a6…` (= 开发 chroma stamp) |
| 规模 | 4329 → 4332 chunks; chapter 90→87, assumptions 476→487, examples 209→200, model 28→32, 其余不变; 2,603,011 token, embedding ≈ $0.052 |
| 开发数据未动 | `data/chroma/chroma.sqlite3`、stamp、`data/meta/meta.yaml` 前后 sha256 一致; `git status` 干净 |

### override 的生效方式 (重要)
- `SDTM_RAG_KB_ROOT_OVERRIDE` 对 ingest / build_meta / eval 都生效。
- `SDTM_RAG_CHROMA_DIR_OVERRIDE` **只对 server/eval 的 `settings.chroma_dir` 生效**; `scripts/ingest.py` 的 `CHROMA_DIR`、`scripts/build_meta.py` 的输出、`settings.meta_path` 都按代码文件位置算 (`<代码根>/data/...`)。
  在主仓只设环境变量跑 ingest 会覆盖开发 chroma 和 tracked 的 meta.yaml。
- 所以预演用 `git archive HEAD` 在 scratchpad 展开独立代码树 (`.env` 软链主仓, venv 用主仓; 已断言 `server.config.__file__`、`ingest.CHROMA_DIR`、`settings.meta_path` 全落在副本里)。

## 复跑命令

本次实跑时 KB 直接读 pedia 工作区 (指纹前后一致)。为了以后可复现, 下面把两边都钉死: B 仓 `83f12bb`, pedia `00a2e93` 用 `git archive` 展开 (对 pedia 只读; 展开后指纹已核对 = `bf33bab…`)。

```bash
R=/Volumes/DevSSD/Project/sdtm-rag; S=<临时目录>; PY=$R/.venv/bin/python; export GIT_OPTIONAL_LOCKS=0
mkdir -p $S/kb && git -C /Volumes/DevSSD/Project/sdtm-pedia archive 00a2e93 knowledge_base | tar -x -C $S/kb
P=$S/kb/knowledge_base; $PY $R/deploy/kbsync/kbsync.py fingerprint --kb-root $P   # 必须 = bf33babcfd29…
for t in base cand; do mkdir -p $S/$t; (cd $R && git archive 83f12bb) | tar -x -C $S/$t; ln -s $R/.env $S/$t/.env
  rm -rf $S/$t/data/chroma $S/$t/data/meta; cp -c -R $R/data/meta $S/$t/data/meta; done
cp -c -R $R/data/chroma $S/base/data/chroma; mkdir $S/cand/data/chroma
EV="eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup"
(cd $S/base && SDTM_RAG_KB_ROOT_OVERRIDE=$R/vendor/sdtm-pedia/knowledge_base $PY -m eval.run_eval $EV --output $S/baseline.json)
(cd $S/cand && export SDTM_RAG_KB_ROOT_OVERRIDE=$P && $PY -m scripts.ingest --no-backup && $PY -m scripts.build_meta \
  && $PY -m eval.run_eval $EV --output $S/candidate.json)
# 判定: 复用 kbsync 的函数 (regressions / _load_recall / _load_avg), 不手写对比
(cd $R && $PY -c "import sys;sys.path.insert(0,'deploy/kbsync');import kbsync as k;from pathlib import Path as p
b=k._load_recall(p('$S/baseline.json'));c=k._load_recall(p('$S/candidate.json'));print(k.regressions(b,c))")
# 反事实: 复制 cand 的 chroma 到第三棵树 cf, 在 cf/scripts/build_meta.py 的 _split_ct 循环里加
#   tok = re.sub(r"^\([A-Z0-9_]+\)\s+(?=C\d+$)", "", tok)
# 再跑 build_meta + 同一条 eval
```

## 结果 (按 kbsync gate 五项)

| 判据 | 基线 | 候选 (原样) | 反事实 (修解析) |
|---|---|---|---|
| 题数 / 题集一致 | 140 | 140 ✓ | 140 ✓ |
| source_recall_avg (≥ 0.95) | 0.9917 | 0.9702 ✓ | 0.9917 ✓ |
| 满分题数 (≥ 基线−1 = 137) | 138 | **132 ✗** | 138 ✓ |
| 逐题回退 (≤ 1) | — | **6 ✗** | 0 ✓ |
| 候选 stamp 指纹 = bf33bab… | — | ✓ | ✓ |
| **verdict** | | **FAIL** | PASS |

基线复现了已知结果 (0.9917, <1 只有 q38 / q126), 环境可信。

### 逐题差异 (其余 134 题逐题相同; 反事实 140 题全部与基线相同)

| 题 | 基线 | 候选 | 反事实 | 未召回的 gold | gold 文件在 tag..00a2e93 是否改动 |
|---|---|---|---|---|---|
| q16 AESEV | 1.0 | 0.5 | 1.0 | `terminology/core/ae.md` | 否 |
| q43 SEX | 1.0 | 0.5 | 1.0 | `terminology/core/dm.md#Sex$` | 否 |
| q96 FATEST | 1.0 | 0.5 | 1.0 | `terminology/core/findings_about.md` | 否 |
| q98 CMDOSU | 1.0 | 0.5 | 1.0 | `terminology/core/general_part5.md` | 否 |
| q99 QSCAT | 1.0 | 0.5 | 1.0 | `terminology/core/qs_part1.md` | 否 |
| q101 TSPARM | 1.0 | 0.5 | 1.0 | `terminology/core/trial_design.md` | 否 |

## 回退分类

**6/6 = B 仓解析器不兼容 (不是检索不到原文, 也不是 source gold 漂移; 140 题 retrieval 闸的 source gold 这次无需改)。**
- pedia `44fb042` (S-CT 批次) 把 570 个 CT 单元格 (实测分布在 59 个 spec.md; 提交说明写 63 个, 应含只改 DOMAIN 的文件)从 `C66769` 改成 `(AESEV) C66769` (照 PDF 加 codelist 短名)。
- `scripts/build_meta.py:43` `_CT_CODE_RE = ^C\d+$` 匹配不上 → meta.yaml 里 `ct_codes` 由 **588 → 0**, 全部落进 `ct_dict` (952 条)。
- structured lookup 走「问句变量 → `MetaStore.ct_codes_for_variable` → terminology 文件」补席位; ct_codes 为空 → 这 6 道「变量的 codelist 是什么」题丢了 terminology 文件。
- 6 个 gold 文件本身零改动; 修解析后逐题回到基线 → 归因闭合。

### 同一根因的其他受影响面 (闸量不到, 需随修复一起处理)
| 位置 | 影响 |
|---|---|
| `server/structured_answer.py:120` | 答案侧「Controlled-terminology codes」事实行消失 |
| `server/graph_validator.py:84,147` / `graph_engine.py:68` | 图校验器按变量取 CT 码 → 全空 (advisory 校验静默失效) |
| `scripts/spec_loader.py:69` `is_ct_code` → `server/validator.py:202` | 私有站 `/api/validate*` 的 CT 校验对全部变量静默跳过 |
| `ct_dict` 语义 | 新增 129 个 `*` 单元格 (如 AECAT/VSCAT, 旧 KB 为空) 和 59 个 DOMAIN 单元格 = 域码 (如 `VS`), 都会被当作「外部字典」token |

其他: DM `RFSTDTC` / `RFENDTC` 的 type 在 meta 里由 DateTime → Char (内容变化, 是否符合 PDF 本轮未核对); codelists 1005 不变; 变量集合不变。
`scripts/chunkers/{variable_index,terminology}.py` 与 `server/rag.py:117` 也用 `^C\d+$`, 但解析的是 VARIABLE_INDEX / terminology 文件, 这两类 chunk 数不变 (234 / 1128), 未见影响。

### 修复可先上线 (仅 `_split_ct` 一行补丁已验证; 见文末 v2 修订第 3 条)
反事实补丁在**旧 KB** (`kb-2026.11.25`) 上生成的 meta.yaml 与 tracked `data/meta/meta.yaml` **逐字节一致** (`cmp` 通过) → 修复可以先于 pedia 打 tag 合进 B 仓 main, 对现生产零影响。
注意: 修复在 `scripts/` → push 会触发部署 (非 `[skip ci]`); kb-sync 候选镜像从 B 仓 main 构建, 所以修复必须先进 main, 否则下次 kb-sync 会 (正确地) FAIL。

## 题集静态核对: fact 级与节级 gold (零费用)

retrieval 闸只看 source gold (路径 / 节), 看不到 `expected_facts` (答案评测与 judge 用)。对新旧 KB 各做一次静态核对:
- **fact**: 每题的 fact 在该题 gold 文件里是否逐字存在 (不分大小写)。466 条 fact 中, **3 条旧 KB 命中、新 KB 不再命中**:

| 题 | fact | gold 文件 | 原因 (pedia 提交) |
|---|---|---|---|
| q39 | `FAOBJ` | `model/02_observation_classes.md` | FA 叙述从 model/02 移到 FA 域文件 (`c8802bf` B-FA "RELOCATE from ch02/model02") |
| q117 | `first 6 columns (STUDYID...QNAM) should be unique` | `chapters/ch08_relationships.md` | 三点改为省略号 `STUDYID…QNAM` (S-TYPO `bc4e42e`) |
| q120 | `Defines which subjects belong to each pool` | `model/06_relationship_datasets.md` | model/06 按 PDF 重写 (`cbc6b75` B-model06) |

- **节级 source gold**: 用两版 KB 的 chunk section 集合重算每条 gold 能否命中。只有 1 条失效: q126 `expected_sources_any` 里的 `model/03_special_purpose_domains.md#Subject Elements (SE)$` — 标题改成 `3.2.3.1 Subject Elements`, 并入 chunk `3.2.3 Subject Summary Domains` (`ed7fd2b` S-MOD1)。同组另一成员 `domains/SE/assumptions.md` 仍可命中, 所以这次分数不变, 但这一成员已是死 gold。
- q38 (`chapters/ch02`, `ch04…#4.1.6 Additional Guidance on Dataset Naming$`) 和 q126 (`domains/TE/spec.md`) 在基线就未命中, 它们在新 KB 里仍然存在 (不是被改名后藏在既有 miss 里)。
- 以上 4 处属于 gold 漂移, 不影响这次 retrieval 闸, 影响答案评测的 fact recall。**本轮不改 `eval/test_set_v3.yml`**: 它在部署路径过滤内, 改了就会部署; 建议随 B 仓解析修复同批改 gold, 并按 CLAUDE.md 先后跑 `python -m eval.tests_support.gold_semantics_diff`。
- 复跑脚本是临时脚本, 未入库。逻辑: fact = 子串 ∈ 拼接后的 gold 文件文本; 节 = 用 `scripts.ingest.collect_chunks()` 取 `{source: [section]}`, 按 run_eval 的 `路径#节[$]` 语义匹配。

## 新 KB 下的 pytest (CI 同款)
命令 (在 `git archive 83f12bb` 展开的树里先 `git init -q`, 因为红线扫描测试要找 `.git`; `data/meta/meta.yaml` 换成新 KB 上未修补的 build_meta 产物, 也就是「KB 更新」流程会提交的那份):
`SDTM_RAG_KB_ROOT_OVERRIDE=<pedia 00a2e93 展开>/knowledge_base .venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rf -p no:cacheprovider`
对照组 (同样的树, 旧 KB 加 tracked meta): **1 failed** (`test_p2_seam_characterization`, 新旧 KB 下都失败, 与 KB 无关; ~~临时树的环境因素~~ → **更正: 主仓 p3 上同样失败, 是日期依赖, 见文末 v2 修订第 2 条**)。
新 KB: **31 failed / 2866 passed / 61 skipped** → **与 KB 相关的失败 30 个**。CI 测试步会用升级后的 submodule, 所以现在直接推 submodule 升级, CI 会在测试步失败, 不会部署。

| 类别 | 失败测试 | 根因 |
|---|---|---|
| ① CT 码解析 (同上文根因) — **16 个** (审查后更正) | test_build_meta ×2 (`multi_code_variable_end_to_end`, `variables_present_and_ct`)、test_build_neo4j ×2 (`uses_ct_domains_property`、`edge_counts` 的 USES_CT 部分)、test_graph_validator ×3、test_graph_validator_e2e、test_graph_engine、test_graph_answer、test_meta_store ×4 (ctcode / codelist / ct_codes union)、test_structured_answer ×2、test_run_eval_judge (graph parity) | `ct_codes` 588 → 0。审查者用补丁 meta + 补丁 build_meta 重跑 31 个失败: 16 个转绿 |
| ② **model_defhome 变化 (检索闸量不到的第二个问题)** — **9 个** (审查后更正) | test_build_meta `model_defhome`、test_meta_store `model_defhome_map` (KeyError EPOCH)、test_structured_lookup `defhome_canary_epoch_six_col_isolation`、test_build_neo4j ×5 (`defhome_edge_shape` KeyError APID、`class_and_chapter_nodes` ModelChapter 多出 model/04、`node_counts` Variable 1544≠1541、`variable_model_only_split` model_only 21≠18、`edge_counts` 补丁后仍报 DEFHOME 64≠59)、test_reconcile_neo4j (ModelChapter 5≠4, Variable 1544≠1541) | 见 `model_defhome_rule_options.md`。EPOCH / TAETORD / MIDS / APID 因多文件被剔除, REFID / SPEC 因 Notes 为空被剔除; 新增 11 个 (8 个 → model/02, RSUBJID / RDEVID / SREL → model/04) |
| ③ KB 计数锚点 / chunker | test_base `mermaid_blocks_ta` (20→24)、test_chapters ×3 (ch04 47→45 等)、test_examples `pc_examples_all_have_cdisc_section_id` (PC 示例 `cdisc_section_id` 为 None) | 前两项多半是 KB 内容按 PDF 改动后的计数变化, 需要逐条确认后更新锚点; PC 示例丢失 `cdisc_section_id` 可能是示例标题格式变了, 要查 chunker |

结论: 修 B 仓时, 这次要同时处理 ① ② ③, 不只是 `_split_ct`。②是设计层面的取舍 (一个变量的定义出现在多个 model 文件时归到哪里), 需要先定规则, 再改代码和锚点测试。

## 给 pedia 的反馈
1. **S-CT 批次 (`44fb042`) 不必在打 tag 前回滚**: 按其提交说明是照 PDF 加 codelist 短名 (本轮未对照 PDF 核对), 下游问题由 B 仓修解析器。请知会: CT 单元格格式是下游契约 (`(短名) Cnnnnn`, 多个用 `; ` 分隔), 以后再改格式先告诉 B 仓。
2. **`*` 单元格 (129 处, 如 AECAT / VSCAT / PCCAT)**: 请确认含义 (PDF 上的星号脚注?), 并考虑在 KB 里给一个可机读的写法或 KB note; 目前下游会当成字典 token。
3. **DOMAIN 的 CT = 域码 (59 处)**: 同上, 下游需要知道这是字面值而非 codelist。
4. S-TYPO (`bc4e42e`) 与其他 Tier B 批次在 140 题 **retrieval 闸**里没有造成回退; 但在 fact 级有 3 条、节级有 1 条 gold 漂移 (见上表)。这些由 B 仓改 gold, 不需要 pedia 改回。
5. 移动内容的批次 (如 B-FA 的 RELOCATE、S-MOD1 的标题改号) 会让下游 gold 失效。打 tag 时在发版说明里列出「移走 / 改名的节」, B 仓就能直接对照修 gold。

## 对 1.9 正例演练的含义
- 若 pedia 先打 tag、B 仓未修: kb-sync 候选必然 FAIL (这正是闸该做的), 候选归档 `chroma_failed_*`, 生产不变。
- 推荐顺序: B 仓修 `build_meta._split_ct` + `spec_loader.is_ct_code` (兼容新旧两种写法) + `_model_defhome` 规则 + 计数锚点 (加单测 + 规则 5 变异验证) → 推 main 部署 (meta 不变) → pedia 打 tag → kb-sync 正例。
- kb-sync 的基线用线上镜像里的题集和代码, 候选用新 checkout 的题集和代码。retrieval 闸的 source gold 本次不用改; 如果同批改了 fact 和节级 gold (见上), 要注意改动的先后: 修 gold 的提交推 main 会部署, 部署后它才进入基线镜像。

## 过程记录
- 开始时有一次对 pedia 的 `git status` 没带 `GIT_OPTIONAL_LOCKS=0`, 可能刷新过 pedia 的 index 缓存 (KB 内容没有变化, 指纹前后一致); 之后所有对 pedia 的 git 命令都带了这个变量。
- 收尾核对 (全部工作完成后): pedia KB 指纹 = `bf33bab…` (2026-11-27T01:16:04Z), `git diff --stat 00a2e93..HEAD -- knowledge_base` 为空; 开发 chroma / stamp / meta.yaml 三个 sha256 与开始时一致; B 仓 `git status` 只有 `.work/` 下的改动, submodule 仍是 `kb-2026.11.25`。


## v2 修订 (2026-11-27, 独立审查后; 与上文冲突处以本节为准)
审查: `kb_rehearsal_bf33bab_review.md` (`oh-my-claudecode:critic`, PASS-with-fixes)。顶部「未经独立审查」一句作废。

1. **pytest 分类更正**: ① 16 / ② 9 / ③ 5 = 30 (原表把 `test_node_counts`、`test_variable_model_only_split`、`test_edge_counts` 的 DEFHOME 部分、`test_reconcile_neo4j` 归进了 ①, 已改到 ②; `test_class_and_chapter_nodes` 结案为 ②)。「新增 11 个变量归到 model/02」更正为 8 个 → 02、3 个 → 04。
2. **对照组那 1 个失败不是临时树的问题, 是日期依赖, 而且会挡住 CI**: `tests/test_p2_seam_characterization.py::test_p2_seam_outbound_calls_and_responses_unchanged` 在主仓 p3 上同样失败; 差异出在 `ask_stream_web_continue` 的 `messages_sha`, 因为 `server/web_search.py:85` 的 `_dt.date.today()` 进了 `[Web: url (retrieved YYYY-MM-DD)]` 标注, 而 golden (`tests/fixtures/p2_seam_characterization.json`) 是 2026-11-26 录的。
   复核: 把 `server.web_search._dt.date.today` 冻结为 2026-11-26 → 2/2 通过; 不冻结 → 1 failed。命令:
   `.venv/bin/python -m pytest -q -o addopts="" -p no:cacheprovider tests/test_p2_seam_characterization.py` (主仓, 1 failed);
   冻结版: `PYTHONPATH=<scratchpad> .venv/bin/python -m pytest ... -p freeze_plugin tests/test_p2_seam_characterization.py` (`freeze_plugin.py` 把 `server.web_search._dt` 换成 `date.today()` 返回 2026-11-26 的替身; 2 passed)。
   **后果: CI 测试步 (`.gitea/workflows/sdtm-rag.yml:74`) 从 2026-11-27 起对任何触发部署的 push 都会失败 → p3 合并 main 会在测试步失败、不部署; §0 的 CT 修复推 main 同样会被挡。修这个日期依赖 (冻结日期或把日期排除出哈希) 是所有后续推 main 的前置条件。** 本轮按范围不改 `tests/` / `server/`。
3. **向后兼容的结论收窄**: 旧 KB 里没有任何 `(短名) C` 写法, `_split_ct` 补丁在旧 KB 上本来就不生效, 所以 `cmp` 一致是必然结果, 证明力弱。它只说明「`_split_ct` 一行补丁在旧 KB 下 meta 不变」; 没覆盖 `spec_loader.is_ct_code`、PC chunker 修复和 `_model_defhome` 规则改动。完整修复要在**旧 KB 与新 KB 下各重跑** `cmp` (meta.yaml)、pytest、两条检索闸。「对 1.9 的含义」里「推 main 部署 (meta 不变)」同样只对 `_split_ct` 成立。
4. **补复跑命令**:
   - 反事实: `S=<scratchpad>/rehearsal; cp -c -R $S/cand/data/chroma $S/cf/data/chroma` (cf 树为 `git archive 83f12bb`, meta 拷自主仓) → 在 `cf/scripts/build_meta.py` 的 `_split_ct` 循环里、`if not tok: continue` 之后加 `tok = re.sub(r"^\([A-Z0-9_]+\)\s+(?=C\d+$)", "", tok)` → `cd $S/cf && SDTM_RAG_KB_ROOT_OVERRIDE=$P $PY -m scripts.build_meta && $PY -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output $S/out/counterfactual.json`。审查者复核: 同环境重跑 build_meta 与 `out/meta_cf_newkb.yaml` 逐字节一致。
   - 向后兼容: `cd $S/cf && SDTM_RAG_KB_ROOT_OVERRIDE=$R/vendor/sdtm-pedia/knowledge_base $PY -m scripts.build_meta && cmp data/meta/meta.yaml $R/data/meta/meta.yaml`。
   - pytest: `mkdir $S/ci && (cd $R && git archive 83f12bb) | tar -x -C $S/ci && cd $S/ci && git init -q && cp $S/cand/data/meta/meta.yaml data/meta/meta.yaml && SDTM_RAG_KB_ROOT_OVERRIDE=$P $PY -m pytest -m "not slow" -q -o addopts="" -rf -p no:cacheprovider`; 对照组同法, 不换 meta, KB 指向 `$R/vendor/sdtm-pedia/knowledge_base`。
   - fact / 节级核对脚本已拷入 `evidence/probes/kb_rehearsal_factcheck.py`、`kb_rehearsal_secdump.py` (节级匹配用 `eval.run_eval` 的匹配语义重算, 结论同上)。fact 核对的局限: 只查 gold 文件里有没有该子串, 而答案评测的 fact recall 是在 LLM 回答里匹配, 所以 q117 的影响是「可能」; 拼接文本未加分隔符, 理论上可能跨文件拼出假命中 (审查者复核结论成立)。
5. **补影响面**: CT 解析坏掉后, 29 道题的 top5 里丢了排第 2 的 terminology 席位; 闸只看得到其中 gold 要求 terminology 的 6 道, 其余 23 道是答案质量风险 (检索闸量不到)。
6. **给 pedia 的反馈第 2 条更正**: `44fb042` 提交说明里已有 "KB note on C-codes", 应先读那份 note 再决定是否还要请 pedia 补 `*` / DOMAIN 单元格的说明。
7. **类别 ③ 逐条查清** (原表「多半 / 可能」已核实):
   - `mermaid_blocks_ta` 20 → 24: pedia `d33674e` B-TA 按 PDF 补到 24 张 Mermaid, 正常计数变化。
   - `test_ch02_splits_by_h2` 9 → 8: 去掉的是 KB 自加 H2 `Findings About — Naming Findings About Domains (Reference Material)`, 内容移到 `domains/FA/assumptions.md §6.4.2` (`c8802bf`), 正常。
   - `test_ch04_*` ×2 47 → 45: 去掉 KB 自加的两节 `§6.1.3.3 … (p115)` / `§6.3.5.7 … RELSPEC … (p261)`, 改为指向 EX / MB examples 的链接 (`42fecd3` S-CH4), 正常; 另 3 个节名按 PDF 改写, 140 题 gold 未引用。
   - **PC `cdisc_section_id` 为 None → 根因是 chunker, 且有内容丢失**: 新 `domains/PC/examples.md` 在 `## §6.3.5.9.3 Relating PP Records to PC Records — Worked Examples` 之前新增 `## PC – Examples` + `### Example 1` (pedia `97e1895` B-PCPP / `f534395` S-SPC2 按 PDF 补回的 PC 浓度示例, 约 45 行含一张表; 另把开头的 *Note* 改成 `> KB note`)。`scripts/chunkers/examples.py` 的 H4 嵌套分支 (`_chunk_h4_nested`) ① 取**第一个** H2 解析 `§` 编号 → `PC – Examples` 无 `§` → None; ② 只为 H4 Method 出块 → 新 Example 1 那 45 行**不进任何 chunk**。全 KB 覆盖率扫描 (每个文件 >30 字符的行是否出现在其 chunk 文本里; 旧 KB 缺 306 行, 新 KB 缺 354 行) 里, 新增缺失全部来自这一个文件 (4 → 47 行)。pedia 的改动符合 PDF, 归入 B 仓 chunker 修复 (向后兼容, 可先合, 见 `kb_upgrade_bundle_checklist.md` §0)。另外 EX / MB / TU 的 examples 首个 H2 也变成了 `§…` 节标题, 它们走的不是 H4 嵌套分支, 覆盖率扫描未见丢内容。
   - 覆盖率扫描脚本: `evidence/probes/kb_rehearsal_coverage.py`。
