"""P3.4 / 3.4b: 公开网络、隧道连接器、隔离规则的静态检查 (不需要 docker)。

同一个事实写在几处 (compose.public.yml 的子网 / compose.tunnel.yml 的静态地址 / 可信代理 / isolation.nft
的网段和网桥名): 每处各钉字面值, 再互相比 —— 只比「两边相等」的话, 两边一起改错照样绿。
workflow 结构的断言不在本文件 (属于另一条线)。
"""
from __future__ import annotations

import importlib.util
import ipaddress
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
PUB_PATH = ROOT / "deploy/container/compose.public.yml"
TUN_PATH = ROOT / "deploy/container/compose.tunnel.yml"
NFT_PATH = ROOT / "deploy/public-net/isolation.nft"
UNIT_PATH = ROOT / "deploy/public-net/sdtm-rag-public-isolation.service"
WATCH_PATH = ROOT / "deploy/public-net/sdtm-rag-public-isolation-watch.service"
TIMER_PATH = ROOT / "deploy/public-net/sdtm-rag-public-isolation-watch.timer"
PROBE_PATH = ROOT / "deploy/public-net/isolation_probe.py"
PUB = yaml.safe_load(PUB_PATH.read_text())
TUN = yaml.safe_load(TUN_PATH.read_text())
PRIV = yaml.safe_load((ROOT / "deploy/container/compose.yml").read_text())

NET_NAME = "sdtm-rag-public"
SUBNET = "10.201.8.0/24"
GATEWAY = "10.201.8.1"
DYNAMIC = "10.201.8.128/25"
CONNECTOR = "10.201.8.2"
BRIDGE = "br-sdtmpub"
NFT_TABLE = "sdtm_rag_public_isolation"
TOKEN_HOST = "/opt/sdtm-rag-public/cloudflared/tunnel-token"
TOKEN_IN_CONTAINER = "/etc/cloudflared/tunnel-token"

# 2026-11-28 只读查到的现有网段 (虚拟机的 docker 网络与网卡、mini 的局域网), 加上 docker 自动分配会用的
# 默认地址池。固定子网不能和其中任何一个重叠。
TAKEN = ([f"172.{i}.0.0/16" for i in range(17, 32)]            # docker 默认池第一段, 现在全被占用
         + ["192.168.0.0/16"]                                   # docker 默认池第二段 + 虚拟机网卡 + 局域网
         + ["192.168.16.0/20", "192.168.5.0/24", "192.168.64.0/24",
            "192.168.2.0/24", "192.168.3.0/24", "192.168.100.0/24"])


def _strip_comments(text: str) -> str:
    return "\n".join(ln.split("#", 1)[0] for ln in text.splitlines())


NFT = _strip_comments(NFT_PATH.read_text())


# ── compose.public.yml: 固定子网 + 可信代理 ──────────────────────────────────

def test_public_network_is_pinned():
    net = PUB["networks"]["public"]
    assert net["name"] == NET_NAME
    assert net["driver"] == "bridge"
    assert net["enable_ipv6"] is False
    assert net["driver_opts"] == {"com.docker.network.bridge.name": BRIDGE}
    assert len(BRIDGE) <= 15                                   # Linux 接口名上限
    assert net["ipam"]["config"] == [{"subnet": SUBNET, "gateway": GATEWAY, "ip_range": DYNAMIC}]
    for k in ("external", "internal", "attachable"):
        assert k not in net, k


def test_public_subnet_free_of_existing_networks():
    subnet = ipaddress.ip_network(SUBNET)
    hits = [t for t in TAKEN if subnet.overlaps(ipaddress.ip_network(t))]
    assert hits == [], hits
    assert subnet.is_private                                   # RFC1918: 不会遮住任何公网地址


def test_connector_address_outside_dynamic_range():
    subnet, dynamic, addr = (ipaddress.IPv4Network(SUBNET), ipaddress.IPv4Network(DYNAMIC),
                             ipaddress.IPv4Address(CONNECTOR))
    assert dynamic.subnet_of(subnet)
    assert addr in subnet and addr not in dynamic              # 动态分配拿不到连接器的地址
    assert addr != ipaddress.ip_address(GATEWAY)
    assert ipaddress.ip_address(GATEWAY) in subnet and ipaddress.ip_address(GATEWAY) not in dynamic


