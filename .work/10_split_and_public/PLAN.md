# 10 拆仓 + RAG 对外开放 — PLAN

> 状态: **v0.3 需求已澄清, 待开工指令** (2026-11-25; v0.1 经 critic 审 REVISE, 13 条已吸收, 见 `evidence/checkpoints/plan_review_v0.1.md`)
> Tier: **3** (多天 / 对外暴露 / 涉及不可逆的仓库历史操作)
> 调查依据: `evidence/recon_2026-11-25.md` (4 路只读调查, prompt 全留 `evidence/subagent_prompts/`)

## 0. 目标与已定决策

| # | 决策 (用户 2026-11-25) |
|---|---|
| D1 | 拆 **两仓**: `sdtm-pedia` (KB + 冻结的发布/网站, GitHub 公开) / `sdtm-rag` (RAG 服务, Gitea 私有) |
| D2 | RAG 对外 **谁都能试**: 免费额度 + 全站限额; 界面可填自己的 API key (BYOK) |
| D3 | 私有站与公开站 **功能一致**, 唯一差别 = 私有站多 STUDY01 (实例级配置, 一套代码) |
| D4 | 答题模型多 provider, 不只 Anthropic |
| D5 | study 数据非机密, **不做** provider 白名单限制 |

**完成定义**: 两仓各自 CI 绿 + 零 LLM 回归闸达标 (§2 P0.2 判据); 公开站经 HTTPS 外网可用, 限额/BYOK/多 provider 过独立安全审查; 私有站功能不退化。

**非目标**: 不改检索/答题算法; 不重启网站/多平台发布线; 不做用户账号体系 (访客 = 签名 cookie + Cloudflare 真实 IP)。

## 1. 用户裁定 (2026-11-25)

**已裁**: Q2 = 每人每天 10 题 / 全站 $5; Q3 = DeepSeek v4-pro; Q5 = **(b) 重写 A 仓历史**; Q1 = **Cloudflare 上的 `bojiang.org`** (2026-11-26 用户裁定; 子域名 3.4 时定)。Q4 (拍平) / Q6 (公开站不开自定义地址) 按推荐执行, 用户可推翻。
第二轮 (同日): 拆仓目的 = 公开/私有边界与减负**同等重要** + 两仓**分开维护** + 公开站要**像产品一样对外展示**; 冻结资料**留 A 仓**; KB **会持续修改** → 需 KB→RAG 同步管线 (P1.9)。

第四轮 (同日): 公开站受众 = **看我项目、对项目感兴趣的人** (作品展示, 流量预期低); 私有站 = **公司局域网**用, 额度不够时由用户自己配 API (私有站额度可配置/放宽); 拆仓根本目的 = **降低维护成本** → 全计划按"少维护"取舍 (见 §5)。部署位置: **mini 虚拟机** (与私有站同机; 用户确认), 公开容器须做网络隔离 (3.4b)。

**已裁 (主会话, 2026-11-26)**: P2.9 审查提出的「每 IP 每日 30 题 vs 每访客 10 题」—— 接受; 因公司共享出口 IP, 默认上调为 **50 题/IP/天、同时进行 5 个/IP** (清 cookie 的同一 IP 上限), 总量仍由免费池 $3 兜底; 详见 `docs/design/P2_request_context.md` §5。

第三轮 (同日): O1 公开站**第一期不开**上传校验与多模型对比 (私有站保留, 后续加防护再开); O2 服务器位置/IT **不构成约束** (用户: 没关系) → 维持 mini VM + Tunnel + 3.4b 网络隔离; O3 国内 provider (通义/Kimi/智谱/硅基等) 默认做成**预设端点** (无需开自定义地址), 用户可推翻。

原问题表:

