# 公开站隧道与网络隔离：合并后的演练方案

> 写于 2026-11-28。**第 1–4 步已于 2026-11-28 执行**，结果都与预期一致，记录在
> `.work/10_split_and_public/evidence/checkpoints/p3_stageB_network_isolation.md`。
> **第 5 步已于 2026-11-28 做完**（含 5a、5b）：第一次部署（run id 219）在「临时容器验收」失败（没有网络的临时容器里，公开档的启动自检
> 给免费模型定不了价；`.work/10_split_and_public/evidence/checkpoints/p3_stageDE_first_public_deploy.md`）；把价格固定进代码之后第二次
> （run id 221）成功，部署后公开容器是「已更新、保持停止」，人工 `docker start sdtm-rag-public-api` 之后做了第 5 步的只读核对、5a、5b
> 和一次隔离复核，结果都与预期一致，记录在 `.work/10_split_and_public/evidence/checkpoints/p3_stageDE_second_attempt.md`。
> 现在公开实例运行中、没有入口（没有连接器、没有 token、没有隧道），env 文件里那行旧的可信代理设置已经删掉。**第 6 步起未执行**。
> 所以第 1 步「预期」里写的是执行之前的现状，现在的现状见该步末尾的补充。
> 每一步都会动虚拟机，执行前由协调方取得主人同意。
> 主人在 Cloudflare 后台做的部分见 `docs/plans/P3_4_tunnel_owner_steps.md`（下称「操作说明」）。
> 配置文件一律经标准输入传给虚拟机里的命令，虚拟机上不落 compose 文件。
>
> 主人 2026-11-28 在待办项上选定的三件事（经协调方转达）已经排进步骤里：首次上线先只放行主人本人，验收全部通过后才放开（第 7–9 步）；
> 限流两层都加（应用里的一层在第 5 步核对，Cloudflare 的一层由主人在第 7 步建，第 8 步实际触发）；
> 删掉公开站 env 文件里那行旧的可信代理设置（第 5 步的 5b）。

## 约定

```bash
# 本机 → 虚拟机里执行一条命令 (进入方式同 p3_step3.1_capacity.md)
VM() { ssh bojiang.local "export PATH=/opt/homebrew/bin:\$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy -- $*"; }
PUB=deploy/container/compose.public.yml
TUN=deploy/container/compose.tunnel.yml
IMG=192.168.100.58/bojiang/sdtm-rag:<要部署的 40 位 commit SHA>
OUT=<本机的一个临时目录>      # 探测结果只放本机, 不进仓库
```

每一步列出：做什么、预期、做完后公开站的状态、回退。任何一步的结果与预期不符就停下，不往后做。

写 `VM "…"` 时注意：引号里的分号、`&&`、管道如果不在更内层的引号里，会被 mini 的 shell 拆开，后半段就在 mini 上执行了。
要在虚拟机里连着执行几条命令，写成 `VM "sh -c '…; …'"`；多行的 Python 用 `VM "… python -" <<'PY'` 从标准输入送进去。
这几种写法 2026-11-28 用下面的只读命令试过，输出依次是 `Linux` / `b`、`ok lima-deploy`、`heredoc ok Linux`、`Host: a` / `CF-Visitor: c`：

```bash
VM "sh -c 'uname -s; echo b | grep --line-buffered \"^b\"'"
VM "python3 -c \"import socket; print('ok', socket.gethostname())\""
VM "python3 -" <<'PY'
import platform
for (k,) in [("x",)]:
    print("heredoc ok", platform.system())
PY
VM "sh -c 'printf \"Host: a\nfoo: b\nCF-Visitor: c\n\" | grep -a -i -E --line-buffered \"^(host|x-forwarded-proto|x-forwarded-for|cf-connecting-ip|cf-visitor):\"'"
```

## 顺序总览

| 步 | 内容 | 做完后公开站 |
|----|------|--------------|
| 0 | 合并前后的注意事项 | 未启动 |
| 1 | 只读记录现状 | 未启动 |
| 2 | 重建公开网络（固定子网） | 已创建、未启动 |
| 3 | 装隔离规则，先证明不装时能连内网，再证明装了连不上 | 已创建、未启动 |
| 4 | 核对静态地址和动态地址段 | 已创建、未启动 |
| 5 | 部署公开实例（临时容器验收 → 换正式容器，另一条线的流程）；核对全局限流；删 env 文件里的旧行 | 运行中，没有入口 |
| 6 | 启动连接器（需要主人已放好 token） | 运行中，连接器在线，没有路由 |
| 7 | 主人在后台建限速规则、访问限制，然后加路由 | 经隧道可达，**只有主人能进** |
| 8 | 隧道这一层的验收（访客 IP、伪造、两层限流） | 只有主人能进 |
| 9 | 全部通过后放开；之后每次部署和重启后的例行核对 | **对所有人开放** |

## 第 0 步：合并前后的注意事项

