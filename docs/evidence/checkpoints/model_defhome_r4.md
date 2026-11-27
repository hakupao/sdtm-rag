# `_model_defhome` 归属规则 R4 (2026-11-27)

分支 `hakupao/defhome-r4`, 叠在 `hakupao/fix-ct-cell-format` (`bfbf547`, CT 修复, 已审未合并) 上, 两者都改 `scripts/build_meta.py`。
代码提交 `a62afba` (R4 + 兜底) + 下一提交 (审查 L2/L4 修正 + 本 checkpoint)。依据: 主仓 p3 分支 `.work/10_split_and_public/evidence/checkpoints/model_defhome_rule_options.md` 文末「v3 修订」 + 同目录 `_review.md`; 参考实算 `../probes/defhome_rules.py`。

## 裁定 (bot 受托代裁)
主人 2026-11-27 把选择题委托给协调 bot「sdtm开发」(原话:「之前那些选项，你可以替我分析后决定嘛。我听从你的建议」), bot 代为选定:
E1 = R4; E2 = 提前合并, 接受旧 KB 下多 3 条 (DOMAIN / USUBJID / POOLID → model/02); E3 = Notes 为空的 4 个变量 (REFID / SPEC / STUDYID / SPDEVID) 不进映射; E5 = 隔离金丝雀换 ETCD; E6 = 保留「多文件时剔除 06」; v3 第 7 条兜底照做。

## 规则 (`scripts/build_meta.py::_model_defhome`)
定义行 = 6 列 `| # | VAR | Label | Type | Role | Notes |`、序号为数字、Notes 非空 (不变)。对每个变量, 看含定义行的文件集合:
1. 含 model/02 (§3.1 通用变量表) → 02;
2. 否则若多于一个文件, 剔除 model/06 (§6 关系数据集只把别处定义的标识变量列为列); 只在 06 的仍归 06;
3. 剩恰好一个 → 归它; 否则丢弃。`--` 变量排除 (不变)。

兜底 (`_model_chapter_file`): `model/02_*.md` / `model/06_*.md` 不是恰好一个, 或首个编号标题不是 §3.1 / §6 的祖先或子节 (02 接受 3 / 3.1 / 3.1.x, 拒绝 3.2; 06 接受 6.x), 或没有编号标题 → `ValueError`, build_meta 失败 (kb-sync 候选构建也随之失败)。model 目录缺失同样报错 (原来静默返回 `{}`)。
两套真实 KB 都不误报: 旧 KB 首标题 `3.1.1` / `6.1`, 新 KB `3` / `6.1`。输出仍是「变量 → 单个文件」, meta.yaml 结构不变。

## 改动 (`a62afba`)
| 文件 | 内容 |
|---|---|
| `scripts/build_meta.py` | R4 判定 + 兜底检查 (审查后: 02 的章节比较从主章节号收紧到 §3.1) |
| `data/meta/meta.yaml` | 旧 KB 重新生成, 只多 3 行 (下节) |
| `tests/test_model_defhome_r4.py` (新) | 合成 model/ 树: 每条分支 (GEN 为 02+03+05+06) + 兜底 6 种触发 (含 02 首标题 §3.2) + 重复前缀 + 目录缺失 + 新 KB 首标题形态 |
| `tests/test_build_meta.py` | 实时构建断言: RDOMAIN→06、DOMAIN/USUBJID/POOLID→02、ETCD→03 (隔离金丝雀)、RPATHCD/RSTGCD/RSTAGE 不在 |
| `tests/test_structured_lookup.py` | EPOCH 金丝雀 → ETCD 金丝雀; EPOCH 降为普通断言 (旧 KB → 03); hygiene: 三变量 → 02, 多文件丢弃守卫改用 RPATHCD/RSTGCD/RSTAGE; docstring 去掉写死的 59 |
| `tests/test_build_neo4j.py`, `tests/test_reconcile_neo4j.py` | DEFHOME 59 → 62 |
| `scripts/build_neo4j.py` | docstring / 注释 59 → 62 |
| `docs/evidence/checkpoints/d_channel_concept_definition.md` | 「宁缺毋滥」处加修订说明 |

