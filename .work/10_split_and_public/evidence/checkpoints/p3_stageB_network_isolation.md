# 公开腿演练阶段 B: 重建公开网络 + 装隔离规则 (隧道演练方案第 1–4 步, 2026-11-28)

方案 = `docs/plans/P3_4_tunnel_drill.md` 第 1–4 步 + `p3_public_leg_impl.md` §5「阶段 B」的容器对照。时间戳是 UTC (虚拟机日志是 JST = UTC+9)。
**结论: 四步的结果都与方案的预期一致, 没有触发任何停止条件, 没有做回退。** 做完后公开站是「已创建、未启动」, 不对外。

## 授权
主人 2026-11-28 在协调方的待办项上亲自选定 (**经待办项转达的选择**, 不是在本会话里说的):
- 问题:「可以在虚拟机里重建公开网络并装上隔离规则吗（公开站保持停止、不对外）？」
- 主人选的 (原话):「可以，现在做」。
- 问题的说明里写明会改三样: 停着的公开容器删掉、用同一个旧镜像重新创建且不启动; 公开网络删掉重建成固定网段 `10.201.8.0/24`; 新装一张防火墙表和每分钟巡检的定时器。也写明: 公开站不启动、不对外, 开关保持关闭, 不建隧道, 私有站不重启, 发现别的服务受影响就立刻停下来汇报。
- **只覆盖**演练方案第 1–4 步。第 5 步及之后 (部署公开实例、启动容器、连接器、隧道) 不在范围内, 这次都没有做。

## 起点
main = origin/main = `5e640a1`, 工作区干净。私有站线上镜像 `613f048…`。`$IMG` = `…/sdtm-rag:613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7` (虚拟机本地已有, 没有拉任何镜像)。`$OLD` = `099c2c930ec869e254b2e9052c3d4a6a85d6d539`。

## 预检 (全部只读; 03:50Z–03:54Z) —— 5 条都满足
| # | 项 | 结果 |
|---|---|---|
| 1 | 现状 = 方案第 1 步的预期 | 公开网络 `172.18.0.0/16 invalid Prefix 172.18.0.1 map[]`; 公开容器 `Exited (0)`, 镜像 `…:099c2c9…` (镜像 ID `sha256:3886799a…`); nft 只有 `ip nat` / `ip filter` / `ip6 nat` / `ip6 filter` / `ip raw`; `/etc/nftables.conf` 第一条语句 `flush ruleset`; `nftables.service` = `disabled` |
| 1 | 没有正在跑 / 排队的 Actions | 本仓最新运行是 23 号 (= 上一份 checkpoint 里的 run 217), 最近 3 次都是 `completed`; 虚拟机里没有 job 容器; 仓库变量 `[]`。动手前 (03:54Z) 和结束后 (04:01Z) 各查一次, 相同 |
| 2 | `-f -` 解析出的项目名 | `docker compose -f - config` 的 `name:` = `sdtm-rag-public`; 现有容器与现有网络的 `com.docker.compose.project` 标签都是 `sdtm-rag-public` (容器是早先用 `/tmp/p33/compose.public.yml` 建的) |
| 3 | 旧镜像在本地 | `docker image inspect …:099c2c9…` → `sha256:3886799a…` |
| 4 | 新 compose 渲染结果 | 子网 `10.201.8.0/24`、网关 `10.201.8.1`、`ip_range: 10.201.8.128/25`、`com.docker.network.bridge.name: br-sdtmpub`、`enable_ipv6: false`; `api` 服务没有 `ports` |
| 4 | 网段不重叠 | 18 个 docker 网络: `172.17`–`172.31` 各 `/16` + `192.168.16.0/20`; 虚拟机网卡 `192.168.5.15/24`、`192.168.64.2/24`; 虚拟机路由表与 mini 路由表里都没有 `10/8` 的条目; 没有 `/etc/docker/daemon.json`; 接口 `br-sdtmpub` 此前不存在; `/etc/sdtm-rag-public/` 与三个单元文件此前不存在 |
| 5 | 回退材料 | 旧镜像完整引用 `192.168.100.58/bojiang/sdtm-rag:099c2c930ec869e254b2e9052c3d4a6a85d6d539`; 旧 compose 文件 `git show 9a8ad43:deploy/container/compose.public.yml` 可取到 |

