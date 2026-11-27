# KB 发版预演 (第二次): pedia 定稿 KB `d46f8af` 入库 + CDISC 140 题闸 (2026-11-27)

**结论: 闸 PASS, 但余量为零。** 140 题里只有 q76 一题回退 (1.0 → 0.5), 原因是 gold 漂移: 这轮 pedia 把 `model/06` 的 6.6 节标题按 PDF 改了名, q76 的节级 gold 用 `$` 精确匹配旧标题, 文件本身仍排在检索第 2 位。闸允许回退 ≤ 1、满分题数 ≥ 基线 − 1, 现在两项都正好踩在线上。
新 KB 下 pytest 失败 18 个, 全部是清单里「随 KB 升级才改」的锚点; 把清单锚点套到临时副本后 0 失败。本机有索引时另有 1 条节级 gold 存在性测试报 q76、q126, 靠 gold 修订消除。没有需要改代码才能过的问题。
q39 加 `domains/FA/assumptions.md` 作必须命中的来源: 实测能召回 (15 席里排第 4, 候选树 5 趟一致), 裁定 (b) 维持。
✅ 已独立审查 (`oh-my-claudecode:critic`, PASS-with-fixes, 见 `kb_rehearsal_477bac3_review.md`); 审查意见已并入正文, 处置见文末「独立审查」。

## 输入与有效性

| 项 | 值 |
|---|---|
| 候选 KB | pedia `d46f8af`, 用 `git archive` 展开到临时目录 (对 pedia 只读)。预演期间 pedia 的 HEAD 又前进到 `c90cb61` (只动 `.work/` 文档), `HEAD:knowledge_base` 的树哈希不变; pedia 两份标题清单文件名里的「HEAD」指的也是这棵 KB 树。KB 树哈希 `git rev-parse d46f8af:knowledge_base` = `63f857774a42cfaa71798705ad40ab51bc5e378a` |
| KB 指纹 (kbsync) | `477bac3ce565aa810c38aeb14a35bf22f2c760c13a7e0b5f7d3bcf6ee24e3236`; 开始 (2026-11-27T04:47Z) 与结束 (04:58Z) 各算一次, 一致 |
| 基线 KB | submodule `kb-2026.11.25`, 指纹 `f863e45445a6…` (= 开发 chroma stamp) |
| B 仓代码 | main `efefb7a`, 用 `git archive HEAD` 展开成独立代码树。`git diff --stat 2b24d53 HEAD` 只有 `.work/` 与 `docs/PROGRESS.md`, 所以运行时代码 = 线上镜像 `2b24d53` (已含 CT 解析、PC 切块、R4) |
| 规模 | 4329 → 4333 chunks; 2,607,334 token, embedding ≈ $0.052 (另有 8 趟 140 题评测的 query embedding: 基线树 3 趟、候选树 5 趟, 可忽略) |
| 开发数据未动 | `data/chroma/chroma.sqlite3`、`ingested_at_commit.txt`、`data/meta/meta.yaml` 三个 sha256 前后一致 (`58565294…` / `fbb3e97b…` / `a2853ff8…`); 仓库 `eval/`、`tests/` 零改动 |

候选确实跑在新 KB 上 (防「override 没生效, 所以 0 差」): 候选 stamp 的 `kb_fingerprint` = `477bac3c…`; chunk 数 4333 ≠ 4329; 候选库里能按新节名 `6.6 Associated Persons Relationships (APRELSUB)` 命中 (见「gold 修订实测」), 旧节名命中不到。

基线用的 meta 是仓库里提交的那份 (`model_defhome` 62 条); 线上 meta 是 59 条 (见 `p3_merge_deploy.md` 第二段)。差的 3 个变量 (DOMAIN / USUBJID / POOLID) 不在 140 题会触发定义通道的题里 (q33 / q73 / q83), 基线结果 0.9917、非满分只有 q38 / q126, 与两段上线时在虚拟机上用线上数据跑的结果相同。

