# 公开腿演练阶段 C: 合并修复分支 → 打开公开部署开关 → 手动派发一次 kb-sync, 建公开候选 (2026-11-28)

方案 = `p3_public_leg_impl.md` §5「阶段 C」。时间戳是 UTC (虚拟机里的文件时间是 JST = UTC+9, 用到的地方已换算)。先例: `p3_tunnel_leg_merge_deploy.md`、`p3_stageB_network_isolation.md`、`pre_switch_fixes.md`。
**结论: 两段的结果都与预期一致, 没有触发任何停止条件, 没有做回退。** 公开站仍然没有上线: 公开容器从未启动, 公开线上数据没有变, 多出来的只有公开数据根里一份过闸的候选。**现在 `SDTM_RAG_PUBLIC_DEPLOY` 是开的。**

⚠ 变量开着的时候, 头提交不带 `[skip ci]`、又命中部署路径过滤的 main push, 以及手动派发 `sdtm-rag` 工作流时没有取消勾选 `deploy` (它默认是勾选的), 都会在私有部署成功之后带上公开部署 (`deploy_public`), 把这份候选换入公开线上数据。只构建 (取消勾选 `deploy`) 不会。依据是 `sdtm-rag.yml` 里 `deploy_public` 的条件 (`needs: deploy`; main + 变量为 `true` + 不是「手动派发且 `deploy` 为 false」) 和 `p3_public_leg_impl.md` §4.4 的真值表; 这个 job 在真机上还一次都没有运行过。

## 授权
主人 2026-11-28 在协调方的待办项上亲自选定 (**经待办项转达的选择**, 不是在本会话里说的):
- 问题一:「可以把修复分支合并进 rag main 并推送吗（不触发构建和部署）？」→ 主人选「可以」。
- 问题二:「合并成功后，可以打开公开部署开关并手动跑一次 kb-sync 建公开候选吗（公开站仍不启动）？」→ 主人选「可以，合并后接着做」。
- 问题的说明里写明: 公开站自己的 OpenAI key 第一次被真正使用 (embedding 约 0.05 美元); 公开数据根里多出一份候选数据; 公开容器不启动、不对外, 公开站线上数据不变, 私有站不变; key 无效或额度不足表现为明确的失败。
- **只覆盖**: 合并、push、把变量设为开、手动派发**一次** kb-sync (以及这项工作的收尾文档的 push)。**不覆盖**: 公开部署 (`sdtm-rag` 工作流的任何派发)、换入候选、启动公开容器、连接器、隧道。这些都没有做。
- 修复分支里「去掉 kb-sync 定时触发、只留手动派发」是协调方受托代裁; 主人在问题一的说明里看到了并同意合并。

执行中协调方的一项判断 (**协调方的判断, 不是主人裁定**): 推送前检查的两类命中放行 (下文「推送前检查」)。

## 第一段: 合并 + push
### 核对与合并
| 项 | 结果 |
|---|---|
| 起点 | 本地 main = `560213e` (比 origin/main `5e640a1` 多 2 个文档提交), 工作区干净 |
| 分支 | `hakupao/pre-switch-fixes` 尖端 `4c0164d`; `git merge-base` = `560213e` (可以快进); 7 个提交的标题都带 `[skip ci]` (连同那 2 个文档提交, 待推送的 9 个都带) |
| 远端 (push 之前) | Gitea 与 GitHub 的 main 都是 `5e640a1` (GitHub 是对它的 URL 单独 `ls-remote` 的) |
| 合并 | `git merge --ff-only hakupao/pre-switch-fixes` → main = `4c0164dc609f144efbfe477746ac4d49ad1dafe6`, 没有合并提交 |

### 主仓全量测试 (这条分支第一次带本机数据跑)
- `pytest -m "not slow"` 在 `4c0164d` 上: **3625 passed / 0 failed / 2 skipped** (99.66 秒; 两个 skip 都是要 playwright 的真浏览器闸)。与浅克隆的 3566 / 0 / 61 相比多 59 条通过、少 59 条 skip, 与上一次 (3542 对 3483) 同一个差值, 就是那批 `local_data` 测试。
- `data/` 运行前后: 2090 个文件的大小与修改时间, 以及备份目录之外 1725 个文件的 sha256。**只有 `data/chroma` 下 9 个文件的修改时间变了**, 0 个大小变化, 内容有变的是 `chroma.sqlite3` 和 2 个 `data_level0.bin` (chromadb 打开索引时自己改写; 与前两次记录的现象相同, 连文件都是同一批)。没有新增或消失的文件; `data/study`、`data/meta` 0 变化。
- 运行后只读核对: 三个集合 4333 / 959 / 125 条 (sqlite 只读 immutable), stamp `477bac3ce565…` / 4333, `check_index_freshness` OK。
- 全仓红线扫描 (`scripts/oidscan_evidence.py` 不带参数): `CLEAN: 0 处未在 allowlist 的 OID/label 命中 (1331 个文件)`。