预检里与方案字面不同的一处 (不影响结论): 方案第 1 步最后一条命令的 `systemctl is-active ufw` 打印 **`active`**。这只是单元的状态 (`Type=oneshot`, `SubState=exited`, 开机启用); `sudo ufw status verbose` = `Status: inactive`, docker 5 张表里 0 条 ufw 链。与隧道 checkpoint 写的「ufw 没启用」一致。**建议把方案那条命令换成 `sudo ufw status`**, 否则下一个执行的人会以为 ufw 开着。

旧公开容器 (只取了挂载 / 端口 / 重启策略, 没有导出环境变量): 两个挂载 (公开 env 文件只读、公开数据根可写), 无端口, `unless-stopped`, 只在 `sdtm-rag-public` 网络。

动手前存的基线 (本机临时目录, 不进仓库): 全部 23 个容器的 `Id / 状态 / StartedAt / RestartCount`; docker 5 张表去掉计数器的全文; `p3_tunnel_leg_merge_snapshot.sh` 的快照 (公开数据根清单指纹 `57bde78cb564aa66`, 与上一份 checkpoint 相同)。

## 第 2 步: 重建公开网络 (03:54:33Z–03:54:43Z)
```
$ VM "IMAGE_TAG=$OLD docker compose -f - down" < $PUB
 Container sdtm-rag-public-api Removed / Network sdtm-rag-public Removed            rc=0
  → down 之后: 网络 0 个, 容器 0 个
$ VM "IMAGE_TAG=$OLD docker compose -f - up --no-start" < $PUB
 Network sdtm-rag-public Created / Container sdtm-rag-public-api Created            rc=0
$ docker network inspect …   → 10.201.8.0/24 10.201.8.128/25 10.201.8.1 v6=false map[com.docker.network.bridge.name:br-sdtmpub]
$ ip -4 -br addr show br-sdtmpub → br-sdtmpub       DOWN           10.201.8.1/24
$ docker ps -a …             → sdtm-rag-public-api Created
```
与预期逐项一致。新容器 Id `2a33f280…`, `status=created running=false started=0001-01-01T00:00:00Z`, 镜像仍是 `…:099c2c9…` (`sha256:3886799a…`), 无端口, `unless-stopped`, 只在 `sdtm-rag-public`, 项目 `sdtm-rag-public`。新网络 Id `eff48d9c…`, 0 个容器。
方案里写的「未核实: `down` 会不会保留网络」: 没有保留, 一次删净。

docker 自己的规则在这一步的变化 (去计数器后 t0 → t1 的 diff, 共 5 行, 都是同一处替换): `172.18.0.0/16` / `br-c01c0c882c0c` → `10.201.8.0/24` / `br-sdtmpub`。其余 228 行不变。私有站健康检查 200。

## 第 3 步: 隔离规则, 先红后绿
目标清单照方案: `LAN` 7 个、`NET` 3 个, 与 `.gitea/workflows/sdtm-rag.yml` 的 `ISOLATION_LAN` / `ISOLATION_EGRESS` 逐个相同 (脚本比过集合)。

### 3a / 3b: 规则没装 (03:55:00Z)
| 侧 | 源地址 | 7 个内网目标 | 3 个外网目标 |
|---|---|---|---|
| 对照: 虚拟机本机 (`control.json`) | `192.168.64.2` | 全部 `open` | — |
| 对照: 默认网桥容器 (`--cap-drop ALL --security-opt no-new-privileges --network bridge`, 同 `kbsync.isolation_check`) | `172.17.0.2` | 全部 `open` | — |
| 隔离侧: 公开网络里的一次性容器 (`before.json`) | `10.201.8.128` | 全部 `open` | 全部 `open` |

