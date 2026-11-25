# P0 基线 (2026-11-25, HEAD f9d6370 = tag `pre-split-2026-11`)

## 0.1 tag + 备份
- `git tag pre-split-2026-11 f9d6370` (本地, 未推)
- 本地数据备份: `/Volumes/DevSSD/backups/sdtm-pedia-pre-split-2026-11/` (data/chroma + data/study + data/meta + .env, 290M, 1684 文件; `MD5SUMS` 自身 md5 = 04ea367ddea68a4b0efc50914ec4d9c1)
- **未做**: mini 上生产 chroma 备份 (本机无到 mini 的 ssh 配置) → 挪到 1.2 生产切换前, 届时需用户提供访问方式或在 mini 上执行
- **未做**: 5 份旧 chroma 备份归档 (不影响基线, P4 收尾再处理, 规则 B 不删)

## 0.2 基线 (cwd = sdtm-rag/)
| 闸 | 命令 | 结果 |
|---|---|---|
| pytest | `.venv/bin/python -m pytest scripts/tests -m "not slow" -q -p no:cacheprovider` | rc=0; 收集 2587 (`--collect-only -o addopts=""`), skipped 2 (playwright), **passed 2585, failed 0** |
| CDISC 140q | `.venv/bin/python -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output <out>` | source recall **0.9917**; <1.0: q126, q38 |
| study 48q | `.venv/bin/python -m eval.run_eval data/study/st01/eval/test_set_study_v2.yml --retrieval-only --hybrid --study-lookup --collection study_st01 --kb-root data/study/st01/cards --output <out>` | source recall **0.875** (= 历史基线); <1.0: st01_v11_q23r, v2_q03, q06, q08, q18, q22 |
| study gold lint | `.venv/bin/python eval/lint_gold.py data/study/st01/eval/test_set_study_v2.yml --catalog data/study/st01/catalog.json` | rc=0, 0 条未唯一定位 |
| webchat | `node --test webchat/tests/*.test.mjs` | 73/73 pass |

逐题结果: CDISC `p0_runs/cdisc140.json`; study 含真实 OID, 按红线闸放 gitignored `sdtm-rag/data/study/st01/eval/runs/split10_p0/study48.{json,log}` (另有一份在 P0 备份目录之外, 勿入库)。注意: `lint_gold.py` 只适用 study 侧 (必须 --catalog/--docs-dir/--events-catalog)。

## 判据 (预登记)
- 元数据改写类改动 (1.1/1.4): 两题集**逐题 source_recall 一致** + pytest 0 failed
- 重新 embedding 类 (3.3): recall 差 ≤ 1 题