## 复跑命令

```bash
R=/Volumes/DevSSD/Project/sdtm-rag; S=<临时目录>; PY=$R/.venv/bin/python; export GIT_OPTIONAL_LOCKS=0
mkdir -p $S/kb $S/out && git -C /Volumes/DevSSD/Project/sdtm-pedia archive d46f8af knowledge_base | tar -x -C $S/kb
P=$S/kb/knowledge_base; O=$R/vendor/sdtm-pedia/knowledge_base
$PY $R/deploy/kbsync/kbsync.py fingerprint --kb-root $P        # 必须 = 477bac3ce565…
for t in base cand ci ctl; do mkdir -p $S/$t; (cd $R && git archive efefb7a) | tar -x -C $S/$t; ln -s $R/.env $S/$t/.env
  rm -rf $S/$t/data/chroma $S/$t/data/meta; cp -c -R $R/data/meta $S/$t/data/meta; done
cp -c -R $R/data/chroma $S/base/data/chroma; mkdir $S/cand/data/chroma
# 闸 (zsh 下参数要逐个写, 放进变量不会自动拆词)
(cd $S/base && SDTM_RAG_KB_ROOT_OVERRIDE=$O $PY -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output $S/out/baseline.json)
(cd $S/cand && export SDTM_RAG_KB_ROOT_OVERRIDE=$P && $PY -m scripts.ingest --no-backup && $PY -m scripts.build_meta \
  && $PY -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output $S/out/candidate.json)
(cd $R && $PY -c "import sys;sys.path.insert(0,'deploy/kbsync');import kbsync as k;from pathlib import Path as p
b=k._load_recall(p('$S/out/baseline.json'));c=k._load_recall(p('$S/out/candidate.json'))
print(k.regressions(b,c), k._load_avg(p('$S/out/candidate.json')), sum(v>=1 for v in b.values()), sum(v>=1 for v in c.values()))")
# pytest: 对照组 (旧 KB + 提交的 meta) 与新 KB 组 (meta 换成候选的 build_meta 产物); 树里先 git init (红线扫描测试要找 .git)
(cd $S/ctl && git init -q && SDTM_RAG_KB_ROOT_OVERRIDE=$O $PY -m pytest -m "not slow" -q -o addopts="" -rf -p no:cacheprovider)
(cd $S/ci && git init -q && cp $S/cand/data/meta/meta.yaml data/meta/meta.yaml \
  && SDTM_RAG_KB_ROOT_OVERRIDE=$P $PY -m pytest -m "not slow" -q -o addopts="" -rf -p no:cacheprovider)
# 清单完整性: 把清单锚点打到副本再跑, 应 0 failed
PR=$R/.work/10_split_and_public/evidence/probes
cp -c -R $S/ci $S/ci2 && $PY -I $PR/kb_rehearsal_apply_anchors.py $S/ci2 \
  && (cd $S/ci2 && SDTM_RAG_KB_ROOT_OVERRIDE=$P $PY -m pytest -m "not slow" -q -o addopts="" -rf -p no:cacheprovider)
# gold 修订实测: 题集副本只写临时目录
$PY -I $PR/kb_rehearsal_gold_variants.py $R/eval/test_set_v3.yml $S/out      # 生成 q39only / goldnext / q76dual 三份题集
ev() { (cd $S/$1 && SDTM_RAG_KB_ROOT_OVERRIDE=$2 $PY -m eval.run_eval $S/out/test_set_v3_$3.yml --retrieval-only --hybrid --structured-lookup --output $S/out/$4.json); }
ev cand $P q39only  cand_q39only_r1; ev cand $P q39only cand_q39only_r2     # q39 单改, 两趟
ev cand $P goldnext cand_goldnext_r1; ev base $O goldnext base_goldnext      # 五处全改: 新 KB / 旧 KB
ev cand $P q76dual  cand_q76dual;     ev base $O q76dual  base_q76dual       # 做法 B: 新 KB / 旧 KB
# 有索引时的 pytest (本机「KB 更新」的真实形态): 锚点 + 候选 chroma 副本 + goldnext 题集
cp -c -R $S/ci2 $S/ci5 && rm -rf $S/ci5/data/chroma && cp -c -R $S/cand/data/chroma $S/ci5/data/chroma && cp $S/out/test_set_v3_goldnext.yml $S/ci5/eval/test_set_v3.yml \
  && (cd $S/ci5 && SDTM_RAG_KB_ROOT_OVERRIDE=$P $PY -m pytest -m "not slow" -q -o addopts="" -rf -p no:cacheprovider)
# 节级 gold 存在性测试 (需要索引): 旧 KB 索引 + 各题集变体
cp -c -R $S/base $S/b2 && (cd $S/b2 && git init -q && cp $S/out/test_set_v3_q76dual.yml eval/test_set_v3.yml \
  && SDTM_RAG_KB_ROOT_OVERRIDE=$O $PY -m pytest -q -o addopts="" -p no:cacheprovider tests/test_section_gold_exists.py)
# 静态核对 (零费用; 在一棵代码树根运行)
cd $S/ctl
for k in old:$O new:$P; do SDTM_RAG_KB_ROOT_OVERRIDE=${k#*:} $PY $PR/kb_rehearsal_secdump.py $S/out/sec_${k%%:*}.json   # 键是绝对路径, 下一行去掉 knowledge_base/ 之前的前缀
  $PY -c "import json,sys;d=json.load(open(sys.argv[1]));json.dump({k.split('knowledge_base/')[-1]:v for k,v in d.items()},open(sys.argv[2],'w'))" $S/out/sec_${k%%:*}.json $S/out/sec_${k%%:*}_rel.json; done
$PY $PR/kb_rehearsal_secmatch.py eval/test_set_v3.yml $S/out/sec_old_rel.json $S/out/sec_new_rel.json
$PY $PR/kb_rehearsal_factcheck.py eval/test_set_v3.yml $O $P
$PY $PR/kb_rehearsal_gold_chunk_check.py eval/test_set_v3.yml $O $P
T=/Volumes/DevSSD/Project/sdtm-pedia/.work/10_tier_b_repair/work/t4
(cd $R && $PY -I $PR/kb_rehearsal_heading_vs_gold.py eval/test_set_v3.yml $T/kb_heading_diff_kb-2026.11.25_HEAD.txt $T/kb_heading_diff_00a2e93_HEAD.txt)
(cd $R && $PY -I $PR/kb_rehearsal_meta_stats.py data/meta/meta.yaml $S/cand/data/meta/meta.yaml)
(cd $R && $PY -I $PR/defhome_rules.py $O $P)
for k in old:$O new:$P; do SDTM_RAG_KB_ROOT_OVERRIDE=${k#*:} $PY $PR/kb_rehearsal_coverage.py ${k#*:} $S/out/cov_${k%%:*}.json; done
```

