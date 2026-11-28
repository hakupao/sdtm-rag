# P3.4 隧道配置 — 审查提示词 (2026-11-28)

writer = 本会话 (orca worker, 主循环)。两位审查者用不同的 subagent 类型 (规则 D), 各自独立, 只读。
提示词里只给改动范围、要求和观测到的环境事实, 不给 writer 的结论。下面是实际发出的文本 (只把本机绝对路径换成了尖括号里的占位: 工作区位置、主仓的 data/chroma)。
两份审查的结论与逐条处理见 `evidence/checkpoints/p3_step3.4_tunnel.md`「审查」一节。

## 1. 代码审查 — `oh-my-claudecode:code-reviewer` (opus)

```
你是独立代码审查者。只读: 不要修改、暂存或提交任何文件, 不要 push, 不要连接任何远程主机 (不要 ssh)。全程用中文汇报。

仓库: <本工作区的绝对路径> (git worktree, 分支 hakupao/public-tunnel)。
审查范围: `git diff 9a8ad43..9b7e0aa` 的全部改动 (先 `git log --oneline 9a8ad43..9b7e0aa` 和 `git diff --stat 9a8ad43..9b7e0aa`)。
工作区里另有一个未提交的草稿 `.work/10_split_and_public/evidence/checkpoints/p3_step3.4_tunnel.md` (里面有 `__占位__`), 不在本次范围, 不要动它。
先读 CLAUDE.md 与 docs/RULES.md (规则 5 / 6: 变异验证、闸失效的成因分类), 再读改动。
跑测试用: `.venv/bin/python -m pytest <文件> -q -o addopts="" -p no:cacheprovider` (需要全量且要索引时: 先 `export SDTM_RAG_CHROMA_DIR_OVERRIDE=<主仓的 data/chroma>`, 那个目录只读使用)。

这批改动要实现的东西 (需求, 不是结论):
- 公开实例 (SDTM_RAG_INSTANCE=public) 接到 Cloudflare 隧道后面: 连接器 cloudflared 作为容器与公开实例在同一个 docker 网络,
  公开实例不发布宿主端口; 网络定固定子网, 连接器定静态地址; 公开实例只信连接器这一个地址带来的 CF-Connecting-IP。
- 隧道 token 是秘密: 只放在虚拟机的一个文件里, 不进仓库、日志、compose 解析结果。
- HTTPS: 公开档的 cookie 加 Secure, 公开档的响应加 HSTS 头。只在公开档生效, 私有档 (局域网 HTTP) 行为必须一个字节不变。
- 网络隔离: 公开容器和连接器不能访问局域网 / 宿主 / 同机其他容器。
- 公开实例的 compose 定义要保持「可以被照着另起一个不接隧道的副本」(另一条线的临时验收容器会读它)。
- 冻结的名字不许改: 容器名 sdtm-rag-public-api、网络名 sdtm-rag-public、数据根 /Volumes/DevSSD/deploy-data/sdtm-rag-public/data、
  env 文件 /opt/sdtm-rag-public/.env、端口 8000。
- 不许改: .gitea/workflows/**、deploy/kbsync/**、tests/test_deploy_public_compose.py (除非旧断言必须改)、检索 / 答题逻辑。

请你独立核对, 不要采信文档或注释里的说法:
1. 正确性与回归: server/auth.py 的改动对私有档是否真的零行为变化? 对公开档有没有打破现有用法 (现有测试、公开实例现有 .env 的键见
   .work/10_split_and_public/evidence/checkpoints/p3_step3.3.md)? 中间件顺序、SSE 流式是否受影响?
2. 测试是否真的在测: 跑相关测试; 自己挑几处做变异 (改坏实现, 看测试是否变红, 并看红的原因对不对), 尤其找「改坏了仍然绿」的地方。
   变异后务必用保存的原始字节还原, 不要用 git checkout; 做完用 `git status --short` 和 `git diff --stat` 确认工作区与开始时一致。
   已有的变异脚本在 .work/10_split_and_public/evidence/checkpoints/p3_step3.4_mutations.py —— 审它的方法有没有漏洞, 也可以补它没覆盖的变异。
   注意: 另一位审查者可能同时在这个工作区里做变异。你的变异尽量在系统临时目录的仓库副本里做 (用 `cp -R` 复制需要的目录), 或者每次变异只持续一次测试运行并立刻还原。
3. 配置文件: deploy/container/compose.public.yml、compose.tunnel.yml、deploy/public-net/* 的语法与语义 (compose 规范、nft 语法、systemd 单元),
   同一事实在多处的写法是否一致, 有没有改一处漏一处的可能没被测试钉住。
4. 自我描述与事实是否脱钩: 新增 / 改写的 docstring、注释、文档 (deploy/README.md 新节、docs/plans/P3_4_tunnel_*.md、
   docs/design/P2_request_context.md §5) 里的每个可核对的说法, 与代码 / 配置是否一致; 文档里的命令引号写法能不能跑 (不要真去连远程主机, 读代码推演即可)。
5. 项目规矩: 红线 (真实研究 OID / label / 真名不进 git)、「实测」附命令、新文档位置、仓根不放文档、提交信息里没有秘密。

输出: 结论 (PASS / PASS-with-fixes / FAIL) + 按严重度排序的发现 (每条: 文件与位置、问题、为什么是问题、建议怎么改、你怎么验证的)。
你做过的变异列成表 (改了什么、哪条测试红了 / 没红、失败信息)。没发现问题的方面也说一句你查了什么。
```