### 推送前检查 (范围 = `origin/main..4c0164d`, 9 个提交)
逐提交扫 `git log -p` 的新增行 (1841 行) 和 9 条提交信息 (不只扫净 diff)。

| 口径 | 新增行 | 提交信息 |
|---|---|---|
| home 路径 (`/Users/<名>`、`/home/<名>`) | 0 | 0 |
| 本机账号名、真名形状、提交者邮箱原值 | 0 | 0 |
| 邮箱 (`noreply@anthropic.com` 与示例域除外) | 0 (正则命中的 6 行都是 `@pytest.mark.parametrize(…` 被误认成邮箱) | 0 |
| 密钥形状 (各家 API key 与访问令牌的前缀、私钥文件头、Bearer 头; 口径与 `p3_tunnel_leg_merge_deploy.md`「推送前检查」的同名一行相同, 这里不重抄, 免得这一行自己被扫中) | **4 行** | 0 |
| JWT 形状 (隧道 token 的外形) | 0 | 0 |
| 口令赋值形状、`curl -u 名:字面量` | 0 | 0 |
| 40 字符以上的连续串 (40 / 64 位 sha 除外) | 36 行, 逐行看过都是仓库内的长路径 | 2 行, 同上 |
| 本机 `.env` 的 8 个密钥类取值: 整值 / 任意 12 字片段 | 0 / 0 | 0 / 0 |
| Gitea 口令的整值 | **1 行 2 处** | 0 |

- 密钥形状的 4 行: `pre_switch_fixes.md` 里 2 行 (审查意见表、「清单之外的发现」第 5 条), `tests/test_kbsync_deploy_public.py` 里 2 行。都是隐名回归测试和审查记录里编出来的假集合名 (名字中间恰好有一段长得像 key 的开头), 不是 key; 里面像研究名的片段也是虚构的, 红线扫描对它们 CLEAN。
- 与某个本地口令的片段重合: 1 行 2 处, 都是更长标识符的一部分; 同样的串在已公开的 `origin/main` 树里原有 10 处 (7 个文件)。与上一次记录的「偶然重合」同类, 不是这次推送带出去的新信息。
- 以上两类我没有自己放行, 报给协调方; 答复「放行并 push（协调方的判断，照此登记）」, 并说会再提醒主人更换那个容易撞上常见字符串的口令。
- 不拦截、只计数: `bojiang` 12 行, 内网 / 公开网段地址 63 行, 不含用户名的机器路径 8 行。

### push
- `git push origin main` (非强推), 06:40:22Z: Gitea 与 GitHub 都是 `5e640a1..4c0164d`。被 push 的最新提交带 `[skip ci]`。
- push 之后: 两个远端各自 `ls-remote`, main 都是 `4c0164dc609f144efbfe477746ac4d49ad1dafe6`; `git status -sb` = `## main...origin/main`。
- 推后 30 / 60 / 90 秒 (06:41:05Z / 06:41:35Z / 06:42:05Z) 各看一次运行列表: 总数仍是 23, 最新仍是 id 217 (接口的 `run_number` 23; 这次两个字段是从同一条接口响应里取到的, 所以阶段 B 的 checkpoint 里「`run_number` 23 对应 run 217, 是按时间推的」现在可以确认: 以前各份 checkpoint 写的 run 2xx 就是接口的 `id`。页面上显示哪一个我没有去看)。**没有被这次 push 触发的运行。** 仓库变量仍是 `[]`。

## 第二段: 开变量之前的只读核对 (06:42:41Z–06:43Z) —— 每一条都满足
| 项 | 结果 |
|---|---|
| 公开容器 | `status=created running=false started=0001-01-01T00:00:00Z restarts=0`, 镜像 `…:099c2c9…` (镜像 ID `sha256:3886799a…`), 容器 Id `2a33f280…` (阶段 B 建的那个) |
| 公开 stamp | `kb_fingerprint=f863e45445a6…`, `total_chunks=4329` |
| 公开数据根 | 上一级只有 `data`; `data` 下只有 `chroma` `meta` `quota.sqlite`; journal / guard / cand / failed / prev 都是 0; 没有 `kbsync_accept_*` |
| 公开网络与隔离 | 子网 `10.201.8.0/24`, 0 个容器; 隔离表 1 张、5 条 `drop`; 巡检定时器 `active` / `enabled`, 隔离单元 `active` / `enabled`; `nftables.service` `disabled` |
| 内存与磁盘 | 可用 5232 MB (总 7913 MB)。参照: 候选阶段的一次性容器上限是 `--memory 1536m` (`kbsync.py candidate` 的默认值), 一次只跑一个; 私有腿上一次真实建候选 (run 210, `kb_update_2026.11.28.md` 第 1 步) 走的是同一段代码、同一个默认上限, 当时私有 api + ui 同样在跑; 那次没有记内存占用, 所以这里没有实测的占用数可比, 只有这个上限。数据盘余量 842G |
| Actions | 运行列表最新 id 217, 最近 3 次都是 `completed`; 虚拟机里 23 个容器都是常驻服务 (含 `act_runner` 本身), 没有 job 容器 |
| 私有站基线 | health `healthy`, `/api/health` 200; `sdtm-rag-api` 启动于 `2026-11-28T03:23:47.097798686Z`、`sdtm-rag-ui` `03:23:57.678917638Z`, 重启 0 次, 镜像 `613f048…`; 私有 stamp `477bac3ce565…` / 4333; `meta.yaml` sha256 `b484d49ef76cc8d5246f68ff2761c49ba70976ca8071fcce78ab922c3078f5c5` |
| 主仓与 Gitea | main = origin/main = `4c0164d`; Gitea 接口取 main 上的 `.gitea/workflows/kb-sync.yml`: blob `555cd140…` 与本地相同, 内容逐字节相同; 解析后 `on` 只有 `workflow_dispatch`, 没有 `schedule`; `public` job 的条件是 `always() && gitea.ref == 'refs/heads/main' && vars.SDTM_RAG_PUBLIC_DEPLOY == 'true'` |