| # | 问题 | 推荐 |
|---|---|---|
| Q1 | 公开站域名 | 已在 Cloudflare 的域名下开子域, 如 `ask.<域名>` |
| Q2 | 免费额度 | 每访客每天 10 题; 全站服务器 key 每天 $5 封顶 (含 embedding/联网/内部调用); 到顶后只剩 BYOK |
| Q3 | 免费题模型 (服务器 key) | DeepSeek v4-pro (便宜) 或 Sonnet 5.5; 免费层关联网 |
| Q4 | B 仓目录 | **拍平** (代码在仓根, KB 以 submodule 挂 `knowledge_base/`) |
| Q5 | **RAG 历史的公开性** | 事实: sdtm-rag 截至 2026-09-30 的全部历史**已在公开 GitHub**; A 仓不重写历史的话这些永远公开, 拆仓只让**新提交**私有。且本地领先的 4 个提交含内网 registry IP 与 Gitea 主机名。选项: (a) 接受历史公开, A 仓删 RAG 后正常推 (推荐, D5 下无机密); (b) A 仓也 filter-repo 去 RAG 历史 → 需 force-push, 影响 tag/fork/Pages |
| Q6 | 自定义 OpenAI 兼容地址 | 公开站**不开** (只给已知 provider 官方端点, 根除 SSRF); 私有站可开 |

## 2. 阶段与步骤

### P0 基线冻结 (半天)
| Step | 内容 | 验收 |
|---|---|---|
| 0.1 | 打 tag `pre-split-2026-11`; 备份 `data/` 与 mini 上生产 chroma; 旧 chroma 备份 5 份**归档到外部盘不删** (规则 B) | tag 存在; 备份 md5 记录 |
| 0.2 | 录基线 + **预登记判据**: `pytest -m "not slow"` 通过数; `run_eval --retrieval-only` CDISC 140q + study 48q (基线 recall 0.875); `lint_gold.py`; webchat node 测试 | `evidence/checkpoints/p0_baseline.md` 附复跑命令; 判据: 元数据改写类改动 = 逐题一致; 重新 embedding 类改动 = recall 差 ≤ 1 题 |

### P1 拆仓 (1-2 天)
| Step | 内容 | 验收 |
|---|---|---|
| 1.1 | **去绝对路径 (不重新 embedding)**: chunk id 已是相对路径 (ingest.py:335), 只有 `source` 元数据是绝对 → 用 `collection.update(ids, metadatas)` 原地改写为相对; 代码**同时兼容绝对/相对**两种 (过渡期); 先查 BM25 索引、`_vi_section_map` 等是否还依赖 `source`; 17 处 `parents[N]/"knowledge_base"` + `config.py:16,402` 收敛到唯一 `kb_root`; 修两处变量名 bug (`.env.service.template` 的 `SDTM_RAG_KB_ROOT`、旧 compose 的 `SDTM_RAG_CHROMA_DIR` 均与代码读的 `*_OVERRIDE` 不符) | 本地: P0 闸逐题一致 |
| 1.2 | **生产切换 (防自动部署打挂)**: 推 main 会自动构建部署 (workflow 路径过滤含 `server/**`)。顺序: ① 兼容版代码上线 (新旧 chroma 都能起) → ② mini 上停服、改写生产 chroma 元数据 → ③ 起服验证 → 回滚预案 = 旧 chroma 副本 + 上一镜像 tag | 私有站健康检查过; 回滚命令写进 checkpoint 并演练一次 |
| 1.3 | **抽 B 仓**: `git filter-repo` 保留 `sdtm-rag/` + 旧路径 `branches/07_rag_kg/` + `.gitea/` + RAG 文档 (recon §1 清单); path-rename 拍平 | 新仓历史追到 2026-04; 文件清单逐项对照 recon §1 |
| 1.4 | B 仓接 KB: submodule 指向 GitHub `sdtm-pedia` 钉 commit; ingest stamp 记 `kb_fingerprint` | P0 闸逐题一致 |
| 1.5 | B 仓 CI/部署: Dockerfile 去 `/Volumes/...` 绝对路径, build context = B 仓根 (checkout 含 submodule); 删遗留 `sdtm-rag/{Dockerfile,docker-compose.yml}` 与 launchd plist 模板; pre-commit 闸迁 B 仓; **CI 加跑 `pytest -m "not slow"`** (现在不跑测试) | Gitea 新仓 Actions 构建+测试+部署成功 |
| 1.6 | **清 A 仓**: 删 B 的路径; 拆元文档 (CLAUDE.md Key Paths ~33 行迁 B; MANIFEST chain 07_RAG 迁 B; PROGRESS 近 30 天段迁 B; AGENT_GUIDE 拆); 修 CLAUDE.md `||` bug; README 仓库树指向 B; 去掉依赖 sdtm-rag venv 的 pre-commit 闸 | A 仓 web 本地 build 过; ai_platforms/06/jp 脚本可跑 |
| 1.6b | **重写 A 仓历史 (Q5=b, 不可逆, 单独确认)**: 在**全新 mirror clone** 上 `git filter-repo --invert-paths` 去掉 B 的全部路径 (含旧 `branches/07_rag_kg/`、`.gitea/`、RAG 文档); 事前: 原仓完整 mirror 打包归档 (规则 B)、记录 GitHub 上 tag/release 列表、处理 2 个开着的 fork PR (`origin-pr/1,2`)、确认 Cloudflare Pages 绑定的分支; 事后: force-push main + 全部 tag, 核对 10 个 tag 与 release 资产仍在、Pages 重建成功 | 新历史 `git log --all -- sdtm-rag` 为空; tag 数 = 10; 网站 prod 正常; **已知局限写进 checkpoint**: GitHub 上旧提交在 PR ref / 缓存中可能仍可按 SHA 访问, 彻底清除需联系 GitHub 支持 (D5 下无机密, 不追) |
| 1.7 | 开发环境迁移: B 仓 clone 到新路径建 venv; Claude 记忆按项目路径存 → 复制 RAG 相关 memory 到新项目目录, **并改写其中的路径** (`sdtm-rag/server/...` → `server/...`) | 新路径开 session 能读到记忆, 抽 3 条路径可打开 |
| 1.8 | 独立审查 (规则 D, `code-reviewer`) + P1 phase_report | 审查 PASS |
| 1.9 | **KB→RAG 同步管线** (KB 持续修改): A 仓 KB 变更 → B 仓自动开"升级 submodule"变更 → CI 跑零 LLM 闸 (CDISC 140q recall 差 ≤1 题; 不达标阻断并归档 failures/) → 合入后私有/公开两套 chroma 各自重建 (按 `kb_fingerprint` 判断是否需要) → 部署; A 仓保留自己的 CLAUDE.md / Chain D 追溯流程 | 演练一次: A 仓改一行 KB → B 仓两实例索引更新且闸通过 |