def test_public_api_trusts_only_the_connector():
    api = PUB["services"]["api"]
    assert api["environment"]["SDTM_RAG_QUOTA_TRUSTED_PROXIES"] == CONNECTOR
    # 整个 environment 逐字钉住: 多出一个键 (例如放宽 FORWARDED_ALLOW_IPS) 也要过这里
    assert api["environment"] == {"SDTM_RAG_INSTANCE": "public", "SDTM_RAG_QUOTA_TRUSTED_PROXIES": CONNECTOR,
                                  "FORWARDED_ALLOW_IPS": "",
                                  "SDTM_RAG_RATE_LIMIT_ENABLED": "true", "SDTM_RAG_RATE_LIMIT_PER_MIN": "60",
                                  "SDTM_RAG_RATE_LIMIT_BURST": "20"}
    # 值都写成字符串: YAML 里裸写 true / 60 会被 compose 当成布尔和整数再转回来, 字符串最不含糊
    assert all(isinstance(v, str) for v in api["environment"].values())
    # 这些键只属于公开实例: 私有站的 compose 里一个都没有
    priv_env = [k for svc in (PRIV["x-common"], *PRIV["services"].values()) for k in (svc.get("environment") or {})]
    assert not set(priv_env) & set(api["environment"]), priv_env
    assert api["networks"] == ["public"]                       # 动态地址, 不占静态位
    # 应用自己的启动自检也认这个值 (单主机)
    from server.auth import _check_public_trusted

    _check_public_trusted(api["environment"]["SDTM_RAG_QUOTA_TRUSTED_PROXIES"])
    with pytest.raises(RuntimeError, match="too broad"):
        _check_public_trusted(SUBNET)


# ── compose.tunnel.yml: 连接器 ──────────────────────────────────────────────

def _cf():
    return TUN["services"]["cloudflared"]


def test_tunnel_is_a_separate_project_with_one_service():
    assert set(TUN["services"]) == {"cloudflared"}
    assert TUN["name"] == "sdtm-rag-public-tunnel"
    assert TUN["name"] not in (PUB["name"], PRIV["name"])
    names = {s["container_name"] for s in (*PRIV["services"].values(), *PUB["services"].values())}
    assert _cf()["container_name"] == "sdtm-rag-public-cloudflared"
    assert _cf()["container_name"] not in names


def test_tunnel_joins_the_public_network_at_the_static_address():
    net = TUN["networks"]["public"]
    assert net == {"name": NET_NAME, "external": True}
    assert net["name"] == PUB["networks"]["public"]["name"]
    assert _cf()["networks"] == {"public": {"ipv4_address": CONNECTOR}}
    assert _cf()["networks"]["public"]["ipv4_address"] == \
        PUB["services"]["api"]["environment"]["SDTM_RAG_QUOTA_TRUSTED_PROXIES"]


def test_tunnel_no_host_exposure_and_least_privilege():
    cf = _cf()
    for k in ("ports", "expose", "network_mode", "privileged", "cap_add", "pid", "ipc", "extra_hosts",
              "links", "devices", "profiles", "depends_on"):
        assert k not in cf, k
    assert cf["cap_drop"] == ["ALL"]
    assert cf["security_opt"] == ["no-new-privileges:true"]
    assert cf["read_only"] is True
    assert cf["user"] == "65532:65532"
    assert cf["restart"] == "unless-stopped"


def test_tunnel_image_pinned_by_version_and_digest():
    m = re.fullmatch(r"cloudflare/cloudflared:(\d{4})\.(\d{1,2})\.(\d+)@sha256:[0-9a-f]{64}", _cf()["image"])
    assert m, _cf()["image"]
    assert tuple(int(x) for x in m.groups()) >= (2025, 4, 0)   # TUNNEL_TOKEN_FILE 自 2025.4.0 起支持


def test_tunnel_token_only_via_readonly_file():
    cf = _cf()
    # 值会出现在 docker inspect / compose config 里的三条路都不许走
    assert "env_file" not in cf
    assert cf["environment"] == {"TUNNEL_TOKEN_FILE": TOKEN_IN_CONTAINER, "TUNNEL_EDGE_IP_VERSION": "4",
                                 "TUNNEL_METRICS": "127.0.0.1:20241"}
    assert "TUNNEL_TOKEN" not in cf["environment"]
    assert cf["command"] == ["tunnel", "--no-autoupdate", "run"]
    assert not [a for a in cf["command"] if a.startswith("--token")]
    assert cf["volumes"] == [{"type": "bind", "source": TOKEN_HOST, "target": TOKEN_IN_CONTAINER,
                              "read_only": True, "bind": {"create_host_path": False}}]
    assert cf["volumes"][0]["target"] == cf["environment"]["TUNNEL_TOKEN_FILE"]
    # 放在虚拟机本地盘 (和公开实例的 .env 同一个 root 700 目录下), 不在 mini 能看到的数据挂载里
    env_dir = Path(next(v["source"] for v in PUB["services"]["api"]["volumes"] if v["target"] == "/app/.env")).parent
    assert Path(TOKEN_HOST).is_relative_to(env_dir) and str(env_dir) == "/opt/sdtm-rag-public"
    data_root = next(v["source"] for v in PUB["services"]["api"]["volumes"] if v["target"] == "/app/data")
    assert not TOKEN_HOST.startswith(data_root)


