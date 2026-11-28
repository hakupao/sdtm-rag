# 公开站接入 Cloudflare 隧道：给主人的操作说明

> 适用：`sdtm.bojiang.org` 首次上线。写于 2026-11-28，**尚未执行**。
> Cloudflare 后台的菜单名和字段名取自官方文档（developers.cloudflare.com），查阅日期 2026-11-28；
> 文档里没有写明的地方标了「未核实」，以后台实际显示为准。
> 虚拟机里的配套步骤在 `docs/plans/P3_4_tunnel_drill.md`（下称「演练方案」）。
>
> 你 2026-11-28 在待办项上选定的三件事已经写进来了（经协调方转达）：首次上线先只放行你本人（第 6 步，必做）；
> 限流两层都加（应用里的那一层已写进部署配置，Cloudflare 的那一条是第 5 步，必做）；
> 公开站配置文件里那行旧的「可信代理」设置删掉（协调方在演练方案第 5 步做）。

## 先看这三条

1. **token 是秘密。** 它只存在两个地方：Cloudflare 后台，和虚拟机里的一个文件。
   不要贴进聊天、工单、提交信息或任何对话；不要截图带 token 的页面。
2. **路由是第 7 步才加的，而且加上之后只有你自己能进。** 之前的每一步做完，公开站都还访问不到，想停在哪一步都可以。
   对所有人开放是最后一步（第 9 步），在第 8 步的验收全部通过之后。
3. **不要打开下面这几个开关**（都在 Cloudflare 后台，作用于整个 `bojiang.org`，会影响别的子域名或让限额失效）：
   - `Always Use HTTPS`（全域）；
   - `HTTP Strict Transport Security (HSTS)`（全域）；HSTS 已由公开站自己发，只对 `sdtm.bojiang.org` 生效；
   - Managed Transforms 里的 `Remove visitor IP headers`：它会去掉 `CF-Connecting-IP`，所有访客会被算成同一个人，共用一份额度；
   - `Pseudo IPv4`（如果后台有这一项）：它可能改写 IPv6 访客的 `CF-Connecting-IP`。具体行为未核实，保持关闭。

## 开始前（协调方确认，不是主人做）

按演练方案第 1–5 步做完并确认（其中第 5 步包含删掉公开站配置文件里那行旧的可信代理设置）：

- 公开网络已重建为固定子网，隔离规则已装，探测结论是 PASS；
- 公开实例已用新镜像启动，健康；
- 这时公开站没有入口，访问不到。

## 第 1 步：在后台建隧道

1. 打开 **Networking** > **Tunnels**，选 **Create a tunnel**。
2. 名字填 `sdtm-rag-public`，选 **Create Tunnel**。
3. 页面会让你选操作系统并给出一条安装命令。**不要运行这条命令。**
   命令里以 `eyJ` 开头的那一长串就是 token（官方文档原话：`The token is the eyJ... string`）。只复制这一串，不带前后的空格和别的词。
4. 这个页面先不要关（下一步要用剪贴板里的 token）。

以后要再看 token：**Networking** > **Tunnels** > 选这条隧道 > **Overview** > **Add a replica**，安装命令里还是它。

- 做完后的状态：隧道已建，没有连接器，没有路由。公开站访问不到。
- 撤回：删掉这条隧道（删除的菜单位置未核实，官方文档没有写）。

## 第 2 步：把 token 放进虚拟机

在自己的终端里做。**下面四段要一段一段地复制执行，不要一次全选粘贴**：第三段会等你输入 token，
如果后面还跟着别的命令一起粘进去，它会把那条命令当成 token 读走。

第一段，进虚拟机：

```bash
ssh bojiang.local
export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl shell deploy
```

第二段，先关掉命令历史（万一粘贴错了位置，token 也不会被记进历史文件）。第一行应输出 `bash` 或 `-bash`；
如果不是（比如 `zsh`），第二行对它不起作用，先执行 `bash` 进入 bash 再继续：

```bash
echo $0
set +o history
```

第三段是一整条命令。执行后出现提示「粘贴 token 后按回车」，这时粘贴 token 再按回车，**屏幕上不会显示你粘贴的内容**：