### P2 统一产品能力 (B 仓, 3-5 天)
| Step | 内容 | 验收 |
|---|---|---|
| 2.1 | **实例档位** `SDTM_RAG_INSTANCE=public\|private`: public 强制关 study 四开关 (federation / study_lookup / study_docs / **dossier**), 发现 study 仍开或 `data/study` 被挂载 → 拒绝启动; 请求里 `dossier="on"` 在 public 档直接 4xx (不只是总开关关); 联网勾选框移出 study `#scope` 区 | 单测覆盖两档 + `dossier=on` 被拒 |
| 2.2 | **请求成本上界 (免费题必须有)**: `history` 服务端裁剪 (≤8 条且总 ≤20k 字; 现在 `list[MessageItem]` 条数无上限, rag.py:1107 原样拼进 prompt); 调用前估 token, 超出剩余预算直接拒; ASGI 层请求体大小上限 | 构造超长 history → 被裁/被拒的测试 |
| 2.3 | **接口收口** (public 档): **不注册** `/api/validate*` (pyreadstat 解析不可信二进制) 与 `/api/ask_compare`; 关 `/docs` `/openapi.json`; **模型白名单只认公开模型 id**, 拒内部组 (`hard`/`light`/`default-fallback` 现在可被访客直接选, llm_config.py:144); `/api/flag` 写到 `data/` 挂载并限大小/频率; `/api/info` 去内部字段; Streamlit (`ui`) 公开档不部署 | 每个接口一条测试 |
| 2.4 | **provider 注册表**: Anthropic / OpenAI / Gemini / DeepSeek + 国内预设端点 (通义/Kimi/智谱/硅基流动等, 固定官方地址) (+ 私有站可选自定义 OpenAI 兼容); 能力矩阵 (工具调用 / 看图 / 上下文长度 / prompt cache); dossier 自动挂改为按上下文长度; PDF 通道按看图能力; `cost.py` 补新模型价格 | 能力矩阵单表; 每种"能力不足→降级"有一条测试断言 UI 收到降级标记 |
| 2.5 | **BYOK 探针 (先做)**: 实测 litellm 逐次传 `api_key`/`api_base` 对 Router 与直调是否生效、流式 usage 是否回来、中断流时 usage 缺失怎么办 | `evidence/checkpoints/p2_byok_spike.md` 附命令 |
| 2.6 | **BYOK 实现**: key 走请求头, 只存浏览器; 用户 key 请求**不回退到服务器 key**; 日志/异常/`exc_info` 全面脱敏; 自定义地址 (仅私有站) 做 IP 钉死 + 禁重定向 + 拒内网/环回/链路本地/IPv6 ULA/IPv4 映射/`0.0.0.0`/metadata | 脱敏测试 (故意让上游报错, grep 日志无 key); SSRF 测试集全拒 |
| 2.7 | **限额 (按预留计费)**: 访客 = 签名 cookie (独立 secret + 中间件, 现 SessionMiddleware 只在登录门路径) + `CF-Connecting-IP` (仅 Tunnel 来源可信); 免费题每日计数; **全站 $ 封顶覆盖所有服务器 key 调用** (答题、embedding、Tavily、`light` 判库、`hard` 审查); **调用前预留**估算成本, 结束按实际结算, 中断流按预留扣; BYOK 不占免费题但受每分钟限流, 且有独立的每日联网 (Tavily) 额度; 计数 SQLite 持久化于 `data/`; **紧急开关** env 一键关免费题; 可选 Turnstile (CSP 加 `challenges.cloudflare.com`) | 第 N+1 题 429; 重启计数不丢; 封顶后免费题关、BYOK 照常; 中断流也扣费 |
| 2.8 | **UI**: 设置面板加 provider / key / 模型; 剩余额度显示; 429 与降级文案; key 存独立 localStorage 键 + "清除 key" | webchat node 测试 + 浏览器手测截图 |
| 2.9 | 回归 + 独立审查: P0 闸达标; `code-reviewer` 审代码, `security-reviewer` 专审 2.2/2.3/2.6/2.7 | 两份审查 PASS |