- `deploy/container/**` 在部署 workflow 的路径过滤里，`server/**` 也在：这条线的提交 push 到 main 会触发**私有站**重新构建和部署。
  私有站的行为没有变化（私有 compose 未改；私有档的 cookie 和响应头由测试逐项核对），但部署本身会发生，按「部署」的常规做法先验测试端口。
- 第 2 步（重建网络）必须在打开仓库变量 `SDTM_RAG_PUBLIC_DEPLOY` **之前**完成。
  否则部署 job 会拿新的 compose 文件去对一个网段不同的已有网络执行 `up`，结果未核实（可能报错，也可能尝试重建）。
- 这条线没有改 workflow。需要 workflow 配合的地方列在 checkpoint 的「集成备注」里。

## 第 1 步：只读记录现状

```bash
VM "docker network inspect sdtm-rag-public --format '{{range .IPAM.Config}}{{.Subnet}} {{.IPRange}} {{.Gateway}}{{end}} {{.Options}}'"
VM "docker ps -a --filter name=sdtm-rag-public --format '{{.Names}} {{.Status}} {{.Image}}'"
VM "sudo nft list tables"
VM "sh -c 'grep -v \"^#\" /etc/nftables.conf | head -3; systemctl is-enabled nftables.service'"
VM "sudo ufw status"
```

最后两条看系统自带的防火墙配置：2026-11-28 查到 `/etc/nftables.conf` 的第一条语句是 `flush ruleset`，`nftables.service` 是 `disabled`。
它必须保持 `disabled`：一旦被启用，它会清空整个规则集，docker 的规则和隔离表一起消失（隔离表一分钟内会被巡检装回，docker 的不会）。
`sudo ufw status` 的预期是 `Status: inactive`（2026-11-28 实测；docker 的 5 张表里也没有 ufw 的链）。
不要用 `systemctl is-active ufw` 来看：它打印的是 `active`，那只是 systemd 单元的状态（开机时执行一次就退出的单元），
不代表防火墙开着——这条方案原先写的就是它，执行时被它误导过一次，所以换掉。

预期（2026-11-28 查到的）：网段 `172.18.0.0/16`（自动分配，没有地址段，那一栏显示 `invalid Prefix`），选项为空；公开容器 `Exited`，镜像是 `099c2c9…`；nft 只有 docker 的 5 张表
（`ip nat`、`ip filter`、`ip6 nat`、`ip6 filter`、`ip raw`）。把看到的镜像 SHA 记下来，回退要用。

第 1–4 步执行之后（2026-11-28）再跑这几条，看到的是：网段 `10.201.8.0/24`、地址段 `10.201.8.128/25`、网关 `10.201.8.1`，
选项里有 `com.docker.network.bridge.name:br-sdtmpub`；公开容器 `Created`（从未启动），镜像仍是 `099c2c9…`；
nft 是 docker 的 5 张表加 `inet sdtm_rag_public_isolation`；`nftables.service` 仍是 `disabled`，`ufw` 仍是 inactive。

第 5 步执行之后（2026-11-28）：公开容器 `Up`（`healthy`），镜像是与私有站相同的 `66cb55d…`；其余不变。

## 第 2 步：重建公开网络

现有网络是早先试跑时自动建的，没有固定子网。改成固定子网必须删掉重建。公开容器现在是停着的，没有入口，重建期间对外没有影响。

```bash
OLD=<第 1 步记下的镜像 SHA>
# 删掉已停止的容器和旧网络 (数据在宿主目录里, 不受影响)
VM "IMAGE_TAG=$OLD docker compose -f - down" < $PUB
# 用新定义建网络, 容器只创建不启动
VM "IMAGE_TAG=$OLD docker compose -f - up --no-start" < $PUB
VM "docker network inspect sdtm-rag-public --format '{{range .IPAM.Config}}{{.Subnet}} {{.IPRange}} {{.Gateway}}{{end}} v6={{.EnableIPv6}} {{.Options}}'"
VM "ip -4 -br addr show br-sdtmpub"
VM "docker ps -a --filter name=sdtm-rag-public-api --format '{{.Names}} {{.Status}}'"
```

预期：`10.201.8.0/24 10.201.8.128/25 10.201.8.1 v6=false`，选项里有 `com.docker.network.bridge.name:br-sdtmpub`；
接口 `br-sdtmpub` 的地址是 `10.201.8.1/24`；容器状态 `Created`。

- 公开站状态：已创建、未启动（和之前一样没有入口；区别只是状态从 `Exited` 变成 `Created`）。
- 回退：再执行一次 `down`，然后用改动前的 compose 文件重建：
  `git show 9a8ad43:deploy/container/compose.public.yml | VM "IMAGE_TAG=$OLD docker compose -f - up --no-start"`。
  回退后也是「已创建、未启动」，不要把它启动。
- 未核实：`down` 会不会因为别的原因保留网络。如果 `down` 之后 `docker network ls` 里还有 `sdtm-rag-public`，
  确认没有容器挂在上面后执行 `docker network rm sdtm-rag-public` 再继续。