任务清单之外加看的 (都满足): pedia 最新的 `kb-*` tag 仍是 `kb-2026.11.28` (有更新的 tag 的话私有腿会判 `changed`、真的建候选, 超出同意范围; 派发前又看了一次); 没有 `sdtm-rag-kbcand` 镜像残留; 镜像总数 36; 公开线上 `chroma` / `meta` 的逐文件清单 (名字 / inode / 大小 / mtime) 与内容摘要存了一份, 供事后比对。

## 开变量
- 接口的写法先查了这台 Gitea 的 swagger: 变量不存在时用 `POST …/actions/variables/{名字}`, 正文 `{"value": "…"}` (已存在时是 `PUT`)。
- **06:43:30Z** `POST …/actions/variables/SDTM_RAG_PUBLIC_DEPLOY`, 正文 `{"value":"true"}` → HTTP 201。
- 读回 (`GET` 单个变量和变量列表各一次): `{"owner_id":0,"repo_id":26,"name":"SDTM_RAG_PUBLIC_DEPLOY","data":"true","description":""}`。
- 设完运行列表没有变化 (设变量本身不触发任何运行)。

## 手动派发一次 kb-sync —— run 218, 两个 job 都 success
- **06:44:08Z** `POST …/actions/workflows/kb-sync.yml/dispatches`, 正文 `{"ref":"main","inputs":{"ref":"","public_baseline_image":""}}` → HTTP 204。只派发了这一次。
- 运行: id **218** (`run_number` 24), 头提交 `4c0164d`, 06:44:09Z → 06:50:49Z (6 分 40 秒), `completed` / `success`。
- 运行期间约每 20 秒只读轮询一次公开容器和私有 api, 没有报出异常; 记到的虚拟机可用内存最低 4473 MB。这只是辅助 (轮询脚本只在读到异常状态时才打印, 某一次没连上虚拟机的话它不会报): 「公开容器从未启动、私有站没有被重启」的依据是运行之后的快照 (下文), 那里公开容器是 `started=0001-01-01T00:00:00Z`、重启 0 次, 私有 api / ui 的启动时间与重启次数不变。

### `private` (job 463, 06:44:09Z → 06:44:28Z, 19 秒) —— `same`, 空跑
| 步骤 | 结论 | 关键日志行 |
|---|---|---|
| checkout | success | |
| 确定 KB ref | success | `KB ref：kb-2026.11.28` |
| 拉取 KB 并计算指纹 | success | `A 仓 commit：b2bd8376e51e4d9e751fc49834a87a103a722b2e；KB 指纹：477bac3ce565；线上镜像：192.168.100.58/bojiang/sdtm-rag:613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7` |
| 检测 | success | `{"result": "same"}` →「no-op：生产 chroma 已是该 KB 指纹」 |
| 构建候选镜像 / 候选入库并运行 CDISC 闸 / 删除候选镜像 | 三步都 **skipped** | |

### `public` (job 464, 06:44:31Z → 06:50:49Z, 6 分 18 秒) —— 不是 skipped, 10 步都 success
| # | 步骤 | 用时 | 关键日志行 |
|---|---|---|---|
| 0 | checkout | 11 秒 | 头提交 `4c0164dc…` |
| 1 | 确定 KB ref | 1 秒 | `KB ref：kb-2026.11.28` |
| 2 | 拉取 KB 并计算指纹 | 1 秒 | 与私有腿同一行 (同一个 A 仓提交、同一个指纹 `477bac3ce565`) |
| 3 | 路径一致性断言 | <1 秒 | `[kbsync] 路径一致：数据根 /Volumes/DevSSD/deploy-data/sdtm-rag-public/data，env 文件 /opt/sdtm-rag-public/.env，与私有挂载源不重叠` |
| 4 | 检测 | 1 秒 | `{"result": "changed", "prod_fp12": "f863e45445a6"}` →「KB 指纹与公开 chroma 不同，开始构建公开候选并运行闸」 |
| 5 | 构建候选镜像 | 1 秒 | 日志里 10 行 `CACHED`, 没有一层重新构建; `naming to docker.io/library/sdtm-rag-kbcand:477bac3ce565` |
| 6 | 检查公开站的 embedding key | 9 秒 | `[kbsync] embedding key 检查通过（text-embedding-3-small，1536 维）` (06:44:55Z; **公开站 OpenAI key 第一次被真正使用**) |
| 7 | 选基线镜像 | <1 秒 | `公开容器镜像：…/sdtm-rag:099c2c930ec869e254b2e9052c3d4a6a85d6d539；私有线上镜像：…/sdtm-rag:613f048a…` → `[kbsync] 基线候选 …/sdtm-rag:099c2c93…：镜像内 KB 指纹 f863e45445a6` → `基线镜像：…/sdtm-rag:099c2c930ec869e254b2e9052c3d4a6a85d6d539（sha256:3886799a29ed0426d17356c3d830dc511e530199d6162b4d6968008968b10f33）` |
| 8 | 公开候选入库并运行 CDISC 闸 | 5 分 53 秒 | 见下 |
| 9 | 删除候选镜像 | <1 秒 | `Untagged: sdtm-rag-kbcand:477bac3ce565` / `Deleted: sha256:1d1edc67…` |

