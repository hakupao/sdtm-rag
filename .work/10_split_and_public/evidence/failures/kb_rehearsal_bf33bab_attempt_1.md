# KB 预演 attempt 1 — 闸 FAIL (2026-11-27)

- **输入**: pedia 本地 KB `00a2e93` (指纹 `bf33babcfd29…`, 前后一致), B 仓 p3 `83f12bb` 代码 (git archive 到 scratchpad), 全新临时 chroma。
- **产物**: 候选 4332 chunks; 140 题 recall 0.9702, 满分 132; 产物在 scratchpad (临时, 不入库), 数字见 `checkpoints/kb_rehearsal_bf33bab.md`。
- **技术判定**: FAIL — 逐题回退 6 > 1 (q16 q43 q96 q98 q99 q101), 满分 132 < 137。
- **业务判定**: 不是 KB 内容错误, 也不是 gold 漂移: pedia `44fb042` 把 CT 单元格改为 `(短名) Cnnnnn`, B 仓 `scripts/build_meta.py:43` `^C\d+$` 不认 → meta.yaml ct_codes 588 → 0。反事实 (剥前缀) 140 题与基线逐题一致。
- **下一 attempt 输入** (审查后补全): B 仓先修 ① `build_meta._split_ct` + `spec_loader.is_ct_code` (兼容两种写法)、PC examples chunker (新结构丢 45 行); 再按用户裁定的 `_model_defhome` 规则与 `kb_upgrade_bundle_checklist.md` 更新锚点 / gold; 前置: 修 `test_p2_seam_characterization` 的日期依赖。用同一 KB 指纹重跑本预演。验收: 140 题逐题回退 0, **且新 KB 下 pytest 全绿**, 且旧 KB 下 meta.yaml / pytest / 两条检索闸不变。