## 第 3 步：隔离规则 —— 先红后绿

这一步的顺序是有意的：先在**没装规则**时跑一遍，证明公开网络里的容器确实连得上内网（探测本身有效），
再装规则跑一遍，证明连不上了。只跑后一遍的话，「连不上」也可能是目标本来就没在听。

内网目标（都是只做一次 TCP 连接）：

```bash
LAN="--lan 10.201.8.1:22 --lan 192.168.5.15:22 --lan 192.168.5.15:8000 --lan 192.168.5.2:22 --lan 192.168.64.1:22 --lan 192.168.100.58:443 --lan 172.22.0.1:22"
NET="--egress api.anthropic.com:443 --egress api.openai.com:443 --egress region1.v2.argotunnel.com:7844"
```

依次是：公开网桥的网关、虚拟机网卡（ssh / 私有站发布的端口）、Lima 宿主网关（通到 mini 本机）、mini 在虚拟机网桥上的地址、
局域网里的镜像仓库、私有站 docker 网络的网关。外网目标是两家模型服务商和 Cloudflare 隧道接入点。

```bash
# 3a 对照侧: 虚拟机本机 (不受规则约束)
VM "python3 - probe $LAN" < deploy/public-net/isolation_probe.py > $OUT/control.json

# 3b 隔离侧, 规则还没装: 公开网络里的一次性容器 (不挂数据, 不带 .env)
VM "docker run --rm -i --network sdtm-rag-public --entrypoint python $IMG - probe $LAN $NET" \
  < deploy/public-net/isolation_probe.py > $OUT/before.json
python3 deploy/public-net/isolation_probe.py judge --isolated $OUT/before.json --control $OUT/control.json --isolated-net 10.201.8.0/24
```

预期：对照侧每个内网目标都是 `open` 或 `refused`；3b 的结论是 **FAIL**（规则没装，容器连得上内网），
并且有一行「隔离侧源地址 10.201.8.x 在 10.201.8.0/24 里」。如果 3b 不是 FAIL，说明探测没有测到东西，先查原因，不要往下装规则。

看一眼 `before.json`：哪个内网目标在这时就是 `timeout`（比如被 docker 自己的跨网络规则挡了），就把它从 `LAN` 里去掉，
重跑 3a 和 3b。留着它的话，3d 会因为它判「无结论」—— 装之前就连不上的目标，证明不了是这套规则挡的。

```bash
# 3c 装规则 (先只做语法检查, 再装)
VM "sudo nft -c -f -" < deploy/public-net/isolation.nft
VM "sudo install -d -m 755 /etc/sdtm-rag-public"
VM "sudo tee /etc/sdtm-rag-public/isolation.nft >/dev/null" < deploy/public-net/isolation.nft
for u in sdtm-rag-public-isolation.service sdtm-rag-public-isolation-watch.service sdtm-rag-public-isolation-watch.timer; do
  VM "sudo tee /etc/systemd/system/$u >/dev/null" < deploy/public-net/$u
  VM "sudo systemd-analyze verify /etc/systemd/system/$u"
done
VM "sudo systemctl daemon-reload"
VM "sudo systemctl enable --now sdtm-rag-public-isolation.service"
VM "sudo systemctl enable --now sdtm-rag-public-isolation-watch.timer"
VM "sudo nft list tables"
VM "sh -c 'systemctl is-active sdtm-rag-public-isolation.service; systemctl is-enabled sdtm-rag-public-isolation.service; systemctl is-enabled sdtm-rag-public-isolation-watch.timer'"
VM "systemctl list-timers sdtm-rag-public-isolation-watch.timer --no-pager"

# 3d 隔离侧, 规则已装
VM "docker run --rm -i --network sdtm-rag-public --entrypoint python $IMG - probe $LAN $NET" \
  < deploy/public-net/isolation_probe.py > $OUT/after.json
VM "python3 - probe $LAN" < deploy/public-net/isolation_probe.py > $OUT/control_after.json     # 对照侧再跑一遍: 规则不能挡住虚拟机自己
python3 deploy/public-net/isolation_probe.py judge --isolated $OUT/after.json --control $OUT/control_after.json \
  --before $OUT/before.json --isolated-net 10.201.8.0/24
VM "sudo nft list table inet sdtm_rag_public_isolation"
```

预期：`nft list tables` 比第 1 步多一张 `inet sdtm_rag_public_isolation`，docker 的 5 张表都还在；
隔离单元 `active` / `enabled`，巡检定时器 `enabled` 并排在定时器列表里；
3d 的结论是 **PASS**（内网目标全部 `timeout`，三个外网目标 `open`，源地址在公开网段里）；
对照侧装规则后仍然每个目标可达（特别是 `10.201.8.1:22`：虚拟机自己连网关地址不该被挡）；
规则列表里 `drop` 那几行的计数器不为零。巡检每分钟重装一次规则，计数器随之清零：如果看到的是 0，多半是整分钟正好落在探测和查看之间，
再跑一次 3d 的探测后立刻看，不算失败。