运行产物 (已入库): `kb_rehearsal_477bac3_runs/` 下的 `baseline.json`、`candidate.json` (闸的两份)、`cand_q39only_r1.json` / `_r2.json`、`cand_goldnext_r1.json`、`base_goldnext.json`、`cand_q76dual.json`、`base_q76dual.json`、`pytest_summary.txt`、`ingest_summary.log`、`sec_diff_tag_new.txt`。

## 闸的结果 (按 kbsync gate 五项, 判定函数直接调用 `kbsync.regressions` / `_load_recall` / `_load_avg`)

| 判据 | 基线 | 候选 | 余量 |
|---|---|---|---|
| 题数 / 题集一致 | 140 | 140 ✓ | — |
| source_recall_avg (≥ 0.95) | 0.9917 | 0.9881 ✓ | 充足 |
| 满分题数 (≥ 基线 − 1 = 137) | 138 | 137 ✓ | **0** |
| 逐题回退 (≤ 1) | — | 1 (q76) ✓ | **0** |
| 候选 stamp 指纹 = `477bac3c…` | — | ✓ | — |
| **verdict** | | **PASS** | |

### 逐题差异

139 题的 source_recall 与基线逐题相同 (top5 排序有 71 题不同, 属 KB 内容变化后的正常重排)。不同的只有:

