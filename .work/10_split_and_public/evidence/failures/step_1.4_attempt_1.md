# step 1.4 + 1.5b attempt 1 — 闸 1/2 FAIL (本机 B 仓 chroma 未迁移) (2026-11-25)

writer executor (opus), prompt `subagent_prompts/step_1.4_1.5b_executor.md`。

## 输入
B HEAD `c0f1ac4` (4 个提交: efe4538 submodule+kb_root / f8e7e44 deploy / 393e92c oidscan / c0f1ac4 docs), submodule `vendor/sdtm-pedia` = ebf0c8a。
无任何 `*_OVERRIDE` (shell 与 `.env` 均无)。`settings.kb_root` = `<B>/vendor/sdtm-pedia/knowledge_base`。

## 产物与技术判定
| 闸 | 命令 | 结果 |
|---|---|---|
| 1 pytest (本机, 原地 data/chroma) | `.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs` | **3 failed** / 2603 passed / 2 skipped (`data/study/st01/eval/runs/split10_p14/pytest.log`) |
| 2 CDISC 140q (原地 data/chroma) | `python -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output data/study/st01/eval/runs/split10_p14/cdisc140.json` | **rc=1, q07 处崩**: `RuntimeError: VARIABLE_INDEX section map 不完整 ... CT 码 0 条 / 通用变量 0 条`; 崩前 q02、q06 src=0% (基线只有 q38/q126 <1) |
| 3 裸 clone (`env -i`, 无 data/) | `git clone --recurse-submodules --shallow-submodules` → `uv sync --frozen --extra dev` → CI 同款 pytest | **0 failed**: 2547 passed / 61 skipped |
| 4 Docker 静态 | COPY 源逐个存在; dockerignore 模拟后 vendor/ 只进 `knowledge_base` | PASS |
| 5 提交闸 | 4 个提交均过 hook, CLEAN, 无 override、无 --no-verify | PASS |

## 根因 (已在副本上证实)
B 仓本机 `data/chroma` 的 `sdtm_kb_v1` 4329 条 `source` 仍是 monorepo 绝对路径 `/Volumes/DevSSD/Project/sdtm-pedia/knowledge_base/...`
(生产 chroma 在 1.2 已迁, 本机这份没迁; 1.3 跑测试时用 KB override 指 monorepo, 绝对形恰好对上)。
`rag._source_where` 用**当前** `kb_root` 拼绝对形 → kb_root 改到 vendor/ 后绝对形回退失效, 所有按 source 过滤的查询 miss。
study 两个 collection 本来就是裸文件名, 不受影响。

副本验证 (不动原地 data/chroma):
```
cp -a data/chroma data/chroma_backup_p14diag_relative      # gitignored (data/chroma_backup_*/)
.venv/bin/python -m scripts.migrate_source_relative data/chroma_backup_p14diag_relative \
  --kb-root /Volumes/DevSSD/Project/sdtm-pedia/knowledge_base --apply   # sdtm_kb_v1 applied=4329, study 0, outside_root 0
export SDTM_RAG_CHROMA_DIR_OVERRIDE=$PWD/data/chroma_backup_p14diag_relative
# 再跑闸 2 两条 (输出 *_relcopy.json) + 闸 1
```
- CDISC 140q: 140/140 逐题 source_recall 与 `p0_runs/cdisc140.json` **0 差** (均值 0.9917)
- study 48q: 51 条逐题与 monorepo `split10_p0/study48.json` **0 差**
- pytest: 1 failed / 2605 passed / 2 skipped —— 剩下的 `test_kb_crossref_completeness.py::test_indexed_ct_chunks_carry_every_variable`
  只按**绝对** source 过滤 (`where={"source": vi_abs}`), 是 1.1 漏改的消费方: 对已迁移的 (含生产) 索引恒 fail, 与本机数据无关

## 业务判定
FAIL (按 brief 停)。代码改动本身未见回归: 迁移后的副本上检索两题集逐题一致; 失败全部归因于本机索引格式 + 1 处测试漏改。

## 下一 attempt 输入
1. 编排者决定是否对本机 `data/chroma` 原地跑上面的迁移 (先备份; 规则 B 不删)
2. 修 `test_kb_crossref_completeness.py:167` 改用与 `_source_where` 同口径 (`$in [abs, rel]`, 或直接相对形)
3. 上线前核实生产 chroma 确为相对形 (`p1_step1.2.md` 声明), 否则新镜像 lifespan 预热 raise
4. `check_index_freshness` 对这份不可用的索引打印 OK —— 只比 KB 指纹不查 source 格式, 记为已知盲区
5. `deploy/README.md`「启动失败」段的 `--kb-root <KB>` 应写明 = 索引里实际存的旧前缀, 不是新 KB 位置