```bash
# 3f 巡检会把被删掉、被清空的规则装回来 (这时公开实例和连接器都没在跑, 动规则没有风险)
VM "sudo nft delete table inet sdtm_rag_public_isolation"
sleep 90
VM "sudo nft list tables"
VM "journalctl -u sdtm-rag-public-isolation-watch.service -n 5 --no-pager"
VM "sudo nft flush table inet sdtm_rag_public_isolation"
sleep 90
VM "sh -c 'sudo nft list table inet sdtm_rag_public_isolation | grep -c drop'"
```

预期：第一个 90 秒后表又在了，日志里有一行 `isolation table was missing`（日志里不该有 `reload failed`）；清空内容后再等 90 秒，表里又有 5 条 `drop` 规则
（巡检每次都把规则文件整份重装，不只是看表在不在）。

```bash
# 3e 别的服务没有被波及
VM "docker run --rm --network sdtm-rag_default --entrypoint python $IMG -c \"import socket; socket.create_connection(('192.168.100.58',443),4); print('private network ok')\""
VM "curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/health"
```

预期：私有站网络里的容器照常连得上局域网；私有站健康检查 `200`。

- 公开站状态：已创建、未启动。
- 回退：**先停巡检**（否则一分钟内规则会被重新装回），再停隔离单元（停单元时会删掉这张表）：
  `VM "sudo systemctl disable --now sdtm-rag-public-isolation-watch.timer"`，
  `VM "sudo systemctl disable --now sdtm-rag-public-isolation.service"`，
  然后删掉 `/etc/systemd/system/sdtm-rag-public-isolation*` 和 `/etc/sdtm-rag-public/`，再 `daemon-reload`。
- **不在演练里重启虚拟机**（会中断同机的全部服务）。「开机时规则先于容器装入」这一条因此没有验证，
  留到下一次计划内的重启：重启后立刻重跑 3a 和 3d。

## 第 4 步：静态地址和动态地址段

```bash
VM "docker run --rm --network sdtm-rag-public --entrypoint python $IMG -c \"import socket; print(socket.gethostbyname(socket.gethostname()))\""
VM "docker run --rm --network sdtm-rag-public --ip 10.201.8.2 --entrypoint python $IMG -c \"import socket; print(socket.gethostbyname(socket.gethostname()))\""
```

预期：第一条打印的地址在 `10.201.8.128`–`10.201.8.255` 之间；第二条打印 `10.201.8.2`
（静态地址在动态段之外仍可指定，这是 Docker 文档给的做法，这里实测确认）。

第二条同时说明了一件事：连接器没在跑的时候，任何能操作 docker 的人都可以起一个占用 `10.201.8.2` 的容器，
公开实例会把它当成连接器。能操作 docker 本来就等于虚拟机的 root，这不是新的权限；记在 checkpoint 的剩余风险里。

## 第 5 步：部署公开实例

按另一条线实现的流程走（临时容器验收通过后再换正式容器）。部署前公开容器是停止的话，部署后它是「已更新、保持停止」，
要先在部署机上 `docker start sdtm-rag-public-api`（2026-11-28 第一次上线就是这样）。正式容器起来后补下面几条，都是只读：

```bash
VM "docker inspect sdtm-rag-public-api --format '{{.State.Health.Status}} {{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}}={{\$v.IPAddress}}{{end}} ports={{.NetworkSettings.Ports}}'"
VM "docker exec sdtm-rag-public-api python -c \"import os; print(os.environ['SDTM_RAG_QUOTA_TRUSTED_PROXIES'])\""
VM "docker exec -i sdtm-rag-public-api python -" <<'PY'
import os, urllib.request
print("FORWARDED_ALLOW_IPS =", repr(os.environ.get("FORWARDED_ALLOW_IPS")))
r = urllib.request.urlopen("http://127.0.0.1:8000/api/info", timeout=5)
print(r.headers.get("strict-transport-security"))
print([c.split("=", 1)[0] + " " + ";".join(c.split(";")[1:]) for c in r.headers.get_all("set-cookie")])
PY
```

预期：`healthy`；只在 `sdtm-rag-public` 网络上，地址在动态段里；没有发布端口；可信代理是 `10.201.8.2`；
`FORWARDED_ALLOW_IPS` 是空串 `''`；HSTS 是 `max-age=31536000`；cookie `sdtm_visitor` 的属性里有 `Secure`（上面的命令不打印 cookie 的值）。

如果正式容器（或临时验收容器）起不来，日志里是 `conflicting case variants of the same setting`：公开站的 env 文件里有某个键
写了大小写不同的两份、取值还不一样。报错只列键名。让主人在 env 文件里只留一种写法，再重新部署。

### 5a 全局限流已经打开