**3b 判定行** (`judge --isolated before.json --control control.json --isolated-net 10.201.8.0/24`, 退出码 1):
```
PASS          隔离侧源地址 10.201.8.128 在 10.201.8.0/24 里
FAIL          10.201.8.1:22: 隔离侧 open (能到达内网)          ← 7 个内网目标都是这一行的形状
PASS          api.anthropic.com:443 / api.openai.com:443 / region1.v2.argotunnel.com:7844: 外网可达
结论: FAIL
```
红得对: FAIL 的是 7 个内网目标, 外网都通, 源地址在公开网段里。没有哪个目标在装之前就是 `timeout`, 清单一个都不用去掉。

### 3c: 装规则 (03:55:24Z 落文件, 03:55:38Z 装入)
- `sudo nft -c -f -` rc=0 (无输出)。
- 落了 4 个文件, 落盘后的 sha256 与仓库里的逐个相同 (`isolation.nft` `4565d6f2…`、`…isolation.service` `67d7842f…`、`…watch.service` `b4fe1590…`、`…watch.timer` `d0b1922d…`)。
- `systemd-analyze verify` 三次都是 rc=0; 只打印了两行与这三个单元无关的系统自带告警 (`xfs_scrub_all.service` / `system-xfs_scrub.slice` 的 `CPUAccounting=` 已移除)。
- `daemon-reload` → `enable --now …isolation.service` (建了 `multi-user.target.wants/` 下的链接) → `enable --now …watch.timer` (建了 `timers.target.wants/` 下的链接), 都是 rc=0。
- 之后: `nft list tables` = docker 的 5 张 + `table inet sdtm_rag_public_isolation`; 隔离单元 `active` / `enabled`; 定时器 `enabled` / `active`, 在定时器列表里 (下一次 `12:56:00 JST`)。定时器一启用就立刻跑了一次 (开机已超过 20 秒, `OnBootSec` 条件当场满足), 之后实际触发时刻是每分钟的第 3–4 秒。
- **docker 5 张表**: 装之前 (`pre3c`) 与装之后 (`post3c`) 去计数器的全文 sha256 都是 `a294026f954c2d83`, `diff` 为空 (两次转储之间没有起过容器)。

### 3d: 规则已装 (03:55:51Z–03:56:19Z)
| 侧 | 源地址 | 7 个内网目标 | 3 个外网目标 |
|---|---|---|---|
| 隔离侧 (`after.json`) | `10.201.8.128` | 全部 `timeout` | 全部 `open` |
| 对照: 虚拟机本机 (`control_after.json`) | `192.168.64.2` | 全部 `open` (含 `10.201.8.1:22`) | — |
| 对照: 默认网桥容器 | `172.17.0.2` | 全部 `open` | — |

**3d 判定行** (`judge --isolated after.json --control control_after.json --before before.json --isolated-net 10.201.8.0/24`, 退出码 0):
```
PASS          隔离侧源地址 10.201.8.128 在 10.201.8.0/24 里
PASS          10.201.8.1:22: 隔离侧 timeout, 对照侧 open
PASS          172.22.0.1:22: 隔离侧 timeout, 对照侧 open
PASS          192.168.100.58:443: 隔离侧 timeout, 对照侧 open
PASS          192.168.5.15:22: 隔离侧 timeout, 对照侧 open
PASS          192.168.5.15:8000: 隔离侧 timeout, 对照侧 open
PASS          192.168.5.2:22: 隔离侧 timeout, 对照侧 open
PASS          192.168.64.1:22: 隔离侧 timeout, 对照侧 open
PASS          api.anthropic.com:443 / api.openai.com:443 / region1.v2.argotunnel.com:7844: 外网可达
结论: PASS
```
规则表 (探测结束后立刻看; 中间 03:56:03Z 巡检重装过一次, 计数器只含那之后的包):
```
table inet sdtm_rag_public_isolation {
	set blocked4 { type ipv4_addr; flags interval; elements = { 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16,
	               172.16.0.0/12, 192.0.0.0/24, 192.168.0.0/16, 198.18.0.0/15, 224.0.0.0/4, 240.0.0.0/4 } }
	chain forward { type filter hook forward priority filter - 10; policy accept;
		iifname "br-sdtmpub" oifname "br-sdtmpub" accept
		ip saddr 10.201.8.0/24 ip daddr 10.201.8.0/24 accept
		iifname "br-sdtmpub" ip daddr @blocked4 counter packets 12 bytes 720 drop
		ip saddr 10.201.8.0/24 ip daddr @blocked4 counter packets 0 bytes 0 drop
		iifname "br-sdtmpub" meta nfproto ipv6 counter packets 0 bytes 0 drop }
	chain input { type filter hook input priority filter - 10; policy accept;
		ct state established,related accept
		iifname "br-sdtmpub" counter packets 4 bytes 240 drop
		iifname != "lo" ip saddr 10.201.8.0/24 counter packets 0 bytes 0 drop }
}
```
按进入接口匹配的两条 `drop` 计数器不为零 (转发 12 个包、进虚拟机本机 4 个包)。按源地址兜底的两条和 IPv6 那条是 0: 包先被按接口的那条丢掉了, 兜底条没有机会命中 —— 这两条兜底规则和 IPv6 规则**这次没有被实际触发过**, 见「仍未验证」。

