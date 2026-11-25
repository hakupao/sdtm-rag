# P1 step 1.6 + 1.6b 准备 — 清 A 仓 + 历史重写 (未推送) (2026-11-25)

> 状态: **writer 完成, 待 reviewer (规则 D) + 用户确认 force-push**. writer = executor (opus), prompt `subagent_prompts/step_1.6_executor.md`.
> 快照源: monorepo `main` @ `c2d396b` (= gitea/main; GitHub origin/main = `36c54d9`, 落后). monorepo 工作树/refs/config 未动, 本文件是唯一新建文件.
> `SP=/private/tmp/claude-501/-Volumes-DevSSD-Project-sdtm-pedia/58914670-fcad-439e-b68e-c96b616605a2/scratchpad/split` (scratchpad 可能被清, 产物需在推送前用完或另行拷出)


> **本文件将随 `.work/10_split_and_public/` 一起移到 B 仓 (A 历史中已整体去除该目录).**

## 0. v2 (2026-11-25, orchestrator 裁定: A 公开, 不得含内网运维信息) — **以本节为准, §2-§3 为 v1 记录**
- 改动: invert-paths 清单加 `.work/10_split_and_public/` (68 行, 历史命中 1228+36=**1264**); 元文档里所有 `git.bojiang.org` 改为「RAG 问答服务已拆到独立的私有仓 `sdtm-rag`」, 指向 `.work/10_split_and_public/` 的行删掉/改为「拆仓过程记录在 sdtm-rag 仓」(CLAUDE.md 119 行); 提交信息同样去主机名; commit-map **不再入 A**, 只放备份目录.
- 产物: `$SP/a_clean_v2` (main `33dcfff`; 清理提交 `2d9a608` 被剪空) → `$SP/a_rewritten_v2` (**HEAD `ebf0c8a`**, 无 remote). 提交 1159 → **484** (--all 485; 剪 675 含自己的 2d9a608); size-pack 48.26 → **39.19 MiB**.
- 验证 (`python3 -I /Volumes/DevSSD/backups/sdtm-pedia-rewrite-2026-11.verify.py $SP/mirror.git $SP/a_rewritten_v2 /Volumes/DevSSD/backups/sdtm-pedia-rewrite-2026-11.filter_paths-v2.txt /Volumes/DevSSD/Project/sdtm-pedia`): V1 0; V2 11208 − 1264 = 9944 = after (缺 0 / 多 0); V3 11/11 tag 树相等 (文件数同 §3 表); V4 KB 296 blob 一致; V6 fsck 干净, refs = main + 11 tag; HEAD 树 == a_clean_v2 (3762 文件); 前缀 grep (含 `.work/10_split_and_public/`) 0; web build 46 pages (= c2d396b 基线).
- 敏感词扫描 (全历史 blob + 提交信息, 大小写不敏感; `python3 -I /Volumes/DevSSD/backups/sdtm-pedia-rewrite-2026-11.scan-v2.py $SP/a_rewritten_v2 $SP/mirror.git <commit-map-v2>`, 结果 `…scan-v2.txt`):

| 模式 | 路径数 | 说明 | 已在公开 GitHub (36c54d9 祖先) |
|---|---|---|---|
| `192\.168\.` / `bojiang\.org` / `limactl` / `deploy-data` / `/opt/sdtm-rag` | 0 | — | — |
| `Lima` (整词) | 4 | CDISC 肿瘤 CT 文献作者名 "Lima SS" (KB `terminology/core/oncology_part1.md` 首提交 8a88538 + 3 份平台 upload 副本) | 4/4 是 |
| `mini` (整词) | 129 blob 路径, 88 提交信息 | "Mini-Mental State" (CT 术语, 617) + 06 深审 "mini-audit"/"mini-batch" 术语; 无主机 "mini" | 129/129 + 88/88 是 |
  ⇒ 重写后 A 中所有命中都早已公开且无运维含义; 未做任何自动删除.
- 备份 (新增, 旧版保留): `sdtm-pedia-rewritten-2026-11-v2.bundle` (150ab6ad…3743), `sdtm-pedia-a_clean-2026-11-v2.bundle` (0a59530e…cbb8), `…commit-map-v2.txt` (040b914c…d6bb), `…ref-map-v2.txt`, `…filter_paths-v2.txt` (a33e777c…bcc), `…scan-v2.py` / `…scan-v2.txt`.
- §4-1 (内网信息公开) 已由 v2 消除; §4-3 旧 SHA 换算改用备份目录的 commit-map-v2.

