# 路径对照表 (旧 → 新)

> 2026-11-25 R1 目录重组。历史文档 (`docs/history/`、`docs/evidence/`、`docs/plans/`、`docs/retrospectives/`、`docs/design/`)
> 正文里的裸路径保持原样不改写, 按下表换算。相对 Markdown 链接已全部改写为新位置。

| 旧前缀 / 文件 | 新位置 | 备注 |
|---|---|---|
| `sdtm-rag/<x>` (monorepo 时代) | `<x>` | 2026-11 拆仓, 本仓根 = 原 `sdtm-pedia/sdtm-rag/`; 旧 SHA 见 `monorepo_commit_map.txt` |
| `branches/07_rag_kg/sdtm-rag/<x>` (更早) | `<x>` | 2026-07 restructure v3 之前的 monorepo 路径 |
| `scripts/tests/` | `tests/` | Python 导入 `scripts.tests.` → `tests.` |
| `evidence/` | `docs/evidence/` | 含 `evidence/checkpoints/`、`evidence/failures/`、`evidence/step_*_audit.md` |
| `failures/` (仓根) | `docs/evidence/failures/` | 与原 `evidence/failures/` 合并, 无重名 |
| `evidence/RETROSPECTIVE_kgval.md` | `docs/retrospectives/RETROSPECTIVE_kgval.md` | |
| `RETROSPECTIVE_*.md` (仓根) | `docs/retrospectives/` | |
| `docs/superpowers/*RETROSPECTIVE*.md` | `docs/retrospectives/` | |
| `PLAN_*.md` (仓根) | `docs/plans/` | |
| `docs/superpowers/plans/` | `docs/plans/` | 文件名带日期, 与 `PLAN_*` 不重名 |
| `docs/superpowers/specs/` | `docs/plans/specs/` | |
| `DESIGN_*.md`, `SP1_meta_yaml_design.md`, `SP2_structured_answer_design.md`, `KG_*.md` (仓根) | `docs/design/` | `KG_ROADMAP.md`, `KG_VALUE_EVAL_{PLAN,KICKOFF}.md` |
| `DEPLOY_PLAN.md` | `docs/history/DEPLOY_PLAN.md` | 历史规划; 现行部署文档 = `deploy/README.md` |
| `kg_viewer.html` (仓根) | `viewer/dist/kg_viewer.html` | 生成物, `scripts/build_kg_viewer.py` 产出 |
| `_progress_{c2r,domain_mapping,dossier,phase3_share}.json` (仓根) | `docs/history/progress/` | 各单元收口时的进度记录 |