def test_no_token_shaped_string_in_deploy_files():
    # 隧道 token 是 base64 的 JSON, 以 eyJ 开头
    files = [PUB_PATH, TUN_PATH, *sorted(p for p in (ROOT / "deploy/public-net").iterdir() if p.is_file())]
    assert len(files) >= 5, files
    for f in files:
        assert not re.search(r"eyJ[A-Za-z0-9_-]{16,}", f.read_text()), f


# ── isolation.nft ───────────────────────────────────────────────────────────

def _chain(name: str) -> list[str]:
    m = re.search(rf"chain {name} \{{(.*?)\n\t\}}", NFT, re.S)
    assert m, f"chain {name} not found"
    return [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]


def _blocked() -> list:
    m = re.search(r"set blocked4 \{.*?elements = \{(.*?)\}", NFT, re.S)
    assert m
    nets = [ipaddress.ip_network(x.strip()) for x in m.group(1).split(",") if x.strip()]
    assert len(nets) >= 8, nets                                # 抽取端失效 ⇒ 下面的断言永真
    return nets


def test_nft_blocked_set_exact():
    # 整个集合逐字钉住: 下面两条按地址抽样, 样本没覆盖到的段被删掉时抽样测不出来
    assert [str(n) for n in _blocked()] == [
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
        "192.0.0.0/24", "192.168.0.0/16", "198.18.0.0/15", "224.0.0.0/4", "240.0.0.0/4"]


def test_nft_touches_only_its_own_table():
    assert not re.search(r"\bflush\b", NFT)                    # flush ruleset = 全机容器断网
    tables = re.findall(r"^\s*(?:delete\s+)?table\s+(\S+)\s+(\S+)", NFT, re.M)
    assert tables == [("inet", NFT_TABLE)] * 3, tables         # 建 / 删 / 定义, 都是自己这张
    assert re.findall(r"^\s*delete\s+(\S+)", NFT, re.M) == ["table"]
    for word in ("DOCKER", "docker", "insert rule", "add rule"):
        assert word not in NFT, word


def test_nft_chains_hook_before_docker_and_keep_policy_accept():
    # policy drop 会丢掉全机的转发 / 进站流量; 本表只做减法
    assert _chain("forward")[0] == "type filter hook forward priority -10; policy accept;"
    assert _chain("input")[0] == "type filter hook input priority -10; policy accept;"
    assert re.findall(r"\bhook (\w+)", NFT) == ["forward", "input"]
    assert "policy drop" not in NFT


def test_nft_forward_rules_exact_and_ordered():
    rules = _chain("forward")[1:]
    assert rules == [
        f'iifname "{BRIDGE}" oifname "{BRIDGE}" accept',
        f"ip saddr {SUBNET} ip daddr {SUBNET} accept",
        f'iifname "{BRIDGE}" ip daddr @blocked4 counter drop',
        f"ip saddr {SUBNET} ip daddr @blocked4 counter drop",
        f'iifname "{BRIDGE}" meta nfproto ipv6 counter drop',
    ], rules
    # 同网络放行必须在丢弃之前: 公开子网自己就在 10/8 里
    assert ipaddress.IPv4Network(SUBNET).subnet_of(ipaddress.IPv4Network("10.0.0.0/8"))
    first_drop = min(i for i, r in enumerate(rules) if r.endswith("drop"))
    assert all(i < first_drop for i, r in enumerate(rules) if r.endswith("accept"))


def test_nft_input_rules_exact_and_ordered():
    # 源地址那条不含回环: 虚拟机自己连网关地址 (10.201.8.1) 走 lo, 源地址也在这个网段里;
    # 不排除的话, 探测的对照侧永远连不上网关, 例行核对永远是「无结论」
    assert _chain("input")[1:] == [
        "ct state established,related accept",
        f'iifname "{BRIDGE}" counter drop',
        f'iifname != "lo" ip saddr {SUBNET} counter drop',
    ]


