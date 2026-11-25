# step_00 recon: deploy_ops — Explore (opus), read-only

Repo: /Volumes/DevSSD/Project/sdtm-pedia/sdtm-rag. Read-only, very thorough. Plan context: run TWO instances of the same code: a private instance (with study st01 data) and a public internet instance (CDISC KB only, no study), exposed via Cloudflare Tunnel; currently deployed as containers on a "mini" VM via Gitea Actions (.gitea/workflows/sdtm-rag.yml at repo root) and/or launchd on the Mac.

Report with file:line refs:
1. sdtm-rag/deploy/: container/{Dockerfile,compose.yml,Dockerfile.dockerignore}, deploy.sh, plist templates, README runbook. Ports (8000 api / 8501 ui), volumes (data/, .env), create_host_path, healthcheck, how chroma is provided (mounted? built?), the absolute-path constraint (chroma metadata stores /Volumes/DevSSD/Project/sdtm-pedia/knowledge_base/... ; S1 mapping check at startup in server/main.py ~205). What would need to change to run 2 instances side by side (different .env, ports, data dirs, compose project names).
2. Whole workflow file /Volumes/DevSSD/Project/sdtm-pedia/.gitea/workflows/sdtm-rag.yml: steps, secrets, rollback, health check.
3. Is launchd still in use? (DEPLOY_PLAN.md, deploy/README). Current prod: Mac launchd or VM container or both?
4. Ingest pipeline: scripts/ingest.py, how chroma collections (CDISC, study_st01, study_st01_docs) are built, time/cost to rebuild, kb_freshness / check_index_freshness stamps. Could a CDISC-only chroma be produced by copying collections or needs re-ingest? Embedding model and cost.
5. Test suite: how to run (pytest paths), approx number of tests, eval harness (eval/, golden sets 53q/48q study golden v2, lint_gold.py), how long / costly; which are zero-LLM regression gates usable for "no regression after split".
6. Any reference to Cloudflare / tunnel / TLS / domain in DEPLOY_PLAN.md §6 roadmap.
Under ~900 words, facts only.