| 题 | 基线 | 候选 | 未命中的 gold | 分类 |
|---|---|---|---|---|
| q76 (AP 域如何关联受试者) | 1.0 | 0.5 | `model/06_relationship_datasets.md#6.6 Associated Persons Related Subjects (APRELSUB)$` | **gold 漂移**, 不是检索丢失, 也不是代码问题 |

- pedia 这轮 (裁定 A5-5 / A5-8) 把该节标题按 PDF 改成 `## 6.6 Associated Persons Relationships (APRELSUB)`; gold 末尾的 `$` 要求节名完全相等, 所以对不上。
- `model/06_relationship_datasets.md` 在候选的检索结果里仍排第 2 (基线也是第 2)。新节正文含 q76 全部 3 条 fact (APID / RSUBJID / SREL)。
- 把 q76 的 gold 换成新标题后, 候选 q76 = 1.0, 140 题与基线 0 回退、满分 138、avg 0.9917 (见「gold 修订实测」)。
- 候选非满分的另两题 q38 (0.333)、q126 (0.5) 与基线相同, 是既有的已知情况。

### 稳定性
候选库上先后跑了 5 趟 140 题 (题集只差 gold): source_recall 除被改 gold 的题外逐题相同; top5 排序只有 q78 一题在各趟之间有差别 (query embedding 的微小波动)。所以「恰好 1 题回退」不是偶然值, 但闸对任何额外的一题波动都没有余量。
这 5 趟共用同一份入库结果。kb-sync 会在虚拟机上重新入库、重新算全部 chunk 的 embedding, 两次入库之间的波动这次预演量不到。

## 对 kb-sync 与提交顺序的含义 (需要裁定)

清单 v3 第 6 条写的是「闸结论不依赖 gold 修订」。现在要改成: **闸仍然 PASS, 但唯一的容错名额被 q76 用掉了。** kb-sync 的基线用线上镜像里的题集, 候选用 main 上的题集, 两边都是旧 gold, 预计结果与本次相同 (1 题回退, 满分 137)。

三种做法 (实测见下节):

| 做法 | 打 tag 前要做的事 | kb-sync 闸的预计结果 | 代价与风险 |
|---|---|---|---|
| **A 不提前动** | 无。q76 的 gold 随「KB 更新」那次提交改成新标题 | 回退 1 题 (q76)、满分 137, PASS, 余量 0 | 再多 1 题波动就 FAIL。FAIL 本身安全 (生产不变), 但候选会被归档, 要重新触发。本机测试全程是绿的 |
| **B 双标题过渡** | 把 q76 的 `model/06` 条目改成 any-of 组 `[旧标题$, 新标题$]`, 合进 main | 回退 0、满分 138 | ① `eval/` 在部署路径过滤里, 这次提交会触发一次只改题集的部署; ② 属于放宽 gold, 按 `check_source_recall` 的用法纪律要由非受益方裁定; ③ **本机 `tests/test_section_gold_exists.py::test_every_section_gold_exists_in_index` 会变红** (它要求每条节级 gold 在当前索引里存在, 而新标题成员在旧 KB 索引里不存在; 已实测)。CI 没有索引会跳过这条测试, 不挡部署, 但本机 push 前的 pytest 是红的, 要在提交说明里写明; ④ KB 升级后要把旧标题成员删掉 |
| **C 提前只换新标题** | 把 q76 的 gold 直接换成新标题, 合进 main | 回退 0、满分 137 → 138 (基线 q76 = 0.5, 候选 = 1.0) | ① 同 B 的 ①③ (本机同一条测试变红, 直到 KB 升级); ② 升级前线上题集的 q76 是 0.5, 这一题在闸里不再有保护作用; ③ 不算放宽 gold |