## 2. 安全审查 — `oh-my-claudecode:security-reviewer` (opus)

```
你是独立安全审查者。只读: 不要修改、暂存或提交任何文件, 不要 push, 不要连接任何远程主机 (不要 ssh), 不要调用任何外部服务的接口。全程用中文汇报。

仓库: <本工作区的绝对路径> (git worktree, 分支 hakupao/public-tunnel)。
审查范围: `git diff 9a8ad43..9b7e0aa`。工作区里另有一个未提交的草稿 `.work/10_split_and_public/evidence/checkpoints/p3_step3.4_tunnel.md`
(里面有 `__占位__`), 你可以读它里面「网络隔离做到了哪一步 / 剩余风险 / 集成备注」几节来核对陈述是否如实, 但不要改它。
先读 CLAUDE.md、docs/RULES.md, 再读改动和它涉及的现有代码 (server/auth.py 全文、server/quota.py 的 cfg / validate、
server/instance.py、server/config.py 开头、deploy/container/compose*.yml、deploy/public-net/*)。

背景: 公开站 (SDTM_RAG_INSTANCE=public) 将经 Cloudflare 隧道对外。访客 → Cloudflare → cloudflared 容器 → 公开实例容器 (HTTP, 端口 8000)。
两者在同一台 Lima 虚拟机的 docker 里; 同机还有私有站、Gitea、镜像仓库等。访客身份 = 签名 cookie + CF-Connecting-IP; 按访客和按 IP 有免费额度与限速。

只读观测到的环境事实 (2026-11-28, 不是结论):
- 虚拟机 Ubuntu 26.04, 内核 7.0; Docker 29.9.2, FirewallBackend=iptables (iptables v1.8.11 nf_tables 变体), 开着 userland proxy;
  Compose v5.7.0; 没有 /etc/docker/daemon.json。
- nft 现有表: ip nat / ip filter / ip6 nat / ip6 filter / ip raw (都是 docker 的)。FORWARD 策略 DROP, 先跳 DOCKER-USER (空) 再跳 DOCKER-FORWARD; INPUT 策略 ACCEPT。
  ufw 未启用; nftables.service 未启用。br_netfilter 模块未加载。
- 虚拟机地址: eth0 192.168.5.15/24 (Lima 用户态网络, 网关 192.168.5.2 通到 mini 宿主), lima0 192.168.64.2/24 (网关 192.168.64.1 = mini)。
  局域网 192.168.100.0/24 (镜像仓库 / Gitea 在 192.168.100.58)。docker 网络占用 172.17–172.31 各 /16 与 192.168.16.0/20。
- 用户自定义网络里容器的 /etc/resolv.conf: nameserver 127.0.0.11, 注释 `ExtServers: [host(127.0.0.53)]`。
- 虚拟机本机监听: 22 (ssh)、8000 (私有站) 以及同机其他服务由 docker 发布的若干端口, 都绑 0.0.0.0。
- 公开实例镜像以 root 运行, 没有去 capability。cloudflared 官方镜像 distroless, USER 65532:65532。

重点 (每一项都请尝试构造攻击路径, 不要只复述设计意图):
1. 可信代理能否被伪造: 谁能让公开实例把一个伪造的 CF-Connecting-IP 当成访客 IP? 考虑: 同网络的其他容器、公开实例自己、
   以后加进这个网络的容器、临时验收容器、IPv6 / IPv4 映射地址、头部重复或大小写、请求走私、X-Forwarded-For、.env 与 compose 的优先级
   (含大小写变体、load_dotenv 行为)、Cloudflare 侧 (Workers、其他租户、Managed Transforms)。静态地址能否被别的容器抢占?
2. cookie 的 Secure 和 HSTS 是否只在公开档生效、在公开档是否无法被配置绕过; 私有档是否真的没有任何行为变化。HSTS 的取值是否合适。
3. 网络隔离 (deploy/public-net/isolation.nft + systemd 单元): 从公开网络里的容器出发, 逐条想能不能到达: 局域网主机、mini 宿主、
   虚拟机本机服务、同机其他容器 (直连 / 经虚拟机地址上的发布端口 / 经 docker-proxy)、IPv6 路径、组播 / 广播、DNS。
   考虑钩子顺序 (DNAT 在 prerouting, forward 在其后)、基链优先级与 docker 规则的关系、伪造源地址、原始套接字、ARP、ICMP、
   「同网络放行」两条规则会不会被滥用、规则没装上 / 网桥名或网段对不上 / 开机顺序时的失效方向。规则会不会误伤同机其他服务或 docker 自身。
   探测脚本 deploy/public-net/isolation_probe.py 的判定会不会给出假的 PASS。
4. token 会不会泄漏: compose 解析结果、docker inspect、进程参数、日志、文件权限与属主、挂载方式、备份 / 镜像、文档里的操作步骤
   (docs/plans/P3_4_tunnel_owner_steps.md 第 2 步的输入方式) 有没有让 token 落进历史 / 屏幕 / 剪贴板之外的地方。镜像钉版本的方式是否可靠。
5. 文档 (docs/plans/P3_4_tunnel_owner_steps.md、P3_4_tunnel_drill.md、checkpoint 草稿) 里对「做到了什么 / 没做到什么 / 剩余风险」的陈述
   有没有夸大、遗漏, 操作顺序里有没有「先对外后设防」的窗口, 回退步骤会不会留下更危险的状态。

你可以跑测试、写一次性脚本做实验 (放在系统临时目录, 不要放进仓库)。另一位审查者可能同时在这个工作区里做变异: 你如果要做变异,
请在系统临时目录的副本里做 (用 `cp -R` 复制需要的目录), 不要改工作区里的文件。做完用 `git status --short` 确认工作区里没有你留下的东西。

输出: 结论 (PASS / PASS-with-fixes / FAIL) + 按严重度 (CRITICAL / HIGH / MEDIUM / LOW) 排序的发现, 每条写清: 攻击路径或失效方式、前提条件、
影响、证据 (文件位置 / 你跑的命令与输出)、建议。明确区分「代码 / 配置里的缺陷」「文档没如实写的风险」「合并前无法验证、需进演练的点」。
```
