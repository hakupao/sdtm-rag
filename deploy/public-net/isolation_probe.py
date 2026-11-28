"""公开站网络隔离探测 (P3.4b)。只用标准库; deploy/ 不进镜像, 所以经 stdin 送进容器跑。

两步:
  probe  对每个 host:port 做一次 TCP 连接, 把观测 (连同本机出站用的源地址) 打成一行 JSON。
         在隔离网络里的一次性容器里跑一遍, 再在不受隔离的地方 (虚拟机本机) 用同一批目标跑一遍作对照。
  judge  拿两份观测给结论, 退出码 0 = PASS, 1 = FAIL, 2 = INCONCLUSIVE。
         --isolated-net: 隔离侧的源地址必须落在这个网段里 (证明它确实是在公开网络里跑的)。
         --before: 首次装规则时用, 给「规则还没装时」的隔离侧观测; 装之前就连不上的目标证明不了是规则挡的, 记无结论。
                   同时给了 --isolated-net 的话, 这份观测的源地址也必须在那个网段里。

为什么要对照: 「连不上」有两种原因 —— 被隔离规则挡了, 或者那个地址本来就没人在听。只看隔离侧, 两者
长得一样。所以每个内网目标必须在对照侧可达, 结论才算数; 对照侧也连不上的目标记「无结论」, 不算通过。
「连接被拒绝」(对方回了 RST) 说明包到了对方, 算可达。外网目标反过来: 隔离侧必须连得上, 否则可能是
整个容器没网, 「内网全不通」就没有意义。

只测 TCP 连接: UDP / ICMP / IPv6 不在探测范围 (规则本身不分协议, 见 isolation.nft)。
用法见 docs/plans/P3_4_tunnel_drill.md。
"""
from __future__ import annotations

import argparse
import errno
import ipaddress
import json
import socket
import sys

REACHABLE = frozenset({"open", "refused"})
BLOCKED = frozenset({"timeout", "unreachable"})
_UNREACHABLE_ERRNOS = frozenset({errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ENETDOWN, errno.EHOSTDOWN})


def classify(exc: BaseException | None) -> str:
    """一次连接的结果 → open / refused / timeout / unreachable / error:<类名>。"""
    if exc is None:
        return "open"
    if isinstance(exc, ConnectionRefusedError):
        return "refused"
    if isinstance(exc, TimeoutError):   # socket.timeout 是它的别名
        return "timeout"
    if isinstance(exc, OSError) and exc.errno in _UNREACHABLE_ERRNOS:
        return "unreachable"
    return f"error:{type(exc).__name__}"


def split_target(target: str) -> tuple[str, int]:
    host, sep, port = target.rpartition(":")
    if not sep or not host or not port.isdigit():
        raise ValueError(f"目标须写成 host:port, 收到 {target!r}")
    return host, int(port)


def connect_state(target: str, timeout: float, connect=socket.create_connection) -> str:
    host, port = split_target(target)
    try:
        connect((host, port), timeout=timeout).close()
    except Exception as e:   # noqa: BLE001 — 每种失败都要归类成一个状态, 不能让一个目标中断整批
        return classify(e)
    return "open"