### P3 部署上线 (1-2 天)
| Step | 内容 | 验收 |
|---|---|---|
| 3.1 | **容量核对**: mini VM 内存/CPU 能否跑两实例 (现单实例 api 1536m + ui 512m) | 实测余量记录; 不够则先扩 VM |
| 3.2 | compose 参数化: 项目名 / 容器名 (现硬编码, workflow 的 `docker inspect` 也硬编码) / 端口 / 数据目录 / `.env` 按实例; **公开实例只绑 `127.0.0.1`** (只给 Tunnel), 不起 `ui` | 同机两实例并跑; 外网/局域网直连公开实例端口不通 |
| 3.3 | 公开站专用 chroma: 干净树重新 ingest **只含 CDISC** (~2 分钟 ~$0.05) | `study_*` 集合数 = 0; CDISC 140q recall 与基线差 ≤ 1 题 |
| 3.4 | Cloudflare Tunnel + 域名 + HTTPS; cookie `Secure` (现 `https_only=False` 硬编码) + HSTS; **Cloudflare WAF/限速规则作第一道防线**; **各 provider 账户侧设硬性月度上限** (应用内封顶不够) | 外网 HTTPS 可访问; 账户上限截图存证 |
| 3.4b | **网络隔离**: 公开容器独立 docker 网络, 出站只允许 provider API / Tavily / Cloudflare, **禁止访问局域网** (同机有 Gitea、镜像仓库) | 容器内 curl 内网地址失败的测试 |
| 3.4c | **产品化展示**: 公开站首页/空状态说明 (能问什么、示例题、额度规则、key 隐私说明: 不落盘不记日志)、中英界面、关于页链接回 sdtm-pedia; A 仓 README 与网站加 "在线试用" 入口 | 用户审一版截图 |
| 3.5 | 上线验收: 外网冒烟 (免费题 / 各 provider BYOK / 额度耗尽 / 封顶 / 紧急开关); **规则 A 抽检** 每 provider 5 题共 25, 判据: 引用可追溯且无事实错 ≥ 23/25, 低于则该 provider 标"未验证" | `evidence/audit_matrix.md` |
| 3.6 | 上线 7 天观察, 预登记告警阈值: 日费用 > 封顶 80%、429 占比 > 20%、5xx > 2% | `evidence/checkpoints/p3_week1.md` |