```bash
VM "docker exec -i sdtm-rag-public-api python -" <<'PY'
import urllib.error, urllib.request
from server.config import Settings
s = Settings()
print("设置:", s.rate_limit_enabled, s.rate_limit_per_min, s.rate_limit_burst)
codes = []
for _ in range(25):
    try:
        codes.append(urllib.request.urlopen("http://127.0.0.1:8000/api/info", timeout=5).status)
    except urllib.error.HTTPError as e:
        codes.append(e.code)
print("25 次 /api/info:", codes.count(200), "个 200,", codes.count(429), "个 429")
print("健康检查:", urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=5).status)
PY
```

预期：`设置: True 60 20`；25 次里 `200` 不超过 20 个、其余是 `429`（从容器内发的请求按 `127.0.0.1` 计，和访客不是一个桶）；
健康检查仍是 `200`（它不计入限流，容器的健康状态不会因此变坏）。等一分钟桶就满了，不影响后面的步骤。

### 5b 删掉 env 文件里那行旧的可信代理设置

主人 2026-11-28 定：删。那一行（3.3 试跑时写的 `SDTM_RAG_QUOTA_TRUSTED_PROXIES=127.0.0.1`）现在不起作用，部署配置里写死的值优先。
这时公开实例没有入口，重启它没有对外影响。下面的命令都不显示 env 文件的内容。

先确认新设置已经生效（删之前必须看到前两行都是 `10.201.8.2`）：

```bash
VM "docker exec -i sdtm-rag-public-api python -" <<'PY'
import os
from server import quota
from server.config import Settings
key = "SDTM_RAG_QUOTA_TRUSTED_PROXIES"
print("环境变量:", os.environ.get(key))
print("应用实际用的:", quota.cfg(Settings(), "quota_trusted_proxies"))
names = [ln.split("=", 1)[0].strip() for ln in open("/app/.env") if "=" in ln and not ln.lstrip().startswith("#")]
print("env 文件里这个键的行数 (不分大小写):", sum(1 for n in names if n.upper().removeprefix("EXPORT ").strip() == key))
PY
```

预期：`环境变量: 10.201.8.2`、`应用实际用的: 10.201.8.2`、行数 `1`。前两行有任何一行不是 `10.201.8.2`：停下，不要删
（说明部署配置里的值没有进到容器，删了旧行公开实例会因为没有可信代理而拒绝启动）。

```bash
# 留一份备份 (和原文件同目录、同权限; 里面有 key, 用完就删)
VM "sudo cp -p /opt/sdtm-rag-public/.env /opt/sdtm-rag-public/.env.before-cleanup"
VM "sudo sed -i '/^SDTM_RAG_QUOTA_TRUSTED_PROXIES=/d' /opt/sdtm-rag-public/.env"
VM "sudo sh -c 'wc -l < /opt/sdtm-rag-public/.env.before-cleanup; wc -l < /opt/sdtm-rag-public/.env; stat -c \"%a %U:%G\" /opt/sdtm-rag-public/.env'"
# 应用只在启动时读 env 文件, 而且文件是按「启动那一刻的那个文件」挂进去的: 重启一次才算数
VM "docker restart sdtm-rag-public-api"
VM "sh -c 'for i in \$(seq 1 40); do s=\$(docker inspect -f \"{{.State.Health.Status}}\" sdtm-rag-public-api); [ \"\$s\" = healthy ] && break; sleep 3; done; echo \$s'"
```

预期：行数正好少 1；权限仍是 `600 root:root`；重启后 `healthy`。然后把上面那段「先确认」的 Python 再跑一遍：
前两行仍是 `10.201.8.2`，行数变成 `0`。再跑一遍 5a 开头的三行检查也可以，结果应与删之前相同。最后删掉备份：

```bash
VM "sudo rm /opt/sdtm-rag-public/.env.before-cleanup"
```

- 行数没有少、或者少了不止 1：`sed` 没有按预期匹配（那一行可能前面有空格，或者写了不止一份）。先按下面恢复，报给协调方，不要手工改文件碰运气。
- **恢复**（删错了，或重启后起不来）：`VM "sudo cp -p /opt/sdtm-rag-public/.env.before-cleanup /opt/sdtm-rag-public/.env"`，
  再 `VM "docker restart sdtm-rag-public-api"`，确认回到 `healthy`。备份在确认一切正常之前不要删。
- 重启后起不来、日志里是 `public tier requires SDTM_RAG_QUOTA_TRUSTED_PROXIES`：部署配置里的值没进容器（「先确认」那一步本该拦住）。恢复备份，再查部署。

- 公开站状态：运行中，没有入口。
- 回退：部署本身按另一条线的流程；5b 按上面的「恢复」。

## 第 6 步：启动连接器

前提：主人已做完操作说明的第 1、2 步（隧道已建，token 文件已放好）。