## 1. 安全归档 (规则 B, 不删)
- `git clone --mirror <monorepo> $SP/mirror.git` → `git bundle create /Volumes/DevSSD/backups/sdtm-pedia-pre-rewrite-2026-11.bundle --all`; `git bundle verify` = "complete history"
- sha256 `f821b5a90cd43ca83d6558ae9dded064df3715bff80736cd582540fbb851d836`, 50,142,562 B
- bundle refs: main/gitea/* = c2d396b; origin/* = 36c54d9; origin-pr/1 = 6d4cebe; origin-pr/2 = 8d706ee; 11 tag (见 §3 表 old 列); mirror 全部 1175 提交
- 同目录 (`/Volumes/DevSSD/backups/`): `sdtm-pedia-pre-rewrite-2026-11.commit-map.txt` (sha256 c1ce66d5…f37b); `sdtm-pedia-rewrite-2026-11.filter_paths.txt` (67 行, 3724ee04…1bfe); 复验脚本 `sdtm-pedia-rewrite-2026-11.verify.py` (5068f8e8…5653); 重写结果 `sdtm-pedia-rewritten-2026-11.bundle` (--all, cb0acfcd…c6e5) 与清理分支 `sdtm-pedia-a_clean-2026-11.bundle` (main, 994942a9…9361) — scratchpad 被清也能恢复

GitHub 现状 (`gh release view` / `git ls-remote --tags origin`, 2026-11-25):

| release | 发布 | assets (name size B) |
|---|---|---|
| v1.0 | 2026-04-28 | chatgpt_bundle_v1.0.zip 1522700; claude_bundle_v1.0.zip 802335; gemini_bundle_v1.0.zip 506288; notebooklm_bundle_v1.0.zip 1619374 |
| v1.1 | 2026-05-15 | chatgpt 1541479; claude 798296; gemini 527782; notebooklm 1625066 (`*_bundle_v1.1.zip`) |
| v1.4 (Latest) | 2026-05-22 | chatgpt 1543007; claude 801414; gemini 527763; notebooklm 1627581 (`*_bundle_v1.4.zip`) |

- 远端 tag 10 个 (GitHub 与 gitea 相同): archive/verify-chapters-2026-04-15, pre-restructure-v3, v1.0, v1.0-company-release, v1.1, v1.1-company-release, v1.2/v1.3-company-release, v1.4, v1.4-company-release. `pre-split-2026-11` **仅本地**.
- PR #1/#2 均 CLOSED; forkCount 0; 默认分支 main.

## 2. [v1] 清理提交 (`$SP/a_clean`, `git clone --no-local` monorepo, 不带 origin-pr/gitea refs)
- `8d6cad6` 删 B 路径 798 个 (= manifest HEAD 800 − restructure-v3 两份双留). 重写时此提交变空被剪 (预期).
- `94334b0` 元文档 + hooks (重写后 `1b6f723`):
  - CLAUDE.md 150→120 行: 删 Phase 7/sdtm-rag/.githooks 共 31 行 Key Paths, 修 `||` 并行行, 加 RAG 仓 (`git.bojiang.org/bojiang/sdtm-rag`, private) + `.work/10_split_and_public/` 指针
  - MANIFEST: 删 Chain 07_RAG + 07_rag_kg Plan Map/Quick Ref 行; Chain D 的 RAG 侧 25 行块 → 1 行指针; 目录表加 10_split
  - PROGRESS: Phase 7 行 → 拆仓指针; 「关键 milestone (近 30 天)」段 (全 RAG) → 1 行指针; 加 10 拆仓行
  - AGENT_GUIDE: 删 RAG/KG/doc 轨/检索 路由词 7 条 + 05_rag_kg 禁令; 05/7 RAG 行改指针
  - worklog INDEX: 删 phase_07_rag_kg 行, 反查表改指针
  - README(_CN): 树去 sdtm-rag/、milestones/07_rag_kg、.work/05_rag_kg、docs/DESIGN_RAG_KG.md; 路线图 4 条 RAG 项 → 1 条; 新增「AI Q&A Service / AI 问答服务」段 (公开站筹备中, **无 URL**)
  - hooks: `.githooks/` 随 B 路径删 (且从历史清除); `tools/git-hooks/` **删** — 未启用, 唯一检查是冻结 release 教程三语同步提醒 (warning-only), 对 A 无用. 切换时 monorepo 本地 `core.hooksPath=.githooks` 需 unset (未改).
  - `.gitignore`: 加 `/sdtm-rag/` (防过渡期本地残留目录含 .env/data 被误 add 回); 删过时注释
  - 代码引用: `.work/04_optimization/scripts/generate_variable_index.py:267` 注释改指 RAG 仓. 其余命中均为历史 prose/json (`.work/09_repo_refactor_v3/_progress.json`, `milestones/release/v1.4/BUILD_MANIFEST.json`), 未改. `web/` 0 命中.
- web build: `cd web && npm ci && npm run build` → rc 0, 46 pages; 基线 c2d396b 同命令也是 46 pages (node v26.13.0; .nvmrc=22.12.0 未切换, 仍过)
- 两仓之间无遗漏: `git diff --name-only edce7f3 c2d396b` (B 抽取点→本快照) 6 个文件全在 `.work/10_split_and_public/`, B 路径 0

## 3. [v1] 历史重写 (`$SP/a_rewritten` = `git clone --no-local a_clean`, 另一份全新 clone)
命令: `git filter-repo --invert-paths --paths-from-file filter_paths.txt` (filter-repo a40bce548d2c; 未用 --force). 清单 = 11 个目录/单文件 (sdtm-rag/, branches/07_rag_kg/, milestones/07_rag_kg/, .work/05_rag_kg/, .gitea/, .githooks/, docs/DESIGN_RAG_KG.md, 3 handoff, worklog/phase_07_rag_kg.md) + 56 个 superpowers 文件逐一列名 (63 历史 − 5 A 专属 − 2 restructure-v3).
预检: 清单命中历史路径 **1228** (= manifest 1230 − 2 双留), HEAD 798.

验证 (全部用 `-c core.quotepath=off`, 否则非 ASCII 路径被引号包住会假 0). V1-V4/V6 + 扫描一键复跑:
`python3 -I /Volumes/DevSSD/backups/sdtm-pedia-rewrite-2026-11.verify.py $SP/mirror.git $SP/a_rewritten /Volumes/DevSSD/backups/sdtm-pedia-rewrite-2026-11.filter_paths.txt /Volumes/DevSSD/Project/sdtm-pedia` (mirror 被清时可用 `git clone --mirror <pre-rewrite bundle>` 代替)
- V1 `git log --all --name-only --format= | grep -cE '^(sdtm-rag|branches/07_rag_kg|\.gitea|milestones/07_rag_kg|\.githooks|\.work/05_rag_kg)/'` → **0**
- V2 集合 (python set, 精确): before 11208 − 去掉 1228 = 9980; after 9981 (缺 0 / 多 1 = 重写后新增的 a_commit_map.txt)
- V3 全部 11 tag: 新 tag 树 == 原 tag 树滤掉 B 路径 (逐 path mode+blob 比), **11/11 equal**

| tag | old→new commit | A 文件 | 去掉 |
|---|---|---|---|
| archive/verify-chapters-2026-04-15 | 4650a31 (不变) | 323 | 0 |
| pre-restructure-v3 | 3e21ab1→7da971c | 3774 | 441 |
| pre-split-2026-11 (本地) | f9d6370→d58321a | 3764 | 796 |
| v1.0 | 2de87c4→a1e2245 | 1684 | 2 |
| v1.0-company-release | c1d6e54→01d7411 | 1379 | 2 |
| v1.1 / v1.1-company-release | 6fb6d0d→e7cb948 | 3220 | 2 |
| v1.2-company-release | b0b6804→1fd9403 | 3417 | 2 |
| v1.3-company-release | e2c360e→57a4910 | 3665 | 2 |
| v1.4 / v1.4-company-release | 0bd647d→46dc20d | 3846 | 2 |

- V4 `knowledge_base/` HEAD 296 文件 blob 与 monorepo HEAD 完全一致; 重写 HEAD 树 == a_clean HEAD 树 (3798 文件)
- V5 web build (重写 HEAD 的一次性 clone) rc 0, 46 pages
- V6 `git fsck --full` 干净; 旧 sdtm-rag blob (`main:sdtm-rag/server/main.py` a1d67fb) 与旧 commit c2d396b 均不可解析; refs 只剩 main + 11 tag, 无 remote / refs/replace
- 规模: monorepo main 1157 + 2 清理提交 = 1159 (--all 1160) → **489 / 490** (剪掉 670 = 669 个历史纯 RAG 提交 + 自己的 8d6cad6; map 中 new=0000…); 加 commit-map 提交后 490 / 491; size-pack 48.27→**39.30 MiB** (mirror 45.09 MiB 含 PR refs)
- commit-map 已作为提交 `ee5fe4e` 入库: `.work/10_split_and_public/evidence/checkpoints/a_commit_map.txt` (1161 行) + 备份目录副本. 重写后 HEAD = **ee5fe4e**, 490 提交. ref-map 存 `$SP/a_ref_map.txt`.

## 4. 推送前须裁定 / 已知问题 (writer 只报不改)
1. **内网信息将公开**: 重写后历史里 `.work/10_split_and_public/evidence/checkpoints/p1_step1.2{,_runbook}.md` 含 `192.168.100.150` + Lima VM 名/路径; `bojiang.org` 主机名出现在 10_split 文档和本次新元文档 (brief 要求的 RAG 仓指针) 共 7 路径. 这些都是 GitHub 尚未有的本地提交. 若要去掉须在推送前改文件并重跑 (或再 filter-repo `--replace-text`). `sdtm-compare.local` 仅为 JSON Schema `$id`, 无害. 密钥模式 (sk-/AKIA/ghp_/PRIVATE KEY) 全历史 0.
2. `pre-split-2026-11`: 本地专属 tag, 重写后落在 d58321a (原 f9d6370 为 RAG 提交, 移到最近的 A 祖先). runbook 默认**不推** (远端维持 10 个); 要推需用户决定.
3. 旧 SHA 失效: 文档/注释里引用的旧 SHA (如 generate_variable_index.py 的 `6ed3d2b`) 需经 `a_commit_map.txt` 换算; 被剪的 RAG 提交查 B 仓 `docs/history/monorepo_commit_map.txt`.
4. monorepo 里未跟踪的 `subagent_prompts/step_1.5a_executor.md`、`step_1.6_executor.md` 与本文件不在重写仓 → 推送前用 §5 步骤 1 补进.
5. B 侧元文档内容 (CLAUDE.md 31 行 Key Paths、MANIFEST Chain 07_RAG + Chain D RAG 侧块、PROGRESS「关键 milestone」段、AGENT_GUIDE RAG 路由词) 在 A 里是删除而不是迁移 → 1.5 (B 仓自己的 CLAUDE/AGENT_GUIDE/PROGRESS) 从 monorepo `c2d396b:<path>` 或重写后 `d334ef8:<path>` 取原文.
6. 两处超出 brief 字面的判断: 删 `tools/git-hooks/`; `.gitignore` 加 `/sdtm-rag/`. 均可单独撤回.
7. 已知局限 (PLAN 1.6b): GitHub 已关闭 PR 的 `refs/pull/{1,2}/head` 与缓存仍可按旧 SHA 访问旧对象, 彻底清除需 GitHub 支持 (D5 下不追).

## 5. 推送 runbook (v2; 未执行; 须用户确认后)
```bash
SP=/private/tmp/claude-501/-Volumes-DevSSD-Project-sdtm-pedia/58914670-fcad-439e-b68e-c96b616605a2/scratchpad/split
GH=https://github.com/hakupao/sdtm-pedia.git; GT=https://git.bojiang.org/bojiang/sdtm-pedia.git
TAGS="archive/verify-chapters-2026-04-15 pre-restructure-v3 v1.0 v1.0-company-release v1.1 v1.1-company-release v1.2-company-release v1.3-company-release v1.4 v1.4-company-release"
M=/Volumes/DevSSD/Project/sdtm-pedia

# 1) 追平: 快照后 monorepo 有新提交 / 新未跟踪文件?
git -C $M status --short                          # 10_split 文件不进 A (已被 filter); 由 orchestrator 迁 B, 这里无需补
git -C $M log --oneline c2d396b..main            # 非空 → 推荐整套重跑 (碰 B 路径的新提交必须先移植到 B 仓, 不能让 filter 静默吞掉:
#   git -C $M diff --name-only c2d396b main | grep -Ef <(sed 's#^#^#' filter_paths.txt) 应为空):
#   (scratchpad 已清时: git clone /Volumes/DevSSD/backups/sdtm-pedia-a_clean-2026-11-v2.bundle $SP/a_clean_v2; 成品 a_rewritten_v2 可从 …rewritten-2026-11-v2.bundle 恢复)
#   git clone --no-local $M a_clean2 && cd a_clean2
#   sed 's#/$##' /Volumes/DevSSD/backups/sdtm-pedia-rewrite-2026-11.filter_paths-v2.txt | xargs git rm -r -q --ignore-unmatch && git commit -m ...
#   git fetch $SP/a_clean_v2 main && git cherry-pick 33dcfff && (cherry-pick 后若元文档冲突手工合)
#   git clone --no-local a_clean2 a_rewritten2 && cd a_rewritten2 && git filter-repo --invert-paths --paths-from-file <同清单>
#   重跑 §0 verify + scan; commit-map 只拷到备份目录. 仅有零星 A 文件 → 也可直接拷进 a_rewritten_v2 新提交.

# 2) lease 预期值核对
git ls-remote $GH refs/heads/main   # 期望 36c54d970eda56cf3ee553ffc6918b897b953253
git ls-remote $GT refs/heads/main   # 期望 c2d396bd29d3583b6c8e46796e9509f390d1ce3c (若变了 → 回到 1)

# 3) 推送 (按 URL, 带 lease; tag 原地强更, 禁止先删后推 — 删 tag 会让 release 变 draft)
cd $SP/a_rewritten_v2
git push --force-with-lease=refs/heads/main:36c54d970eda56cf3ee553ffc6918b897b953253 $GH main:refs/heads/main
for t in $TAGS; do git push --force $GH "refs/tags/$t:refs/tags/$t"; done
git push --force-with-lease=refs/heads/main:c2d396bd29d3583b6c8e46796e9509f390d1ce3c $GT main:refs/heads/main
for t in $TAGS; do git push --force $GT "refs/tags/$t:refs/tags/$t"; done
# gitea 新 main 不含 .gitea/workflows → 这个仓不再触发 RAG 部署; RAG 部署待 B 仓 CI (1.5) 开.

# 4) 核对
git ls-remote --tags $GH | grep -v '\^{}' | wc -l      # 10; 与 a_rewritten_v2 对应 tag SHA 一致
for v in v1.0 v1.1 v1.4; do gh release view $v --repo hakupao/sdtm-pedia --json isDraft,tagName,assets \
  --jq '{tagName,isDraft,assets:[.assets[]|{name,size}]}'; done   # isDraft=false; assets 与 §1 表逐一相同
#   若变 draft: gh release edit <v> --repo hakupao/sdtm-pedia --draft=false --tag <v>
curl -sI https://sdtm-pedia.pages.dev/ | head -1       # 200; 另在 Cloudflare Pages 面板确认生产分支=main 且 ebf0c8a 构建成功

# 5) 本地切换 (切勿在 monorepo 工作树 reset --hard / clean: sdtm-rag/ 下有未跟踪 .env、data/、.venv)
#   ⚠ 旧历史回流风险: 新旧历史共享 2026-04-15 前的提交 (4650a31 未变), 任何旧 clone 一 pull 就能干净合并再 fast-forward 推回整段 RAG 历史.
#   规则: 除 monorepo 外的所有 A clone (含部署机/其它机器) 一律重新 clone 或 `git fetch --force --tags && git reset --hard origin/main`, 禁止 pull/merge.
#   monorepo 里: git fetch --force --tags origin; git fetch --force --tags gitea (普通 fetch 不覆盖本地已有 tag → 11 个 tag 仍指旧提交);
#   本地专属 `pre-split-2026-11` (指 f9d6370 = 带 RAG 祖先) 必须删或改指: git -C $M tag -d pre-split-2026-11 (原值在 pre-rewrite bundle);
#   之后永远不要 `git push --tags` / `--mirror`.
#   推荐: A 仓另 clone 到新路径使用; monorepo 在 B 仓开发环境 (1.7) 就绪前保持原样.
#   ⚠ checkout 新 main 也会删掉工作树里已跟踪的 `.work/10_split_and_public/` → 先确认已迁到 B.
#   真要切 monorepo: git -C $M config --unset core.hooksPath; git -C $M fetch origin;
#   git -C $M checkout -B main origin/main (会删已跟踪的 sdtm-rag/* 文件, 未跟踪的保留且被 /sdtm-rag/ 忽略);
#   git -C $M update-ref -d refs/remotes/origin-pr/1; ...origin-pr/2

# 回滚 (从 bundle)
git clone --mirror /Volumes/DevSSD/backups/sdtm-pedia-pre-rewrite-2026-11.bundle /tmp/rb.git && cd /tmp/rb.git
git push --force $GH 36c54d970eda56cf3ee553ffc6918b897b953253:refs/heads/main
git push --force $GT c2d396bd29d3583b6c8e46796e9509f390d1ce3c:refs/heads/main
for t in $TAGS; do git push --force $GH "refs/tags/$t:refs/tags/$t"; git push --force $GT "refs/tags/$t:refs/tags/$t"; done
# 然后重跑步骤 4 核对 (release/Pages)
```