第 8 步的输出 (原样; 这一步的输出是结束时一次性刷出来的, 日志时间戳都是 06:50:49Z, 所以各小步的用时取自候选目录里文件的写入时间):
```
[kbsync] prepare chroma_cand_477bac3ce565
{"candidate": "chroma_cand_477bac3ce565", "meta": "meta_cand_477bac3ce565", "archived_stale": []}
[kbsync] baseline_eval (sha256:3886799a29ed0426d17356c3d830dc511e530199d6162b4d6968008968b10f33)
[kbsync] ingest (sdtm-rag-kbcand:477bac3ce565)
[kbsync] build_meta (sdtm-rag-kbcand:477bac3ce565)
[kbsync] candidate_eval (sdtm-rag-kbcand:477bac3ce565)
[kbsync] kb-only：sdtm_kb_v1 在，非 KB 集合 0 个
[kbsync] gate {"verdict": "PASS", "reason": null, "n_questions": 140, "baseline_full": 138, "candidate_full": 138, "candidate_avg": 0.9917, "regressed_ids": [], "improved_ids": [], "chromadb": "1.5.9", "archived": null}
```
| 小步 | 时刻 (UTC, 按文件写入时间) | 用时 |
|---|---|---|
| 开始 (marker 里的 `timestamp`) | 06:44:56 | |
| 复制线上 chroma / meta + 基线评测 (`kbsync_eval/baseline.json` 写出) | 06:47:54 | 约 178 秒 |
| 入库 (新索引段目录 06:49:53 建出, stamp 的 `ingested_at` = 06:50:01) | 06:50:01 | 不超过 127 秒 (含起容器; 预期约 95 秒) |
| build_meta (`meta.yaml` 写出) | 06:50:02 | 约 1 秒 |
| 候选评测 (`kbsync_eval/candidate.json` 写出) | 06:50:46 | 约 44 秒 |
| 判闸、写 marker | 06:50:49 | 约 3 秒 |

### 与预期逐条对照
| 预期 | 实际 |
|---|---|
| `private`: 检测 `same`, 空跑, 末尾「删除候选镜像」被跳过 | 一致 |
| `public`: 路径一致 → `changed` → 构建 → key 检查通过 → 基线镜像 → 入库 → kb-only → 过闸 | 一致, 10 步都 success |
| 基线镜像: 公开容器的镜像与公开 stamp 配对就用它 | 用的就是它 (`…:099c2c9…`, 镜像内指纹 `f863e45445a6` = 公开 stamp); 没有回落到私有线上镜像 |
| 入库约 95 秒、预期 4333 条 | 不超过 127 秒 (含起容器); stamp `total_chunks=4333`, sqlite 只读核对也是 4333 |
| 「kb-only：sdtm_kb_v1 在，非 KB 集合 0 个」 | 逐字出现 |
| 基线满分 138, 候选满分 138 / avg 0.9917 | 基线 138, 候选 138, avg 0.9917; 回退 0 题, 改善 0 题; `verdict` PASS |
| 公开数据根多出 `chroma_cand_477bac3ce565` / `meta_cand_477bac3ce565` | 一致 (下节) |
| 公开线上 chroma、stamp 不变; 公开容器不变; 私有站不变; 没有候选镜像残留 | 一致 (下节) |

