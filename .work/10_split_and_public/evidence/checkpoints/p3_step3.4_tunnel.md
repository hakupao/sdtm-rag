# P3.4 / 3.4b 隧道配置与网络隔离 (2026-11-28, 分支 hakupao/public-tunnel)

只写了配置和代码。**没有**接隧道、没有动虚拟机、没有 push、没有改 workflow 和 Gitea 变量。
主人的同意: 2026-11-28 在协调方的待办项上选「开始，先做 rag 的三项代码工作」(分支上做, 不合并不部署)。
提交 (按先后): `9b7e0aa` 初版 → `5021cc3` 第一轮审查的修正 → `dbf5e6b` 收尾核对的补正 → `4821c6d` 增量审查的修正 → `a0fd595` 第三轮复核的收尾 → `b546a01` 镜像下限标记 → `1cf2448` 补审的修正 → `18a3b93` 预检标记 → `ade6a59` 落实主人的三项裁定 → `ff663ea` 第七轮审查的修正 (中间的 `5b969a7`、`9d9f811`、`0ff8b1a`、`17936a7` 是本文件的早期版本)。下文的测量数字都取自 `ff663ea`。
**本分支须以 squash 方式合并** (协调方 2026-11-28 裁定), 见「集成备注」第 11 条。

## 主人的裁定 (2026-11-28)

三项都是主人在协调方的待办项上亲自选的, 经协调方转达到本会话 (不是协调方代裁):

| 问题 | 主人的选择 | 落在哪里 |
|---|---|---|
| 首次上线时, 要不要先加访问限制只放行你本人, 验完再对所有人开放? | **要** | 操作说明第 6 步 (必做, 先于加路由)、第 9 步放开是最后一步; 演练第 7–9 步 |
| 公开站要不要再加一层限流? (提问接口已有每访客、每 IP 的限额) | **两层都加** (应用里打开全局限流, 再建一条 Cloudflare 限速规则) | `compose.public.yml` 的三个 `SDTM_RAG_RATE_LIMIT_*` 键; 操作说明第 5 步 (必做); 演练 5a、第 8 步 |
| 公开站配置文件里那行已经不生效的旧「可信代理」设置, 演练时顺手删掉吗? | **删** | 演练第 5 步的 5b (动虚拟机, 未执行) |

此前协调方的两项裁定: 临时验收容器用 `--network none`; 本分支须以 squash 方式合并 (集成备注第 3、11 条)。

## 做了什么

| 项 | 落点 |
|---|---|
| 公开网络固定子网 `10.201.8.0/24`, 网桥名固定 `br-sdtmpub`, 动态地址只从 `.128/25` 取, 不启用 IPv6 | `deploy/container/compose.public.yml` |
| 可信代理写死为连接器的静态地址 `10.201.8.2` (写在 `environment`, 压过 `.env` 同名键) | 同上 |
| 连接器: 独立 compose 项目, 镜像钉版本 + 摘要, 静态地址, token 只经只读文件, 不发布端口, 去掉全部 capability | `deploy/container/compose.tunnel.yml` (新) |
| 公开档可信代理必须是单主机 (原为 ≥ /24) | `server/auth.py` `_check_public_trusted` |
| 公开档 cookie 强制 `Secure` (显式关 → 拒启动); 登录门 session cookie 的 `Secure` 跟随档位 | `server/auth.py` `_install_quota` / `install_security` |
| 公开档响应加 `Strict-Transport-Security: max-age=31536000` (不带 includeSubDomains / preload) | `server/auth.py` `SecurityHeadersMiddleware(hsts=)` |
| 可信对端送来的 `CF-Connecting-IP` 不是恰好一条时不采信 (审查后加) | `server/auth.py` `_resolve_ip` |
| 公开实例 `FORWARDED_ALLOW_IPS` 置空: uvicorn 不再采信回环来的 `X-Forwarded-For` (审查后加) | `deploy/container/compose.public.yml` |
| 网络隔离规则 (独立 nft 表) + 开机装入的 systemd 单元 + 带对照的探测脚本 | `deploy/public-net/` (新) |
| 公开实例打开全局限流: 每访客 IP 每分钟 60、突发 20 (主人裁定后加) | `deploy/container/compose.public.yml` |
| 公开档启动时拒绝取值不同的大小写变体环境变量 (主人裁定后加; 为了让上一行不依赖虚拟机上的 env 文件) | `server/auth.py` `_check_public_env_case_variants` |
| 镜像下限: 常量 `server.auth.PUBLIC_EDGE_LEVEL = 1` + 预检脚本 (协调方收尾时要求明确标记) | `server/auth.py`、`deploy/public-net/image_floor_check.py` (新) |
| 巡检: 每分钟把规则文件整份重装一遍, 连续两次装不上就停连接器 (审查后加) | `deploy/public-net/sdtm-rag-public-isolation-watch.{service,timer}` (新) |
| 测试 | `tests/test_p3_4_public_https.py`、`tests/test_deploy_public_tunnel.py` (新); `tests/test_p2_9_fixes.py` 一处参数表 |
| 文档 | `deploy/README.md`「公开实例与隧道」; `docs/design/P2_request_context.md` §5; `docs/plans/P3_4_tunnel_owner_steps.md`; `docs/plans/P3_4_tunnel_drill.md` |

没有改: `.gitea/workflows/**`、`deploy/kbsync/**`、`tests/test_deploy_public_compose.py`、私有 `compose.yml`、检索 / 答题逻辑、
`_progress.json` / `docs/PROGRESS.md` / `trace.jsonl` (两条线都可能改, 留给协调方)。
冻结的接缝名字 (容器名、网络名、数据根、`.env` 路径、端口 8000) 一个没动。

## 设计取舍

1. **连接器放独立 compose 文件, 不进 `compose.public.yml`。** 后者只定义 `api`, 临时验收容器可以照着它另起副本;
   连接器的起停 = 对外开关, 不随公开实例的部署变化。连接器以 `external` 方式加入公开网络。
2. **子网选 `10.201.8.0/24`。** 2026-11-28 只读查到的占用 (只列网段):
   - 虚拟机的 docker 网络: `172.17.0.0/16` (默认网桥)、`172.18.0.0/16` (公开网络现在的自动网段)、`172.19`–`172.31` 各 `/16`
     (私有站在 `172.22`, 其余是同机别的 compose 项目)、`192.168.16.0/20` (172 段用完后 docker 转到 192.168 池分的);
   - 虚拟机网卡: `192.168.5.0/24`、`192.168.64.0/24`;
   - mini 侧: `192.168.100.0/24` (局域网)、`192.168.2.0/24`、`192.168.3.0/24`、`192.168.64.0/24`;
   - 虚拟机没有 `/etc/docker/daemon.json`, 所以自动分配只用默认池 (`172.17`–`172.31`、`192.168.0.0/16`)。

   `10/8` 在虚拟机和 mini 两侧都没有路由, 也不在 docker 默认池里, 以后新建的自动网络撞不上它。
   它是私有地址, 不会遮住任何公网目的地 (模型服务商的地址不可能落在里面)。

   ```bash
   ssh bojiang.local 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- sh -c "
     for n in \$(docker network ls --format {{.Name}}); do docker network inspect \$n --format \"{{range .IPAM.Config}}{{.Subnet}}{{end}}\"; done; ip -4 -br addr; ip -4 route; cat /etc/docker/daemon.json"'
   ssh bojiang.local 'netstat -rn -f inet'
   ```
3. **连接器静态地址放在动态段之外。** Docker 文档 (`docker network connect`): 「One way to guarantee that the IP address is available is to
   specify an `--ip-range` when creating the network, and choose the static IP address(es) from outside that range.」
   否则连接器没起时, 公开实例会被分到 `.2`, 连接器之后起不来。
4. **可信代理写进 compose, 不留在 `.env`。** 它和静态地址是同一个事实, 放在同一处由测试对照。
   `.env` 里现有的 `SDTM_RAG_QUOTA_TRUSTED_PROXIES=127.0.0.1` 不再生效 (见下节机制); 主人 2026-11-28 定: 删, 做法在演练第 5 步的 5b (不显示文件内容, 先确认新值生效, 留备份)。
5. **token 走文件。** cloudflared 自 2025.4.0 支持 `TUNNEL_TOKEN_FILE`, 读文件后去首尾空白 (源码 `strings.TrimSpace`)。
   环境变量、命令行参数、`env_file` 三种写法都会让值出现在 `docker inspect` / `compose config` 里, 测试逐条禁掉。
   文件位置 `/opt/sdtm-rag-public/cloudflared/tunnel-token`: 虚拟机本地盘, 和公开站 `.env` 同一个 root 700 目录下,
   属主 `65532:65532` (镜像里进程的用户), 权限 `400`。
6. **HSTS 由应用发。** 不依赖 Cloudflare 的全域开关; 值不带 `includeSubDomains` (那是对本主机名以下整棵子树的承诺) 和 `preload`。
   官方文档: Cloudflare 原样透传源站的响应头, 例外清单里没有 `Strict-Transport-Security`。明文跳转用只匹配本主机名的重定向规则 (操作说明第 4 步)。
7. **没做: 应用侧按 `X-Forwarded-Proto` 把明文请求直接跳转。** 依赖隧道实际送到源站的头, 合并前观察不到, 写错就是首次对外时的重定向死循环。
   演练第 8 步记录源站实际收到的头, 之后再定。
8. **隔离用独立的 nft 表, 不用 `DOCKER-USER`, 不用 ufw。** 虚拟机的 docker 是 iptables-nft 后端 (它的规则就在 `ip filter` / `ip nat` 表里),
   ufw 没启用。独立表与 docker、ufw 互不干扰; Docker 文档对「在 docker 规则之前执行自己的规则」的建议也是自建表、基链优先级取更小的数。
   文件里只有对自己这张表的建 / 删 / 定义, 没有清空规则集的语句 (测试钉死; 那会让全机容器断网)。
   匹配条件两个取或: 进入接口 `br-sdtmpub` (挡得住伪造源地址的包) 和源网段 (网桥名万一没固定住时仍生效)。
9. **DNS 不需要给内网开例外。** 容器的解析器是 docker 内置的 `127.0.0.11`, 由 dockerd 在宿主命名空间转给 systemd-resolved
   (私有站容器的 `resolv.conf` 里写着 `ExtServers: [host(127.0.0.53)]`), 查询不经过转发链。

