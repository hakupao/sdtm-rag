# CT cell format fix: `Cnnnnn` + `(短名) Cnnnnn` 兼容 (2026-11-27)

分支 `hakupao/fix-ct-cell-format` (基于 main `647fb9c`): `83a3a69` (解析) + `1d4b082` (`*` / DOMAIN 不进 ct_dict) + 本提交 (审查 nit 补测 + 本 checkpoint)。
只修预演报告 (`.work/10_split_and_public/evidence/checkpoints/kb_rehearsal_bf33bab.md`, 主仓 p3 分支) 的类别 ①; 类别 ② `_model_defhome`、③ 计数锚点、gold 漂移未动。

## 改动
| 文件 | 内容 |
|---|---|
| `scripts/spec_loader.py` | 唯一归一化 `ct_code_of(token)`: `fullmatch (?:\([A-Z0-9_]+\)\s*)?(C\d+)` → 纯码 / None; `is_ct_code` 改用它 |
| `scripts/build_meta.py` | `_split_ct` 用 `ct_code_of`, ct_codes 存纯码; `*` 与 (仅 DOMAIN 变量的) 本域码字面值不进 ct_dict |
| `server/validator.py` | `_check_ct` 用纯码查 codelist 与出消息 (改前传整格原文, 新格式下全部 "not found") |
| `tests/test_ct_cell_format.py` | 合成输入 (CI 用旧 KB 也覆盖新格式): 归一化正反例、`_split_ct`、`_variables`、validator 端到端 |

报告的「其他受影响面」核对: `structured_answer` / `graph_validator` / `graph_engine` / `build_neo4j` / `reconcile_*` 只读 meta 的 `ct_codes`, 随 build_meta 修复恢复 (下方 pytest 清零); 直接读 spec.md CT 格的只有 `_split_ct` 与 `validator._check_ct`。
chunkers (`variable_index` / `terminology`) 与 `rag._VI_CT_RE`: 新 KB 中除 spec.md 外无 `) C\d` (`grep -rln ') C[0-9]' <新KB> | grep -v /spec.md$` 为空), 不受影响。

## `*` / DOMAIN 的处理 (依据 pedia `t4_downstream_notes.md`「下游格式约定」)
- `*` (129) = 「可能受 CT 约束, 暂无 CDISC codelist」(SDTMIG §4.3.1), 非字典 token → 丢弃, 不进 ct_dict。
- DOMAIN 格 (59) = 本域码字面值 → 仅当变量为 `DOMAIN` 且值 = 本域码时丢弃; 其他情况原样保留 (异常值可见)。
- meta 结构不变; 信息损失: `*` 标志未入 meta。pedia 建议的 `ct_open: true` 之类标志位属 meta 结构变更, 本轮不做, 留主人定。
- validator 对 `*` / 域码 / 多 codelist 格 (10 处) 均跳过, 与旧 KB 行为一致 (多 codelist 格逐码校验是行为变更, 未做)。

## 验收 (命令见文末)
| 项 | 结果 |
|---|---|
| 旧 KB build_meta | `git diff --exit-code data/meta/meta.yaml` 通过, sha256 `abfa9815…` = tracked |
| 旧 KB pytest | 修复前 1 failed / 2890 passed / 61 skipped; 修复后 1 failed / 2908 passed / 61 skipped。唯一失败 `test_p2_seam_characterization` 修复前即失败 (审查者在 `647fb9c` 展开树复现, 与 CT 无关) |
| 新 KB meta | ct_codes 588 (未修复 0); 逐变量 ct_codes 与 ct_dict 与旧 KB meta **完全相同**; 剩余差异仅 RFSTDTC/RFENDTC type 与 model_defhome (范围外) |
| 新 KB 140 题闸 | 基线 0.9917 / 修复后 0.9917, `kbsync.regressions` = [], 140 题逐题 0 差。对照: 未修复候选回退 q16/q43/q96/q98/q99/q101, avg 0.9702 (复现报告) |
| 新 KB pytest | 修复前 31 failed → 修复后 16 failed; 类别 ① 16 项全部清零 |