```bash
sudo bash -c 'umask 077; d=/opt/sdtm-rag-public/cloudflared; f=$d/tunnel-token; install -d -m 700 -o root -g root "$d"; IFS= read -rsp "粘贴 token 后按回车 (不会显示): " T; echo; case "$T" in eyJ*) ;; *) echo "不像 token (应以 eyJ 开头), 没有写入"; exit 1;; esac; case "$T" in *[!A-Za-z0-9+/=_-]*) echo "含有 token 里不该有的字符 (空格或别的词), 没有写入"; exit 1;; esac; [ ${#T} -ge 100 ] || { echo "太短 (${#T} 个字符), 像是没复制全, 没有写入"; exit 1; }; printf "%s\n" "$T" > "$f" && chown 65532:65532 "$f" && chmod 400 "$f" && echo "已写入 ${#T} 个字符"'
```

- 看到「已写入 … 个字符」（一两百个字符）就是成功了。
- 看到「不像 token」「含有 token 里不该有的字符」或「太短」：什么都没写入，重新复制 token（只要 `eyJ` 开头的那一串），再执行一遍这条命令。
- **等提示出现之后再粘贴。** 提示出现之前就粘贴的话，那一刻终端还在回显，token 会显示出来。
- 只要屏幕上出现过 `eyJ…` 字样（粘早了，或者粘到了普通的命令提示符下），不管最后有没有写入成功，都按「怀疑泄漏」处理 ——
  做完本步后到后台刷新 token（见文末「换 token」），用新 token 重做本步。

第四段，恢复命令历史，并检查（不会显示 token 内容）：

```bash
set -o history
sudo stat -c '%a %u:%g %s 字节' /opt/sdtm-rag-public/cloudflared/tunnel-token   # 应为：400 65532:65532，大小一两百字节
```

做完后随便复制一段别的文字，把剪贴板里的 token 顶掉。如果你用了剪贴板历史工具，或者开着苹果设备之间的通用剪贴板，
那里还会留一份，记得清掉。

为什么这样放：

- 文件在虚拟机自己的盘上（和公开站的 `.env` 同一个目录下），不在 mini 能直接看到的共享目录里；
- 属主 `65532` 是连接器容器里进程的用户，权限 `400` 表示只有它（和 root）能读；所在目录只有 root 能进；
- 输入时不回显，token 不显示在屏幕上；命令本身不含 token，所以即使历史没关也不会把它记下来；
- 连接器以只读方式挂载这个文件来读 token，token 不会出现在 `docker inspect` 或 compose 配置的输出里。

要知道的：虚拟机的磁盘镜像在 mini 上，镜像的任何备份里都有这个文件（公开站的 `.env` 也一样）。

- 做完后的状态：和第 1 步一样，公开站访问不到。
- 撤回：`sudo rm /opt/sdtm-rag-public/cloudflared/tunnel-token`。

## 第 3 步：启动连接器（协调方做，需要主人点头）

见演练方案第 6 步。做完后回到第 1 步的后台页面，隧道应显示已连接，选 **Continue**（文档原话：`After the tunnel connects, select Continue`）。

- 做完后的状态：连接器在线，但还没有任何路由指向它。公开站访问不到。
- 撤回：停掉并删除连接器容器（演练方案第 6 步的回退）。

## 第 4 步：加一条只对本主机名生效的 HTTPS 跳转规则

目的：有人用 `http://` 打开时跳到 `https://`。用单条重定向规则，不用全域的 `Always Use HTTPS`
（官方文档对「只想让部分主机名跳转」的建议也是这样）。

1. 进入 Rules 的 **Overview** 页，选 **Create rule** > **Redirect Rule**。
2. **Rule name**：`sdtm http to https`。
3. **When incoming requests match** 选 **Wildcard pattern**，**Request URL** 填 `http://sdtm.bojiang.org/*`。
4. **Then** 下面：**Target URL** 填 `https://sdtm.bojiang.org/${1}`，**Status code** 选 `301`，勾选 **Preserve query string**。
5. 选 **Deploy**。

免费套餐能建几条重定向规则：未核实。

- 做完后的状态：规则已在，但主机名还不存在，暂时不起作用。公开站访问不到。
- 撤回：删掉这条规则。

## 第 5 步：建一条限速规则（必做）

这是两层限流里 Cloudflare 的那一层：灌水式的请求在 Cloudflare 就被挡掉，到不了虚拟机。应用里的那一层已经写在部署配置里
（每个访客 IP 每分钟 60 个请求、突发 20；提问另有每访客和每 IP 的限额）。