10. **全局限流的取值: 每访客 IP 每分钟 60 个请求, 突发 20。**
    - **取的是谁的 IP**: 公开档下全局限流和限额用的是同一个函数 (`resolve_client_ip`): 连接对端是可信代理 (连接器) 时取它传来的 `CF-Connecting-IP`,
      IPv6 按 /64 归并。不是连接器自己的地址, 所以不会把所有访客并成一个桶 (这是 P2.9 时就有的接线, 这次由
      `test_public_compose_turns_on_the_global_rate_limit` 用 compose 的取值再钉一遍: 一位访客的桶空了, 另一位照常)。
    - **计哪些请求**: 除 `/`、`/static/*`、`/api/health` 之外的全部。打开一次页面要取的十几个静态文件不计; 容器的健康检查不计。
      前端每次打开页面发 1 个 `/api/info`, 每问一题发 1 个 `/api/ask_stream`, 点反馈发 1 个 `/api/flag`。
    - **和已有限额怎么配合**: 提问接口自己的限额是每访客每分钟 6 题 / 突发 3、每 IP 每分钟 20 题 / 突发 6; 反馈是每 IP 每分钟 5 条 / 突发 3。
      这些拒绝是带说明的 JSON (前端会显示「多久后再试」「剩余额度」); 全局限流的拒绝是一句纯文本 `Too Many Requests`, 前端只会显示「服务错误 429」。
      所以全局这一层必须比它们宽, 让正常用户先碰到的是带说明的那一种: 60 ≥ 2 × (20 + 5), 20 ≥ 2 × (6 + 3)
      (`test_global_rate_limit_sits_above_the_question_limits` 两边各钉字面值)。余量留给页面加载和重试; 公司共用出口 IP 的情形下,
      先起作用的仍是每 IP 的提问限额。全局这一层挡的是对便宜接口 (`/api/info`、乱扫的路径、被拒后继续重发) 的灌水。
    - **为什么写进 compose 而不是 `.env`**: 和可信代理一样, 不依赖虚拟机上那个文件里有没有写、写得对不对。
      这三个键是 `Settings` 字段, pydantic 按不分大小写匹配环境变量名, 后出现的赢 —— `.env` 里一行小写的 `sdtm_rag_rate_limit_enabled=false`
      会压过 compose 的值 (实测, 见下节)。所以公开档启动时发现「同一个键、大小写不同、取值不同」就拒绝启动, 报错只列键名。
    - **共用出口 IP**: 同一个出口后面的人在这一层 (和每 IP 的提问限额、Cloudflare 那一层) 算作一个来源。60/分钟对几个人同时用是够的;
      人多时有人会看到没有说明的「服务错误 429」。操作说明「以后会用到的」里写了。
    - **没有把「全局限流开着」设成公开档的启动必需项**: 现有的公开档测试和验收都不带它, 改成必需要动很多不属于这一步的文件; 由 compose 的测试钉住取值。
    - **Cloudflare 那一层**: 10 秒 50 次。应用这一层对同一 IP 在任意 10 秒内最多放行 30 个 (突发 20 + 这 10 秒补回的 10), 50 > 30, 正常使用碰不到。

## `.env` 同名键与 compose 值的优先级 (真机制)

- `quota.cfg` 读 `os.environ["SDTM_RAG_QUOTA_TRUSTED_PROXIES"]` (大写原名); 这个键不是 `Settings` 字段, 所以没有 pydantic 大小写不敏感匹配的问题
  (3.2 审查 H1 的同类洞不在这里; 测试钉住「它不是 Settings 字段」)。
- `.env` 由 `load_dotenv(路径)` 读入, 默认不覆盖已有环境变量 ⇒ compose 的值赢。`.env` 里的小写变体会进环境, 但没人读它。
- **`Settings` 字段不一样 (全局限流的三个键就是)。** pydantic-settings 把环境变量名全部转小写再匹配, 同一个键有两种大小写时后出现的赢;
  `load_dotenv` 把 `.env` 里的变体加在真实环境变量之后, 所以是 `.env` 的那一份赢。实测:

  ```bash
  SDTM_RAG_RATE_LIMIT_ENABLED=true sdtm_rag_rate_limit_enabled=false .venv/bin/python -c "from server.config import Settings; print(Settings().rate_limit_enabled)"   # False
  sdtm_rag_rate_limit_enabled=false SDTM_RAG_RATE_LIMIT_ENABLED=true .venv/bin/python -c "from server.config import Settings; print(Settings().rate_limit_enabled)"   # True: 谁后出现谁赢
  ```

  同名同大小写的 `.env` 行不受影响 (compose 赢, `test_dotenv_same_name_cannot_turn_the_global_rate_limit_off`)。
  大小写变体由公开档的启动检查拦住 (`test_public_refuses_case_variant_that_would_override_compose`, 它先断言「变体确实压过了 compose」再断言拒启动)。
- 测试 `test_compose_env_wins_over_dotenv_same_key_and_case_variant` 用真的 `load_dotenv` 两个方向各跑一次
  (compose 设了 → 用 compose 的; 没设 → 用 `.env` 的, 证明文件确实被读了);
  `test_config_loads_dotenv_without_override_and_key_is_not_a_settings_field` 钉住 `server/config.py` 那一行没有 `override=True`。

## 验证

```bash
.venv/bin/python -m pytest tests/test_p3_4_public_https.py tests/test_deploy_public_tunnel.py tests/test_deploy_public_compose.py tests/test_p2_9_fixes.py -q -o addopts=""
.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs
.venv/bin/python .work/10_split_and_public/evidence/checkpoints/p3_step3.4_mutations.py
.venv/bin/ruff check server/auth.py tests/test_p3_4_public_https.py tests/test_deploy_public_tunnel.py tests/test_p2_9_fixes.py deploy/public-net/isolation_probe.py
```

- 四个相关文件: `189 passed`。
- 全量 (本机有研究数据): `3127 passed, 2 skipped, 3 deselected` (跳过的 2 条需要 playwright), 在本工作区被忽略的 `data/` 下放了研究数据和索引的副本后跑的。没有索引时有 1 条依赖索引的用例 (`test_validate_study_endpoint.py::test_create_app_boots_through_lifespan`) 报集合不存在, 与本次改动无关。改动前 (9a8ad43) 的同款全量没有在本工作区跑过, 不给对比数。
- 「只在公开档生效」每项两档各一条, 都从 `create_app` (session cookie 那条从 `install_security`) 走到真实响应:

  | 项 | 公开档 | 私有档 |
  |---|---|---|
  | HSTS | `test_public_every_response_carries_hsts` (头值逐字相等; 头名集合 = 私有档集合 + HSTS) | `test_private_responses_unchanged_no_hsts` (头名集合 = 改动前的字面集合) |
  | 访客 cookie `Secure` | `test_public_every_cookie_is_secure` | `test_private_visitor_cookie_not_secure_by_default` |
  | 关掉 `Secure` | `test_public_refuses_insecure_visitor_cookie` (拒启动) | `test_private_accepts_explicit_insecure` |
  | session cookie `Secure` | `test_session_cookie_secure_follows_tier` (同一条里两档) | 同左 |
  | 可信代理单主机 | `test_public_install_refuses_trusted_network_wider_than_one_host` | 同一条的末段; `test_private_trusted_proxies_breadth_unchanged` (原有) |
  | 只信连接器 | `test_connector_address_is_the_only_trusted_peer`、`test_other_peers_cannot_set_the_visitor_ip` (5 个对端)、`test_duplicate_cf_connecting_ip_from_the_connector_is_not_trusted` | `test_private_ignores_cf_connecting_ip_without_trusted_proxies` |

  | 全局限流 | `test_public_compose_turns_on_the_global_rate_limit` (compose 的取值 → 真实中间件: 突发 20 后 429、另一位访客不受牵连、外壳和健康检查不计) | `test_private_has_no_global_rate_limit` (没有这层中间件, 连发 40 个都放行) |
  | 大小写变体冲突 | `test_public_refuses_case_variant_that_would_override_compose` (拒启动, 只报键名) | `test_public_case_variant_check_names_no_values_and_private_is_untouched` 的末段 (同样的冲突照常启动) |

  `FORWARDED_ALLOW_IPS` 不是按档位分支的代码, 是公开 compose 里的一个环境变量 (私有 compose 没有它, 私有站行为不变):
  `test_public_compose_disables_uvicorn_proxy_headers` 拿 compose 的取值喂真的 uvicorn 中间件 (置空 → 不改写对端; 默认值 → 会改写, 证明测试有分辨力)。

- 私有档的字面集合确实是改动前的行为: 初版时把 `server/auth.py` 换回 9a8ad43 的版本, 私有档那 7 条照样通过 (`7 passed, 19 deselected`), 随后按原始字节写回并比对 sha。
  代码审查者独立做了更强的一版: 新旧两版 `auth.py` 在 8 种私有配置下抓 `/`、`/api/info`、流式接口的全部响应头 (名字、取值、顺序、cookie 属性), 逐字节相同。
- compose 用虚拟机里的真 `docker compose` (v5.7.0) 解析, 文件经标准输入传入, 虚拟机上不落文件:

  ```bash
  ssh bojiang.local 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- sh -c "cd /tmp && IMAGE_TAG=abc docker compose -f - config"' < deploy/container/compose.public.yml
  ssh bojiang.local 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- sh -c "cd /tmp && docker compose -f - config"' < deploy/container/compose.tunnel.yml
  ssh bojiang.local 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- sudo -n nft -c -f -' < deploy/public-net/isolation.nft
  ```

  结果: 公开实例只在 `public` 网络上, 没有 `ports`, 环境变量是档位和可信代理两项, 网络段 = `subnet 10.201.8.0/24 / gateway 10.201.8.1 / ip_range 10.201.8.128/25`,
  `enable_ipv6: false`, 网桥名选项在; 不给 `IMAGE_TAG` 时报缺变量。连接器: `ipv4_address: 10.201.8.2`, 网络 `external: true`,
  环境变量只有 `TUNNEL_TOKEN_FILE` (路径) / `TUNNEL_EDGE_IP_VERSION` / `TUNNEL_METRICS`, 解析结果里没有 token。
  审查修正后重跑: 公开实例的环境变量是三项 (多了 `FORWARDED_ALLOW_IPS: ""`, 解析后确实是空串), nft 语法检查仍是 0。
  nft 语法检查 (`-c`, 只检查不应用) 退出码 0, 检查前后 `nft list tables` 都是 docker 的 5 张表。
- 探测脚本的对照侧在虚拟机本机实跑过一次 (只做 TCP 连接): 6 个内网目标 `open`, 还不存在的公开网关 `10.201.8.1:22` 是 `timeout`;
  拿这份对照配一份假想的「全部被挡」隔离侧去判, 结论是 `INCONCLUSIVE` (网关那一条对照也连不上) —— 三态判定按设计工作。

  ```bash
  ssh bojiang.local 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- python3 - probe --lan 10.201.8.1:22 --lan 192.168.5.15:22 --lan 192.168.5.15:8000 --lan 192.168.5.2:22 --lan 192.168.64.1:22 --lan 192.168.100.58:443 --lan 172.22.0.1:22' < deploy/public-net/isolation_probe.py
  ```

## 变异验证 (规则 5)

脚本 `p3_step3.4_mutations.py`: 启动时冻结各文件原始字节和 sha; 每个变异先比对磁盘 sha (不符即拒跑), 精确替换一处 (出现次数必须为 1),
回读必须逐字等于「原文替换后」; 跑完用冻结的字节写回并再比 sha。
判定不只看退出码 (代码审查第 4 条): 每个变异预登记「应该打红的用例」, 只有「有用例失败、没有 error、打红的用例里有预登记的那条」才算 killed;
收集阶段报错或红的是不相干的用例记 INVALID, 和存活一样算没通过。

基线 `189 passed`; 变异 98 个, 没被正确打红的 0 个。初版 46 个 (A01–A12、C01、P01–P06、T01–T10、N01–N10、U01–U02、R01–R05); 其余 52 个是各轮审查和主人裁定之后补的 (审查者做出来存活的变异 + 修正和新要求引入的行为; 其中 G01–G12 对应全局限流和大小写变体检查)。两位审查者各自在副本里复跑过当时的全集 (46 个 / 63 个), 结果一致。
有 12 行的失败信息是空的: 都是带参数的用例, 脚本按用例名去详情里找第一条失败信息时没对上; 判定不受影响 (判定看的是预登记用例是否在失败名单里)。
判 killed 只要求预登记的用例失败, 不检查它失败的原因 —— 原因要看这一列 (代码审查者第二轮指出的局限)。