### 第一次真实运行, 记下来的几样
- **job 级 `vars` 门控打开后的表现**: `public` job 在私有腿运行期间是 `requested` (等待), 私有腿结束 3 秒后 (06:44:31Z) 开始运行, 没有被跳过。加上 run 216 / 217 证实过的「变量未开 → 跳过」, 这个门控的两个方向现在都在真机上见过了。
- **`needs: private` 之后公开腿照跑**: 见过的是「私有腿 success → 公开腿运行」。`always()` 要保证的另一半 (私有腿失败后公开腿仍然运行) 这次走不到, 仍未验证。
- **步骤级 `always()`**: 公开腿的「删除候选镜像」(`always() && result == 'changed'`) 执行并删掉了镜像; 私有腿的同一步因为检测是 `same` 而跳过。失败 / 取消之后它是否执行, 这次走不到。
- **基线镜像**: 最后选的是公开容器的镜像 `…:099c2c930ec869e254b2e9052c3d4a6a85d6d539`, 理由行是 `镜像内 KB 指纹 f863e45445a6` (= 公开 chroma 的 stamp)。阶段 B 重建网络时用同一个旧镜像重新创建了容器, 所以这里读到的仍是它。之后按镜像 ID 使用 (marker 里 `prod_image` 是 `sha256:3886799a…`, `prod_image_ref` 是带标签的引用)。
- **embedding 实际用量**: 日志里没有 (key 检查只打印模型和维度; 入库和评测的输出不进 job 日志)。这次运行实际调用了公开站的 key: key 检查 1 次, 4333 条入库, 两趟 140 题的查询向量。实际金额要在 OpenAI 后台看。
- **docker 层缓存**: 候选镜像的 10 层全部命中缓存 (约 1 秒)。原因是我推的, 没有核实: 进镜像的那部分仓库内容和 KB 与线上镜像 `613f048` 构建时相同 (其后的提交都没有动镜像里的东西)。这不是「两条腿都 `changed` 时第二次构建命中缓存」那种情形 (这次私有腿没有构建), 那一条仍未验证。
- **内存**: 运行期间可用内存最低 4473 MB (起点 5232 MB), 余量充足。

## 运行之后: 公开 / 私有两侧前后对比
同一个快照脚本 (`p3_stageC_snapshot.sh`) 在开变量之前 (06:42:41Z) 和运行结束之后 (06:51:28Z、06:53:56Z 各一次, 后两次相同) 的输出做机械 diff, 去掉带时间和余量的一行之后**只差两处, 都是多出候选**:
```
< top: data  | data: chroma meta quota.sqlite
< 残留: journal=0 guard=0 cand=0 failed=0 prev=0 accept=0
> top: data  | data: chroma chroma_cand_477bac3ce565 meta meta_cand_477bac3ce565 quota.sqlite
> 残留: journal=0 guard=0 cand=2 failed=0 prev=0 accept=0
> PUBEXTRA chroma_cand_477bac3ce565: files=15 stamp=kb_fingerprint=477bac3ce565aa810c38aeb14a35bf22f2c760c13a7e0b5f7d3bcf6ee24e3236 total_chunks=4333  size_kb=115880
> PUBEXTRA meta_cand_477bac3ce565: files=1 stamp= size_kb=488
```
没有出现在 diff 里、也就是前后相同的:

| 侧 | 项 | 值 (前 = 后) |
|---|---|---|
| 公开 | 容器 | Id `2a33f280…`, `created` / `running=false` / `started=0001-01-01T00:00:00Z` / 重启 0 次, 镜像 `…:099c2c9…` (`sha256:3886799a…`) —— **仍然从未启动** |
| 公开 | 线上 `chroma` | stamp `f863e45445a6…` / 4329; 目录 inode、7 个文件的名字 / inode / 大小 / mtime 清单指纹 `7a91a1360dcc6cf9`、全部文件内容的摘要 `dabd65645e3d3d9a` |
| 公开 | 线上 `meta`、`quota.sqlite` | `meta` 清单指纹 `c9a94e8bd019b981`、内容摘要 `5db4931da6ddf8c0`; `quota.sqlite` 的 inode / 大小 / mtime |
| 公开 | 网络与隔离 | 网络 Id `eff48d9c…`, `10.201.8.0/24`, 0 个容器; 隔离表 1 张 5 条 `drop`; 定时器与单元 `active` / `enabled` |
| 公开 | 其他 | 没有连接器、没有验收容器; 数据根上一级只有 `data`; journal / guard / failed / prev 都是 0 |
| 私有 | 容器 | api / ui 的 Id、启动时间 (`03:23:47…` / `03:23:57…`)、重启 0 次、镜像 `613f048…`; health `healthy`, 200 |
| 私有 | 数据 | stamp `477bac3ce565…` / 4333; `chroma` / `meta` 目录 inode 与文件名清单指纹; `meta.yaml` sha256 `b484d49e…`; `*_prev_*`、`*_failed_*` 原样; `study` 1557 个文件; 没有 cand / journal |
| 机器 | 容器与镜像 | 容器总数 23, 运行中 22, 非运行的只有 `sdtm-rag-public-api`; 镜像总数 36; 没有 `sdtm-rag-kbcand` 镜像; 没有 job 容器、没有 job 网络残留 |