def test_nft_names_match_compose():
    assert set(re.findall(r'[io]ifname (?:!= )?"([^"]+)"', NFT)) == {BRIDGE, "lo"}
    assert re.findall(r'[io]ifname != "([^"]+)"', NFT) == ["lo"]
    assert PUB["networks"]["public"]["driver_opts"]["com.docker.network.bridge.name"] == BRIDGE
    assert set(re.findall(r"ip [sd]addr (\d[\d./]+)", NFT)) == {SUBNET}
    assert PUB["networks"]["public"]["ipam"]["config"][0]["subnet"] == SUBNET


@pytest.mark.parametrize("addr", [
    GATEWAY,               # 公开网桥的网关 = 虚拟机本机
    "192.168.5.15",        # 虚拟机网卡
    "192.168.5.2",         # Lima 宿主网关 (通到 mini 本机)
    "192.168.64.1",        # mini 在虚拟机网桥上的地址
    "192.168.100.58",      # 局域网: 镜像仓库 / Gitea
    "192.168.2.1", "192.168.3.1",
    "172.22.0.2",          # 同机别的 docker 网络 (含 DNAT 之后的目的地址)
    "172.17.0.1", "172.31.255.254", "192.168.16.5",
    "169.254.169.254",     # 链路本地 / 元数据
    "100.64.0.1", "127.0.0.1", "10.0.0.1", "224.0.0.251",
])
def test_nft_blocks_private_destinations(addr):
    assert any(ipaddress.ip_address(addr) in n for n in _blocked()), addr


@pytest.mark.parametrize("addr", [
    "198.41.192.167", "198.41.200.13",    # Cloudflare 隧道接入点 (官方文档列的地址, 2026-11-28 查)
    "1.1.1.1", "8.8.8.8", "104.18.0.1", "160.79.104.10", "172.32.0.1", "172.15.255.255", "192.167.0.1",
    "198.17.255.255", "198.20.0.1", "11.0.0.1", "100.63.255.255", "100.128.0.1",
])
def test_nft_leaves_public_destinations_alone(addr):
    assert not any(ipaddress.ip_address(addr) in n for n in _blocked()), addr


def test_isolation_unit_loads_the_ruleset_before_docker():
    unit = _strip_comments(UNIT_PATH.read_text())
    assert "Before=docker.service" in unit
    assert "ExecStart=/usr/sbin/nft -f /etc/sdtm-rag-public/isolation.nft" in unit
    # 前缀 - : 表已经不在时停 / 重启单元不算失败 (演练的回退和「规则装不回去」的验证都会走到)
    assert f"ExecStop=-/usr/sbin/nft delete table inet {NFT_TABLE}" in unit
    assert len(re.findall(r"^Exec\w+=", unit, re.M)) == 3     # Start / Reload / Stop, 没有别的
    assert "RemainAfterExit=yes" in unit and "Type=oneshot" in unit
    assert "WantedBy=multi-user.target" in unit                # 没有它 enable 不生效, 开机不装规则
    assert "flush" not in unit
    # 没有硬依赖: 规则文件出错不该拖垮同机的私有站 (兜底是巡检单元)
    for k in ("RequiredBy=", "Requires=", "ConditionPathExists=", "After=docker.service"):
        assert k not in unit, k


WATCH_CMD = ("/usr/sbin/nft list table inet sdtm_rag_public_isolation >/dev/null 2>&1 || echo \"isolation table was missing\"; "
             "/usr/sbin/nft -f /etc/sdtm-rag-public/isolation.nft && exit 0; sleep 3; "
             "/usr/sbin/nft -f /etc/sdtm-rag-public/isolation.nft && exit 0; "
             "echo \"isolation ruleset reload failed twice: stopping the tunnel connector\"; "
             "/usr/bin/docker stop sdtm-rag-public-cloudflared; exit 1")


def _watch_command() -> str:
    starts = [ln for ln in _strip_comments(WATCH_PATH.read_text()).splitlines() if ln.startswith("ExecStart=")]
    assert len(starts) == 1, starts
    m = re.fullmatch(r"ExecStart=/bin/sh -c '(.*)'", starts[0])
    assert m, starts[0]
    # systemd 会展开 % 和 $, 把反斜杠当转义; 单引号里出现单引号会提前结束。命令里一个都不能有
    assert not set(m.group(1)) & set("%$\\'"), m.group(1)
    return m.group(1)