### 容器对照与 `ISOLATION_LAN` (阶段 B 加做)
按部署预检同款再判一次: 隔离侧也加 `--cap-drop ALL --security-opt no-new-privileges`, 对照 = 默认网桥容器, 不带 `--before`, 带 `--isolated-net` → 11 行全 PASS, **结论 PASS**, 退出码 0。
| 目标 (`ISOLATION_LAN` 逐项) | 默认网桥容器, 装前 | 默认网桥容器, 装后 | 公开网络, 装前 | 公开网络, 装后 (去 capability) |
|---|---|---|---|---|
| `10.201.8.1:22` | open | open | open | timeout |
| `192.168.5.15:22` | open | open | open | timeout |
| `192.168.5.15:8000` | open | open | open | timeout |
| `192.168.5.2:22` | open | open | open | timeout |
| `192.168.64.1:22` | open | open | open | timeout |
| `192.168.100.58:443` | open | open | open | timeout |
| `172.22.0.1:22` | open | open | open | timeout |

`ISOLATION_EGRESS` 三项在公开网络里装前、装后 (含去掉全部 capability 的容器) 都是 `open`。
**对 `ISOLATION_LAN` / `ISOLATION_EGRESS` 的结论: 不需要改。** 默认网桥上的容器连得上清单里的每一个内网目标, 没有会让部署预检判「无结论」的目标。workflow 文件没有动。
顺带确认了 `p3_public_leg_impl.md` §7 第 4 条里的两件事: 默认网桥上的对照容器连得上那批内网目标; 去掉全部 capability 的容器能解析域名并连上 Anthropic (TCP 443)。

### 3f: 巡检把规则装回来 (03:57:13Z–04:00:23Z)
```
$ sudo nft delete table inet sdtm_rag_public_isolation      rc=0, 表数 0          (03:57:13Z)
  … 等 90 秒 …
$ sudo nft list tables                                       → 5 张 docker 表 + table inet sdtm_rag_public_isolation
$ journalctl -u sdtm-rag-public-isolation-watch.service
  Nov 28 12:58:03 lima-deploy sh[3170685]: isolation table was missing
$ sudo nft flush table inet sdtm_rag_public_isolation        rc=0, 清空后 drop 条数 0   (03:58:52Z)
  … 等 90 秒 …
$ sudo nft list table inet sdtm_rag_public_isolation | grep -c drop   → 5
```
日志里 `reload failed` 0 次; 隔离单元 `active`, 巡检服务没有失败记录, `systemctl --failed` 为空。
规则不在位的时间: 删表后约 50 秒 (03:57:13Z → 03:58:03Z 装回); 清空后约 12 秒 (03:58:52Z → 按日志巡检在 03:59:04Z 重装, 这一次是从日志时刻推的, 我是 90 秒后才看的)。期间公开网络里没有任何容器。