```bash
VM "sudo stat -c '%a %u:%g' /opt/sdtm-rag-public/cloudflared/tunnel-token"      # 预期 400 65532:65532
VM "docker compose -f - config" < $TUN | grep -c eyJ                             # 预期 0
VM "docker compose -f - up -d" < $TUN
VM "docker inspect sdtm-rag-public-cloudflared --format '{{.State.Status}} {{(index .NetworkSettings.Networks \"sdtm-rag-public\").IPAddress}} ro={{.HostConfig.ReadonlyRootfs}} cap_drop={{.HostConfig.CapDrop}} user={{.Config.User}} ports={{.NetworkSettings.Ports}}'"
VM "docker inspect sdtm-rag-public-cloudflared" | grep -c eyJ                    # 预期 0
VM "docker logs sdtm-rag-public-cloudflared 2>&1" | grep -c eyJ                  # 预期 0
VM "docker logs --tail 30 sdtm-rag-public-cloudflared"
# 同一网络内, 连接器走的那条路是通的 (隔离规则不能挡它)
VM "docker run --rm --network sdtm-rag-public --entrypoint python $IMG -c \"import urllib.request; print(urllib.request.urlopen('http://sdtm-rag-public-api:8000/api/health', timeout=5).status)\""
```

预期：`running 10.201.8.2 ro=true cap_drop=[ALL] user=65532:65532`，没有发布端口；三处 `grep -c eyJ` 都是 `0`
（token 不在配置、容器元数据和日志里）；日志里有隧道连接建立的记录（具体措辞未核实），没有读 token 文件失败或权限错误；最后一条打印 `200`。
后台里这条隧道显示已连接。

```bash
# 连接器在跑的时候, 它的地址不能被别的容器占用
VM "docker run --rm --network sdtm-rag-public --ip 10.201.8.2 --entrypoint python $IMG -c \"print('不该走到这里')\""
```

预期：docker 报地址已被占用，容器起不来。

如果连接器因为只读文件系统或去掉 capability 起不来：日志会写明原因。临时处理办法是不要改 compose 去放宽，先停下来报告
（这两项在合并前没法实测，属于未验证事项）。

可选（这时还没有路由）：验证「规则装不回去时巡检会停掉连接器」。做法是把规则**文件**暂时挪开，内核里已装的规则不动，
所以整个过程里隔离一直在位：

```bash
VM "sudo mv /etc/sdtm-rag-public/isolation.nft /etc/sdtm-rag-public/isolation.nft.off"
VM "sudo systemctl start sdtm-rag-public-isolation-watch.service"              # 预期: 以失败退出
VM "docker inspect sdtm-rag-public-cloudflared --format '{{.State.Status}}'"   # 预期: exited
# 复原
VM "sudo mv /etc/sdtm-rag-public/isolation.nft.off /etc/sdtm-rag-public/isolation.nft"
VM "sudo systemctl start sdtm-rag-public-isolation-watch.service"              # 预期: 成功
VM "sudo nft list tables"                                                      # 预期: 隔离表在
VM "docker start sdtm-rag-public-cloudflared"
```

如果中途断了：规则文件还没挪回去的话，定时器下一次触发时重装会失败，连接器会被停掉（或保持停止）——方向是安全的。
回来先执行「复原」那三行，再 `docker start`。

上线后留意巡检日志：`VM "journalctl -u sdtm-rag-public-isolation-watch.service --since -1d --no-pager"` 里如果零星出现
`reload failed twice`（而规则文件没人动过），说明重装和 docker 自己改规则撞上了、重试一次还不够，报给协调方。

- 公开站状态：运行中，连接器在线，**没有路由，仍访问不到**。
- 回退：`VM "docker compose -p sdtm-rag-public-tunnel down"`（删掉连接器容器；token 文件和网络都还在）。

## 第 7 步：主人在后台建限速规则、访问限制，然后加路由

操作说明第 4–7 步，顺序不能换：HTTPS 跳转规则（第 4 步）、限速规则（第 5 步）、只放行主人的访问限制（第 6 步）都建好之后，才加路由（第 7 步）。
加路由之后公开站经隧道可达，但只有主人的邮箱登录后能进。

主人加完路由后，协调方从外面（不带任何登录状态）确认访问限制在起作用：

```bash
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://sdtm.bojiang.org/
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://sdtm.bojiang.org/api/info
```

预期：两条都是跳转（`30x`），而且跳转地址里有 `cloudflareaccess.com`（Access 的登录地址）。
对不带浏览器特征的请求，Access 也可能直接回它自己的 `401` / `403` 页面而不跳转：确切形式未核实，把看到的状态码记下来。

判读要从严，「不是 200」不够：`429`（被限流）、`502`（源站没起来）也不是 200，却不能说明访问限制在起作用。
只有「跳到 `cloudflareaccess.com`」或「Access 自己的 401 / 403」算通过；其余任何结果都先停下来查清楚是谁回的。
任何一条返回 `200`（直接拿到了页面或数据）：访问限制没生效，立即 `VM "docker stop sdtm-rag-public-cloudflared"`，让主人回操作说明第 6 步查。