新 KB 修复后剩余 16 个失败 (均非类别 ①):
- ② model_defhome: `test_build_meta::test_model_defhome`, `test_meta_store::test_model_defhome_map`, `test_structured_lookup::…defhome_canary_epoch_six_col_isolation`, `test_build_neo4j::{test_defhome_edge_shape, test_class_and_chapter_nodes, test_node_counts, test_variable_model_only_split, test_edge_counts}`, `test_reconcile_neo4j::test_expected_counts_match_golden_anchors`
  - 更正报告: 报告把 build_neo4j node/edge counts、variable split、reconcile 归入 ①。修复后其 CT 部分已对 (USES_CT 0 → 542 = 锚点), 剩余断言是 model-only 变量 1541→1544、ModelChapter 4→5、DEFHOME 59→64, 属 ②。
- ③ 计数锚点 / chunker: `test_base::test_find_mermaid_blocks_ta_returns_20`, `test_chapters` ×3, `test_examples::test_pc_examples_all_have_cdisc_section_id`
- gold 漂移: `test_section_gold_exists` (q126 `Subject Elements (SE)` 节已不存在; 修复前树无 chroma 故 skip, 非本修复引入)
- 环境: `test_p2_seam_characterization` (新旧 KB 都失败)

## 变异验证 (规则 5)
脚本 `mutate.py` (scratchpad, 未入库): 冻结原始字节 → 断言磁盘 sha = 原始 → 替换 (`count == 1`) → 回读断言 sha 变化且新串在 → 跑 `tests/test_ct_cell_format.py tests/test_build_meta.py` (旧 KB) → `finally` 回写原始字节并断言 sha。结束后 `shasum -c` 三文件 OK。

| 变异 | 结果 |
|---|---|
| M1 `_split_ct` 回到只认纯码 | RED (2 failed) |
| M2 `ct_code_of` 去掉短名前缀 | RED (7 failed) |
| M3 `is_ct_code` 回到 `^C\d+$` | RED (1 failed) |
| M4 validator 传整格原文查 codelist | RED (1 failed) |
| M5 不丢 `*` | RED (2 failed) |
| M6 不丢域码字面值 | RED (2 failed) |
| M7 对所有变量都传域码 | RED (1 failed) |
| M8 `tok == "*"` → `"*" in tok` (审查者变异 E 存活后补测) | RED (1 failed) |
| 还原后 | 31 passed |

⚠ 变异工具自身失效一次 (规则 5 第 4 族, 新形态): M8 两串**等长** (10 字节), 回写原始字节与变异同一秒 → `__pycache__` 的 mtime+size 校验通过, 还原后 Python 仍执行**变异版字节码** (`_split_ct("ISO * x")` 返回 `([], [])`)。sha 核对只证明了磁盘字节, 证明不了解释器跑的代码。
对策: 清 `__pycache__`, 变异子进程设 `PYTHONDONTWRITEBYTECODE=1`, 全部 8 个变异重跑 (上表即重跑结果), 再清缓存重跑旧 KB build_meta 逐字节 + 全量 pytest (1 failed seam / 2908 passed)。M1-M7 的首轮串长都与原串不同, 不受影响; 新 KB 树没有做过变异。

