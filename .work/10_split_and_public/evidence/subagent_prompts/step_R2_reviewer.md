# R2 reviewer — code-reviewer (opus), independent of the writer

Read-only. Review local unpushed commits ebf0c8a..HEAD in /Volumes/DevSSD/Project/sdtm-pedia (repo reorg: milestones/ → releases/ + archive/*, path fixes, link checker tools/check_links.py, README/README_CN/CLAUDE.md/MANIFEST/AGENT_GUIDE/PROGRESS/PATH_MAP docs). Writer brief: /Volumes/DevSSD/Project/sdtm-rag/.work/10_split_and_public/evidence/subagent_prompts/step_R2_pedia_reorg_executor.md. This repo is PUBLIC (portfolio); website deploys from main via Cloudflare Pages.
Check:
1. Nothing behavior-relevant still points at old paths (web build, bundle scripts, tools/build_release.sh, jp build_zip, any Astro/TS import); run `cd web && npm run build` yourself if fast (node_modules present) or verify statically.
2. knowledge_base/ untouched (tree hash 62dfce36…).
3. README.md / README_CN.md: factual (every number traceable to a repo file — check), no internal IPs/hostnames/local absolute paths/emails beyond what was already public, working links (relative + key external), consistent EN/CN, no claims about a live demo URL. Showcase quality: clear for a stranger in 30 seconds?
4. CLAUDE.md ≤150 lines and its own rules; 跨会话路由词 sensible; no stale state.
5. Anything sensitive newly added in these commits (grep diff for /Users/, 192.168, bojiang.org, tokens).
6. METHODOLOGY.md §2 says audit "active, 97% as of 2026-04-29" while the deep verification is complete (archive/deep_verification/RETROSPECTIVE.md) — propose exact corrected wording grounded in that file.
Output PASS / PASS-with-fixes / FAIL; findings with file:line + concrete fix; < 500 words; English.