- 公开站状态：经隧道可达，只有主人能进。
- 回退：`VM "docker stop sdtm-rag-public-cloudflared"`；主人在后台删路由。

## 第 8 步：隧道这一层的验收（放开之前）

这一步全程在「只有主人能进」的状态下做。主人用浏览器按操作说明第 8 步的表逐项看，同时在虚拟机里做下面的只读核对。
全部通过之后才做第 9 步。

**源站实际收到的头。** 连接器到公开实例这一段是明文 HTTP，可以在网桥上抓。过滤放在虚拟机里做，
只有要看的那几个头会离开虚拟机（完整报文里有 cookie、Access 的登录凭据和提问正文，不能整段传出来）。
输出里有访客的真实 IP，**只在终端里看，不保存、不贴进任何文档**：

```bash
VM "sh -c 'sudo timeout 60 tcpdump -i br-sdtmpub -A -l tcp dst port 8000 and src host 10.201.8.2 2>/dev/null | grep -a -i -E --line-buffered \"^(host|x-forwarded-proto|x-forwarded-for|cf-connecting-ip|cf-visitor):\"'"
```

抓包期间主人刷新一次页面。预期：`Host: sdtm.bojiang.org`；`X-Forwarded-Proto: https`；`CF-Connecting-IP` 是主人当前的公网 IP。
把看到的头名和 `X-Forwarded-Proto` 的值记进 checkpoint（不记 IP）。这是以后要不要在应用侧加「明文请求直接跳转」的依据。

**访客 IP 没有被算成连接器的地址。** 主人问过一个问题之后：

```bash
VM "docker exec -i sdtm-rag-public-api python -" <<'PY'
import ipaddress, sqlite3
rows = sqlite3.connect("/app/data/quota.sqlite").execute("select key from counters where key like 'ip:%'").fetchall()
print(len(rows), "个按 IP 的计数键")
for (k,) in rows:
    a = k[3:]
    try:
        print("global" if ipaddress.ip_network(a, strict=False).is_global else "NOT GLOBAL: " + a)
    except ValueError:
        print("unparsed")
PY
```

预期：至少 1 个键，每一行都是 `global`。出现 `NOT GLOBAL: 10.201.8.2` 说明真实 IP 没有传进来（所有访客会共用一份额度），立即停连接器排查。
出现别的 `NOT GLOBAL`（例如 `240.` 开头的地址）也停下来查：可能是 Cloudflare 侧改写了访客地址。

**伪造 `CF-Connecting-IP`。** 主人在浏览器控制台执行下面一行，同时重复上面的抓包：

```js
fetch('/api/info', {headers: {'CF-Connecting-IP': '203.0.113.9'}}).then(r => console.log(r.status))
```

预期：抓到的 `CF-Connecting-IP` 仍是主人的真实 IP，不是 `203.0.113.9`（Cloudflare 会覆盖访客自带的这个头；官方文档没有明说，所以这里实测）。
如果抓到的是 `203.0.113.9`：访客可以冒充任意 IP 绕过按 IP 的限额，立即停连接器并上报。

浏览器会把同名的头合并成一条，测不出「带两条」的情况，再用 curl 补一次（Access 开着时要带上登录后的 cookie：
在浏览器开发者工具里复制 `CF_Authorization` 的值；这个值是登录凭据，用完即弃，不要贴进任何文档）：

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "Cookie: CF_Authorization=<从浏览器复制>" \
  -H 'CF-Connecting-IP: 203.0.113.9' -H 'CF-Connecting-IP: 203.0.113.10' https://sdtm.bojiang.org/api/info