### 候选本身 (`p3_stageC_candidate_check.sh`, 只读; 不经 chromadb 打开索引)
- `chroma_cand_477bac3ce565`: stamp `kb_fingerprint=477bac3ce565aa810c38aeb14a35bf22f2c760c13a7e0b5f7d3bcf6ee24e3236`、`total_chunks=4333`、`embedding_model=text-embedding-3-small`、`embedding_dim=1536`; sqlite 只读: 集合恰为 `sdtm_kb_v1`, 4333 条 (公开线上那一份是 `sdtm_kb_v1` 4329 条)。约 113 MB, 属主 `root:root`。
- marker `kbsync_gate.json`: `verdict` PASS, `ref` `kb-2026.11.28`, `a_commit` `b2bd8376…`, `image` `sdtm-rag-kbcand:477bac3ce565`, `prod_image` `sha256:3886799a…`, `prod_image_ref` `…:099c2c9…`, `chromadb` `1.5.9`, `n_questions` 140, `baseline_full` 138, `candidate_full` 138, `candidate_avg` 0.9917, `regressed_ids` `[]`, `max_regressions` 1, `min_avg` 0.95。
- `meta_cand_477bac3ce565/meta.yaml` 的 sha256 = `b484d49ef76c…`, **与私有线上的 `meta.yaml` 相同** (同一个 KB、各自独立 build_meta 出来的); 公开线上的是旧 KB 的 `abfa9815…`。
- 两份评测结果留在候选目录的 `kbsync_eval/` 里 (`baseline.json`、`candidate.json`; CDISC 题集, 不含研究数据)。

### 日志的敏感内容扫描 (先只计数, 再看具体行)
两个 job 的日志 (224 行、377 行) 存到本机临时目录后扫: 密钥形状 0, JWT 形状 0, 带取值的 key / token 赋值 0, `study` 开头的词 0, home 路径 0。另外拿开发机 `.env` 里的 8 个密钥类取值 (私有站 / 开发用的 key, **不是公开站的**) 比了整值与 12 字片段, 0 命中 —— 公开站自己的 key 我没有读过, 所以对它只有上面的形状扫描这一道。出现的掩码只有 runner 自己打的 `***` (checkout 的 `AUTHORIZATION: basic ***`), 各 4 行。没有读 `/opt/sdtm-rag-public/.env`; 日志里出现的只是它的路径。

## 发现 (只汇报, 没有改)
1. **候选目录里带着一个孤儿索引段目录**: `chroma_cand_477bac3ce565/8894229e-…/` (5 个文件, 约 25 MB) 是从线上副本带过来的旧向量段; 入库重建集合后 sqlite 里登记的向量段是新的 `f192749a-…`, 旧的不再被引用, chromadb 没有删它。内容是旧版公开 KB 的向量, 没有研究数据。换入之后它会跟着进线上目录, 每次 KB 更新多攒一份。私有数据根大概也有同样的情况 (线上 `chroma` 130 个文件, 换下去的那份 122 个), 没有去核实。
2. **基线评测比候选评测慢得多** (约 178 秒对 44 秒; 前者含复制线上数据, 用的是旧镜像 `099c2c9`)。没有查原因; 总时长 6 分 40 秒, 远在 90 分钟的超时之内。
3. **候选步骤的输出是结束时一次性刷出来的**: 跑的那 6 分钟里 job 日志没有新行, 看上去像卡住。只影响观感。
4. **接口里一次运行有两个编号**: 这次是 `id` 218 / `run_number` 24。以前各份 checkpoint 里写的 run 211–217 对应的都是 `id` (页面上显示哪一个没有去看)。
5. **现在已经过时、这次没有改的文档** (不在点名要改的范围里, 留给协调方):
   - `deploy/README.md`「公开实例与隧道」开头的状态说明里「公开部署开关 `SDTM_RAG_PUBLIC_DEPLOY` 仍是关的」这一句: 开关现在是开的, 公开数据根里有一份过闸候选 (同一段里其余的话仍然成立)。
   - `docs/plans/P3_4_tunnel_drill.md` 开头的执行状态 (第 1–4 步之后的进展)。
   - `CLAUDE.md` 路由词里「公开站 (变量 `SDTM_RAG_PUBLIC_DEPLOY`, 默认关)」写的是默认值, 没有错, 但现在实际是开的; 「⚠ 自动部署」那一行没有提变量开着时公开部署会跟在私有部署后面一起跑。

## 回退办法 (这次没有用到)
- **停用公开腿和公开部署**: 把变量关掉。
  `DELETE …/actions/variables/SDTM_RAG_PUBLIC_DEPLOY` (或 `PUT` 同一地址, 正文 `{"value":"false"}`), 再 `GET …/actions/variables` 读回。关掉之后 kb-sync 的 `public` job 和 `sdtm-rag` 的 `deploy_public` job 都会被跳过; 候选留在原地不受影响。
- **不想要这份候选**: 把两个目录改名移走, **不删**。用 kbsync 自己归档失败候选的名字 (这类目录它永不自动处理):
  ```sh
  VM() { ssh <mini 主机> "export PATH=/opt/homebrew/bin:\$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- $*"; }
  PD=/Volumes/DevSSD/deploy-data/sdtm-rag-public/data; TS=$(date -u +%Y%m%dT%H%M%SZ)
  VM "sudo mv $PD/chroma_cand_477bac3ce565 $PD/chroma_failed_477bac3ce565_$TS && sudo mv $PD/meta_cand_477bac3ce565 $PD/meta_failed_477bac3ce565_$TS"
  ```
  移走之后公开部署会走「公开 chroma 落后而没有过闸候选 → 只告警并跳过」; 下一次 kb-sync (变量开着的话) 会重新建一份 (再花一次 embedding 费用)。
