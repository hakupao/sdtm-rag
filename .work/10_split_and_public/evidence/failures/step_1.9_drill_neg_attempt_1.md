# step 1.9 反例演练 (规则 5) — 闸按预期拦下 (2026-11-26)

- **输入**: sdtm-rag b55d5ca + KB kb-2026.11.25 (A 7819398) 删掉 `domains/DM/spec.md` → 损坏 KB 指纹 c5ef769965fd。
- **跑法** (mini VM `deploy`, 与 kb-sync.yml 同一 `kbsync.py candidate` 代码; 脚本见下): clone → 删文件 → `docker build` 本机候选镜像
  → `sudo python3 deploy/kbsync/kbsync.py candidate --data-root /Volumes/DevSSD/deploy-data/sdtm-rag/data --fp <fp> --ref drill-neg-dm-spec
  --a-commit <A> --prod-image <线上镜像> --cand-image sdtm-rag-kbcand:<fp12> --env-file /opt/sdtm-rag/.env --max-regressions 1`。
- **产物**: rc=1, 167s。gate `FAIL`: 逐题回退 9 > 1 (q02 q08 q135 q20 q43 q45 q92 s01 s03, 与本机实测同一组); 全中 129 < 138-1; 平均 0.9417 < 0.95; n=140; chromadb 1.5.9。
  候选目录改名归档 `chroma_failed_c5ef769965fd_20261126T051433Z` / `meta_failed_…` (留在数据根, 不删)。候选镜像已删。
- **技术判定**: 闸生效; 挂载叠加 / 子容器写数据根 / 1536m 内存 / 候选灌库 在 VM 上首次实跑通过。
- **业务判定**: 生产未动 — `docker exec sdtm-rag-api python -m scripts.check_index_freshness` → OK f863e45445a6; api healthy cb5fd06; LAN /api/health 200。
- **下一步**: 无需重跑; 正例演练待用户确认推 A 仓。