```

预期：源站只收到一条 `CF-Connecting-IP`，值是真实 IP。如果收到两条：应用这时两条都不采信（按连接器的地址计，这一个请求和别人共用额度），
不会被冒充，但要记下来上报。

**提问限额。** 主人在浏览器控制台执行（会用掉 3 道免费题）：

```js
(async () => {
  const m = (await (await fetch('/api/info')).json()).selectable_models[0].id;
  const ask = () => fetch('/api/ask', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({question: 'What is the DM domain?', model: m})}).then(r => r.status);
  console.log(await Promise.all([ask(), ask(), ask(), ask(), ask()]));
})()
```

预期：3 个 `200`、2 个 `429`（每位访客的突发上限是 3）。

**两层限流。** 等一分钟（让上面用掉的额度补回来），主人在浏览器控制台执行：

```js
(async () => {
  const one = () => fetch('/api/info').then(async r => {
    if (r.status === 200) return '放行';
    if (r.status !== 429) return '其他 (' + r.status + ')';
    return (await r.text()).startsWith('Too Many Requests') ? '应用拒绝 (429)' : 'Cloudflare 挡 (429)';
  });
  const rs = await Promise.all([...Array(80)].map(one));
  const n = {}; rs.forEach(x => n[x] = (n[x] || 0) + 1); console.log(n);
})()
```

预期：`放行` 不超过 20 个（应用里的全局限流：突发 20）；有一批 `应用拒绝 (429)`；总数过了 50 之后的那一批是 `Cloudflare 挡 (429)`
（操作说明第 5 步的规则：10 秒 50 次，挡 10 秒）；**没有 `其他`**。前三类的确切个数会有出入（Cloudflare 的计数不是逐个精确的），
看的是三类都出现、放行的没有超过 20。之后 10 秒内主人访问 `/api/` 下的地址都会被挡，属于预期。

- 出现 `其他 (…)`：不能算通过。那是别的原因造成的非 200（源站出错的 502 / 520 / 524、Access 登录过期的跳转等），先查清楚再重做。
  例外：如果 Cloudflare 的限速规则挡人时用的不是 429（它返回什么状态码未核实），这里会全部落进 `其他 (同一个状态码)`；
  那就把这个状态码记下来，确认页面是 Cloudflare 的限速提示后，按「Cloudflare 挡」算。
- `放行` 明显多于 20：应用里的全局限流没生效，回第 5 步的 5a 查。
- 没有任何 `Cloudflare 挡`：限速规则没生效（没部署，或匹配条件没写对），让主人回操作说明第 5 步查。

全局限流是不是按访客各算各的（而不是所有人共用一个桶）：这一项**不在演练里验**。从容器内发请求看不出来 —— 即使所有访客都被错算成连接器的地址，
容器内的请求（按 `127.0.0.1` 计）也还是另一个桶，照样放行。它由测试守着：`test_public_compose_turns_on_the_global_rate_limit`
（按 compose 的取值起应用，一位访客的桶空了，另一位照常）。想在线上再看一眼的话：主人刚被应用拒绝的那几秒里，
用另一个出口（比如手机流量，同样先登录 Access）打开 `/api/info`，应该是正常的。

**流式输出。** 主人正常问一个问题，答案应逐段出现。连接器对 `Content-Type: text/event-stream` 的响应不做缓冲（官方文档）；
如果答案是憋到最后一次性出来的，记下来排查，不影响安全。

**公开实例重建后连接器不用重启。** 重新部署一次公开实例（或 `docker restart sdtm-rag-public-api`）后，不动连接器，主人刷新页面应恢复正常。
这一条未核实（依赖连接器重新解析容器名）。

- 回退：任何一项不符，先 `VM "docker stop sdtm-rag-public-cloudflared"`（几秒内不可达），再排查。

## 第 9 步：放开（最后一步），以及之后的例行核对

- 放开：第 8 步每一项都通过、主人决定放开之后，主人做操作说明第 9 步（删掉 Access 应用）。有任何一项没过，就不放开。
  放开后协调方从外面确认一次：`curl -s -o /dev/null -w '%{http_code}\n' https://sdtm.bojiang.org/` 应是 `200`（现在不需要登录了）。
- 每次公开实例部署之后、每次虚拟机重启之后：重跑第 3 步的 3a 和 3d（这时 `judge` 不带 `--before`，带 `--isolated-net`），结论必须是 PASS。
  同时确认巡检还开着（两行都应是肯定的：`active`、`enabled`），以及系统自带的防火墙服务没有被启用（应是 `disabled`）：
  `VM "sh -c 'systemctl is-active sdtm-rag-public-isolation-watch.timer; systemctl is-enabled sdtm-rag-public-isolation-watch.timer; systemctl is-enabled nftables.service'"`
  `INCONCLUSIVE` 不算通过：通常是某个对照目标没在听了，换一个仍在听的内网目标再跑。
- 升级 cloudflared：同时改 `compose.tunnel.yml` 里的版本标签和摘要，然后重做第 6 步。

## 回退总表

| 想撤回什么 | 做法 | 影响 |
|------------|------|------|
| 立即下线 | `docker stop sdtm-rag-public-cloudflared` | 公开站不可达；其余不变 |
| 撤掉入口配置 | 后台**先删路由**，再删 Access 应用、重定向规则、限速规则 | 同上，且主机名不再解析到隧道。顺序不能反：路由还在时删 Access 应用 = 对所有人开放 |
| 放开之后想收回 | 主人重新建 Access 应用（操作说明第 6 步） | 回到只有主人能进 |
| 作废 token | 后台 **Refresh token**，再停连接器，删虚拟机里的 token 文件 | 旧 token 不能再建立新连接 |
| 撤掉连接器 | `docker compose -p sdtm-rag-public-tunnel down` | 容器删除 |
| 撤掉隔离规则 | 第 3 步的回退（先停巡检定时器） | 公开网络里的容器又能访问内网：**只在公开实例和连接器都停着时做** |
| 撤掉固定子网 | 先撤掉连接器，再按第 2 步的回退 | 网络回到自动分配的网段和随机网桥名：可信代理地址对不上，**隔离规则的两个匹配条件也都对不上（隔离失效，而且不会报错）**。回退后公开实例必须保持停止，不能再接隧道 |