- **本仓回退**: 这次合进来的 7 个提交只动了 `deploy/kbsync`、`kb-sync.yml`、测试和文档, 要退就 `git revert` (带 `[skip ci]`); kb-sync 从 main 的 checkout 运行, 下一次运行即生效。
- 回不到的: 公开站的 OpenAI key 已经被用过一次 (费用已发生)。

## 仍未验证的事项
1. **候选还没有被换入**: `deploy_public` 的全部步骤 (红线检查、镜像下限、网络与隔离预检、没有网络的临时容器验收、答题 key 探测、换入、`up --no-start`、失败后停机、中断兜底) 仍然一次都没有真实运行过。部署时会重新核对这份候选 (marker、chromadb 版本须与目标镜像相同、换入前在副本上核对集合), 这次没有替它验。
2. **公开站的 embedding 实际花了多少**: 日志里没有, 要在 OpenAI 后台看。key 的额度 / 月上限是否够后续使用, 这次只证明了「够跑完这一次」。
3. **act_runner / Gitea**: `always()` 的另一半 (私有腿失败后公开腿照跑); 失败 / 取消之后「删除候选镜像」是否执行; `concurrency` 是否真的让 kb-sync 与部署排队 (这次没有并发的运行); 两条腿都 `changed` 时第二次构建是否命中缓存; 公开腿任何一条失败路径 (key 无效、基线不配对、kb-only 不过、闸不过) 在真机上的表现 —— 都只有单测。
4. **公开线上 chroma 在公开容器运行时被复制是否总能打开**: 这次公开容器是停着的, 复制的是静止的文件。
5. **Gitea 上有没有已登记的定时任务**: 没有接口可查; 依据仍是源码 (带跳过标记的 push 不登记) 加「历次 push 的头提交都带标记」。这次 push 也带标记。
6. 合进 main 的这 7 个提交仍然没有经过 Gitea 的 CI (不在路径过滤里; kb-sync 工作流不跑测试)。依据是浅克隆、runner 镜像 (到 `e4b33d3`) 和这次主仓的全量。`kbsync.py` 的这个版本在真机上走过的只有这次的两条路径 (私有 `same`、公开 `changed` → PASS)。
7. **没有独立审查**: 派单要求不起子代理, 这份记录是执行者自己写的 (规则 D 的缺口; 需要的话由协调方另派)。可以机械复核的东西 (快照 diff、marker、日志) 都留了命令。
8. 阶段 B 留下的两条依赖重启的事项照旧挂着 (规则先于容器装入; 从未启动的容器在 `unless-stopped` 下重启后是否仍不启动)。
9. 阶段 D 及之后的全部内容。

## 小结 (规则 C)
- **保留下来的做法**: 推送前检查提到合并和测试之前做 (这次只能快进, 历史里有拦截项就没有补救余地); 命中项不自己放行, 报给协调方; 开变量之前把任务清单之外、但会让结果超出同意范围的条件也查了 (pedia 有没有更新的 tag); 「线上那一份没动」单独取逐文件清单和内容摘要, 不拿整个数据根的指纹当证据; 派发只有一次机会, 派发后先看运行列表而不是看返回码; 运行期间只读轮询公开容器; 日志先落文件、只计数扫描, 再看具体行; 集合条数用 sqlite 只读方式看, 不让 chromadb 打开索引。
- **必须补上的缺口**: (1) 候选步骤的各小步用时只能从文件时间反推, 日志里没有 —— 编排的输出没有逐行刷出; embedding 用量也不进日志, 「约 $0.05」这个数这次没有被实测证实。(2) 我的核对脚本第一版把虚拟机本地时间标成了 `Z`, 写记录时才发现差 9 小时, 已改成明写 JST; 时间类输出要写明时区来源。(3) 公开腿的失败路径在真机上一条都没有走过, 这次只证明了成功路径。
- **关键决策复盘**: (1) 密钥形状和口令片段重合两类命中明显是假阳性, 仍然停下来问了一次 —— 代价是几分钟, 换来放行是协调方的判断而不是执行者自己说了算。(2) 发现的孤儿段目录、过时文档都只汇报不动: 这次的同意只覆盖建候选, 动候选目录或部署文档都会让「候选 = kb-sync 原样产出」「改动面 = 点名的文件」这两条不再成立。

## 结束状态
- 变量 `SDTM_RAG_PUBLIC_DEPLOY` = `true` (**开着**; 下一步的公开部署需要它)。
- main = origin/main (Gitea 与 GitHub 相同); 收尾的文档提交带 `[skip ci]`, 其提交号见向协调方的最终汇报。私有站线上镜像仍是 `613f048…`。
- 公开站: 容器已创建、从未启动 (镜像 `099c2c9`); 线上数据是旧 KB (`f863e454…` / 4329); 数据根里有一份过闸候选 (`477bac3ce565` / 4333), 等第一次公开部署换入。没有连接器, 没有隧道。
- 分支 `hakupao/pre-switch-fixes` 和它的子工作区没有动, 留给协调方处理。