### P4 收尾
- 更新 `docs/history/DEPLOY_PLAN.md` / `deploy/README.md` (现仍写 launchd, 已过时), 两仓 CLAUDE.md / PROGRESS / worklog
- `RETROSPECTIVE.md` (规则 C)

## 3. 风险

| 风险 | 对策 |
|---|---|
| 改代码自动部署打挂私有站 | 1.1 兼容新旧 + 1.2 有序切换 + 回滚演练 |
| 免费题单次成本无上界 | 2.2 history 裁剪 + 调用前估算 + 预留计费 |
| 公开站被刷费用 | 访客额度 + 全站封顶 (覆盖全部服务器 key 调用) + WAF + Turnstile + provider 账户上限 + 紧急开关 |
| BYOK key 泄漏 | key 不落盘, 日志脱敏测试, 强制 HTTPS |
| SSRF | 公开站不开自定义地址; 私有站 IP 钉死 + 禁重定向 |
| 不可信文件解析 | 公开站不注册上传接口 |
| 联网结果 prompt 注入 | 免费层关联网; 保留硬性轮数上限 (`web_max_rounds`) |
| filter-repo 漏文件/漏历史 | 对照 recon §1 清单; 原仓 tag 保留可重抽 |
| 别家模型答题质量差 | 能力矩阵 + 规则 A 抽检 + "未验证"标记 |

## 5. 降维护取舍 (第四轮)
- provider/模型清单与价格走**配置文件** + litellm 自带价格表, 不手写价格常量; 新增模型 = 改配置不改代码
- 两实例共用一份 compose 模板 + 两份 `.env`, 不分叉代码路径
- KB→RAG 同步 (1.9) 全自动, 人只看闸结果
- 一期不做: Turnstile (先靠额度+封顶+WAF, 被刷再加)、自定义地址、公开站上传/对比
- 公开站流量低, 免费额度/封顶先按 10 题 / $5, 观察期后可调低

## 6. 并行与多 agent 编排 (用户 2026-11-25 全权委托)
- **串行**: P0 → P1.1–1.3 (主工作树, 改仓库结构, 并行会因 filter-repo 失效)
- **双线**: 1.3 后 A 线 (1.6 + 1.6b 准备; force-push 待确认) ‖ B 线 (1.4/1.5/1.7); 二者完成后 1.9
- **P2**: 先串行 **P2.0 接缝** (ask_stream 引入请求上下文: provider / key / 额度预留 / 实例档位; 冻结前后端接口约定), 再 4 线并行, 各自独立工作树:
  - L1 provider + BYOK (`llm_config.py`, 新 provider 模块) — 含 2.4/2.5/2.6
  - L2 限额 (`auth.py`, 新 quota 模块 + SQLite) — 2.2/2.7
  - L3 实例档位 + 接口收口 (`main.py`, `config.py`, 路由注册) — 2.1/2.3
  - L4 UI (`webchat/` only, 按冻结约定) — 2.8
  - 合并序 L3 → L1 → L2 → L4, 每合一条跑全部零 LLM 闸; 2.9 审查在集成后
- **P3**: 串行 (动生产)
- 每线 writer = `executor` (opus), reviewer = `code-reviewer` / `security-reviewer` (opus), 不同 agent (规则 D); prompt 全留 `evidence/subagent_prompts/`
- 工作树约束: Claude 记忆按路径存 → 每线 prompt 自带完整背景; chroma / KB 用 `*_OVERRIDE` 只读共享, 不复制; venv 各自 `uv sync`

## 4. 流程约束
- 规则 A: 3.5 抽检 N=25; 规则 B: 失败 attempt 归档 `evidence/failures/`; 规则 C: 收尾 RETROSPECTIVE; 规则 D: writer (executor) 与 reviewer (code-reviewer / security-reviewer) 分离。
- 每阶段一次 hard checkpoint, 用户确认后进下一阶段; 1.2 (动生产 chroma)、1.3/1.6 (仓库历史/删目录)、3.4 (对外暴露) 执行前单独确认。
- trace: `evidence/trace.jsonl`; 进度: `_progress.json`。
