# KB 发版预演: pedia 本地 KB (Tier B) 入库 + CDISC 140 题闸 (2026-11-27)

**结论: 闸 FAIL (6 题回退 > 1); 另外新 KB 下 pytest 有 30 个与 KB 相关的失败 (见「新 KB 下的 pytest」)。根因不在检索、也不在 gold, 而在 B 仓 `scripts/build_meta.py` 的 CT 码解析与 pedia 新的 CT 单元格写法不兼容。**
反事实 (只在临时副本里给 `_split_ct` 加一行剥前缀) → 140 题与基线逐题一致, 闸 PASS。
⚠ 未经独立审查 (本轮任务限定不开子代理, 规则 D 待补)。

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
- pedia `44fb042` (S-CT 批次) 把 63 个 spec.md 的 570 个 CT 单元格从 `C66769` 改成 `(AESEV) C66769` (照 PDF 加 codelist 短名)。
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

### 修复可先上线 (已验证向后兼容)
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
对照组 (同样的树, 旧 KB 加 tracked meta): **1 failed** (`test_p2_seam_characterization`, 新旧 KB 下都失败, 是临时树的环境因素, 与 KB 无关)。
新 KB: **31 failed / 2866 passed / 61 skipped** → **与 KB 相关的失败 30 个**。CI 测试步会用升级后的 submodule, 所以现在直接推 submodule 升级, CI 会在测试步失败, 不会部署。

| 类别 | 失败测试 | 根因 |
|---|---|---|
| ① CT 码解析 (同上文根因) | test_build_meta ×2 (`multi_code_variable_end_to_end`, `variables_present_and_ct`)、test_build_neo4j ×4 (node/edge counts, uses_ct, variable split)、test_graph_validator ×3、test_graph_validator_e2e、test_graph_engine、test_graph_answer、test_meta_store ×4 (ctcode / codelist)、test_structured_answer ×2、test_run_eval_judge (graph parity)、test_reconcile_neo4j | `ct_codes` 588 → 0 |
| ② **model_defhome 失效 (检索闸量不到的第二个问题)** | test_build_meta `model_defhome`、test_meta_store `model_defhome_map` (KeyError EPOCH)、test_build_neo4j `defhome_edge_shape` (KeyError APID)、test_structured_lookup `defhome_canary_epoch_six_col_isolation`、test_build_neo4j `class_and_chapter_nodes` (待确认) | `scripts/build_meta.py:134` `_model_defhome` 只保留「6 列定义表只出现在一个 model 文件」的变量。S-MOD2 (`6f2c38a`, model/02 Findings 表 16→100 行) 和 S-MOD1 之后, EPOCH / TAETORD / MIDS (原属 model/03), APID / REFID / SPEC (原属 model/06) 在多个文件里都有 6 列行, 于是被剔除; 另外新增 11 个变量 (VISIT / VISITNUM / VISITDY 等, 归到 model/02)。这会影响概念定义通道 (D 通道, 「EPOCH 是什么」一类问题), 而 140 题里没有题依赖它, 所以闸没报 |
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