def source_address() -> str:
    """本机出站用的源地址。UDP 套接字 connect 只选路不发包; 没有路由时返回 "unknown"。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        return s.getsockname()[0]
    except OSError:
        return "unknown"
    finally:
        s.close()


def probe(lan: list[str], egress: list[str], timeout: float, connect=socket.create_connection,
          src=source_address) -> dict:
    return {"src": src(),
            "lan": {t: connect_state(t, timeout, connect) for t in lan},
            "egress": {t: connect_state(t, timeout, connect) for t in egress}}


def _in_net(addr: str, net: str) -> bool:
    try:
        return ipaddress.ip_address(addr) in ipaddress.ip_network(net)
    except ValueError:
        return False


def judge(isolated: dict, control: dict, before: dict | None = None,
          isolated_net: str | None = None) -> tuple[str, list[str]]:
    """(结论, 逐条说明)。结论: PASS / FAIL / INCONCLUSIVE。"""
    lines, fail, unsure = [], False, False
    iso_lan, ctl_lan = isolated.get("lan", {}), control.get("lan", {})
    if isolated_net is not None:
        src = isolated.get("src", "missing")
        if _in_net(src, isolated_net):
            lines.append(f"PASS          隔离侧源地址 {src} 在 {isolated_net} 里")
        else:
            unsure = True
            lines.append(f"INCONCLUSIVE  隔离侧源地址 {src} 不在 {isolated_net} 里: 这份观测不是在公开网络里取的")
    if before is not None and isolated_net is not None and not _in_net(before.get("src", "missing"), isolated_net):
        unsure = True
        lines.append(f"INCONCLUSIVE  装规则前那份观测的源地址 {before.get('src', 'missing')} 不在 {isolated_net} 里: "
                     "它不是在公开网络里取的, 「装之前可达」不算数")
    if before is not None and set(before.get("lan", {})) != set(iso_lan):
        unsure = True
        lines.append("INCONCLUSIVE  装规则前后的内网目标不一致: 只在一侧出现 "
                     f"{sorted(set(before.get('lan', {})) ^ set(iso_lan))}")
    if not iso_lan:
        unsure = True
        lines.append("INCONCLUSIVE  没有内网目标: 什么也没验")
    if set(iso_lan) != set(ctl_lan):
        unsure = True
        lines.append(f"INCONCLUSIVE  两侧的内网目标不一致: 只在一侧出现 {sorted(set(iso_lan) ^ set(ctl_lan))}")
    for target in sorted(iso_lan):
        iso, ctl = iso_lan[target], ctl_lan.get(target, "missing")
        if iso in REACHABLE:
            fail = True
            lines.append(f"FAIL          {target}: 隔离侧 {iso} (能到达内网)")
        elif iso not in BLOCKED:
            unsure = True
            lines.append(f"INCONCLUSIVE  {target}: 隔离侧 {iso} (既不是可达也不是被挡)")
        elif ctl not in REACHABLE:
            unsure = True
            lines.append(f"INCONCLUSIVE  {target}: 隔离侧 {iso}, 但对照侧也是 {ctl} (目标没在听, 证明不了隔离)")
        elif before is not None and before.get("lan", {}).get(target, "missing") not in REACHABLE:
            unsure = True
            lines.append(f"INCONCLUSIVE  {target}: 隔离侧 {iso}, 但装规则前就是 "
                         f"{before.get('lan', {}).get(target, 'missing')} (不是这套规则挡的, 换一个目标)")
        else:
            lines.append(f"PASS          {target}: 隔离侧 {iso}, 对照侧 {ctl}")
    iso_egress = isolated.get("egress", {})
    if not iso_egress:
        unsure = True
        lines.append("INCONCLUSIVE  没有外网目标: 分不清「被隔离」和「整个容器没网」")
    for target in sorted(iso_egress):
        state = iso_egress[target]
        if state == "open":
            lines.append(f"PASS          {target}: 外网可达")
        else:
            fail = True
            lines.append(f"FAIL          {target}: 外网 {state} (需要的出站被挡, 或容器没网)")
    return ("FAIL" if fail else "INCONCLUSIVE" if unsure else "PASS"), lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe", help="连一遍, 输出观测 JSON")
    p.add_argument("--lan", action="append", default=[], metavar="HOST:PORT", help="应当被挡的内网目标 (可多次)")
    p.add_argument("--egress", action="append", default=[], metavar="HOST:PORT", help="应当可达的外网目标 (可多次)")
    p.add_argument("--timeout", type=float, default=4.0)
    j = sub.add_parser("judge", help="比较隔离侧与对照侧的观测")
    j.add_argument("--isolated", required=True, help="隔离侧 probe 输出的 JSON 文件")
    j.add_argument("--control", required=True, help="对照侧 probe 输出的 JSON 文件")
    j.add_argument("--before", help="规则装上之前隔离侧 probe 输出的 JSON 文件 (首次装规则时用)")
    j.add_argument("--isolated-net", help="隔离侧源地址必须落在的网段, 如 10.201.8.0/24")
    args = ap.parse_args(argv)
    if args.cmd == "probe":
        print(json.dumps(probe(args.lan, args.egress, args.timeout), ensure_ascii=False, sort_keys=True))
        return 0
    with open(args.isolated, encoding="utf-8") as f:
        isolated = json.load(f)
    with open(args.control, encoding="utf-8") as f:
        control = json.load(f)
    before = None
    if args.before:
        with open(args.before, encoding="utf-8") as f:
            before = json.load(f)
    verdict, lines = judge(isolated, control, before, args.isolated_net)
    print("\n".join(lines))
    print(f"结论: {verdict}")
    return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
