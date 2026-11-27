# KB 发版预演: pedia 本地 KB (Tier B) 入库 + CDISC 140 题闸 (2026-11-27)

**结论: 闸 FAIL (6 题回退 > 1)。根因不在检索、也不在 gold, 而在 B 仓 `scripts/build_meta.py` 的 CT 码解析与 pedia 新的 CT 单元格写法不兼容。**
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

```bash
R=/Volumes/DevSSD/Project/sdtm-rag; P=/Volumes/DevSSD/Project/sdtm-pedia/knowledge_base; S=<临时目录>; PY=$R/.venv/bin/python
$PY $R/deploy/kbsync/kbsync.py fingerprint --kb-root $P                       # 开始/结束各一次
for t in base cand; do mkdir -p $S/$t; (cd $R && git archive HEAD) | tar -x -C $S/$t; ln -s $R/.env $S/$t/.env
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

**6/6 = B 仓解析器不兼容 (不是检索不到原文, 也不是 gold 漂移, gold 无需改)。**
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

其他: DM `RFSTDTC` / `RFENDTC` 的 type 在 meta 里由 DateTime → Char (pedia 按 PDF 改, 属预期内容变化); codelists 1005 不变; 变量集合不变。
`scripts/chunkers/{variable_index,terminology}.py` 与 `server/rag.py:117` 也用 `^C\d+$`, 但解析的是 VARIABLE_INDEX / terminology 文件, 这两类 chunk 数不变 (234 / 1128), 未见影响。

### 修复可先上线 (已验证向后兼容)
反事实补丁在**旧 KB** (`kb-2026.11.25`) 上生成的 meta.yaml 与 tracked `data/meta/meta.yaml` **逐字节一致** (`cmp` 通过) → 修复可以先于 pedia 打 tag 合进 B 仓 main, 对现生产零影响。
注意: 修复在 `scripts/` → push 会触发部署 (非 `[skip ci]`); kb-sync 候选镜像从 B 仓 main 构建, 所以修复必须先进 main, 否则下次 kb-sync 会 (正确地) FAIL。

## 给 pedia 的反馈
1. **S-CT 批次 (`44fb042`) 本身可以保留**: 改动符合 PDF, 下游问题由 B 仓修解析器。打 tag 前不需要回滚它, 但请知会: CT 单元格格式是下游契约 (`(短名) Cnnnnn`, 多个用 `; ` 分隔), 以后再改格式先告诉 B 仓。
2. **`*` 单元格 (129 处, 如 AECAT / VSCAT / PCCAT)**: 请确认含义 (PDF 上的星号脚注?), 并考虑在 KB 里给一个可机读的写法或 KB note; 目前下游会当成字典 token。
3. **DOMAIN 的 CT = 域码 (59 处)**: 同上, 下游需要知道这是字面值而非 codelist。
4. S-TYPO (`bc4e42e`, 弯引号 / 破折号, 51 文件) 与其他 Tier B 批次: 140 题里**没有**造成任何回退; gold 是路径 / 节级匹配, 不受正文写法影响。

## 对 1.9 正例演练的含义
- 若 pedia 先打 tag、B 仓未修: kb-sync 候选必然 FAIL (这正是闸该做的), 候选归档 `chroma_failed_*`, 生产不变。
- 推荐顺序: B 仓修 `build_meta._split_ct` + `spec_loader.is_ct_code` (兼容新旧两种写法, 加单测 + 规则 5 变异验证) → 推 main 部署 (meta 不变) → pedia 打 tag → kb-sync 正例。
- kb-sync 的基线用线上镜像里的题集和代码, 候选用新 checkout; 本次不需要改 gold, 所以没有题集先后问题。