def test_isolation_watchdog_command_and_timer_pinned():
    assert _watch_command() == WATCH_CMD
    assert "/etc/sdtm-rag-public/isolation.nft" in _strip_comments(UNIT_PATH.read_text())   # 与装入单元同一份规则文件
    assert NFT_TABLE in WATCH_CMD and _cf()["container_name"] in WATCH_CMD
    watch = _strip_comments(WATCH_PATH.read_text())
    assert "Type=oneshot" in watch and "flush" not in watch
    timer = _strip_comments(TIMER_PATH.read_text())
    # 按墙上时钟每分钟: OnUnitActiveSec 在巡检失败退出后可能不再触发
    assert "OnBootSec=20s" in timer and "OnCalendar=minutely" in timer and "AccuracySec=5s" in timer
    assert "OnUnitActiveSec" not in timer and "OnUnitInactiveSec" not in timer
    assert "WantedBy=timers.target" in timer
    assert TIMER_PATH.stem == WATCH_PATH.stem                  # timer 按同名触发 service


_LIST = "nft list table inet sdtm_rag_public_isolation"
_LOAD = "nft -f /etc/sdtm-rag-public/isolation.nft"
_STOP = "docker stop sdtm-rag-public-cloudflared"
_MISSING = "isolation table was missing\n"
_FAILED = "isolation ruleset reload failed twice: stopping the tunnel connector\n"


@pytest.mark.parametrize(("table_present", "loads_ok", "want_rc", "want_calls", "want_out"), [
    (True, [True], 0, [_LIST, _LOAD], ""),                                   # 平时: 重装一次就成
    (False, [True], 0, [_LIST, _LOAD], _MISSING),                            # 表被删了: 装回, 不碰连接器
    (True, [False, True], 0, [_LIST, _LOAD, _LOAD], ""),                     # 第一次撞上别人在改规则: 再试一次就成
    (True, [False, False], 1, [_LIST, _LOAD, _LOAD, _STOP], _FAILED),        # 两次都不行: 停连接器
    (False, [False, False], 1, [_LIST, _LOAD, _LOAD, _STOP], _MISSING + _FAILED),
])
def test_isolation_watchdog_behaviour(tmp_path, table_present, loads_ok, want_rc, want_calls, want_out):
    """把单元里的命令原样拿出来跑, 只把 nft / docker 换成记录调用的桩 (并把两次重装之间的等待缩成 0 秒):
    每次都重装; 重装成功就此结束, 不碰连接器; 连续两次失败才停连接器并以失败退出。"""
    import subprocess

    log, results = tmp_path / "calls.log", tmp_path / "load_results"
    results.write_text("".join(f"{0 if ok else 1}\n" for ok in loads_ok))
    (tmp_path / "nft").write_text(
        f'#!/bin/sh\necho "nft $*" >> {log}\n'
        f'if [ "$1" = list ]; then exit {0 if table_present else 1}; fi\n'
        f'n=$(grep -c "^nft -f" {log})\nexit $(sed -n "${{n}}p" {results})\n')   # 第 n 次重装的结果
    (tmp_path / "docker").write_text(f'#!/bin/sh\necho "docker $*" >> {log}\n')
    for name in ("nft", "docker"):
        (tmp_path / name).chmod(0o755)
    real = _watch_command()
    assert real.count("sleep 3; ") == 1
    cmd = (real.replace("/usr/sbin/nft", str(tmp_path / "nft")).replace("/usr/bin/docker", str(tmp_path / "docker"))
           .replace("sleep 3; ", "sleep 0; "))
    assert "/usr/sbin/" not in cmd and "/usr/bin/" not in cmd
    r = subprocess.run(["/bin/sh", "-c", cmd], capture_output=True, text=True)
    assert (r.returncode, log.read_text().splitlines(), r.stdout) == (want_rc, want_calls, want_out), r.stderr


def test_dockerfile_cmd_does_not_override_forwarded_allow_ips():
    # 命令行参数会压过环境变量: Dockerfile 的 CMD 一旦带上这两个选项, compose 里置空的 FORWARDED_ALLOW_IPS 就不作数了
    cmd = [ln for ln in (ROOT / "deploy/container/Dockerfile").read_text().splitlines() if ln.startswith("CMD ")]
    assert len(cmd) == 1 and "uvicorn" in cmd[0], cmd
    assert "forwarded-allow-ips" not in cmd[0] and "proxy-headers" not in cmd[0]
    assert "command" not in PUB["services"]["api"]             # 公开 compose 也没有另起命令