做法 C 的数字由 `base_goldnext.json` 与 `cand_goldnext_r1.json` 推出 (各题的得分只取决于本题的 gold, 这两份里 q76 用的就是新标题), 没有单独跑。
本报告只给出各做法的实测结果, 未改 `eval/`。三种做法里只有 A 能让本机测试在升级前后一直是绿的。

## gold 修订实测 (题集副本只在临时目录, 候选 chroma 不变)

| 题集变体 | 库 | q39 | q76 | 回退 (对原基线) | 满分 / avg |
|---|---|---|---|---|---|
| 原题集 | 新 KB | 1.0 (2/2) | 0.5 | q76 | 137 / 0.9881 |
| 只改 q39 (加 FA 来源), 跑两趟 | 新 KB | **1.0 (3/3)**, 两趟相同 | 0.5 | q76 | 137 / 0.9881 |
| 全部修订 (q39 + q117 + q120 + q126 删成员 + q76 新标题) | 新 KB | 1.0 (3/3) | 1.0 | 无 | 138 / 0.9917 |
| 全部修订 | 旧 KB | 1.0 (3/3) | 0.5 (新标题在旧 KB 不存在) | q76 | 137 / 0.9881 |
| q76 双标题 any-of (做法 B) | 旧 KB | 1.0 (2/2) | 1.0 (命中旧标题成员) | 无 (与原基线逐题相同) | 138 / 0.9917 |
| q76 双标题 any-of (做法 B) | 新 KB | 1.0 (2/2) | 1.0 (命中新标题成员) | 无 | 138 / 0.9917 |

- **q39**: `domains/FA/assumptions.md` 在新 KB 候选的 15 席检索结果里排第 4 (top5 = PC/spec, ch08, SS/spec, **FA/assumptions**, BS/spec), 候选树 5 趟都一样; 原有两条来源 (`model/02` 第 10 席、`ch08#8.6.3…` 第 2 席) 也都命中。审查者导出了每一席的 chunk: 召回的是 `domains/FA/assumptions.md` 的 `item_3` 块 (chunk id `…#3`), 正文含 `§6.4.3 Variables Unique to Findings About` 与 FAOBJ, 也就是从 `model/02` 搬过来的那段内容。q39 这条 gold 是路径级的 (该文件任一 chunk 命中即算); FA 文件里有两个都叫 `item_3` 的块, 所以不建议把它改成节级 gold。**裁定 (b) 维持, 不用退回 (a)。** 在旧 KB 上加这一条同样 3/3 命中, 所以这条修订不挑 KB 版本。
- **q76 新标题**只在新 KB 成立, 必须和 submodule 升级放在同一次提交 (或用做法 B 的双标题过渡)。
- **q126** 删掉 `model/03…#Subject Elements (SE)$` 成员后仍是 0.5: 同组 `domains/SE/assumptions.md` 命中, 未命中的是 `domains/TE/spec.md` (既有情况)。
- q117 / q120 改的是 fact, 不参与 retrieval 闸。

做法 B 的题集副本: q76 保留 `expected_sources: [model/04_associated_persons.md]`, 把 `model/06` 那条移进 `expected_sources_any: [旧标题$, 新标题$]` (计分单位仍是 2 个)。按同一条 `run_eval` 命令在基线树 (旧 KB) 和候选树 (新 KB) 各跑一趟, 用 `kbsync.regressions(旧 KB 结果, 新 KB 结果)` 判定: 0 回退。两个成员是同一节的新旧名字, 正文都含 q76 的 3 条 fact, 符合 any-of「每个成员独立覆盖全部 fact」的要求。

## 节级与 fact 级 gold 的静态核对 (零费用)