## 旧 KB (kb-2026.11.25) 下 meta 的 diff (`git diff bfbf547 a62afba -- data/meta/meta.yaml`)
```
+  DOMAIN: model/02_observation_classes.md
+  POOLID: model/02_observation_classes.md
+  USUBJID: model/02_observation_classes.md
```
其余 0 变化 (3 insertions, 0 deletions); 59 → 62; 3 个都是 IG 变量, Variable 1541 / model-only 18 / ModelChapter 4 不变。

## 验收
| 项 | 结果 |
|---|---|
| 旧 KB pytest (`bfbf547` → 最终代码) | 1 failed / 2908 passed / 61 skipped → 1 failed / 2919 passed / 61 skipped (`a62afba` 时 2918, 审查后补 1 个参数化用例)。唯一失败 `test_p2_seam_characterization` 基点即失败 (已知日期问题) |
| 旧 KB `_model_defhome` vs `defhome_rules.py` R4 | 整张字典相等, 62 条 |
| 新 KB (`00a2e93`, 指纹 `bf33babc…`) `_model_defhome` vs R4 实算 | 整张字典相等, 72 条 (03:31 02:18 06:12 05:7 04:4); 生成的 meta.yaml 中 model_defhome 与进程内结果相同 |
| 新 KB 140 题 retrieval 闸 | avg 0.9917; 与本轮重跑的基线 `baseline_mine.json` 逐题双向 0 差, `kbsync.regressions` = []; 与 CT 分支的 `baseline.json` / `candidate_fixed2.json` (同 KB 同 chroma, 只差 defhome) 也逐题 0 差。q73 / q83 = 1.0 |
| 新 KB pytest (`a62afba`; 审查后改动只收紧兜底, 新 KB 重建 meta.yaml 与 `a62afba` 逐字节相同, R4 两个测试文件 23 passed) | 15 failed / 2909 passed / 56 skipped。相对 CT 分支新 KB 结果 (16 failed): `test_build_meta::test_model_defhome` 转绿; `test_defhome_canary_epoch_six_col_isolation` 改名为 `test_defhome_epoch` 后仍失败 (= 下方清单)。其余失败均属下方清单或非本范围 (③ 计数/chunker 5 个、q126 gold 漂移、p2 seam) |

新 KB 下 R4 相对旧 KB meta: 新增 12 (VISIT / VISITNUM / VISITDY / RPPLDY / RPPLSTDY / RPPLENDY / MIDSDTC / RELMIDS / RPHASE → 02; RSUBJID / RDEVID / SREL → 04); 改归属 4 (EPOCH / TAETORD / MIDS 03 → 02, APID 06 → 04); 丢 2 (REFID / SPEC, Notes 空, E3)。

## 随 KB 升级才改的期望 (只在新 KB 成立, 本分支未提交)
| 位置 | 旧 KB (现提交) | 新 KB |
|---|---|---|
| `tests/test_meta_store.py:181` `m["EPOCH"]` | model/03 | model/02 |
| `tests/test_structured_lookup.py::test_defhome_epoch` | model/03 | model/02 |
| `tests/test_build_neo4j.py::test_node_counts` | Variable 1541, ModelChapter 4 | 1546, 5 |
| `tests/test_build_neo4j.py::test_variable_model_only_split` | model-only 18 | 23 |
| `tests/test_build_neo4j.py::test_edge_counts` / `test_defhome_edge_shape` | DEFHOME 62; APID → model/06 | 72; APID → model/04 |
| `tests/test_build_neo4j.py::test_class_and_chapter_nodes` | 4 个 ModelChapter | 加 `model/04_associated_persons.md` |
| `tests/test_reconcile_neo4j.py:16-18` | Variable 1541, ModelChapter 4, DEFHOME 62 | 1546, 5, 72 |
| `scripts/build_neo4j.py` docstring + D3/D4 注释 | Variable 1541 (18 model-only), ModelChapter 4, DEFHOME 62 | 1546 (23), 5, 72 |
| `data/meta/meta.yaml` | 62 条 | 72 条 (随 KB 升级重新生成) |

⚠ 上表新 KB 数字都钉 `00a2e93`。协调方知会: pedia 解冻后会给 model/05 TS 表加第 6 列 (Usage Restrictions), TSVALCD / TSVCDREF / TSVCDVER 按 R4 归 model/05, 最终映射约 75 条; Variable / model-only / DEFHOME 计数随之变。**升级时以 pedia 定稿 tag 的新指纹重跑 build_meta + `defhome_rules.py` 重算, 不要照抄本表数字。**