## 独立审查 (规则 D)
writer = 主会话 (Claude Code 主代理); reviewer = `oh-my-claudecode:code-reviewer` 子代理 (不同 subagent_type, 只读, 自行变异)。
- `83a3a69`: **PASS-with-nits**。自做 5 个变异 (in-memory 注入, 不改工作区) 全红; 旧 KB 746 格新旧判定差 0、参与 CT 校验 560 格不变; 旧 KB meta sha 一致。nits: `*`/域码进 ct_dict (已由 `1d4b082` 处理); 短名不与 codelist 核对; `controlled_terms` 注释过时 (已更新); `[Cc]` 大小写口径与 terminology 解析不一致 (数据中无小写); 多 codelist 格静默跳过 (沿用旧行为); 测试只用合成数据; `validator.py` 未用 `Path` 导入 (既有)。
- `1d4b082`: **PASS-with-nits**。边界核对 (新 KB, 进程内): 无 DOMAIN 变量的域 = RELREC/RELSPEC/RELSUB/SUPPQUAL; DOMAIN 格 ≠ 本域码 0 处; 非 DOMAIN 格为域码 0 处; 非空 DOMAIN 格 59。新 KB ct_codes+ct_dict 与旧 KB 1917 变量全等; 旧 KB meta sha 一致。自做变异 A-D 全红, E (`"*" in tok`) 存活 → 已补 `_split_ct("ISO * x")` 断言 (M8)。另补 `(NY) C66742; *` 组合格用例。上一轮 `controlled_terms` 注释 nit 确认已修。

## 建议 (未做)
- meta 加 `*` 标志位 (如 `ct_open`) — 需改 meta 结构, 主人定。
- build_meta 对「含 `C\d+` 却解析不出码」的 token 报警, 防格式再变时 588 → 0 静默发生 (新增失败路径会影响 kb-sync, 本轮不加)。
- 修复在 `scripts/` + `server/`: push main 即部署 (旧 KB meta 不变, 生产零影响); 需先于 pedia 打 tag 合入 main。

## 复跑命令
```bash
R=/Volumes/DevSSD/Project/sdtm-rag; W=<本工作区>; S=<临时目录>; PY=$R/.venv/bin/python; export GIT_OPTIONAL_LOCKS=0
OLD=$R/vendor/sdtm-pedia/knowledge_base   # kb-2026.11.25, 指纹 f863e454…
mkdir -p $S/kbnew && git -C /Volumes/DevSSD/Project/sdtm-pedia archive 00a2e93 knowledge_base | tar -x -C $S/kbnew
P=$S/kbnew/knowledge_base; $PY $W/deploy/kbsync/kbsync.py fingerprint --kb-root $P   # = bf33babcfd29…
# 旧 KB (工作区, .venv/.env 软链主仓; data/study 不要存在, 否则 local_data 测试误判)
cd $W && SDTM_RAG_KB_ROOT_OVERRIDE=$OLD $PY -m scripts.build_meta && git diff --exit-code data/meta/meta.yaml
SDTM_RAG_KB_ROOT_OVERRIDE=$OLD $PY -m pytest -m "not slow" -q -o addopts="" -rf -p no:cacheprovider
# 新 KB: 每棵树 = git archive <rev> 展开 + git init + .env/.venv 软链; base 用主仓 chroma 的 cp -c 副本, cand 用新 KB ingest
EV="eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup"
(cd $S/base && SDTM_RAG_KB_ROOT_OVERRIDE=$OLD $PY -m eval.run_eval $EV --output $S/baseline.json)
(cd $S/cand && SDTM_RAG_KB_ROOT_OVERRIDE=$P $PY -m scripts.ingest --no-backup)        # ≈ $0.05, 4332 chunks
# fix_new = git archive 1d4b082 + cp -c -R $S/cand/data/chroma
(cd $S/fix_new && export SDTM_RAG_KB_ROOT_OVERRIDE=$P && $PY -m scripts.build_meta && $PY -m eval.run_eval $EV --output $S/cand_fixed.json \
  && $PY -m pytest -m "not slow" -q -o addopts="" -rf -p no:cacheprovider)
(cd $W && $PY -c "import sys;sys.path.insert(0,'deploy/kbsync');import kbsync as k;from pathlib import Path as p
b=k._load_recall(p('$S/baseline.json'));c=k._load_recall(p('$S/cand_fixed.json'));print(k.regressions(b,c))")
```