- **节级 (49 条带 `#` 的 gold, 全量重算)**: 用新旧 KB 的 chunk 节名全集按 `eval.run_eval` 的匹配语义重算 (`kb_rehearsal_secdump.py` + `kb_rehearsal_secmatch.py`), 新 KB 下对不上的有 2 条:
  - q126 `model/03…#Subject Elements (SE)$` — 上次已知, 已裁定删除该成员;
  - **q76 `model/06…#6.6 Associated Persons Related Subjects (APRELSUB)$` — 本轮新增**, 也就是闸里回退的那一题。
- **与 pedia 两份标题变动清单交叉核对** (`kb_rehearsal_heading_vs_gold.py`): `kb-2026.11.25 → HEAD` (79 个文件, 删 104 / 增 239) 命中 q76、q126; `00a2e93 → HEAD` (8 个文件, 删 28 / 增 22) 只命中 q76。与上面一致, 没有第三条。
- **命中 chunk 的正文比较** (`kb_rehearsal_gold_chunk_check.py`): 节级 gold 命中的 chunk 正文有变化、但该题 fact 数不变的有 q10、q38、q39、q19、q91、q115、q117 (与上次审查列的相同)。其中由解冻轮 (`00a2e93 → d46f8af`) 引起变化的只有 q76 一条。
- **fact 级 (466 条 fact, 202 条 gold 引用, 逐个 gold 文件比较, 不分大小写的子串)**: 旧 KB 有、新 KB 没有的仍是 3 条, 与上次相同: q39 `FAOBJ` (`model/02`)、q117 `first 6 columns (STUDYID...QNAM) should be unique` (`ch08`)、q120 `Defines which subjects belong to each pool` (`model/06`)。这轮的值 / 措辞改动、CRF 符号、KB note 前缀没有造成新的 fact 丢失。
- **裁定的新 fact 在定稿 KB 里逐字存在**:
  - q120 `individual subjects included in a pool` → `model/06_relationship_datasets.md` 6.3 节: "This dataset identifies individual subjects included in a pool of subjects for which a single observation record (pool level) is captured."
  - q117 `should be unique for every record` → `chapters/ch08_relationships.md`: "The combined set of values for the first 6 columns (STUDYID…QNAM) should be unique for every record."
- 局限同上次: fact 核对只看 gold 文件里有没有该子串, 答案评测的 fact recall 是在模型回答里匹配。
- 这轮未跑 `eval.tests_support.gold_semantics_diff` 与 `eval/lint_gold.py` (没有改 `eval/`); 改 gold 的那次提交要跑。
- 观察 (既有情况, 不是这轮引入): q10 的 gold `domains/RS/assumptions.md#item_4$` 在新 KB 下匹配到 2 个同名块 (旧 KB 1 个), 两版里这些块都不含 q10 的 2 条 fact (fact 在该题别的 gold 文件里)。清单 v3 第 5 条写的「fact 仍在」对这一条不准确; 下次修 gold 时一起看。

## 新 KB 下的 pytest (CI 同款)

| 组 | 结果 |
|---|---|
| 对照组: 旧 KB + 提交的 meta | 2936 passed / 0 failed / 61 skipped |
| 新 KB + 候选 meta, 测试原样 | **18 failed** / 2918 passed / 61 skipped |
| 新 KB + 候选 meta, 套上清单锚点 (临时副本) | 2936 passed / **0 failed** / 61 skipped |
| 同上, 再放入候选 chroma 和五处全改的题集 (本机「KB 更新」的真实形态, 有索引) | 2941 passed / **0 failed** / 56 skipped |

前三组的代码树里没有索引, 依赖索引的测试被跳过 (与 CI 相同)。本机做「KB 更新」时有索引, 会多跑 5 个测试, 其中 **`test_section_gold_exists.py::test_every_section_gold_exists_in_index` 在新 KB 索引 + 原题集下失败** (报 q76、q126 两条节级 gold 在索引里不存在)。它不靠测试锚点修, 靠 gold 修订修: 五处全改后通过 (上表第 4 行)。所以「KB 更新」那次提交里 q76、q126 的 gold 修订是本机测试通过的必要条件。审查者另做了反向验证: 套了锚点的测试放回旧 KB, 那 18 条全部失败, 说明锚点有分辨力。