### 3e: 别的服务没有被波及 (装完立刻跑了一遍 03:55:40Z 前后, 3f 之后又跑了一遍 04:00:37Z, 两遍结果相同)
| 项 | 结果 |
|---|---|
| 私有站网络里的容器连局域网 | `private network ok` |
| 私有站健康检查 (虚拟机内 `127.0.0.1:8000`) | `200`; 从 dev 机经局域网入口也是 `200`; 容器 `healthy` |
| 私有站容器没有被重启 | `sdtm-rag-api` StartedAt `2026-11-28T03:23:47.097798686Z`、`sdtm-rag-ui` `2026-11-28T03:23:57.678917638Z`, 重启次数 0, 镜像 `613f048…` —— 与动手前相同 |
| 全部 23 个容器 | `Id / 状态 / StartedAt / RestartCount` 清单与动手前的 diff 只有公开容器一行 (`1830f9e8… exited` → `2a33f280… created`); 带健康检查的 13 个都是 `healthy`; docker 守护进程启动时间仍是 2026-11-25 (没有重启) |
| Gitea | 虚拟机本机 `https://git.bojiang.org/api/v1/version` 有应答 (`403`: 这个接口不带凭据就是 403, dev 机不带凭据也是 403; 私有网络里的容器同样拿到 403); dev 机带凭据访问仓库接口 `200` |
| 镜像仓库 | 虚拟机本机 `https://192.168.100.58/v2/` → `401` (有应答, 要认证; 没有拉任何镜像) |
| docker 的 5 张 nft 表 | 都在; 去计数器全文 `pre3c` = `post3c` = `post3f` = 结束时 = `a294026f954c2d83`, 三次 `diff` 都为空 |
| `nftables.service` | `disabled` |

## 第 4 步: 静态地址和动态地址段 (04:00:54Z)
```
$ docker run --rm --network sdtm-rag-public --entrypoint python $IMG -c "…gethostbyname(gethostname())"                  → 10.201.8.128
$ docker run --rm --network sdtm-rag-public --ip 10.201.8.2 --entrypoint python $IMG -c "…"                              → 10.201.8.2
```
动态地址落在 `.128`–`.255`; 静态地址在动态段之外可以指定。方案里记的那条剩余风险照旧成立: 连接器没在跑时, 能操作 docker 的人可以起一个占用 `10.201.8.2` 的容器。

## 结束状态 (04:01:10Z–04:01:51Z)
- 又跑了一遍隔离侧 + 两种对照 + `judge` (例行核对的写法, 不带 `--before`): 11 行全 PASS, **结论 PASS** (两种对照都是)。
- `watch.timer` `active` / `enabled`; 隔离单元 `active` / `enabled`; `nftables.service` `disabled`; 隔离表里 5 条 `drop`。
- 快照 (`p3_tunnel_leg_merge_snapshot.sh`) 与动手前的 diff 只有三处: 公开容器 (Id、`Exited` → `Created`、启动 / 结束时间归零), 公开网络 (Id、子网 `172.18.0.0/16` → `10.201.8.0/24`), 隔离规则表数 0 → 1。私有容器、私有数据根各行不变; **公开数据根的清单指纹不变** (`57bde78cb564aa66`, 9 个文件)。
- 没有残留的一次性容器 (容器总数仍是 23, 非运行状态的只有 `sdtm-rag-public-api Created`); 网络总数仍是 18; 没有连接器容器。
- 公开网络里 0 个在运行的容器; 默认网桥 `docker0` 在对照容器退出后回到没有容器的状态。
- 仓库变量仍是 `[]`; 没有新的 Actions 运行 (最新仍是 23 号)。