TOKEN_OK = "eyJ" + "hIjoiZmFrZS1mb3ItdGVzdCIsInQiOiJ4IiwicyI6InkrLz0ifQ" * 3 + "=="


@pytest.mark.parametrize(("typed", "written"), [
    (TOKEN_OK, True),
    ("eyJ" + "A+/=_-" * 30, True),                       # token 字符集里的符号都放行
    ("sudo chown 65532:65532 /opt/x", False),           # 整块粘贴时被吞进来的下一行命令
    ("cloudflared service install " + TOKEN_OK, False),  # 连着安装命令一起复制了
    (TOKEN_OK[:60] + " " + TOKEN_OK[60:], False),        # 中间混进空格
    (TOKEN_OK + ";id", False),
    ("eyJ", False), (TOKEN_OK[:99], False),              # 复制不全
    ("A" * 150, False),                                  # 字符都合法但不是 token (不以 eyJ 开头)
    ("", False),
])
def test_owner_token_command_validates_before_writing(tmp_path, typed, written):
    """操作说明第 2 步的那条命令原样拿出来跑 (目录换成临时目录, install / chown 换成桩): 只有像 token 的输入才写文件。"""
    import subprocess

    doc = (ROOT / "docs/plans/P3_4_tunnel_owner_steps.md").read_text()
    lines = [ln for ln in doc.splitlines() if ln.startswith("sudo bash -c '")]
    assert len(lines) == 1, lines
    body = lines[0][len("sudo bash -c '"):-1]
    assert lines[0].endswith("'") and "'" not in body
    assert "eyJ*" in body and TOKEN_HOST == "/opt/sdtm-rag-public/cloudflared/tunnel-token"
    # 不回显 (-s) 和收紧新建文件权限 (umask) 在管道喂输入的测试里观察不到 (-s 只对终端起作用), 钉字面
    assert 'IFS= read -rsp "' in body and body.startswith("umask 077; ")
    assert body.count("/opt/sdtm-rag-public/cloudflared") == 1 and "f=$d/tunnel-token" in body
    out_dir, stubs = tmp_path / "cf", tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "install").write_text('#!/bin/sh\nfor a; do last=$a; done\nmkdir -p "$last"\n')
    (stubs / "chown").write_text("#!/bin/sh\nexit 0\n")
    for name in ("install", "chown"):
        (stubs / name).chmod(0o755)
    import os

    r = subprocess.run(["bash", "-c", body.replace("/opt/sdtm-rag-public/cloudflared", str(out_dir))],
                       input=typed + "\n", capture_output=True, text=True,
                       env={**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}"})
    token_file = out_dir / "tunnel-token"
    if written:
        assert r.returncode == 0, r.stdout + r.stderr
        assert token_file.read_text() == typed + "\n"
        assert token_file.stat().st_mode & 0o777 == 0o400
    else:
        assert r.returncode == 1 and not token_file.exists(), r.stdout + r.stderr
        assert "没有写入" in r.stdout


# ── isolation_probe.py: 三态判定 ────────────────────────────────────────────

@pytest.fixture(scope="module")
def probe():
    spec = importlib.util.spec_from_file_location("isolation_probe", PROBE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True   # 不在 deploy/ 下留 __pycache__
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
    return mod


def test_probe_classifies_each_failure_mode(probe):
    import errno
    import socket

    assert probe.classify(None) == "open"
    assert probe.classify(ConnectionRefusedError()) == "refused"
    assert probe.classify(TimeoutError()) == "timeout"
    assert probe.classify(OSError(errno.EHOSTUNREACH, "x")) == "unreachable"
    assert probe.classify(OSError(errno.ENETUNREACH, "x")) == "unreachable"
    assert probe.classify(socket.gaierror(8, "x")) == "error:gaierror"
    assert probe.classify(OSError(errno.EACCES, "x")) == "error:PermissionError"
    # 拒绝连接 = 包到了对方, 必须算可达; 超时才算被挡
    assert {"open", "refused"} == probe.REACHABLE and {"timeout", "unreachable"} == probe.BLOCKED


def test_probe_uses_the_connect_function_per_target(probe):
    seen = []

    class _Sock:
        def close(self):
            seen.append("closed")

    def connect(addr, timeout):
        seen.append((addr, timeout))
        if addr[0] == "10.0.0.9":
            raise ConnectionRefusedError
        if addr[0] == "10.0.0.8":
            raise TimeoutError
        return _Sock()

    out = probe.probe(["10.0.0.9:22", "10.0.0.8:443"], ["example.org:443"], 1.5, connect, lambda: "10.201.8.130")
    assert out == {"src": "10.201.8.130", "lan": {"10.0.0.9:22": "refused", "10.0.0.8:443": "timeout"},
                   "egress": {"example.org:443": "open"}}
    assert (("10.0.0.8", 443), 1.5) in seen and seen[-1] == "closed"
    with pytest.raises(ValueError):
        probe.split_target("no-port")


LAN, NET = "192.168.100.58:443", "api.anthropic.com:443"


@pytest.mark.parametrize(("iso_lan", "ctl_lan", "iso_net", "want"), [
    ("timeout", "open", "open", "PASS"),
    ("unreachable", "refused", "open", "PASS"),       # 对照侧被拒绝 = 目标活着
    ("open", "open", "open", "FAIL"),                 # 隔离侧能连上内网
    ("refused", "open", "open", "FAIL"),              # 被拒绝也是到达了
    ("timeout", "timeout", "open", "INCONCLUSIVE"),   # 对照也连不上: 证明不了隔离
    ("timeout", "unreachable", "open", "INCONCLUSIVE"),
    ("error:gaierror", "open", "open", "INCONCLUSIVE"),
    ("timeout", "open", "timeout", "FAIL"),           # 外网不通: 可能整个容器没网
    ("timeout", "open", "refused", "FAIL"),
    ("open", "timeout", "open", "FAIL"),              # FAIL 压过无结论
])
def test_probe_judge_three_states(probe, iso_lan, ctl_lan, iso_net, want):
    verdict, lines = probe.judge({"lan": {LAN: iso_lan}, "egress": {NET: iso_net}}, {"lan": {LAN: ctl_lan}})
    assert verdict == want, lines


def test_probe_judge_refuses_to_pass_on_missing_evidence(probe):
    ok_iso = {"lan": {LAN: "timeout"}, "egress": {NET: "open"}}
    assert probe.judge(ok_iso, {"lan": {LAN: "open"}})[0] == "PASS"
    assert probe.judge({"lan": {}, "egress": {NET: "open"}}, {"lan": {}})[0] == "INCONCLUSIVE"       # 没验内网
    assert probe.judge({"lan": {LAN: "timeout"}, "egress": {}}, {"lan": {LAN: "open"}})[0] == "INCONCLUSIVE"
    assert probe.judge(ok_iso, {"lan": {}})[0] == "INCONCLUSIVE"                                     # 对照没跑这个目标
    assert probe.judge(ok_iso, {"lan": {LAN: "open", "10.9.9.9:1": "open"}})[0] == "INCONCLUSIVE"
    two = {"lan": {LAN: "timeout", "192.168.5.2:22": "open"}, "egress": {NET: "open"}}
    assert probe.judge(two, {"lan": {LAN: "open", "192.168.5.2:22": "open"}})[0] == "FAIL"           # 一个漏就是 FAIL


def test_probe_judge_requires_reachable_before_the_rules(probe):
    """首次装规则: 装之前就连不上的目标, 装之后连不上不能记在规则头上。"""
    iso, ctl = {"lan": {LAN: "timeout"}, "egress": {NET: "open"}}, {"lan": {LAN: "open"}}
    assert probe.judge(iso, ctl, before={"lan": {LAN: "open"}})[0] == "PASS"
    assert probe.judge(iso, ctl, before={"lan": {LAN: "refused"}})[0] == "PASS"
    assert probe.judge(iso, ctl, before={"lan": {LAN: "timeout"}})[0] == "INCONCLUSIVE"
    assert probe.judge(iso, ctl, before={"lan": {}})[0] == "INCONCLUSIVE"                # 装之前没测这个目标
    # 装之前多测了一个目标 (装之后没测它): 两份观测不是同一批目标, 不给 PASS
    assert probe.judge(iso, ctl, before={"lan": {LAN: "open", "192.168.5.2:22": "open"}})[0] == "INCONCLUSIVE"
    assert probe.judge(iso, ctl, before=None)[0] == "PASS"                                # 例行核对不带 before
    leak = {"lan": {LAN: "open"}, "egress": {NET: "open"}}
    assert probe.judge(leak, ctl, before={"lan": {LAN: "open"}})[0] == "FAIL"


def test_probe_judge_checks_where_the_isolated_side_ran(probe):
    ctl = {"lan": {LAN: "open"}}

    def iso(src):
        return {"src": src, "lan": {LAN: "timeout"}, "egress": {NET: "open"}}

    assert probe.judge(iso("10.201.8.130"), ctl, isolated_net=SUBNET)[0] == "PASS"
    assert probe.judge(iso("172.17.0.3"), ctl, isolated_net=SUBNET)[0] == "INCONCLUSIVE"   # 跑在别的网络里
    assert probe.judge(iso("unknown"), ctl, isolated_net=SUBNET)[0] == "INCONCLUSIVE"
    no_src = {"lan": {LAN: "timeout"}, "egress": {NET: "open"}}
    assert probe.judge(no_src, ctl, isolated_net=SUBNET)[0] == "INCONCLUSIVE"
    assert probe.judge(no_src, ctl)[0] == "PASS"                                         # 不要求时不看
    # 「装规则前」那份观测也得是在公开网络里取的: 在虚拟机本机取的话, 每个目标都可达, 「装之前可达」被假满足
    good, before_lan = iso("10.201.8.130"), {"lan": {LAN: "open"}}
    assert probe.judge(good, ctl, before={"src": "10.201.8.131", **before_lan}, isolated_net=SUBNET)[0] == "PASS"
    assert probe.judge(good, ctl, before={"src": "192.168.5.15", **before_lan}, isolated_net=SUBNET)[0] == "INCONCLUSIVE"
    assert probe.judge(good, ctl, before=before_lan, isolated_net=SUBNET)[0] == "INCONCLUSIVE"       # 没记源地址


def test_probe_source_address_is_what_the_kernel_would_use(probe, monkeypatch):
    """source_address 报的必须是内核为出站选的那个地址 (UDP 套接字 connect 之后的本端地址), 不是写死的值。"""
    calls = []

    class _Udp:
        def __init__(self, family, kind):
            calls.append(("socket", family, kind))

        def connect(self, addr):
            calls.append(("connect", addr))

        def getsockname(self):
            return ("10.201.8.177", 40000)

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(probe.socket, "socket", _Udp)
    assert probe.source_address() == "10.201.8.177"
    assert calls == [("socket", probe.socket.AF_INET, probe.socket.SOCK_DGRAM), ("connect", ("192.0.2.1", 9)), ("close",)]

    class _NoRoute(_Udp):
        def connect(self, addr):
            raise OSError(101, "Network is unreachable")

    monkeypatch.setattr(probe.socket, "socket", _NoRoute)
    assert probe.source_address() == "unknown"


def test_probe_cli_roundtrip_and_exit_codes(probe, tmp_path, capsys):
    iso, ctl = tmp_path / "iso.json", tmp_path / "ctl.json"
    ctl.write_text(json.dumps({"lan": {LAN: "open"}, "egress": {}}))
    cases = [({"lan": {LAN: "timeout"}, "egress": {NET: "open"}}, 0),
             ({"lan": {LAN: "open"}, "egress": {NET: "open"}}, 1),
             ({"lan": {LAN: "timeout"}, "egress": {}}, 2)]
    for body, code in cases:
        iso.write_text(json.dumps(body))
        assert probe.main(["judge", "--isolated", str(iso), "--control", str(ctl)]) == code
    assert capsys.readouterr().out.rstrip().endswith("结论: INCONCLUSIVE")
    assert probe.main(["probe"]) == 0                         # 没给目标: 空观测, 交给 judge 判无结论
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"src", "lan", "egress"} and out["lan"] == {} and out["egress"] == {}
    # --before / --isolated-net 经命令行生效
    iso.write_text(json.dumps({"src": "10.201.8.130", "lan": {LAN: "timeout"}, "egress": {NET: "open"}}))
    before = tmp_path / "before.json"
    before.write_text(json.dumps({"src": "10.201.8.131", "lan": {LAN: "open"}}))
    base = ["judge", "--isolated", str(iso), "--control", str(ctl)]
    assert probe.main([*base, "--before", str(before), "--isolated-net", SUBNET]) == 0
    assert probe.main([*base, "--isolated-net", "10.99.0.0/24"]) == 2
    before.write_text(json.dumps({"lan": {LAN: "timeout"}}))
    assert probe.main([*base, "--before", str(before)]) == 2
    capsys.readouterr()