18 个失败全部属于「随 KB 升级才改」的锚点, 没有清单之外的失败。失败信息见 `kb_rehearsal_477bac3_runs/pytest_summary.txt`。

| 类别 | 失败测试 | 失败信息 (实际 vs 现期望) | pedia 侧原因 |
|---|---|---|---|
| 计数锚点 — 4 个 | `test_base::test_find_mermaid_blocks_ta_returns_20` | 24 ≠ 20 | B-TA 按 PDF 补到 24 张 (这轮「统一渲染」没有改变张数) |
| | `test_chapters::test_ch02_splits_by_h2` | 8 ≠ 9 | FA 叙述移到 FA 域文件 |
| | `test_chapters::test_ch04_produces_47_chunks`、`test_large_chapter_still_splits_by_h3` | 45 ≠ 47 | 两个 KB 自加节改成链接 |
| PC 示例 — 6 个 | `test_examples::test_pc_examples_produces_14_chunks` | 15 ≠ 14 | 新增 `PC – Examples` 块 (PC 自己的 Example 1) |
| | `…all_have_sub_label_method`、`…sub_labels_are_valid_methods` | 该块 `sub_label` 为 None | 同上 |
| | `…all_have_example_index` | 该块 `example_index` 为 None | 同上 |
| | `…example_indices_range_1_to_4` | `TypeError` (`1 <= None`) | 同上 (与清单 v4 预期的失败方式一致) |
| | `…all_have_cdisc_section_id` | 该块为 None, 期望 `§6.3.5.9.3` | 同上 |
| R4 映射 — 8 个 | `test_build_neo4j::test_node_counts` | Variable 1546 ≠ 1541 (被它挡住的后一条: ModelChapter 5 ≠ 4) | 映射由 62 条变 75 条 |
| | `test_build_neo4j::test_variable_model_only_split` | model-only 23 ≠ 18 | 同上 |
| | `test_build_neo4j::test_edge_counts` | DEFHOME 75 ≠ 62 | 同上 |
| | `test_build_neo4j::test_class_and_chapter_nodes` | 多出 `model/04_associated_persons.md` | APID / RSUBJID / RDEVID / SREL → 04 |
| | `test_build_neo4j::test_defhome_edge_shape` | APID → model/04 ≠ model/06 (后一条: 75 ≠ 62) | 同上 |
| | `test_reconcile_neo4j::test_expected_counts_match_golden_anchors` | Variable 1546、ModelChapter 5 (后一条: DEFHOME 75) | 同上 |
| | `test_meta_store::test_model_defhome_map` | EPOCH → model/02 ≠ model/03 | EPOCH 在 02 有通用定义行 |
| | `test_structured_lookup::TestConceptDefinitionChannel::test_defhome_epoch` | 同上 | 同上 |

一个失败的测试只报第一条不成立的断言, 后面的断言被挡住。为了确认清单没有漏项, 用 `probes/kb_rehearsal_apply_anchors.py` 把清单的全部锚点打到临时副本 (每处替换先断言旧串出现次数、写完回读), 重跑后 0 失败。脚本只允许对临时目录运行。

## 重算的数字