免费套餐的限制（官方文档，查阅日期 2026-11-28）：只能建 **1 条**；只能按 **IP** 计数；计数周期固定 **10 秒**；
封禁时长固定 **10 秒**；匹配条件只能用**路径**（和是否已验证的爬虫），**不能限定主机名**。

1. 进入 **Security rules** 页，选 **Create rule** > **Rate limiting rules**。
2. **Rule name**：`api flood`。
3. 匹配条件：**Field** 选路径那一项（官方文档列的可用字段是 `Path`；后台里的确切叫法未核实，可能显示为 `URI Path`），
   **Operator** 选 `starts with`，值填 `/api/`。
4. **With the same characteristics**：`IP`（免费套餐只有这一项）。
5. **When rate exceeds**：请求数填 `50`，周期 `10 seconds`（免费套餐只有这一档）。
6. **Then take action** 下的 **Choose action** 选 `Block`，**Duration** `10 seconds`（免费套餐只有这一档）。
7. 选 **Deploy**。

为什么这样填：

- **路径 `/api/`**：公开站要花钱、要算的接口都在这个前缀下。页面本身和静态文件不在里面，打开一次页面要取的十几个文件不会被计数。
- **10 秒 50 次**：应用里那一层对同一个 IP 在任意 10 秒内最多放行 30 个请求（突发 20，加上这 10 秒里补回来的 10 个）。
  50 高于 30，所以正常使用碰不到这条规则；碰到它的只能是已经在被应用拒绝、还在继续灌的来源。
- **影响范围**：因为不能限定主机名，这条规则对 `bojiang.org` 下**所有**子域名里以 `/api/` 开头的路径都生效。
  别的站点如果也有这样的路径，同一个 IP 10 秒内超过 50 次同样会被挡 10 秒。这个阈值对人来说很宽；
  如果你有别的站点会有程序高频调用 `/api/…`，告诉协调方，把阈值调高或把路径写得更窄（比如 `/api/ask`）。

`Block` 这个动作在免费套餐里是否可选、被挡时访客看到什么页面：未核实，以后台为准；第 8 步会实际触发一次。

- 做完后的状态：规则已在，但主机名还不存在，暂时不起作用。公开站访问不到。
- 撤回：删掉这条规则。

## 第 6 步：先只让自己能进（Cloudflare Access，必做）

你已选定：首次上线先加访问限制，只放行你本人，验完再对所有人开放。

原因：隧道这一层有几件事只能在加了路由之后才验得了 —— Cloudflare 传进来的访客 IP 对不对、访客能不能伪造它、两层限流有没有生效（第 8 步）。
先建好这一步，这些就是在「只有你能进」的状态下验的。**这一步必须在第 7 步（加路由）之前做完**：
官方文档也是这个顺序，否则路由一加上，任何人都能访问。

1. 打开 **Zero Trust** > **Access controls** > **Applications**，选 **Create new application** > **Self-hosted and private**。
2. 选 **Add public hostname**：子域名填 `sdtm`，**Domain** 选 `bojiang.org`。
3. Access policies 一栏选新建策略：**Policy name** 随意，**Action** 选 **Allow**；规则里 **Include** 选 **Emails**，填你自己的邮箱。
4. **Session Duration** 用默认值即可，选 **Create**。

登录方式（默认是否为邮箱验证码）：未核实。第一次用 Zero Trust 可能要先建一个团队名，按页面提示做。

做完后检查一遍再往下走：应用列表里有这个应用，主机名是 `sdtm.bojiang.org`，策略是 **Allow** 且只有你的邮箱。

- 做完后的状态：访问策略已就位，还没有路由。公开站访问不到。
- 撤回：删掉这个 Access 应用（只在路由还没加、或公开站已经下线时做；路由在而 Access 应用被删 = 对所有人开放）。

## 第 7 步：加路由 —— 这一步之后你自己能访问

前提：第 5、6 步都已做完。

1. 打开 **Networking** > **Tunnels**，选 `sdtm-rag-public`，进 **Routes** 标签页。
2. 选 **Add route** > **Published application**。
3. 子域名填 `sdtm`，**Domain** 选 `bojiang.org`，路径留空。
4. **Service URL** 填 `http://sdtm-rag-public-api:8000`（一个字都不要改：这是公开实例的容器名和端口）。
5. 选 **Add route**（有的页面写的是 **Save**）。

对应的 DNS 记录是否由这一步自动创建：未核实；做完后在 DNS 页面看一眼有没有 `sdtm` 这条记录。