## 虚拟机里新增 / 变更的东西 (完整清单)
| 类别 | 内容 |
|---|---|
| 删除 | 容器 `sdtm-rag-public-api` (Id `1830f9e8…`, 已停止); docker 网络 `sdtm-rag-public` (Id `c01c0c88…`, `172.18.0.0/16`, 网桥 `br-c01c0c882c0c`) |
| 新建 (docker) | 网络 `sdtm-rag-public` (Id `eff48d9c…`, `10.201.8.0/24`, 网桥 `br-sdtmpub`); 容器 `sdtm-rag-public-api` (Id `2a33f280…`, 镜像 `…:099c2c9…`, **Created, 从未启动**) |
| 新建 (文件, 都是 `root:root 644`) | `/etc/sdtm-rag-public/` (目录 755) 及其中的 `isolation.nft`; `/etc/systemd/system/sdtm-rag-public-isolation.service`、`…-isolation-watch.service`、`…-isolation-watch.timer` |
| 新建 (启用链接) | `/etc/systemd/system/multi-user.target.wants/sdtm-rag-public-isolation.service`; `/etc/systemd/system/timers.target.wants/sdtm-rag-public-isolation-watch.timer` |
| 新建 (内核) | nft 表 `inet sdtm_rag_public_isolation` (2 条基链, 钩子优先级 -10) |
| 在跑的新东西 | 巡检定时器每分钟触发一次 `…watch.service` (每次把规则文件整份重装; 日志在 `journalctl -u sdtm-rag-public-isolation-watch.service`, 每分钟 3 行) |
| docker 自己的规则 | 5 行里的网段 / 网桥名随网络重建而换 (见第 2 步), 是 docker 自己改的 |
| 用过即删 | 12 个一次性容器 (`--rm`; 探测、对照、3e、第 4 步), 都用 `$IMG`, 不挂数据、不带 env 文件 |

没有碰: 私有站容器与数据根、公开数据根里的文件、`/opt/sdtm-rag-public/` (没有读 `.env`)、Gitea 变量、任何 workflow、Cloudflare; 没有启动公开容器; 没有重启虚拟机或 docker。

## 回退办法 (这次没有用到)
1. 撤掉隔离规则 (**先停巡检**, 否则一分钟内被装回; 只在公开实例和连接器都停着时做):
   `VM "sudo systemctl disable --now sdtm-rag-public-isolation-watch.timer"` → `VM "sudo systemctl disable --now sdtm-rag-public-isolation.service"` (停单元时删表) →
   删 `/etc/systemd/system/sdtm-rag-public-isolation*` 和 `/etc/sdtm-rag-public/` → `VM "sudo systemctl daemon-reload"`。
2. 撤掉固定子网: `VM "IMAGE_TAG=099c2c930ec869e254b2e9052c3d4a6a85d6d539 docker compose -f - down" < deploy/container/compose.public.yml`, 再
   `git show 9a8ad43:deploy/container/compose.public.yml | VM "IMAGE_TAG=099c2c930ec869e254b2e9052c3d4a6a85d6d539 docker compose -f - up --no-start"`。
   回退后网络回到自动网段和随机网桥名, 隔离规则的两个匹配条件都对不上且不报错: 公开实例必须保持停止, 不能接隧道。
3. 回不到的: 旧容器的 Id 和它的启动 / 结束时间记录 (新容器从未启动过); 旧网络当时自动分到的 `172.18.0.0/16` 不保证再分到同一段。