## 复跑命令
```sh
R=<本仓根>; cd $R; PY=.venv/bin/python; OUT=<本机临时目录>
VMS() { ssh <mini 主机> 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- bash -s'; }
# 第一段: 核对、合并
git rev-parse hakupao/pre-switch-fixes; git merge-base main hakupao/pre-switch-fixes; git log --format='%h %s' 560213e..hakupao/pre-switch-fixes
git ls-remote https://git.bojiang.org/bojiang/sdtm-rag.git refs/heads/main; git ls-remote https://github.com/hakupao/sdtm-rag.git refs/heads/main
git merge --ff-only hakupao/pre-switch-fixes
# 本机全量 (前后各记一次 data/ 的状态, 再比)
find data -type f -print0 | sort -z | xargs -0 stat -f '%N|%z|%m' > $OUT/data_before.txt
find data -type f -not -path 'data/chroma_backup*' -print0 | sort -z | xargs -0 shasum -a 256 > $OUT/data_sha_before.txt
$PY -m pytest -m "not slow" -q -o addopts="" -rs
sqlite3 -readonly "file:data/chroma/chroma.sqlite3?mode=ro&immutable=1" "select c.name, count(e.id) from collections c join segments s on s.collection=c.id join embeddings e on e.segment_id=s.id group by c.name;"
$PY -m scripts.check_index_freshness; $PY scripts/oidscan_evidence.py
# 推送前检查的输入 (口径见上表; 逐提交的新增行 + 提交信息)
git log -p --no-color --format='COMMIT %H' origin/main..HEAD | grep -E '^\+' | grep -vE '^\+\+\+ ' > $OUT/added.txt; git log --format='%H%n%B' origin/main..HEAD > $OUT/msgs.txt
git push origin main
# Gitea API (账号与口令取自 git credential, 经标准输入交给 curl, 不进命令行、不写进任何文件; 下面用占位符)
API=https://git.bojiang.org/api/v1/repos/bojiang/sdtm-rag
curl -s -u <账号>:$P "$API/actions/runs?limit=3"                                   # id / run_number / status / head_sha
curl -s -u <账号>:$P "$API/contents/.gitea/workflows/kb-sync.yml?ref=main"          # sha 与 git rev-parse HEAD:.gitea/workflows/kb-sync.yml 比
curl -s https://git.bojiang.org/swagger.v1.json                                     # 变量与派发接口的写法
git ls-remote --tags --refs https://github.com/hakupao/sdtm-pedia 'kb-*' | sed 's#.*refs/tags/##' | sort -V | tail -1   # kb-2026.11.28
# 快照 (只读; 开变量之前、运行之后各一次, 去掉 [T] 行再 diff)
VMS < .work/10_split_and_public/evidence/checkpoints/p3_stageC_snapshot.sh > $OUT/snap_pre.txt
# —— 以下三条会改状态 / 花钱, 需要主人同意 ——
curl -s -u <账号>:$P -H 'Content-Type: application/json' -X POST "$API/actions/variables/SDTM_RAG_PUBLIC_DEPLOY" -d '{"value":"true"}'   # 201
curl -s -u <账号>:$P "$API/actions/variables/SDTM_RAG_PUBLIC_DEPLOY"                                                                    # data = true
curl -s -u <账号>:$P -H 'Content-Type: application/json' -X POST "$API/actions/workflows/kb-sync.yml/dispatches" -d '{"ref":"main","inputs":{"ref":"","public_baseline_image":""}}'   # 204
# 运行结果与日志 (run 218; job 463 = private, 464 = public)
curl -s -u <账号>:$P "$API/actions/runs/218"; curl -s -u <账号>:$P "$API/actions/runs/218/jobs"
curl -s -u <账号>:$P "$API/actions/jobs/463/logs" > $OUT/job_463.log; curl -s -u <账号>:$P "$API/actions/jobs/464/logs" > $OUT/job_464.log
grep -nE 'KB ref：|A 仓 commit|"result"|no-op|\[kbsync\]|公开容器镜像|基线镜像|Untagged|Job succeeded' $OUT/job_463.log $OUT/job_464.log
grep -cE 'sk-[A-Za-z0-9_-]{6,}|eyJ[A-Za-z0-9_-]{8,}\.|study[_-]' $OUT/job_463.log $OUT/job_464.log        # 0 / 0
# 运行之后
VMS < .work/10_split_and_public/evidence/checkpoints/p3_stageC_snapshot.sh > $OUT/snap_post.txt
diff <(grep -v '^\[T\]' $OUT/snap_pre.txt) <(grep -v '^\[T\]' $OUT/snap_post.txt)        # 只差候选的两处
VMS < .work/10_split_and_public/evidence/checkpoints/p3_stageC_candidate_check.sh
curl -s -u <账号>:$P "$API/actions/variables"                                              # 现在的变量状态
```
