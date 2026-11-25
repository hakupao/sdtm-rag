# step_00 recon: repo_split — Explore (opus), read-only

Repo: /Volumes/DevSSD/Project/sdtm-pedia (monorepo). Read-only, very thorough. Plan context: split into TWO git repos: (A) sdtm-pedia — knowledge_base/, source/ (gitignored), milestones/{06_deep_verification,release,ai_platforms,jp_delivery,archive}, web/ (Astro site, frozen), tools/, .work/ KB phases, METHODOLOGY/README/LICENSE/DISCLAIMER; public on GitHub. (B) sdtm-rag — sdtm-rag/ plus RAG docs scattered outside it; private on Gitea (git.bojiang.org), deploys via .gitea/workflows/sdtm-rag.yml. History preserved via git filter-repo.

Report with paths/line refs:
1. Classify every top-level and second-level path (incl. docs/*, docs/superpowers/{plans,specs}/*, .work/* subdirs, milestones/07_rag_kg, milestones/archive contents, .githooks, .gitea, tools, .mcp.json, .claude/ project settings, CLAUDE.md sections) into A / B / both / delete-candidate. Flag ambiguous ones.
2. All cross-references B→A: code using knowledge_base paths (grep parents[N] / "knowledge_base", KB_ROOT), gold/eval files containing "knowledge_base/..." path strings (count files), chroma metadata absolute paths, Dockerfile, CI path filters, pre-commit hook (.githooks uses sdtm-rag/.venv; sdtm-rag/scripts/precommit_oidscan.py — does it scan KB too?). And A→B refs (README links to sdtm-rag, web, METHODOLOGY).
3. Docs/meta referencing both: .work/MANIFEST.md chains (list chain names and which side), docs/PROGRESS.md sections, .work/meta/worklog/*.md per phase, .work/AGENT_GUIDE.md, CLAUDE.md Key Paths rows (count per side).
4. Git facts: remotes (origin GitHub public, gitea), branches, whether origin/main is behind gitea/main (it is by 4 commits), tags list, large files in history (git rev-list --objects --all | git cat-file --batch-check, top 15 by size), whether data/study or sensitive things ever entered history (grep history paths for data/study, .env, dogfood_failures).
5. Who consumes knowledge_base besides sdtm-rag (web? tools/build_release.sh? milestones release builds?).
Under ~1000 words, facts only. Do not modify anything.