## 仍未验证的事项
1. **开机时规则先于容器装入**: 没有重启虚拟机。留到下一次计划内的重启, 重启后立刻重跑 3a 和 3d。
2. **从未启动过的容器在 `restart: unless-stopped` 下, 虚拟机或 docker 重启后是否仍不启动** (`p3_public_leg_impl.md` §7 第 3 条): 现在的公开容器正是这个状态, 同样要等下一次重启后看 `docker inspect -f '{{.State.Status}}' sdtm-rag-public-api`。**在那之前如果虚拟机意外重启, 要先看这一条** —— 它要是被拉起来了, 就是旧镜像 `099c2c9` 在公开网络里运行 (没有入口, 受隔离规则约束, 但不是预期状态)。
3. **规则里没有被实际触发的三条**: 按源地址兜底的两条 (转发、进本机) 和 IPv6 那条, 计数器都是 0。它们只在网桥名没固定住 / 有 IPv6 包时才起作用, 这次的探测触发不到。
4. 探测只做 TCP 连接, 而且只有这 7 个内网目标。UDP、ICMP、IPv6、清单以外的内网地址 (例如 mini 的 `192.168.2.x` / `192.168.3.x`、别的 compose 网络里的容器地址) 没有逐个探测, 依据是规则按整个私有网段丢弃。
5. 同一网络内 (连接器 → 公开实例) 的通路: 这时没有两个同时在跑的容器, 没有验 (方案第 6 步)。`br_netfilter` 没有加载 (`lsmod` 0 行), 与规则文件注释里的前提一致。
6. 巡检「连续两次装不回去就停连接器」这条分支没有验 (方案第 6 步的可选项, 需要连接器)。巡检每分钟重装对已有连接有没有影响也没有验 (这时没有长连接)。
7. 别的服务: 依据是全部容器的启动时间 / 重启次数 / 健康状态不变、docker 5 张表不变、私有站的三项探测。没有逐个服务做功能测试。
8. **没有独立审查**: 派单要求不起子代理, 这份记录是执行者自己写的 (规则 D 的缺口, 需要的话由协调方另派)。
9. 隧道 checkpoint「网络隔离做到了哪一步」列的剩余风险都还在: 不是出站白名单 (公网全放)、DNS 走宿主解析器、公开实例以 root 运行等。这次只证明了「私有地址连不上」这一半。
10. 第 5 步及之后的全部内容。

## 需要协调方处理的文档 (这次没有改)
- `deploy/README.md`「公开实例与隧道」开头的状态说明写着「虚拟机里的网络还是旧的自动网段, 隔离规则没有装」, 已经过时。没有改: 那一段写的是「上线后改掉」, 而且这次的派单只让更新进度文件。
- `docs/plans/P3_4_tunnel_drill.md` 开头写「全部未执行」, 第 1–4 步现在已执行; 第 1 步那条 `systemctl is-active ufw` 建议换成 `sudo ufw status` (见预检)。
- `p3_public_leg_impl.md` §5 阶段 C 的只读核对里写「公开容器的状态与镜像 (隧道第 2 步重建网络时容器可能被重建过)」: 现在的实际情况是 `Created`、镜像仍是 `…:099c2c9…`, kb-sync 公开腿选基线镜像时读到的还是这个镜像。

## 小结 (规则 C)
- **保留下来的做法**: 动手前把「要停下来的条件」逐条做成只读预检 (项目名、旧镜像在不在、网段重叠); 每个会改东西的命令单独一次调用, 中间看结果; 判定之前先数探测 JSON 的键数; 「别的服务没受影响」用动手前后的机械 diff (全部容器的启动时间、docker 规则表去计数器全文、线上快照) 而不是只看一个健康检查; 3e 在装完规则的第一时间就跑, 不等到最后; 结束前再跑一遍探测, 让留下的状态有证据。
- **必须补上的缺口**: (1) 方案的「预期」对 `is-active ufw` 这一行没有写预期值, 实际输出 `active` 乍看像是 ufw 开着, 要另查 `ufw status` 才能排除 —— 方案里的每条只读命令都应该写明预期输出。(2) 规则表里有三条规则这次的探测触发不到, 「PASS」只覆盖了按接口匹配的那两条。(3) 两条依赖重启的事项 (规则的开机顺序、从未启动的容器是否保持不启动) 还挂着, 没有排期。
- **关键决策复盘**: 容器对照在装规则前后各跑一遍, 并且按 `kbsync.isolation_check` 的原样参数 (去 capability) 再判一次, 所以对 `ISOLATION_LAN` 的结论是按部署预检实际会走的路径得出的, 不是从虚拟机本机的对照推出来的。