| # | 变异 | 判定: summary | 预登记并打红的用例 | 它的第一条失败信息 (截断) |
|---|---|---|---|---|
| A01 | HSTS 漏到私有档 | killed: 3 failed, 186 passed | `test_private_responses_unchanged_no_hsts[/]` | `AssertionError: assert 'strict-transport-security' not in Headers({'cache-control': 'no-cache', 'con` |
| A02 | 公开档没有 HSTS | killed: 3 failed, 186 passed | `test_public_every_response_carries_hsts[/]` | `assert None == 'max-age=31536000'` |
| A03 | HSTS 波及子域 | killed: 5 failed, 184 passed | `test_public_every_response_carries_hsts[/]` | `AssertionError: assert 'max-age=3153...udeSubDomains' == 'max-age=31536000'` |
| A04 | 公开档可关 Secure | killed: 3 failed, 186 passed | `test_public_refuses_insecure_visitor_cookie[false]` | `Failed: DID NOT RAISE <class 'RuntimeError'>` |
| A05 | Secure 强制漏到私有档 | killed: 9 failed, 180 passed | `test_private_visitor_cookie_not_secure_by_default` | `RuntimeError: public tier refuses SDTM_RAG_VISITOR_COOKIE_SECURE=false (the public site is HTTPS onl` |
| A06 | 私有档默认带 Secure | killed: 1 failed, 188 passed | `test_private_visitor_cookie_not_secure_by_default` | `AssertionError: ['sdtm_visitor=…; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax; Secure']` |
| A07 | 公开档可信代理放宽回 /24 | killed: 8 failed, 181 passed | `test_public_install_refuses_trusted_network_wider_than_one_host` | `Failed: DID NOT RAISE <class 'RuntimeError'>` |
| A08 | 单主机约束漏到私有档 | killed: 2 failed, 187 passed | `test_private_trusted_proxies_breadth_unchanged` | `RuntimeError: public tier: SDTM_RAG_QUOTA_TRUSTED_PROXIES too broad ['10.0.0.0/8'] (trust only the t` |
| A09 | 公开档 session cookie 不带 Secure | killed: 1 failed, 188 passed | `test_session_cookie_secure_follows_tier` | `AssertionError: assert 'secure' in {'httponly', 'max-age=43200', 'path=/', 'samesite=lax'}` |
| A10 | 私有档 session cookie 带 Secure | killed: 1 failed, 188 passed | `test_session_cookie_secure_follows_tier` | `AssertionError: assert 'secure' not in {'httponly', 'max-age=43200', 'path=/', 'samesite=lax', 'secu` |
| A11 | 任何对端都能设 CF-Connecting-IP | killed: 5 failed, 184 passed | `test_other_peers_cannot_set_the_visitor_ip[10.201.8.1]` | `AssertionError: assert 200 == 429` |
| A12 | 档位判断恒为私有 | killed: 27 failed, 162 passed | `test_public_every_response_carries_hsts[/]` | `assert None == 'max-age=31536000'` |
| C01 | .env 压过 compose 的环境变量 | killed: 1 failed, 188 passed | `test_config_loads_dotenv_without_override_and_key_is_not_a_settings_field` | `` |
| P01 | compose 信整个子网 | killed: 13 failed, 176 passed | `test_public_api_trusts_only_the_connector` | `AssertionError: assert '10.201.8.0/24' == '10.201.8.2'` |
| P02 | 子网撞私有站网段 | killed: 2 failed, 187 passed | `test_public_network_is_pinned` | `AssertionError: assert [{'gateway': ...2.22.0.0/24'}] == [{'gateway': ....201.8.0/24'}]` |
| P03 | 动态分配可抢连接器地址 | killed: 1 failed, 188 passed | `test_public_network_is_pinned` | `AssertionError: assert [{'gateway': ....201.8.0/24'}] == [{'gateway': ....201.8.0/24'}]` |
| P04 | 网桥名与 nft 脱钩 | killed: 2 failed, 187 passed | `test_public_network_is_pinned` | `AssertionError: assert {'com.docker....': 'br-other'} == {'com.docker.... 'br-sdtmpub'}` |
| P05 | 公开实例发布宿主端口 | killed: 1 failed, 188 passed | `test_public_no_host_exposure_or_escape_hatches` | `AssertionError: ports` |
| P06 | 公开网络开 IPv6 | killed: 1 failed, 188 passed | `test_public_network_is_pinned` | `assert True is False` |
| T01 | token 走环境变量 | killed: 1 failed, 188 passed | `test_tunnel_token_only_via_readonly_file` | `AssertionError: assert {'TUNNEL_EDGE...tunnel-token'} == {'TUNNEL_EDGE...tunnel-token'}` |
| T02 | token 走命令行 | killed: 1 failed, 188 passed | `test_tunnel_token_only_via_readonly_file` | `AssertionError: assert ['tunnel', '-...--token', 'x'] == ['tunnel', '-...pdate', 'run']` |
| T03 | token 走 env_file | killed: 1 failed, 188 passed | `test_tunnel_token_only_via_readonly_file` | `AssertionError: assert 'env_file' not in {'cap_drop': ['ALL'], 'command': ['tunnel', '--no-autoupdat` |
| T04 | 连接器地址与可信代理脱钩 | killed: 1 failed, 188 passed | `test_tunnel_joins_the_public_network_at_the_static_address` | `AssertionError: assert {'public': {'...'10.201.8.3'}} == {'public': {'...'10.201.8.2'}}` |
| T05 | 连接器自建网络 (不是公开实例那张) | killed: 1 failed, 188 passed | `test_tunnel_joins_the_public_network_at_the_static_address` | `AssertionError: assert {'name': 'sdtm-rag-public'} == {'external': ...m-rag-public'}` |
| T06 | 镜像不钉摘要 | killed: 1 failed, 188 passed | `test_tunnel_image_pinned_by_version_and_digest` | `AssertionError: cloudflare/cloudflared:2026.11.2` |
| T07 | token 文件可写挂载 | killed: 1 failed, 188 passed | `test_tunnel_token_only_via_readonly_file` | `AssertionError: assert [{'bind': {'c...-token', ...}] == [{'bind': {'c...-token', ...}]` |
| T08 | 连接器保留 capability | killed: 1 failed, 188 passed | `test_tunnel_no_host_exposure_and_least_privilege` | `KeyError: 'cap_drop'` |
| T09 | 连接器发布端口 | killed: 1 failed, 188 passed | `test_tunnel_no_host_exposure_and_least_privilege` | `AssertionError: ports` |
| T10 | token 文件缺失时 docker 建空目录顶上 | killed: 1 failed, 188 passed | `test_tunnel_token_only_via_readonly_file` | `AssertionError: assert [{'bind': {'c...-token', ...}] == [{'bind': {'c...-token', ...}]` |
| N01 | 清空全机规则 | killed: 1 failed, 188 passed | `test_nft_touches_only_its_own_table` | `assert not <re.Match object; span=(91, 96), match='flush'>` |
| N02 | 丢掉全机转发 | killed: 1 failed, 188 passed | `test_nft_chains_hook_before_docker_and_keep_policy_accept` | `AssertionError: assert 'type filter ... policy drop;' == 'type filter ...olicy accept;'` |
| N03 | 同网络放行排到丢弃之后 | killed: 1 failed, 188 passed | `test_nft_forward_rules_exact_and_ordered` | `AssertionError: ['iifname "br-sdtmpub" oifname "br-sdtmpub" accept', 'iifname "br-sdtmpub" ip daddr ` |
| N04 | 放过 192.168/16 (局域网 / 宿主) | killed: 8 failed, 181 passed | `test_nft_blocks_private_destinations[192.168.5.15]` | `AssertionError: 192.168.5.15` |
| N05 | 误挡 Cloudflare 隧道接入点 | killed: 5 failed, 184 passed | `test_nft_leaves_public_destinations_alone[198.41.192.167]` | `AssertionError: 198.41.192.167` |
| N06 | nft 网桥名与 compose 脱钩 | killed: 2 failed, 187 passed | `test_nft_input_rules_exact_and_ordered` | `assert ['ct state es...counter drop'] == ['ct state es...counter drop']` |
| N07 | nft 网段与 compose 脱钩 | killed: 2 failed, 187 passed | `test_nft_input_rules_exact_and_ordered` | `assert ['ct state es...counter drop'] == ['ct state es...counter drop']` |
| N08 | 虚拟机连容器的回包被丢 | killed: 1 failed, 188 passed | `test_nft_input_rules_exact_and_ordered` | `assert ['iifname "br...counter drop'] == ['ct state es...counter drop']` |
| N09 | 少一条转发丢弃 | killed: 1 failed, 188 passed | `test_nft_forward_rules_exact_and_ordered` | `AssertionError: ['iifname "br-sdtmpub" oifname "br-sdtmpub" accept', 'ip saddr 10.201.8.0/24 ip dadd` |
| N10 | 钩子排到 docker 之后 | killed: 1 failed, 188 passed | `test_nft_chains_hook_before_docker_and_keep_policy_accept` | `AssertionError: assert 'type filter ...olicy accept;' == 'type filter ...olicy accept;'` |
| U01 | 规则晚于容器启动 | killed: 1 failed, 188 passed | `test_isolation_unit_loads_the_ruleset_before_docker` | `AssertionError: assert 'Before=docker.service' in '\n\n\n\n\n[Unit]\nDescription=sdtm-rag public doc` |
| U02 | 停单元时清空全机规则 | killed: 1 failed, 188 passed | `test_isolation_unit_loads_the_ruleset_before_docker` | `AssertionError: assert 'ExecStop=-/usr/sbin/nft delete table inet sdtm_rag_public_isolation' in '\n\` |
| R01 | 被拒绝不算可达 | killed: 4 failed, 185 passed | `test_probe_classifies_each_failure_mode` | `AssertionError: assert ({'open', 'refused'} == frozenset({'open'})` |
| R02 | 不看对照侧 | killed: 2 failed, 187 passed | `test_probe_judge_three_states[timeout-timeout-open-INCONCLUSIVE]` | `AssertionError: ['PASS          192.168.100.58:443: 隔离侧 timeout, 对照侧 timeout', 'PASS          api.an` |
| R03 | 外网不通仍可通过 | killed: 2 failed, 187 passed | `test_probe_judge_three_states[timeout-open-timeout-FAIL]` | `AssertionError: ['PASS          192.168.100.58:443: 隔离侧 timeout, 对照侧 open', 'FAIL          api.anthr` |
| R04 | 拒绝连接归成超时 | killed: 2 failed, 187 passed | `test_probe_classifies_each_failure_mode` | `AssertionError: assert 'timeout' == 'refused'` |
| A13 | 连接器送来两条 CF-Connecting-IP 时采信第一条 | killed: 1 failed, 188 passed | `test_duplicate_cf_connecting_ip_from_the_connector_is_not_trusted` | `AssertionError: assert 200 == 429` |
| P07 | 公开实例采信回环来的 X-Forwarded-For | killed: 2 failed, 187 passed | `test_public_compose_disables_uvicorn_proxy_headers` | `AssertionError: assert '127.0.0.1' == ''` |
| N11 | input 链丢掉虚拟机自己连网关地址的包 | killed: 2 failed, 187 passed | `test_nft_input_rules_exact_and_ordered` | `assert ['ct state es...counter drop'] == ['ct state es...counter drop']` |
| N12 | 放过保留段 240/4 | killed: 1 failed, 188 passed | `test_nft_blocked_set_exact` | `AssertionError: assert ['0.0.0.0/8',....0.0/12', ...] == ['0.0.0.0/8',....0.0/12', ...]` |
| N13 | 放过 198.18/15 | killed: 1 failed, 188 passed | `test_nft_blocked_set_exact` | `AssertionError: assert ['0.0.0.0/8',....0.0/12', ...] == ['0.0.0.0/8',....0.0/12', ...]` |
| N14 | 放过 0/8 | killed: 1 failed, 188 passed | `test_nft_blocked_set_exact` | `AssertionError: assert ['10.0.0.0/8'....0.0/24', ...] == ['0.0.0.0/8',....0.0/12', ...]` |
| N15 | 放过 192.0.0.0/24 | killed: 1 failed, 188 passed | `test_nft_blocked_set_exact` | `AssertionError: assert ['0.0.0.0/8',....0.0/12', ...] == ['0.0.0.0/8',....0.0/12', ...]` |
| U03 | 隔离单元 enable 不生效 (开机不装规则) | killed: 1 failed, 188 passed | `test_isolation_unit_loads_the_ruleset_before_docker` | `AssertionError: assert 'WantedBy=multi-user.target' in '\n\n\n\n\n[Unit]\nDescription=sdtm-rag publi` |
| U04 | 隔离单元同时排在 docker 之后 | killed: 1 failed, 188 passed | `test_isolation_unit_loads_the_ruleset_before_docker` | `AssertionError: After=docker.service` |
| W01 | 规则装不回去时不停连接器 | killed: 3 failed, 186 passed | `test_isolation_watchdog_behaviour[True-loads_ok3-1-want_calls3-isolation ruleset reload…` | `` |
| W02 | 巡检停错容器 (私有站) | killed: 3 failed, 186 passed | `test_isolation_watchdog_behaviour[True-loads_ok3-1-want_calls3-isolation ruleset reload…` | `` |
| W03 | 巡检一天才跑一次 | killed: 1 failed, 188 passed | `test_isolation_watchdog_command_and_timer_pinned` | `AssertionError: assert ('OnBootSec=20s' in '\n\n\n\n[Unit]\nDescription=sdtm-rag public docker netwo` |
| W04 | 巡检定时器 enable 不生效 | killed: 1 failed, 188 passed | `test_isolation_watchdog_command_and_timer_pinned` | `AssertionError: assert 'WantedBy=timers.target' in '\n\n\n\n[Unit]\nDescription=sdtm-rag public dock` |
| R06 | 装规则前就连不上的目标也记 PASS | killed: 2 failed, 187 passed | `test_probe_judge_requires_reachable_before_the_rules` | `AssertionError: assert 'PASS' == 'INCONCLUSIVE'` |
| R07 | 不核对隔离侧是在哪个网络里跑的 | killed: 2 failed, 187 passed | `test_probe_judge_checks_where_the_isolated_side_ran` | `AssertionError: assert 'PASS' == 'INCONCLUSIVE'` |
| U05 | 表不在时停单元报失败 | killed: 1 failed, 188 passed | `test_isolation_unit_loads_the_ruleset_before_docker` | `AssertionError: assert 'ExecStop=-/usr/sbin/nft delete table inet sdtm_rag_public_isolation' in '\n\` |
| W05 | 巡检失败一次后可能不再触发 | killed: 1 failed, 188 passed | `test_isolation_watchdog_command_and_timer_pinned` | `AssertionError: assert ('OnBootSec=20s' in '\n\n\n\n[Unit]\nDescription=sdtm-rag public docker netwo` |
| A14 | 连接器不带 CF-Connecting-IP 时抛异常 | killed: 1 failed, 188 passed | `test_connector_request_without_cf_connecting_ip_falls_back_to_the_peer` | `IndexError: list index out of range` |
| W06 | 重装失败也当成功 (不停连接器) | killed: 3 failed, 186 passed | `test_isolation_watchdog_behaviour[True-loads_ok3-1-want_calls3-isolation ruleset reload…` | `` |
| W07 | 重装成功也把连接器停掉 | killed: 2 failed, 187 passed | `test_isolation_watchdog_behaviour[True-loads_ok2-0-want_calls2-]` | `AssertionError:` |
| W08 | 巡检不重装 (只看表在不在) | killed: 6 failed, 183 passed | `test_isolation_watchdog_behaviour[True-loads_ok0-0-want_calls0-]` | `assert 0 == 1` |
| W10 | 重装失败一次就停连接器 (不重试) | killed: 6 failed, 183 passed | `test_isolation_watchdog_behaviour[True-loads_ok0-0-want_calls0-]` | `assert 0 == 1` |
| W11 | 第一次重装成功了还要再装一次 | killed: 3 failed, 186 passed | `test_isolation_watchdog_behaviour[True-loads_ok0-0-want_calls0-]` | `AssertionError:` |
| D05 | 输入 token 时回显 | killed: 10 failed, 179 passed | `test_owner_token_command_validates_before_writing[eyJhIjoiZmFrZS1mb3ItdGVzdCIsInQiOiJ4I…` | `` |
| D06 | token 文件创建瞬间权限过宽 | killed: 10 failed, 179 passed | `test_owner_token_command_validates_before_writing[eyJhIjoiZmFrZS1mb3ItdGVzdCIsInQiOiJ4I…` | `` |
| W09 | 巡检触发精度退回默认的一分钟 | killed: 1 failed, 188 passed | `test_isolation_watchdog_command_and_timer_pinned` | `AssertionError: assert ('OnBootSec=20s' in '\n\n\n\n[Unit]\nDescription=sdtm-rag public docker netwo` |
| R08 | 源地址写死成公开网段里的值 | killed: 1 failed, 188 passed | `test_probe_source_address_is_what_the_kernel_would_use` | `AssertionError: assert '10.201.8.200' == '10.201.8.177'` |
| R09 | 装规则前后目标不一致也给 PASS | killed: 1 failed, 188 passed | `test_probe_judge_requires_reachable_before_the_rules` | `AssertionError: assert 'PASS' == 'INCONCLUSIVE'` |
| R10 | 不核对装规则前那份观测的来源 | killed: 1 failed, 188 passed | `test_probe_judge_checks_where_the_isolated_side_ran` | `AssertionError: assert 'PASS' == 'INCONCLUSIVE'` |
| D01 | token 复制不全也写入 | killed: 2 failed, 187 passed | `test_owner_token_command_validates_before_writing[eyJ-False]` | `AssertionError:` |
| D02 | token 里混进空格也写入 | killed: 10 failed, 179 passed | `test_owner_token_command_validates_before_writing[eyJhIjoiZmFrZS1mb3ItdGVzdCIsInQiOiJ4I…` | `` |
| D03 | 不以 eyJ 开头也写入 | killed: 10 failed, 179 passed | `test_owner_token_command_validates_before_writing[eyJhIjoiZmFrZS1mb3ItdGVzdCIsInQiOiJ4I…` | `` |
| D04 | token 文件权限放宽 | killed: 2 failed, 187 passed | `test_owner_token_command_validates_before_writing[eyJhIjoiZmFrZS1mb3ItdGVzdCIsInQiOiJ4I…` | `` |
| F01 | 镜像的启动命令压过 compose 置空的 FORWARDED_ALLOW_IPS | killed: 1 failed, 188 passed | `test_dockerfile_cmd_does_not_override_forwarded_allow_ips` | `assert ('forwarded-allow-ips' not in 'CMD ["uvico...w-ips", "*"]'` |
| A15 | 镜像下限标记失效 (预检会拒绝本镜像) | killed: 2 failed, 187 passed | `test_image_floor_check_passes_this_build` | `AssertionError: assert (1, '', 'imag...LEVEL >= 1\n') == (0, 'image-floor: ok\n', '')` |
| A16 | 镜像下限标记被改名 (预检按名字找不到) | killed: 2 failed, 187 passed | `test_image_floor_marker` | `AttributeError: module 'server.auth' has no attribute 'PUBLIC_EDGE_LEVEL'` |
| F02 | 预检不看标记 (旧镜像走到后面才报错, 原因不对) | killed: 2 failed, 187 passed | `test_image_floor_check_refuses[_HSTS = None⏎-predates P3.4]` | `AssertionError: (1, '', 'Traceback (most recent call last):` |
| F03 | 预检把「接受网段」当成合格 | killed: 2 failed, 187 passed | `test_image_floor_check_passes_this_build` | `AssertionError: assert (1, '', 'PUBL...s accepted\n') == (0, 'image-floor: ok\n', '')` |
| F04 | 预检拿单主机地址去试 (试不出实现缺失) | killed: 1 failed, 188 passed | `test_image_floor_check_passes_this_build` | `AssertionError: assert (1, '', 'PUBL...s accepted\n') == (0, 'image-floor: ok\n', '')` |
| F05 | 预检合格时不打标记 (和「脚本没送进去」分不开) | killed: 2 failed, 187 passed | `test_image_floor_check_passes_this_build` | `AssertionError: assert (0, '', '') == (0, 'image-floor: ok\n', '')` |
| G01 | 公开 compose 没开全局限流 | killed: 5 failed, 184 passed | `test_public_compose_turns_on_the_global_rate_limit` | `assert (False, 60, 20) == (True, 60, 20)` |
| G02 | 全局限流的每分钟额度放宽 100 倍 | killed: 4 failed, 185 passed | `test_public_compose_turns_on_the_global_rate_limit` | `assert (True, 6000, 20) == (True, 60, 20)` |
| G03 | 全局限流的突发额度低于提问限额 | killed: 3 failed, 186 passed | `test_global_rate_limit_sits_above_the_question_limits` | `assert (60, 5) == (60, 20)` |
| G04 | 公开档全局限流按连接对端计 (所有访客并成连接器一个桶) | killed: 5 failed, 184 passed | `test_public_compose_turns_on_the_global_rate_limit` | `KeyError: 'trusted_proxies'` |
| G05 | 公开档不查大小写变体 (.env 可悄悄关掉全局限流) | killed: 2 failed, 187 passed | `test_public_refuses_case_variant_that_would_override_compose[sdtm_rag_rate_limit_enabled]` | `` |
| G06 | 大小写变体检查漏到私有档 | killed: 1 failed, 188 passed | `test_public_case_variant_check_names_no_values_and_private_is_untouched` | `RuntimeError: public tier: conflicting case variants of the same setting in the environment / .env: ` |
| G07 | 冲突报错里带出取值 (可能是秘密) | killed: 3 failed, 186 passed | `test_public_case_variant_check_names_no_values_and_private_is_untouched` | `assert ('SDTM_RAG_VISITOR_SECRET' in "public tier: conflicting case variants of the same setting in ` |
| G08 | 全局限流误伤静态文件 | killed: 1 failed, 188 passed | `test_public_compose_turns_on_the_global_rate_limit` | `AssertionError: /static/app.js` |
| G09 | 全局限流误伤健康检查 | killed: 1 failed, 188 passed | `test_public_compose_turns_on_the_global_rate_limit` | `AssertionError: /api/health` |
| G10 | 取值相同的大小写变体也拒启动 | killed: 3 failed, 186 passed | `test_public_refuses_case_variant_that_would_override_compose[sdtm_rag_rate_limit_enabled]` | `` |
| G11 | 非 ASCII 的键名不拒 (开尔文符号可冒充 k) | killed: 1 failed, 188 passed | `test_public_case_variant_check_names_no_values_and_private_is_untouched` | `RuntimeError: public tier: conflicting case variants of the same setting in the environment / .env: ` |
| G12 | 只看全大写写法的键 (小写变体漏过去) | killed: 3 failed, 186 passed | `test_public_refuses_case_variant_that_would_override_compose[sdtm_rag_rate_limit_enabled]` | `` |
| R05 | 没有外网对照也通过 | killed: 2 failed, 187 passed | `test_probe_judge_refuses_to_pass_on_missing_evidence` | `AssertionError: assert 'PASS' == 'INCONCLUSIVE'` |

## 网络隔离做到了哪一步

**做到的** (规则已写好并通过语法检查和静态测试; 实际效果要在演练第 3 步才能验证):

- 公开网络里的容器发往以下目的地的包一律丢弃: `10/8`、`172.16/12`、`192.168/16`、`169.254/16`、`100.64/10`、`127/8`、`0/8`、
  `192.0.0.0/24`、`198.18/15`、组播和保留段。覆盖: 局域网 (镜像仓库 / Gitea)、mini 本机 (经 `192.168.5.2` 和 `192.168.64.1`)、
  同机其他 docker 网络 (含经虚拟机地址上的发布端口 DNAT 之后的地址)。
- 发往虚拟机本机的新连接 (网关地址、虚拟机各地址、docker-proxy 代发布的端口) 一律丢弃; 虚拟机主动连容器的回包放行;
  按源网段兜底的那条不含回环接口 (虚拟机自己连网关地址 `10.201.8.1` 走 lo, 源地址也在这个网段里; 代码审查第 1 条)。
- 同一网络内 (连接器 → 公开实例) 放行; 该网桥进来的 IPv6 一律不转发 (网络本身也没开 IPv6)。
- 公网不受限。测试钉住 Cloudflare 隧道接入点 (官方文档列的 `198.41.192.x` / `198.41.200.x`) 不在丢弃集合里。

**验证办法** (演练第 3 步): 先在没装规则时从公开网络里的一次性容器探测, 结论必须是 FAIL (证明洞是真的、探测是有效的);
装规则后同样的探测结论必须是 PASS。每个内网目标还要在不受规则约束的地方 (虚拟机本机) 可达, 否则记「无结论」;
首次装规则时逐个目标对比「装之前可达、装之后被挡」, 装之前就连不上的目标也记「无结论」; 隔离侧的源地址必须在公开网段里。
「连接被拒绝」算可达。外网目标必须连得上, 否则「内网全不通」可能只是容器没网。探测只做 TCP 连接 (规则本身不分协议)。

**没做到的, 和剩余风险**:

1. **不是出站白名单。** 任务写的是「出站只需要各模型服务商的 API、OpenAI embedding 和 Cloudflare」; 现在做到的是「私有地址全禁, 公网全放」。
   容器被攻破后仍可把数据发往任意公网地址、从任意公网地址取指令。原因: 服务商的地址是 CDN 动态地址, nft 按 IP 写不了域名白名单。
   要做到域名级, 需要把公开网络设成 `internal` 再加一个按域名放行的出站代理容器, 并确认应用里每个 HTTP 客户端都走代理 ——
   这会改答题路径的运行方式, 且各服务商的域名清单要跟着 BYOK 预设一起维护, 这次没有做。
   「公网」也包括主人自己对外的入口: 出口公网 IP 上的端口转发 (路由器回环), 同域名下别的对外子域名。
2. **规则不在位时, 最长约一分钟没有隔离; 巡检本身没有在虚拟机上实测过。** 隔离单元排在 docker 之前, 正常开机时规则先于容器装入。
   它失败 (规则文件被改坏、`nft` 不在), 或者运行中规则被移除或改动 (有人停了单元、清空了规则集或这张表、启用了系统自带的 `nftables.service` ——
   它的配置文件第一句就是清空规则集, 2026-11-28 只读查到该服务是 `disabled`) 时, docker 不受影响, 公开实例和连接器照常在跑。
   没有加硬依赖是有意的: 那样规则文件出错会拖垮同机的私有站。
   兜底是每分钟一次的巡检: 把规则文件整份重装一遍 (所以表被删、被清空、被改动都会恢复), 连续两次重装不上就停连接器。
   停连接器的那一刻: 表还在的话内核里原有的规则仍然有效; 表已经不在的话 (被删了, 或开机时就没装上) 公开实例处于没有隔离的状态, 只是没有入口。它保证的是「内核里的规则 = 规则文件」:
   不验证实际效果; 规则文件本身被人改成别的内容它会照装 (文件在虚拟机的 `/etc/` 下, 要 root 才能写); 定时器被停用它自己发现不了 (例行核对里加了一条)。
   取舍: 规则文件被改坏时, 即使内核里原有的规则还好好的, 连接器也会在一分钟内被停掉。
   这些单元文件合并前没法在虚拟机上验证 (演练第 3 步 3c / 3f、第 6 步可选项)。每次部署后和重启后仍要跑探测。
3. **DNS 仍走宿主解析器。** 公开容器能解析局域网里的主机名 (信息泄漏), 也可以用 DNS 查询往外带少量数据。
4. **临时验收容器: 已定为不带网络。** 协调方 2026-11-28 裁定临时验收容器用 `--network none`, 它没有任何网络面, 隔离规则不需要覆盖它。
   另一条线另用一个临时加入公开网络的一次性容器做模型 key 的有效性探测: 它受这套规则约束 (与公开实例同等待遇), 使用上的约束见集成备注第 3 条。
5. **规则只认网桥名和网段。** 有人改了 compose 的子网或网桥名而没改 nft 文件 → 静态测试会红; 但有人在虚拟机上手工重建网络 → 只有探测能发现。
6. **公开实例以 root 运行, 保留 docker 默认 capability** (含 `NET_RAW`)。按进入接口匹配的规则挡得住伪造源地址;
   给公开实例去 capability / 换非 root 用户没有做 (没法在合并前验证数据目录的属主是否允许), 列为后续项。
7. **同一网络内不设防。** 公开实例可以连连接器 (连接器的指标端口已绑到容器内回环)。
8. **`CF-Connecting-IP` 的可信度依赖 Cloudflare。** 官方文档没有明说访客自带的这个头会被覆盖, 演练第 8 步实测。
   同一个 Cloudflare 账号下自己的 Worker 可以影响这个值 (文档原话是同域的 Worker 子请求取 `x-real-ip`), 那是主人自己的代码, 不算外部攻击面。
   后台的 `Remove visitor IP headers` 一旦被打开, 所有访客会并成一个 (方向安全, 但额度被共用), 操作说明里写了不要开。
9. **token 的可见范围。** 虚拟机里 root 能读; 能访问 docker 套接字的人和 job 也能 (`docker cp` 可以把文件拷出来), 这和现有 `.env` 是同一个信任级别。
   Cloudflare 账号里有权限的成员在后台随时能看到 token。
   操作说明第 2 步的输入方式不回显、命令本身不含 token; 但剪贴板历史工具、苹果设备间的通用剪贴板、虚拟机磁盘镜像的备份里都会有它。
   演练里用 `grep -c eyJ` 查泄漏只认得出 token 的原始外形, 认不出解码后的密钥, 是个弱检查。
   镜像摘要是 2026-11-28 查 Docker Hub 得到的, 没有做签名校验。
10. **HSTS 一年。** 浏览器记住之后, 这个主机名一年内只能走 HTTPS; 要提前撤销得在 HTTPS 上发 `max-age=0` (需要改代码)。
11. **首次上线先只放行主人 (主人 2026-11-28 定: 要), 所以隧道层的验收不再是在开放状态下做的; 剩下的风险在「只靠顺序和人」这一点上。**
    隧道这一层的验收 (访客 IP 是否传对、能否伪造、两层限流) 只能在加路由之后做。现在的顺序是: 限速规则 → Access 应用 → 路由 → 验收 → 放开。
    没有任何自动的闸保证这个顺序: 如果主人先加了路由、后建 Access 应用 (或建错了主机名), 中间那一段公开站对所有人开放。
    对策都是人工核对: 操作说明第 6 步建完后核对一遍, 第 7 步加完路由立刻用无痕窗口确认看到的是登录页, 演练第 7 步协调方再从外面用 curl 确认一次;
    任何一处直接拿到了页面就停连接器。放开之后 Access 这一层就没有了, 之后靠的是额度、两层限流和每日费用封顶。
    撤入口配置时如果先删 Access 应用、后删路由, 同样会有一段对所有人开放 —— 回退表里写了先删路由。
12. **连接器没在跑时, 它的地址可以被占用。** 能操作 docker 的人可以起一个占用 `10.201.8.2` 的容器, 公开实例会把它当连接器。
    能操作 docker 等于虚拟机的 root, 不是新的权限 (演练第 4、6 步各验一半)。
13. **回退固定子网会让隔离同时失效。** 网络回到自动网段和随机网桥名后, 规则的两个匹配条件都对不上, 而且不报错。回退表里写了此时公开实例必须保持停止。

## 集成备注 (给另一条线和协调方)

1. **`tests/test_deploy_public_compose.py` 我没有动。** compose 文件本身的新断言都在 `tests/test_deploy_public_tunnel.py`;
   workflow 结构的断言留给对方。对方如果要改 `compose.public.yml`: 网络段、`environment` 里的可信代理、服务只有 `api` 这三处被我的测试逐字钉住。
2. **部署前的三道只读预检** (另一条线实现; 我没有改 workflow)。协调方 2026-11-28 确认会加这三道:
   - **网段**: `docker network inspect sdtm-rag-public` 的子网必须是 `10.201.8.0/24`, 不是就失败 (说明演练第 2 步没做, 可信代理地址对不上)。
   - **隔离探测**: 隔离侧用公开网络里的一次性容器跑 `isolation_probe.py probe` (脚本经标准输入送进去, `deploy/` 不进镜像),
     对照侧用默认网桥上的一次性容器跑同一批内网目标, 然后 `judge --isolated-net 10.201.8.0/24` (例行核对不带 `--before`); 退出码非 0 就不换。命令照演练第 3 步的 3a / 3d,
     对照侧把 `VM "python3 - probe …"` 换成 `docker run --rm -i --network bridge --entrypoint python <镜像> - probe …`。
     用容器作对照比用虚拟机本机更贴切 (证明「没有规则的容器连得上」)。
   - **镜像下限**: 见第 9 条。
3. **临时验收容器与一次性探测容器** (协调方 2026-11-28 裁定: 临时验收容器用 `--network none`, 不需要第二个网段, 我这边的规则和测试不为它改)。
   - **临时验收容器** (`--network none`): 从 `compose.public.yml` 照抄 `environment` (三个键, 含 `SDTM_RAG_QUOTA_TRUSTED_PROXIES=10.201.8.2` 和 `FORWARDED_ALLOW_IPS=""`) 和两个挂载的写法;
     **`networks` 段不能照抄** (网络名、网桥名、子网都是写死的)。
   - **一次性探测容器** (临时加入 `sdtm-rag-public`, 做模型 key 的有效性探测): 在现有定义下它和公开实例同等待遇, 不需要我这边改任何东西。
     - 规则只看进入的网桥 `br-sdtmpub` 和源网段 `10.201.8.0/24`, 不看是哪个容器: 它能访问公网的 HTTPS (解析走 docker 内置解析器), 访问不了私有地址、虚拟机本机和同机其他容器。
     - 它的地址由 docker 自动分配, 只从 `10.201.8.128/25` 取 (`compose.public.yml` 的 `ip_range`; 测试 `test_connector_address_outside_dynamic_range` 钉住连接器的 `.2` 不在这一段), 抢不到连接器的地址。
     - 它的地址不是可信代理, 它向公开实例发请求时带的 `CF-Connecting-IP` 不被采信 (测试 `test_other_peers_cannot_set_the_visitor_ip` 含动态段里的 `10.201.8.130`)。
     - 以上两条在虚拟机上的实际表现由演练第 3 步 3b / 3d 的探测 (它本身就是这样一个容器) 和第 4 步验证; 合并前只有静态依据。
     - **起这个容器时要守的几条** (安全审查第四轮给的, 请写进对方的预检):
       1. 不要指定地址 (`--ip`)。指定 `--ip 10.201.8.2` 就成了「连接器」; 连接器没在跑时 docker 允许这样做。
       2. 不要叫 `sdtm-rag-public-api`, 不要加这个网络别名, 也不要用 `docker compose run api` (会带上服务别名 `api`)。连接器按名字找公开实例, 同名或同别名的容器可能分到访客的请求。
       3. 加 `--cap-drop ALL`。默认 capability 里的 `NET_RAW` 让容器能在网桥上冒领别人的地址; 这个容器不需要它。
       4. key 不要用 `-e` / `--env-file` 传 (值会出现在 `docker inspect` 里); 像公开实例那样只读挂载 `.env`。
       5. `--rm`, 不监听任何端口, 跑完即删。
4. **连接器不归部署 job 管。** 它起一次之后靠 `restart: unless-stopped` 常驻。公开实例被重建后连接器是否无需重启就能连上新容器, 未核实 (演练第 8 步)。
5. **以后改公开网络的定义**: 连接器挂在网络上时 compose 无法删掉重建网络, 部署 job 的 `up -d` 会失败或行为不确定。要先停并删除连接器, 再按演练第 2 步做。
6. **路径过滤**: `deploy/container/compose.tunnel.yml` 和 `compose.public.yml` 在 `deploy/container/**` 下, `server/auth.py` 在 `server/**` 下,
   合并 push 会触发私有站的构建和部署 (私有站行为不变)。`deploy/public-net/**`、`docs/**`、`tests/**` 不触发。
7. **打开 `SDTM_RAG_PUBLIC_DEPLOY` 之前必须先做演练第 2 步** (重建网络)。
8. **共享状态文件** (`_progress.json`、`docs/PROGRESS.md`、`evidence/trace.jsonl`) 我没有改, 请协调方合并时统一更新。
   `todo_later` 里「P3 冒烟: … 可信代理=cloudflared + 端口只绑 127.0.0.1」那一条: 可信代理部分由本步落实; 「端口只绑 127.0.0.1」早已改成不发布端口。
9. **镜像下限: 推荐的标记和判法。** 现在的预检只拒 P2 之前的镜像。隧道接上以后, 如果手动用 tag 回滚到这一步之前的镜像,
   公开站会在没有 HSTS、没有重复头处理、可信代理允许 `/24` 的代码上对外。
   - **标记**: 常量 `server.auth.PUBLIC_EDGE_LEVEL`, 本步的值是整数 `1`。它只在这一步 (squash 合并后的那个提交) 之后才有; 之前的镜像没有这个属性。
     用整数等级而不是布尔: 以后再有「不能回滚越过」的公开档改动, 把数字加一, 预检的阈值跟着提高, 不用换名字。代码里写了不要改名; 改名或改成 0 测试会红。
   - **判法 (推荐)**: 用仓库里的脚本, 经标准输入送进待部署的镜像执行。**合格 = 退出码 0 并且标准输出恰好是 `image-floor: ok`**, 两样都要核对:

     ```bash
     out=$(docker run --rm -i --entrypoint python "$IMG" - < deploy/public-net/image_floor_check.py) \
       && [ "$out" = "image-floor: ok" ] || { echo "镜像下限预检未通过"; exit 1; }
     ```

     只看退出码不行: `docker run` 漏写 `-i` 时脚本没送进容器, python 读到空输入, 什么都不做就以 0 退出, 任何镜像都会被放行 (第五轮审查发现)。
     脚本先看 `getattr(auth, "PUBLIC_EDGE_LEVEL", 0) >= 1`, 再实际调一次「可信代理必须是单主机」的检查 —— 标记是镜像自己声明的, 只看标记的话「标记在、实现被回退」会被放行。
     不合格时退出码非 0, 原因在标准错误里。`server.auth` 不读 `.env`、不碰数据目录, 这一步不需要任何环境变量或挂载。
   - **只想要一行的话**: `docker run --rm --entrypoint python <镜像> -c 'import sys; from server import auth; sys.exit(0 if getattr(auth, "PUBLIC_EDGE_LEVEL", 0) >= 1 else "image predates P3.4")'`
     (只看标记, 不验行为; 它不经标准输入, 没有「漏写 `-i`」的问题)。
   - 本仓的测试: `test_image_floor_marker`、`test_image_floor_check_passes_this_build`、`test_image_floor_check_refuses` (六种不合格的情形都以非零退出)、
     `test_image_floor_check_needs_the_marker_not_just_exit_zero` (空输入: 退出码 0 但没有那行输出)。
10. **全局限流: 已按主人的裁定打开** (原先这一条是「观察到、没有处理」)。应用里的一层写在 `compose.public.yml` 的 `environment` 里;
    Cloudflare 的一层由主人按操作说明第 5 步建。给另一条线的两点:
    - 临时验收容器照抄 `environment` 后也带着全局限流。从容器内发的请求按 `127.0.0.1` 计 (对端不是可信代理): **验收里对 `/api/*` 的请求一分钟内不要超过 20 个**
      (`/api/health` 不计)。现有的验收只发两三个, 没有问题; 以后往里加检查时留意。
    - 公开档启动时多了一项检查: env 文件里同一个 `SDTM_RAG_*` 键如果有取值不同的大小写变体, 启动会失败, 日志是
      `conflicting case variants of the same setting` 加键名。临时验收容器会先撞上它 (方向安全: 正式容器不动)。

11. **本分支须以 squash 方式合并, 不保留逐个提交** (协调方 2026-11-28 裁定)。原因是早期提交 (`9b7e0aa`、`5021cc3`) 里留档的审查提示词含本机路径 (带用户名的绝对路径)。
    HEAD 的工作树里没有: `git diff --name-only 9a8ad43..HEAD | xargs git grep -n -I -e '/[U]sers/' -e '<用户名>' HEAD --` 没有输出 (本分支动过的 19 个文件;
    模式里的方括号只是为了不匹配到这一行自己)。
    仓库里别处早就有同类路径 (9a8ad43 时已有), 不在本步范围。

12. **合并时要重新生成另一条线的 `tests/fixtures/kbsync/compose_config_public_tunnel.json`。** 它是照当时的 `compose.public.yml` 渲染出来的;
    这次 `environment` 多了三个 `SDTM_RAG_RATE_LIMIT_*` 键 (更早还加过 `FORWARDED_ALLOW_IPS`), 不重新生成的话对方依赖它的测试会和实际的 compose 脱节。
    渲染命令 (文件经标准输入传入, 虚拟机上不落文件; 2026-11-28 只读试过, 输出的 `services.api.environment` 是六个键):

    ```bash
    ssh bojiang.local 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- sh -c "cd /tmp && IMAGE_TAG=<对方生成它时用的标签> docker compose -f - config --format json"' \
      < deploy/container/compose.public.yml > tests/fixtures/kbsync/compose_config_public_tunnel.json
    ```

    这个文件不在我的分支里, 我不知道对方生成它时用的确切参数 (`IMAGE_TAG` 的取值、有没有 `--format json`、有没有再加工): 以对方的生成方式为准, 上面只保证 compose 这一侧的输入是最新的。

## 合并前没法验证的事项

都写进了演练方案对应的步骤:

- 网络重建后的实际网段、网桥名、compose 对已有网络的处理 (第 2 步);
- 隔离规则的实际效果, 包括「不装时确实连得上」这半边 (第 3 步); 开机时规则先于容器装入 (不在演练里重启, 留到下次计划内重启);
- 巡检: 三个单元文件的语法、表被删或被清空后是否自动装回 (第 3 步 3f)、装不回去时是否停连接器 (第 6 步可选项)、每分钟重装对已有连接有没有影响 (第 8 步验收期间自然覆盖);
  input 链排除回环那条的效果 (第 3 步 3d: 对照侧装规则后仍连得上 `10.201.8.1:22`);
- 公开实例里 `FORWARDED_ALLOW_IPS` 确实是空串 (第 5 步); 连接器在跑时别的容器占不了它的地址 (第 6 步);
- Cloudflare 限速规则的实际行为 (免费套餐里 `Block` 是否可选、被挡时的状态码和页面、计数的精确程度), 以及它和应用那一层叠在一起的效果 (演练第 8 步的 80 连发);
  Access 生效与否的两处人工确认 (操作说明第 7 步的无痕窗口、演练第 7 步的 curl) 看到的确切状态码和跳转地址;
- 演练 5b 删旧行: `sed -i` 之后重启容器是否如预期读到新文件、公开站现有的 env 文件里有没有会触发新启动检查的大小写变体 (我没有读那个文件);
- 镜像下限预检脚本在真实镜像里的表现 (本机只在仓库的虚拟环境里跑过, 含清空环境变量的一次; 没有在容器里跑过);
- Cloudflare 对重复的 `CF-Connecting-IP` 怎么处理 (第 8 步的 curl); `Pseudo IPv4` 的实际行为 (没有专门的步骤, 第 8 步的访客 IP 核对能间接发现);
- 静态地址在动态段之外是否被接受、`external` 网络上能否指定静态地址 (第 4、6 步; 前者有 Docker 文档依据, 后者只有 `compose config` 解析通过);
- 连接器在只读根文件系统、去掉全部 capability、`TUNNEL_METRICS` 绑回环这几项下能否正常运行 (第 6 步);
- token 不出现在容器元数据和日志里 (第 6 步);
- 隧道送到源站的头、`CF-Connecting-IP` 是否不可伪造、真实 IP 是否进了限额、限速、流式输出、公开实例重建后连接器是否自愈 (第 8 步);
- Cloudflare 后台里文档没写明的地方 (操作说明里标了「未核实」): 删除隧道 / 路由的菜单位置、加路由时是否自动建 DNS 记录、
  Access 默认登录方式、免费套餐的重定向规则条数、隧道连接成功的日志措辞;
- 三个 systemd 单元文件没有用 `systemd-analyze verify` 检查过 (它不接受标准输入, 而我不能在虚拟机上落文件), 放进了第 3 步。

## 查阅的资料 (2026-11-28)

- cloudflared: 运行参数文档 (`--token-file` / `TUNNEL_TOKEN_FILE`, 2025.4.0 起)、仓库的 `RELEASE_NOTES`、`Dockerfile` (`USER 65532:65532`, distroless)、
  `cmd/cloudflared/tunnel/subcommands.go` (读 token 文件后 `strings.TrimSpace`)、防火墙文档 (7844 端口与接入点地址)。
  镜像摘要取自 Docker Hub 的标签接口: `curl -s https://hub.docker.com/v2/repositories/cloudflare/cloudflared/tags/2026.11.2` (多架构索引, 2026-11-23 推送)。
- Cloudflare 后台: 建隧道、路由 (Published application)、隧道权限与 token (Add a replica / Refresh token)、Access 自托管应用与策略、
  Always Use HTTPS、HSTS、单条重定向规则、HTTP 头参考、Managed Transforms、限速规则、隧道常见错误 (SSE 不缓冲)。
- Docker: compose 文件参考 (networks / ipam / external / driver_opts)、`docker network create` / `connect`、网桥驱动选项、iptables 与 nftables 防火墙说明。

## 审查 (规则 D)

> 下面各轮记录里提到的「操作说明第 N 步」是当时的编号。落实主人 2026-11-28 的裁定后, 操作说明新增了第 5 步 (限速规则),
> 原来的第 5–8 步 (Access / 加路由 / 经隧道验 / 放开) 顺延成了第 6–9 步。

writer = 本会话 (orca worker 主循环)。两位审查者类型不同于 writer, 也互不相同, 各自独立、只读, 审的是初版提交 `9b7e0aa`。
提示词原文在 `evidence/subagent_prompts/step_P3.4_reviewers.md` (只给改动范围、需求和观测到的环境事实, 不给 writer 的结论)。

### 代码审查 — `oh-my-claudecode:code-reviewer` (opus): **PASS-with-fixes**, 没有 CRITICAL / HIGH

审查者复跑了初版的 46 个变异 (全部打红), 自己另做 13 个 (6 个存活、2 个无害存活), 并做了私有档新旧两版响应头逐字节对比 (8 种配置, 完全相同)。

| # | 级别 | 问题 | 处理 |
|---|---|---|---|
| 1 | MEDIUM | nft input 链按源网段丢包没限定接口: 虚拟机自己连网关地址 `10.201.8.1` 走 lo, 源地址也在网段里, 会被丢 ⇒ 探测的对照侧永远连不上网关, 例行核对永远「无结论」 | 改成 `iifname != "lo" ip saddr … drop`; 测试逐字钉住; 变异 N11; 演练 3d 加「对照侧装规则后仍可达」 |
| 2 | MEDIUM | 演练 3c 有一条 `VM "…; …"` 的后半段会在 mini 上执行 | 改成 `VM "sh -c '…'"`; 多行 Python 改从标准输入送; 文档开头写明这条规矩; 几种写法用只读命令试过 (命令和输出写在演练方案「约定」一节) |
| 3 | LOW-MEDIUM | 已提交的文字 (测试 docstring、演练第 0 步、提交信息) 指向还没提交的 checkpoint | 本文件随修正一起提交 |
| 4 | LOW | 变异脚本只看退出码判「打红」, 收集报错也会记成 killed; 直接改共享工作区 | 加预登记用例 + INVALID 判定; 支持 `P34_MUT_ROOT` 指到副本 |
| 5 | LOW | 存活的变异: 单元缺 `[Install]`; `blocked4` 去掉 `240/4`、`198.18/15`、`0/8`、`192.0.0.0/24`; 单元同时写 `After=docker.service` | 整个集合逐字钉住; 断言 `WantedBy=` 和没有 `After=`; 变异 N12–N15、U03、U04。另两个无害存活 (`hsts` 形参默认值、连接器 `mem_limit`) 没有处理 |
| 6 | LOW | README 里的探测命令照抄跑不起来 | 改成文字说明 + 指向演练第 3 步 |
| 7 | LOW | 测试注释写「实测」没附命令 | 注释里补上复核做法 |
| — | 待确认 | 另一条线照抄 compose 起副本时不能照抄 `networks` 段 | 写进集成备注第 3 条 |

### 安全审查 — `oh-my-claudecode:security-reviewer` (opus): **PASS-with-fixes**, 风险 MEDIUM, 没有 CRITICAL / HIGH

| # | 级别 | 问题 | 处理 |
|---|---|---|---|
| M1 | MEDIUM | 操作说明第 2 步: 四条命令放一个代码块, 整块粘贴时 `read` 会吞掉下一行命令, 随后 token 被贴到普通提示符下, 进历史和屏幕 | 改成一条自带提示和校验的命令 (不以 `eyJ` 开头、含别的字符、或不足 100 个字符就不写入), 前后关 / 开命令历史, 分四段并写明不要整块粘贴; 校验逻辑由测试把文档里的命令原样取出来跑 (`test_owner_token_command_validates_before_writing`, 10 种输入); 补了剪贴板工具和磁盘镜像备份 |
| M2 | MEDIUM | Access 一步可选, 跳过就是先对外后验证 | 文档改成「建议不要跳过」并写明跳过的后果, 「放开」以前一步全部通过为前提; 记入剩余风险第 11 条。**没有改成必做**: 这是主人的决定, 请协调方请主人裁定 |
| L1 | LOW | 可信对端带两条 `CF-Connecting-IP` 时取第一条 | 不是恰好一条就按连接对端计; 测试 + 变异 A13; 演练第 8 步加 curl 双头测试 |
| L2 | LOW | uvicorn 默认采信回环来的 `X-Forwarded-For` 并改写对端, 容器内请求可以冒充连接器; 以后有人放宽更糟 | 公开 compose 设 `FORWARDED_ALLOW_IPS: ""` (不动共用的 Dockerfile, 私有站不变); 测试拿这个值喂真的 uvicorn 中间件; 整个 `environment` 逐字钉住; 变异 P07 |
| L3 | LOW | 规则表运行中被移除没有持续检测 | 加巡检定时器 (第一轮后是「不在就重装」, 增量审查后改成每分钟整份重装; 装不上就停连接器); 测试 + 变异 W01–W09; 剩余风险第 2 条如实改写 |
| L4 | LOW | 4 个 fail-open 变异存活 | 同代码审查第 5 条 |
| L5 | LOW | README 用现在时描述还没生效的东西 | 节首加状态说明 |
| L6 | LOW | 「公网不受限」没说包含主人自己对外的入口 | 写进剩余风险第 1 条和 README |
| L7 | LOW | 回退固定子网会让隔离静默失效; 没提 `Pseudo IPv4`; 抓包是整段传回本机后才过滤 | 回退表改写; 「不要打开」清单加一项 (标未核实); 过滤挪到虚拟机里做 |
| L8 | LOW | 连接器停着时静态地址可被占用 | 演练第 4、6 步各验一半; 剩余风险第 12 条 |
| L9 | LOW | 探测不按目标对比装规则前后; 只测 TCP; 没记录源地址 | `judge` 加 `--before` 和 `--isolated-net`, `probe` 记录源地址; 测试 + 变异 R06、R07; 「只测 TCP」写进脚本说明和本文件 |

安全审查者核实后认为成立、不构成问题的: `.env` 与 compose 的优先级; 公开档的强制项无法被配置关掉; 私有档无变化; 非预期对端 (IPv4 映射地址、非法头值) 回落到对端;
网络定义不对时连接器起不来; nft 规则的静态推演 (进入接口匹配挡伪造源、DNAT 后的目的地址、IPv6 / 组播到本机、两条同网络放行、DNS); token 不在 compose / inspect / 进程参数里。

### 增量审查 (审的是修正: `9b7e0aa..dbf5e6b`)

第一轮之后的修正加了新机制 (重复头回落、`FORWARDED_ALLOW_IPS`、巡检、input 规则改写、探测的新判定), 不只是照意见改字, 所以请原来的两位审查者各做了一次增量审查。

**代码审查 (增量): PASS-with-fixes**, 没有 CRITICAL / HIGH。复跑了当时的 63 个变异 (全部 killed, 0 INVALID), 自己另做 6 个 (4 个存活、2 个无害存活); 把巡检命令换上桩跑了三种情形, 与文件头一致。

| # | 级别 | 问题 | 处理 (`4821c6d`) |
|---|---|---|---|
| 1 | MEDIUM | 巡检「重装成功就退出」没被测试钉住: 去掉那个 `exit 0`, 规则装回来了连接器却被停掉, 测试全绿 | 巡检改成每次整份重装, 分支减到两个; 新测试把单元里的命令原样取出来、把 nft / docker 换成桩跑四种情形, 断言退出码、调用序列和输出; 变异 W06–W08 |
| 2 | LOW-MEDIUM | 连接器不带 `CF-Connecting-IP` 的边界没钉住: `!= 1` 改成 `> 1` 会抛异常, 测试全绿 | 补用例 `test_connector_request_without_cf_connecting_ip_falls_back_to_the_peer`; 变异 A14 |
| 3 | LOW-MEDIUM | 两处「试过」没附命令; 本文件里有过期的「61 个」 | 命令写进演练方案; token 校验改由测试执行; 数字随本次更新 |
| 4 | LOW | 源地址取法写死成固定值仍全绿; 装规则前后目标集不一致的检查去掉仍全绿 | 各补一条测试 (替换 `socket.socket` 核对取法; before 多一个目标 → 无结论); 变异 R08、R09 |
| 5 | LOW | 巡检文件头说「清空」也会重装, 实际只看表在不在 | 巡检改成整份重装后这句话成立; 演练 3f 加了「清空表内容后是否恢复」 |
| 6 | LOW | 无害的存活: 定时器去掉 `AccuracySec`、巡检去掉 `After=docker.service`; Dockerfile 的 CMD 没被钉住 | `AccuracySec` 和 Dockerfile CMD 各加断言 (变异 W09、F01); `After=` 没处理 |

**安全审查 (增量): PASS-with-fixes**, 风险 LOW。对新机制逐项尝试绕过, 没有找到新的 CRITICAL / HIGH / MEDIUM; 实验确认 `FORWARDED_ALLOW_IPS=''` 下 `X-Forwarded-For` / `X-Forwarded-Proto` / `Forwarded` 都不再改写对端和协议。

| # | 级别 | 问题 | 处理 (`4821c6d`) |
|---|---|---|---|
| L1 | LOW | 探测: `--before` 那份观测自己的源地址没核对, 在虚拟机本机取的 before 会让「装之前可达」被假满足 | 带 `--isolated-net` 时 before 的源地址也必须在网段里; 测试 + 变异 R10 |
| L2 | LOW | 巡检只看表在不在, 表被清空内容发现不了 | 改成每分钟整份重装 |
| L3 | LOW | 例行核对没查巡检定时器本身 | 演练第 9 步加一条 (顺带查 `nftables.service` 仍是 disabled) |
| L4 | LOW | token 输入: 复制不全的 token 能通过; 提示出现前粘贴会回显 | 加长度下限; 文档写明等提示出现再粘贴、屏幕上出现过 `eyJ…` 就按泄漏处理、先确认是 bash |
| L5 | LOW | 演练第 6 步的可选验证中断时会停在「没有规则也没有巡检」的状态 | 改成只挪规则文件, 内核里的规则不动; 中断时方向是安全的 |
| L6 | LOW | 本文件两处陈述 (没附命令的「试过」; 「修正后没有再审」) | 已更新 |
| — | 可只读核实 | `nftables.service` 默认配置是否清空规则集 | 只读查了: 第一条语句是 `flush ruleset`, 服务 `disabled`; 写进演练第 1 步和 README |

### 第三轮 (窄范围, 审的是 `dbf5e6b..4821c6d`)

巡检从「表不在才重装」改成「每分钟整份重装」是机制变化, 所以请安全审查者再看了一次。**结论: PASS**, 没有 CRITICAL / HIGH / MEDIUM。
它核对的要点: `nft -f` 把整个文件作为一个原子事务提交, 没有「表短暂不在」的时刻; 不影响已有连接和 docker 的规则;
规则文件只有 root 能写, 不是新的权限面; 探测的 L1 已堵住; 第 6 步可选验证不再有无隔离的窗口, 中途断了方向是安全的。

| # | 级别 | 问题 | 处理 (`a0fd595`) |
|---|---|---|---|
| L1 | LOW | token 命令的测试用管道喂输入, 「不回显」那条断言什么也没测到 (`read -rsp` 改成 `-rp` 仍绿; 去掉 `umask` 仍绿) | 删掉那条空断言, 改为钉字面 (`read -rsp`、开头的 `umask 077`); 变异 D05、D06。真正的不回显没有用伪终端测 |
| L2 | LOW | 巡检命令的测试测的是 shell 分支, 测不到真实 `nft` 的原子性, 也测不到虚拟机上 `/bin/sh` 是 dash | 没法在合并前补, 靠演练 3f 和第 6 步可选项; 命令只用了 `||`、`&&`、`;` |
| L3 | LOW | 演练 3d 的「drop 计数器不为零」可能因巡检清零而误判 | 文档写明看到 0 就再跑一次探测后立刻看, 不算失败 |
| L4 | LOW (需进演练) | 每分钟的 `nft -f` 如果撞上 docker 自己提交规则而偶发失败, 巡检会误停连接器 (未核实会不会发生) | 巡检改成失败后隔 3 秒重试一次, 两次都失败才停; 测试加「第一次失败第二次成功」; 变异 W10、W11; 演练写明上线后留意日志里的 `reload failed twice` |

### 第四轮 (补审, 审的是 `a0fd595` 和 `b546a01`)

协调方要求给 `a0fd595` 补独立审查; 同时送审的还有收尾时加的镜像下限标记 `b546a01`。审查者仍是 `oh-my-claudecode:security-reviewer`。
**结论: PASS-with-fixes**, 风险 LOW, 没有 CRITICAL / HIGH / MEDIUM。它核对了巡检新命令的五种情形、`sleep 3` 在 oneshot 单元里没有超时或重叠问题、
标记的判据不会误放 P3.4 之前的镜像 (清空环境执行过)、一次性探测容器与公开实例同等待遇。

| # | 级别 | 问题 | 处理 (`1cf2448`) |
|---|---|---|---|
| L1 | LOW (文档) | 「两次重装失败时内核里原有的规则还在」只在表本来就在时成立; 表已经不在的话公开实例处于无隔离状态 (无入口) | 巡检单元文件头、README、本文件剩余风险第 2 条都改成分两种情形写 |
| L2 | LOW (给另一条线) | 一次性探测容器带着模型 key 加入公开网络时要守的约束 | 写进集成备注第 3 条 (五条) |
| L3 | LOW (加固) | 镜像下限标记是自我声明, 不验证行为 | 加预检脚本 `image_floor_check.py`: 看标记之外实际调一次单主机检查; 测试 + 变异 F02–F04 |

### 第五轮 (审的是 `1cf2448`)

**结论: PASS-with-fixes** (一条 LOW)。预检脚本的判定逻辑、三条测试的两个方向、两处措辞都核对过, 没有问题;
它把可信代理检查改回 P3.4 之前的「≥ /24」后预检被拒, 确认那项行为核对正好卡住旧实现。

| # | 级别 | 问题 | 处理 (`18a3b93`) |
|---|---|---|---|
| L1 | LOW | `docker run` 漏写 `-i` 时脚本没送进容器, `python -` 读到空输入以 0 退出, 预检会放行任何镜像 (失败时的样子和成功时一样) | 脚本合格时打印 `image-floor: ok`; 推荐的判法改为同时核对退出码和这行输出; 测试钉住「空输入退出码为 0 但没有标记」; 变异 F05 |

### 第六轮 (确认 `18a3b93`)

**结论: PASS**, 落实了上一轮的 L1, 没有引入新问题。审查者用替身 `docker` 把文件头那行 shell 判法原样跑了五种情况:
漏写 `-i`、镜像不合格、标记之前多出别的输出、带 `-t` 产生的回车换行都被拒绝, 只有合格的镜像放行; 这段判法在 `set -e` 下照样工作。

没做的一条可选加固 (审查者说明不阻塞合并): 仓库里的测试只测脚本的 Python 部分, 没有执行文件头里那行 shell 判法; 另一条线照抄它时, 守着它的只有这一轮的手工验证。

至此 (截至 `18a3b93`) 本分支的每个代码提交都有独立审查者看过。

### 第七轮 (审的是 `ade6a59`: 落实主人的三项裁定)

审查者仍是 `oh-my-claudecode:security-reviewer` (与 writer 不同的类型, 只读)。**结论: PASS-with-fixes**, 风险 LOW, 没有 CRITICAL / HIGH / MEDIUM。
它确认: 公开档的全局限流经 `resolve_client_ip` 取连接器传来的访客 IP; 不计数的只有 `/`、`/api/health` 和 `/static/` 前缀, 路径的各种变体都按计数处理 (保守方向);
攻击者伪造不了访客 IP, 只能耗尽自己所在出口的桶, 内存里的桶有上界; 私有档没有变化; 操作顺序里没有对所有人开放的窗口;
5b 的命令不显示文件内容, 「`sed -i` 之后重启才算数」成立, 备份和恢复可行。

| # | 级别 | 问题 | 处理 (`ff663ea`) |
|---|---|---|---|
| L1 | LOW (代码) | 大小写变体检查用 `.upper()` 归并键名, pydantic 用的是 `.lower()`: 开尔文符号 (U+212A) 小写后是普通的 k, 这样的键名能冒充 `top_k` 等而不被检查认出 (前提: 能写 env 文件的人) | 改用 `.lower()`; 非 ASCII 的 `SDTM_RAG_*` 键名直接拒; 测试三种情形; 变异 G11、G12 |
| L2 | LOW (演练假通过) | 「两层限流」的控制台代码把一切非 200 都算成「Cloudflare 挡」, 源站出错也会被算进去 | 非 429 单列为「其他」, 判据要求没有「其他」; 写了 Cloudflare 挡人不用 429 时怎么处理 |
| L3 | LOW (演练假通过) | 从容器内验「桶分离」测不到它声称的失效 (所有访客被错算成连接器地址时, 容器内的请求仍是另一个桶) | 去掉这一项, 写明由测试覆盖, 另给一个可选的换出口检查 |
| L4 | LOW (演练假通过) | 确认 Access 生效的判据「不是 200」太宽 (被限流、源站 502 也不是 200) | 判据改为「跳到 `cloudflareaccess.com` 或 Access 自己的 401 / 403」, 其余都停下来查 |
| L5 | LOW (文档) | 同一出口 IP 共用限流额度没写 | 操作说明和本文件设计取舍第 10 条各补一句 |
| L6 | 需进演练 | Cloudflare 的 Block 返回什么; Access 对未登录的 curl 返回 302 还是 401 / 403 | 两处都在演练里写了「把看到的记下来」 |

### 第八轮 (确认 `ff663ea`)

**结论: PASS**, 上一轮的 L1–L5 都落实了, 没有引入新问题。审查者遍历了全部 Unicode 码位: 小写后变成 ASCII 的非 ASCII 字符只有开尔文符号,
而前缀 `sdtm_rag_` 里没有 k, 所以凡是 pydantic 会认成某个 `SDTM_RAG_*` 键的名字都会经过这项检查; 普通的键和不带这个前缀的非 ASCII 键不会被误拒; 报错只带键名。

至此 (截至 `ff663ea`) 本分支的每个代码提交都有独立审查者看过; 之后只有本文件的提交。

## 过程记录

写的过程中改过的几处 (都在提交 `9b7e0aa` 之前):

- 旧用例 `tests/test_p2_9_fixes.py::test_public_trusted_proxies_must_be_narrow` 的参数表里, `/24` 和 `/120` 原来期望通过。
  单主机约束是这次有意收紧的, 两格改为期望拒绝, 并补了 `/31`、`/127`、不带前缀的单地址、`/128` 四格。
- 变异脚本第一次启动时基线不绿 (`1 failed, 35 passed`), 按设计拒跑。原因: 测试加载探测脚本时在 `deploy/public-net/` 下生成了 `__pycache__` 目录,
  「部署文件里没有 token 形状的串」那条把目录当文件读。改法: 只扫文件, 并在加载探测脚本时不写字节码。
- 一条同时用公开档和私有档两个夹具的用例失败: 后一个夹具清环境变量时把前一个设的也清了。拆成两条。
- HSTS 那条断言原来带了自定义消息 (整份响应头), 变异表里看不出实际值; 去掉自定义消息后失败信息直接是 `assert None == 'max-age=31536000'`。
- 初版的变异共跑过三轮 (第一版 / lint 修正后 / 断言消息修正后), 三轮都是 46 个全部打红。之后随每轮修正扩充 (61 → 63 → 76 → 80 → 82 → 85 → 86 → 96 → 98 个) 并换成带预登记用例的判定, 上表取自最后一轮。

审查阶段:

- 两位审查者各自在临时目录的副本里做变异。代码审查者报告: 会话的临时目录被两位审查者共用, 它的一份副本被对方的同名目录覆盖过,
  它把受影响的几次作废后在独立目录重做; 并提醒它往对方副本里写过几秒钟的旧版 `auth.py`, 对方那段时间的一次结果可能是假红。
  存活的变异两位审查者各自独立报告了同样的几个 (`198.18/15`、`240/4`、`192.0.0.0/24`、单元缺 `WantedBy`), 所以我没有在修之前自己复现, 直接补了断言;
  修之后这些变异都放进了变异脚本, 在工作区里跑出来是打红的 (N12–N15、U03)。
- 工作区在两位审查者结束后与审查开始时一致 (`git status --short` 只有本文件)。

收尾核对 (向 advisor 复核之后) 又改了几处, 都在最后一个提交里:

- 留档的审查提示词里有两处本机绝对路径 (含用户名), 换成了占位。**`9b7e0aa` 和 `5021cc3` 这两个提交的历史里仍有那两行**;
  仓库里别处早就有同样的路径 (9a8ad43 时已有 60 个文件含这个用户名), 不是新类别。协调方 2026-11-28 裁定合并时用 squash (集成备注第 11 条)。
- 隔离单元的 `ExecStop` 加了 `-` 前缀: 表已经不在时停 / 重启单元不该报失败 (演练的回退和「规则装不回去」的验证都会走到)。
- 巡检定时器从 `OnUnitActiveSec=60s` 改成 `OnCalendar=minutely`: 前者相对「上次激活」计时, 巡检以失败退出后可能不再触发 (依据是对 systemd 行为的记忆, 没有实测; 改成按墙上时钟后不依赖这一点)。
- 变异脚本改成记录预登记用例自己的第一条失败信息 (上一版 63 行里 55 行的失败信息是空的)。
- `docs/design/P2_request_context.md` §5 补了「恰好一条头」和 `FORWARDED_ALLOW_IPS`。
- **我写了主仓的文件 (非有意)。** 任务要求不写主仓。为了让依赖索引的那一条用例能跑, 我按 `docs/design/P2_request_context.md` §4「只读共享」的做法设了
  `SDTM_RAG_CHROMA_DIR_OVERRIDE` 指向主仓的 `data/chroma` 跑了两趟全量 pytest (代码审查者也跑了一趟)。事后发现主仓 `data/chroma/chroma.sqlite3`
  和两个 study 集合的向量段文件的修改时间变成了 08:14–08:15 —— chromadb 打开持久化库时自己会写。内容核对:
  `sqlite3 "file:<主仓>/data/chroma/chroma.sqlite3?mode=ro" "pragma integrity_check"` 返回 `ok`; 三个集合的条数是 4333 / 959 / 125,
  其中 `sdtm_kb_v1` 的 4333 与 `ingested_at_commit.txt` 的 `total_chunks` 一致 (另两个没有可对照的基准)。主仓的 git 状态不受影响 (那是被忽略的数据目录)。
  之后把索引复制进了本工作区被忽略的 `data/chroma`, 最后一趟全量是在这份副本上跑的。§4 那句「只读共享」我补了一段说明。
- 审查者留在系统临时目录里的仓库副本 (其中一份带着研究数据的副本) 已删除。

## 本步小结 (整个拆仓线的 retro 在 P4 写)

- **保留的做法**: 动手前只读查清虚拟机现状 (网段、防火墙后端、DNS 走向), 三处设计因此改了方向 (子网选 `10/8`、用独立 nft 表、不需要给 DNS 开例外);
  配置文件用虚拟机里的真工具做解析检查, 经标准输入传入、不落盘; 探测脚本要求对照侧可达才算数; 变异预登记应该打红的用例。
- **要补的缺口**: 这一步的大部分安全性质合并前验证不了, 只能靠演练。演练方案里每条命令的预期都写了, 但只有只读的那几条实跑过。
  初版漏了三处靠审查才发现的问题: input 链误伤回环 (会让例行核对永远过不了)、uvicorn 默认采信回环来的 `X-Forwarded-For`、整块粘贴会让 token 进历史。
- **关键决策**: 连接器独立成项目; 可信代理写进 compose 而不是 `.env`; 不做域名级出站白名单并如实写明; 不做应用侧的明文跳转;
  规则与 docker 之间不加硬依赖, 改用「巡检 + 重装 + 装不上就下线」。