两套 KB 都成立、已提交: RDOMAIN→06、DOMAIN/USUBJID/POOLID→02、ETCD→03、RPATHCD/RSTGCD/RSTAGE 不在、`"EPOCH" in mdh`。

## v3 第 6 条使用方核对
- `eval/prod_wirein/sp4_cookbook_golden.py:142-150` defhome:ch06 闸: 期望集合由 `store.model_defhome_map` 动态求得, 不写死, 无需改。ch06 变量数旧 KB 15 → 15 (3 个新增都归 02), 新 KB 12 (APID → 04, REFID / SPEC 丢); `docs/evidence/checkpoints/sp4_cookbook_golden.txt` 的「15 vars」是历史证据, 不改。
- `scripts/build_neo4j.py:13,89-91`、`tests/test_structured_lookup.py:199`: 已改 (见改动表); 新 KB 数字随 KB 升级再改 (清单)。
- `docs/evidence/checkpoints/d_channel_concept_definition.md`: 已加修订说明。
- 其他读 `model_defhome` 的: `server/meta_store.py`、`server/structured_lookup.py:427`、`server/graph_engine.py:81`、`scripts/reconcile_neo4j.py`、`eval/prod_wirein/sp2p2_equiv_snapshot.py` 都只读映射, 结构没变, 不用改。`docs/design/*`、`docs/evidence/checkpoints/sp*` 里的 59 是历史记录, 不改。

## 变异验证 (规则 5)
脚本 `mutate.py` (scratchpad, 未入库): 冻结原始字节 → 断言磁盘 sha = 原始 → 每处替换 `count == 1` → 回读断言 sha 变化且新串在 → 清 `__pycache__`、`PYTHONDONTWRITEBYTECODE=1` 子进程跑 `tests/test_model_defhome_r4.py tests/test_build_meta.py` (旧 KB) → `finally` 回写原始字节并断言 sha。最终代码前后 sha `92058015…` 一致 (首轮 M1-M9 跑在 `a62afba` 代码上, 审查后改动后全部 12 个重跑, 上表为重跑结果)。

| 变异 (`scripts/build_meta.py`) | 结果 | 红在 |
|---|---|---|
| M1 `if general in files:` → `if False:` | RED 2 | 合成 GEN; 实时 DOMAIN→02 |
| M2 总是剔除 06 (`cands = files - {relation}`) | RED 2 | 合成 ONLY06; 实时 RDOMAIN |
| M3 从不剔除 06 (`cands = files`) | RED 1 | 合成 APX |
| M4 放宽 `len(inner) != 6` → `not in (5, 6)`, 解包改取 `inner[-1]` | RED 2 | 合成 USE5; 实时 RDOMAIN (先于 ETCD 断言)。另做进程内核对: M4 下 ETCD 在新旧 KB 都从 03 变为丢弃, ETCD 金丝雀单独也能抓到 |
| M5 不要求 Notes 非空 | RED 1 | 合成 EMPTY02 |
| M6 兜底不查章节号 | RED 3 | 章节号不对的 3 个参数化用例 |
| M10 兜底只比主章节号 (`n = 1`, 审查 L2) | RED 1 | 02 首标题 §3.2 用例 |
| M11 无编号标题时放行 | RED 1 | 无编号标题用例 |
| M12 02 只在恰好两个文件时优先 (审查 L4) | RED 2 | 合成 GEN (02+03+05+06); 实时 DOMAIN |
| M7 兜底允许同前缀多文件 (`if not hits:`) | RED 1 | 重复前缀用例 |
| M8 剩多个时取第一个 | RED 2 | 合成 AMBIG; 实时 RPATHCD |
| M9 model 目录缺失时返回 `{}` | RED 1 | 目录缺失用例 |
| 还原后 | 23 passed | |

局限: `test_structured_lookup` / `test_meta_store` / `test_build_neo4j` 读 tracked meta.yaml, 对 build_meta 的变异不可见; 能被变异抓到的断言都放在实时构建的 `test_build_meta` 与合成测试里。