## 复跑命令 (只读部分可随时重跑; 第 2 步、3c、3f 会改虚拟机, 需要主人同意)
```sh
cd <本仓根>
VM() { ssh bojiang.local "export PATH=/opt/homebrew/bin:\$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- $*"; }
VMS() { ssh bojiang.local 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- bash -s'; }
PUB=deploy/container/compose.public.yml; OUT=<本机临时目录>
IMG=192.168.100.58/bojiang/sdtm-rag:613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7; OLD=099c2c930ec869e254b2e9052c3d4a6a85d6d539
LAN="--lan 10.201.8.1:22 --lan 192.168.5.15:22 --lan 192.168.5.15:8000 --lan 192.168.5.2:22 --lan 192.168.64.1:22 --lan 192.168.100.58:443 --lan 172.22.0.1:22"
NET="--egress api.anthropic.com:443 --egress api.openai.com:443 --egress region1.v2.argotunnel.com:7844"
# 预检 (只读)
VM "IMAGE_TAG=$OLD docker compose -f - config" < $PUB                      # name / 子网 / 网桥名 / 无 ports
VM "docker inspect sdtm-rag-public-api --format '{{index .Config.Labels \"com.docker.compose.project\"}}'"
VM "docker image inspect 192.168.100.58/bojiang/sdtm-rag:$OLD --format '{{.Id}}'"
VM "sh -c 'for n in \$(docker network ls --format {{.Name}}); do echo \"\$n \$(docker network inspect \$n --format \"{{range .IPAM.Config}}{{.Subnet}} {{end}}\")\"; done'"; VM "ip -4 route"; ssh bojiang.local 'netstat -rn -f inet'
VM "sudo ufw status verbose"
# 机械 diff 用的两份清单 (动手前、每个阶段后各存一份再 diff)
echo "sudo docker ps -a --format '{{.Names}}' | sort | while read n; do sudo docker inspect \"\$n\" --format '{{.Name}} {{.Id}} {{.State.Status}} {{.State.StartedAt}} restarts={{.RestartCount}}'; done" | VMS > $OUT/started.txt
echo "for t in 'ip nat' 'ip filter' 'ip6 nat' 'ip6 filter' 'ip raw'; do echo \"#### \$t\"; sudo nft list table \$t 2>/dev/null | sed -E 's/counter packets [0-9]+ bytes [0-9]+/counter/g'; done" | VMS > $OUT/nft_docker.txt
VMS < .work/10_split_and_public/evidence/checkpoints/p3_tunnel_leg_merge_snapshot.sh > $OUT/snap.txt
# 第 2–4 步: 命令与 docs/plans/P3_4_tunnel_drill.md 逐字相同 (3f 的 sleep 90 写成 VM "sleep 90")
# 例行核对 (只读; 结论必须是 PASS)
VM "docker run --rm -i --network sdtm-rag-public --entrypoint python $IMG - probe $LAN $NET" < deploy/public-net/isolation_probe.py > $OUT/iso.json
VM "python3 - probe $LAN" < deploy/public-net/isolation_probe.py > $OUT/ctl.json
VM "docker run --rm -i --cap-drop ALL --security-opt no-new-privileges --network bridge --entrypoint python $IMG - probe $LAN" < deploy/public-net/isolation_probe.py > $OUT/ctl_bridge.json
python3 deploy/public-net/isolation_probe.py judge --isolated $OUT/iso.json --control $OUT/ctl.json --isolated-net 10.201.8.0/24
python3 deploy/public-net/isolation_probe.py judge --isolated $OUT/iso.json --control $OUT/ctl_bridge.json --isolated-net 10.201.8.0/24
VM "sh -c 'systemctl is-active sdtm-rag-public-isolation-watch.timer; systemctl is-enabled sdtm-rag-public-isolation-watch.timer; systemctl is-enabled nftables.service'"
VM "sudo nft list table inet sdtm_rag_public_isolation"; VM "journalctl -u sdtm-rag-public-isolation-watch.service --since -1d --no-pager"
VM "docker inspect sdtm-rag-public-api --format '{{.State.Status}} {{.State.StartedAt}} {{.Config.Image}}'"     # created 0001-01-01T00:00:00Z …:099c2c9…
```