**马上确认访问限制在起作用**：开一个无痕窗口（没有登录过 Access）打开 `https://sdtm.bojiang.org`，应该看到 Access 的登录页，而不是聊天页。
如果直接看到了聊天页：访问限制没生效，立刻停连接器（下面的撤回 1），回第 6 步查。

- 做完后的状态：**公开站经隧道可达，但只有你的邮箱登录后能进**。
- 撤回（三种，从快到彻底）：
  1. 停连接器：`docker stop sdtm-rag-public-cloudflared`。几秒内公开站不可达，后台配置都还在，重新 `docker start` 即恢复。
  2. 在 **Routes** 标签页删掉这条路由。
  3. 在隧道的 **Overview** 页选 **Refresh token**（旧 token 无法再建立新连接），再停连接器。

## 第 8 步：经隧道验一次（放开之前）

用浏览器打开 `https://sdtm.bojiang.org`（登录 Access 之后），按下表逐项看。协调方同时在虚拟机里做只读核对（演练方案第 8 步），
浏览器控制台里要粘贴的代码也在那里。

| 看什么 | 应该是 |
|--------|--------|
| 无痕窗口打开 `https://sdtm.bojiang.org` | Access 登录页（第 7 步已看过一次） |
| 打开 `http://sdtm.bojiang.org` | 自动跳到 `https://` |
| 登录后的首页 | 聊天页 |
| 开发者工具里任一响应的响应头 | 有 `strict-transport-security: max-age=31536000` |
| 开发者工具里的 cookie `sdtm_visitor` | 带 `Secure`、`HttpOnly`、`SameSite=Lax` |
| 问一个问题 | 答案逐段出现，不是等很久后一次性出来 |
| 界面上的剩余额度 | 问完减 1 |
| 控制台：同时发 5 个提问（会用掉 3 道免费题） | 3 个 `200`、2 个 `429`（提问限额生效） |
| 控制台：10 秒内连发 80 个 `/api/info` | 放行的不超过 20 个（应用里的全局限流生效）；后面一批是 Cloudflare 挡的（第 5 步的规则生效） |

访客 IP 是否传对、能否伪造，由协调方在虚拟机里核对（需要你配合刷新页面、在控制台执行两行代码），见演练方案第 8 步。

任何一项不对：先停连接器（第 7 步的撤回 1），再排查。**没有全部通过之前不做第 9 步。**

## 第 9 步：放开（最后一步）

前提：第 8 步的每一项、以及协调方在虚拟机里的核对（演练方案第 8 步）全部通过，并且你决定放开。

做法：删掉第 6 步建的 Access 应用（或把策略改成放行所有人）。之后公开站对所有人开放。

- 做完后的状态：**公开站对所有人开放**。
- 撤回：重新建第 6 步的 Access 应用（回到只有你能进），或直接停连接器。

## 以后会用到的

- **换 token**（怀疑泄漏，或定期更换）：隧道 **Overview** 页选 **Refresh token**，页面给出带新 token 的安装命令；
  按第 2 步用新 token 覆盖文件；让协调方重建连接器容器。官方文档：刷新后旧 token 无法建立新连接，已连上的连接器暂时不受影响。
  怀疑泄漏时，换完再让协调方确认旧连接已断。
- **紧急下线**：`docker stop sdtm-rag-public-cloudflared`。
- **公开站自己下线了**：虚拟机里有一个每分钟一次的巡检，每次把隔离规则重装一遍；装不上就停掉连接器，让公开站下线，
  而不是让它在没有隔离的情况下继续对外。这时让协调方按演练方案排查，修好后 `docker start sdtm-rag-public-cloudflared`。
- **只关免费题、不下线**：公开站 `.env` 里设 `SDTM_RAG_FREE_TIER_DISABLED=true` 后重启公开实例。
- **同一个出口 IP 后面的人共用限流额度**：公司里从同一个出口上网的同事，在两层限流和「每 IP」的提问限额里算作一个来源
  （每分钟 60 个请求、其中最多 20 题；打开页面取的静态文件不计）。几个人同时用问题不大；一个部门同时用，可能有人看到「服务错误 429」，过几秒再试即可。
- **调限流**：应用里的全局限流写在部署配置 `deploy/container/compose.public.yml` 里（改它要走一次部署）；
  Cloudflare 的那条在第 5 步的规则里改。两边要一起看：Cloudflare 的阈值应高于应用在 10 秒内会放行的数量，否则正常用户会先被 Cloudflare 挡。