## 独立审查 (规则 D)
writer = 主会话 (Claude Code 主代理); reviewer = `oh-my-claudecode:code-reviewer` 子代理 (不同 subagent_type, 只读, 自行变异)。
- `a62afba`: **PASS-with-nits** (0 CRITICAL/HIGH/MEDIUM, LOW 5)。自行复核: 规则逐条一致; 两套 KB 兜底不误报; 整张字典与 probe R4 相等 (旧 62 / 新 72); 进程内 build_meta + dump_meta 与提交的 meta.yaml 逐字节相同, 只多 3 行; 在 `git archive` 副本上自做 13 个变异, 12 红, 1 个 (5 列行补空 Notes) 为等价变异; 旧 KB 全量 2918 passed + 已知 seam 失败。
  - L1 `d_channel_concept_definition.md` 引用的本文件未入库 → 随本提交入库。
  - L2 兜底只比主章节号, 分不出 §3.1 / §3.2 → 已收紧 (见规则节), 补 §3.2 用例, 变异 M10 红。
  - L3 标题正则要求数字后跟空白 (`## 3. Foo` / `## §3` 会被跳过)、代码块里的 `#` 行也会被当标题 → 两套 KB 都没有, 记录不改。
  - L4 合成测试缺「02 + 两个以上其他文件」→ GEN 改为 02+03+05+06, 变异 M12 合成测试也红。
  - L5 兜底只查 02 / 06, 与 v3 第 7 条范围一致 → 不改。
- 审查后修正提交: 见下一轮审查。

## 环境与副作用
- 未 push (分支无 upstream), 未合并、未开 PR、未触发部署。未写主仓 (主仓 `data/meta/meta.yaml` mtime 仍为 2026-11-26 22:11)、未写 pedia 仓、未改 submodule 指针、未改 `eval/test_set_v3.yml`。新 KB 用 `git archive 00a2e93` 展开。
- 未重新入库, 零 embedding 费用 (只有两次 140 题 eval 的查询 embedding)。新 KB chroma 用 `cp -c -R` 复制自 CT 分支会话的候选 (`ingested_at_commit.txt`: 指纹 `bf33babc…`, 4332 chunks)。
- 工作区 `.venv` / `.env` 软链主仓 (未提交); 提交时临时软链 `data/study/st01/catalog.json` 供 pre-commit 闸, 提交后即删。pytest 在工作区建了一个空的 `data/chroma/chroma.sqlite3` (gitignored)。

## 复跑命令
```bash
R=/Volumes/DevSSD/Project/sdtm-rag; W=<本工作区>; S=<临时目录>; PY=$R/.venv/bin/python; export GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1
OLD=$R/vendor/sdtm-pedia/knowledge_base   # kb-2026.11.25
mkdir -p $S/newkb && git -C /Volumes/DevSSD/Project/sdtm-pedia archive 00a2e93 knowledge_base | tar -x -C $S/newkb; NEW=$S/newkb/knowledge_base
# 旧 KB
cd $W && SDTM_RAG_KB_ROOT_OVERRIDE=$OLD $PY -m scripts.build_meta && git diff --exit-code a62afba -- data/meta/meta.yaml
SDTM_RAG_KB_ROOT_OVERRIDE=$OLD $PY -m pytest -m "not slow" -q -o addopts="" -rf -p no:cacheprovider
# 与 probe 整表比对 (cmp_probe.py: 把 probe R4 的两位前缀映射成 model/<文件名>, 与 _model_defhome 比字典)
$PY -I $S/cmp_probe.py $OLD $NEW $W $R/.work/10_split_and_public/evidence/probes/defhome_rules.py   # old 62 EQUAL / new 72 EQUAL
# 新 KB: r4new = git archive a62afba 展开 + git init + .env/.venv 软链 + 新 KB chroma (cp -c -R); base = git archive bfbf547 + 主仓 chroma 副本
(cd $S/base && SDTM_RAG_KB_ROOT_OVERRIDE=$OLD $PY -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output $S/baseline_mine.json)
(cd $S/r4new && export SDTM_RAG_KB_ROOT_OVERRIDE=$NEW && $PY -m scripts.build_meta \
  && $PY -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output $S/cand_r4.json \
  && $PY -m pytest -m "not slow" -q -o addopts="" -rf -p no:cacheprovider)
(cd $W && $PY -c "import sys;sys.path.insert(0,'deploy/kbsync');import kbsync as k;from pathlib import Path as p
b=k._load_recall(p('$S/baseline_mine.json'));c=k._load_recall(p('$S/cand_r4.json'));print(k.regressions(b,c),{q for q in b if b[q]!=c.get(q)})")
```