全部写进 `kb_upgrade_bundle_checklist.md` 的 v6 节 (替换原 §C 表)。要点:
- chunk: 4333 (chapter 87 / assumptions 487 / examples 201 / model 32 / spec 2164 / terminology 1128 / variable_index 234)。相对 `00a2e93` + 现代码同为 4333, 解冻轮本身是 PP −1 (删掉 KB 自写的 Method 速查节)、SS +1 (`##### Example 1` 改成 `## Example 1` 后才进 chunk)。
- meta: `ct_codes` 588 (与旧 KB 相同, (域, 变量, 码) 三元组逐一相同)、`ct_dict` 176、codelists 1005、变量 1917 / 去重 1523, 都不变; `model_defhome` 62 → **75**; DM `RFSTDTC` / `RFENDTC` 的 type DateTime → Char。
- R4: 真实 `scripts.build_meta` 的产物是 75 条, 与 probe `defhome_rules.py` 的 R4 集合逐条相等; 相对 `00a2e93` (72) 只多 TSVALCD / TSVCDREF / TSVCDVER → model/05, 与 pedia 的实算一致。`build_meta` 的兜底检查 (model/02、model/06 首个编号标题) 在 model/06 标题改名后仍通过。
- 图计数: Variable 1546 (= 1523 + model-only 23)、ModelChapter 5、DEFHOME 75。
- 覆盖率扫描: 缺失行 306 → 302; PC 4 → 3 (PC Example 1 已进 chunk), SS 8 → 0。没有新丢的正文: 新出现的缺失行是文件头的 `> Source text: …` / `> See …` 指针行、被 chunker 当作分组标题的行 (如 PC 的 `## §6.3.5.9.3 … — Worked Examples`), 或原本就缺、这轮改了措辞的行。
- 非 terminology 的 chunk 超过 8191 token 的个数: 0 (最大 MB `§6.3.5.7.3` 7878, CP `Example 6` 7296); terminology 超限 18 个, 与旧 KB 相同。

## 给 pedia 的反馈

1. **不需要 pedia 再改 KB。** 这轮没有发现 KB 侧的问题; R4 映射 75 条与 pedia 的实算逐条一致。
2. 这轮的标题改名让 q76 的节级 gold 失效 (6.6 节)。由本仓改 gold, 不需要改回。pedia 给的两份标题变动清单直接定位到了这一条, 这个做法有效, 以后每次发版请照旧提供。
3. SS 示例的标题层级改正 (`#####` → `##`) 让这个文件第一次进入索引 (之前 8 行不在任何 chunk 里)。
4. 提醒 (沿用上次): CT 单元格格式、model 文件编号与 SDTM 章节的对应、model 表第 6 列是否为空, 都是下游契约; `model_defhome` 的结果会随任何 Notes / Usage Restrictions 单元格的增删而变, 这轮的 +3 就是例子。

## 过程记录
- 第一次跑基线时把评测参数放在一个 shell 变量里, zsh 不拆词, `run_eval` 找不到题集文件直接报错 (没有产生任何结果); 改成逐个写参数后重跑。复跑命令已按后者写。
- 对 pedia 仓只执行了 `git archive`、`git rev-parse`、`git diff --stat` 和读文件, 都带 `GIT_OPTIONAL_LOCKS=0`; 没有写入。
- 没有 push、部署、升级 submodule、触发 kb-sync、动虚拟机。

## 独立审查 (规则 D)
审查者 `oh-my-claudecode:critic` (写作者是主会话), 结论 **PASS-with-fixes** (MAJOR 2 / MINOR 7), 全文与处置见 `kb_rehearsal_477bac3_review.md`, prompt 存档 `evidence/subagent_prompts/review_kb_rehearsal_477bac3.md`。
审查者独立复核成立的: 闸的五项判据与「余量为零」、指纹与树哈希、q76 归为 gold 漂移 (候选第 2 席就是改名后的 6.6 节)、18 个失败的分类与锚点没有改弱断言、清单 v6 抽查约 15 个数字、节级 gold 用另一种方法 (直接读新旧 chroma 的全部节名) 重算仍只有 q76 / q126、kb-sync 机制的描述。
两条 MAJOR 都已并入正文: 做法 B 会让本机一条 gold 存在性测试变红 (写进三种做法的表, 并补了「有索引」的 pytest 组); 做法 B 与「旧 KB 上全改」两组实测原先没有复跑命令 (已补命令, 题集变体脚本补上 q76dual, 评测 JSON 入库)。
