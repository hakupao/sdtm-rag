"""P3.4 变异验证 (docs/RULES.md 规则 5)。跑法 (仓根):

    .venv/bin/python .work/10_split_and_public/evidence/checkpoints/p3_step3.4_mutations.py

每个变异: 先比对磁盘 sha (与脚本启动时冻结的基线不符即拒跑) → 精确替换一处 (count 必须为 1) → 回读,
必须逐字等于「原文替换后」→ 跑测试 → finally 用启动时冻结的原始字节写回并再比 sha。
判定不只看退出码: 每个变异预登记「应该打红的用例」。killed = 有用例失败、没有 error、且打红的用例里有预登记的那条;
退出码非零但不满足这三条 (收集阶段报错 / 环境故障 / 红的是不相干的用例) 记 INVALID, 和存活一样算没通过。
记录 pytest 的 summary 行 + 预登记用例的第一条失败信息 (它的详情里第一条 E 行)。直接在工作区里改文件, 别人同时在用工作区时用 P34_MUT_ROOT 指到副本。
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# P34_MUT_ROOT: 指到仓库的一份副本上跑 (别人同时在用工作区时)。副本里要有 server/ tests/ deploy/ 等测试用到的目录。
ROOT = Path(os.environ.get("P34_MUT_ROOT") or Path(__file__).resolve().parents[4])
TESTS = ["tests/test_p3_4_public_https.py", "tests/test_deploy_public_tunnel.py",
         "tests/test_deploy_public_compose.py", "tests/test_p2_9_fixes.py"]
AUTH, CONF = "server/auth.py", "server/config.py"
PUB, TUN = "deploy/container/compose.public.yml", "deploy/container/compose.tunnel.yml"
NFT, UNIT = "deploy/public-net/isolation.nft", "deploy/public-net/sdtm-rag-public-isolation.service"
PROBE = "deploy/public-net/isolation_probe.py"
FLOOR = "deploy/public-net/image_floor_check.py"
OWNER = "docs/plans/P3_4_tunnel_owner_steps.md"
DOCKERFILE = "deploy/container/Dockerfile"
WATCH = "deploy/public-net/sdtm-rag-public-isolation-watch.service"
TIMER = "deploy/public-net/sdtm-rag-public-isolation-watch.timer"

MUTATIONS = [
    # (编号, 文件, 原文, 改成, 这条变异在验什么, 应该打红的用例名子串)
    ("A01", AUTH, "SecurityHeadersMiddleware, hsts=public)", "SecurityHeadersMiddleware, hsts=True)", "HSTS 漏到私有档", "test_private_responses_unchanged_no_hsts"),
    ("A02", AUTH, "SecurityHeadersMiddleware, hsts=public)", "SecurityHeadersMiddleware, hsts=False)", "公开档没有 HSTS", "test_public_every_response_carries_hsts"),
    ("A03", AUTH, '_HSTS = "max-age=31536000"', '_HSTS = "max-age=31536000; includeSubDomains"', "HSTS 波及子域", "test_public_every_response_carries_hsts"),
    ("A04", AUTH, "    if public and not secure:\n", "    if False:\n", "公开档可关 Secure", "test_public_refuses_insecure_visitor_cookie"),
    ("A05", AUTH, "    if public and not secure:\n", "    if not secure:\n", "Secure 强制漏到私有档", "test_private_visitor_cookie_not_secure_by_default"),
    ("A06", AUTH, "    if secure is None:\n        secure = public\n", "    if secure is None:\n        secure = True\n", "私有档默认带 Secure", "test_private_visitor_cookie_not_secure_by_default"),
    ("A07", AUTH, "if n.num_addresses != 1]", "if n.num_addresses > 256]", "公开档可信代理放宽回 /24", "test_public_install_refuses_trusted_network_wider_than_one_host"),
    ("A08", AUTH, "    if public:\n        _check_public_trusted(trusted)\n", "    if True:\n        _check_public_trusted(trusted)\n", "单主机约束漏到私有档", "test_private_trusted_proxies_breadth_unchanged"),
    ("A09", AUTH, "https_only=_is_public(settings),", "https_only=False,", "公开档 session cookie 不带 Secure", "test_session_cookie_secure_follows_tier"),
    ("A10", AUTH, "https_only=_is_public(settings),", "https_only=True,", "私有档 session cookie 带 Secure", "test_session_cookie_secure_follows_tier"),
    ("A11", AUTH, "        if not nets or not any(ipaddress.ip_address(peer) in n for n in nets):\n", "        if not nets:\n", "任何对端都能设 CF-Connecting-IP", "test_other_peers_cannot_set_the_visitor_ip"),
    ("A12", AUTH, '    return getattr(settings, "instance", "private") == "public"\n', "    return False\n", "档位判断恒为私有", "test_public_every_response_carries_hsts"),
    ("C01", CONF, 'load_dotenv(_SDTM_RAG_ROOT / ".env")', 'load_dotenv(_SDTM_RAG_ROOT / ".env", override=True)', ".env 压过 compose 的环境变量", "test_config_loads_dotenv_without_override"),
    ("P01", PUB, "SDTM_RAG_QUOTA_TRUSTED_PROXIES: 10.201.8.2", "SDTM_RAG_QUOTA_TRUSTED_PROXIES: 10.201.8.0/24", "compose 信整个子网", "test_public_api_trusts_only_the_connector"),
    ("P02", PUB, "        - subnet: 10.201.8.0/24", "        - subnet: 172.22.0.0/24", "子网撞私有站网段", "test_public_network_is_pinned"),
    ("P03", PUB, "          ip_range: 10.201.8.128/25\n", "", "动态分配可抢连接器地址", "test_public_network_is_pinned"),
    ("P04", PUB, "com.docker.network.bridge.name: br-sdtmpub", "com.docker.network.bridge.name: br-other", "网桥名与 nft 脱钩", "test_public_network_is_pinned"),
    ("P05", PUB, "    networks: [public]\n", '    networks: [public]\n    ports: ["8000:8000"]\n', "公开实例发布宿主端口", "test_public_no_host_exposure_or_escape_hatches"),
    ("P06", PUB, "    enable_ipv6: false\n", "    enable_ipv6: true\n", "公开网络开 IPv6", "test_public_network_is_pinned"),
    ("T01", TUN, "      TUNNEL_TOKEN_FILE: /etc/cloudflared/tunnel-token\n", "      TUNNEL_TOKEN_FILE: /etc/cloudflared/tunnel-token\n      TUNNEL_TOKEN: ${TUNNEL_TOKEN}\n", "token 走环境变量", "test_tunnel_token_only_via_readonly_file"),
    ("T02", TUN, 'command: ["tunnel", "--no-autoupdate", "run"]', 'command: ["tunnel", "--no-autoupdate", "run", "--token", "x"]', "token 走命令行", "test_tunnel_token_only_via_readonly_file"),
    ("T03", TUN, "    restart: unless-stopped\n", "    restart: unless-stopped\n    env_file: /opt/sdtm-rag-public/cloudflared/env\n", "token 走 env_file", "test_tunnel_token_only_via_readonly_file"),
    ("T04", TUN, "        ipv4_address: 10.201.8.2", "        ipv4_address: 10.201.8.3", "连接器地址与可信代理脱钩", "test_tunnel_joins_the_public_network_at_the_static_address"),
    ("T05", TUN, "    external: true\n", "", "连接器自建网络 (不是公开实例那张)", "test_tunnel_joins_the_public_network_at_the_static_address"),
    ("T06", TUN, "@sha256:55c7e3e8d89d5e8d20b75a82f3602cbf98e06db406e73e282073cfdc5a9a3af6", "", "镜像不钉摘要", "test_tunnel_image_pinned_by_version_and_digest"),
    ("T07", TUN, "        read_only: true\n        bind:", "        read_only: false\n        bind:", "token 文件可写挂载", "test_tunnel_token_only_via_readonly_file"),
    ("T08", TUN, "    cap_drop: [ALL]\n", "", "连接器保留 capability", "test_tunnel_no_host_exposure_and_least_privilege"),
    ("T09", TUN, "    mem_limit: 256m\n", '    mem_limit: 256m\n    ports: ["20241:20241"]\n', "连接器发布端口", "test_tunnel_no_host_exposure_and_least_privilege"),
    ("T10", TUN, "          create_host_path: false\n", "          create_host_path: true\n", "token 文件缺失时 docker 建空目录顶上", "test_tunnel_token_only_via_readonly_file"),
    ("N01", NFT, "delete table inet sdtm_rag_public_isolation\n", "delete table inet sdtm_rag_public_isolation\nflush ruleset\n", "清空全机规则", "test_nft_touches_only_its_own_table"),
    ("N02", NFT, "type filter hook forward priority -10; policy accept;", "type filter hook forward priority -10; policy drop;", "丢掉全机转发", "test_nft_chains_hook_before_docker_and_keep_policy_accept"),
    ("N03", NFT, '\t\tip saddr 10.201.8.0/24 ip daddr 10.201.8.0/24 accept\n\t\tiifname "br-sdtmpub" ip daddr @blocked4 counter drop\n', '\t\tiifname "br-sdtmpub" ip daddr @blocked4 counter drop\n\t\tip saddr 10.201.8.0/24 ip daddr 10.201.8.0/24 accept\n', "同网络放行排到丢弃之后", "test_nft_forward_rules_exact_and_ordered"),
    ("N04", NFT, "\t\t\t192.168.0.0/16,\n", "", "放过 192.168/16 (局域网 / 宿主)", "test_nft_blocks_private_destinations"),
    ("N05", NFT, "\t\t\t198.18.0.0/15,\n", "\t\t\t198.0.0.0/8,\n", "误挡 Cloudflare 隧道接入点", "test_nft_leaves_public_destinations_alone"),
    ("N06", NFT, '\t\tiifname "br-sdtmpub" counter drop\n', '\t\tiifname "br-other" counter drop\n', "nft 网桥名与 compose 脱钩", "test_nft_input_rules_exact_and_ordered"),
    ("N07", NFT, '\t\tiifname != "lo" ip saddr 10.201.8.0/24 counter drop\n', '\t\tiifname != "lo" ip saddr 10.201.9.0/24 counter drop\n', "nft 网段与 compose 脱钩", "test_nft_input_rules_exact_and_ordered"),
    ("N08", NFT, "\t\tct state established,related accept\n", "", "虚拟机连容器的回包被丢", "test_nft_input_rules_exact_and_ordered"),
    ("N09", NFT, '\t\tiifname "br-sdtmpub" ip daddr @blocked4 counter drop\n', "", "少一条转发丢弃", "test_nft_forward_rules_exact_and_ordered"),
    ("N10", NFT, "type filter hook input priority -10; policy accept;", "type filter hook input priority 10; policy accept;", "钩子排到 docker 之后", "test_nft_chains_hook_before_docker_and_keep_policy_accept"),
    ("U01", UNIT, "Before=docker.service", "After=docker.service", "规则晚于容器启动", "test_isolation_unit_loads_the_ruleset_before_docker"),
    ("U02", UNIT, "ExecStop=-/usr/sbin/nft delete table inet sdtm_rag_public_isolation", "ExecStop=-/usr/sbin/nft flush ruleset", "停单元时清空全机规则", "test_isolation_unit_loads_the_ruleset_before_docker"),
    ("R01", PROBE, 'REACHABLE = frozenset({"open", "refused"})', 'REACHABLE = frozenset({"open"})', "被拒绝不算可达", "test_probe_classifies_each_failure_mode"),
    ("R02", PROBE, "        elif ctl not in REACHABLE:\n", "        elif False:\n", "不看对照侧", "test_probe_judge_three_states"),
    ("R03", PROBE, "            fail = True\n            lines.append(f\"FAIL          {target}: 外网 {state}", "            lines.append(f\"FAIL          {target}: 外网 {state}", "外网不通仍可通过", "test_probe_judge_three_states"),
    ("R04", PROBE, '    if isinstance(exc, ConnectionRefusedError):\n        return "refused"\n', '    if isinstance(exc, ConnectionRefusedError):\n        return "timeout"\n', "拒绝连接归成超时", "test_probe_classifies_each_failure_mode"),
    # ── 两份独立审查之后补的 (审查者做出来存活的变异 + 审查修正引入的新行为) ──
    ("A13", AUTH, "    if len(values) != 1:\n", "    if not values:\n", "连接器送来两条 CF-Connecting-IP 时采信第一条", "test_duplicate_cf_connecting_ip_from_the_connector_is_not_trusted"),
    ("P07", PUB, 'FORWARDED_ALLOW_IPS: ""', 'FORWARDED_ALLOW_IPS: "127.0.0.1"', "公开实例采信回环来的 X-Forwarded-For", "test_public_compose_disables_uvicorn_proxy_headers"),
    ("N11", NFT, '\t\tiifname != "lo" ip saddr 10.201.8.0/24 counter drop\n', "\t\tip saddr 10.201.8.0/24 counter drop\n", "input 链丢掉虚拟机自己连网关地址的包", "test_nft_input_rules_exact_and_ordered"),
    ("N12", NFT, "\t\t\t240.0.0.0/4\n", "\t\t\t233.252.0.0/24\n", "放过保留段 240/4", "test_nft_blocked_set_exact"),
    ("N13", NFT, "\t\t\t198.18.0.0/15,\n", "", "放过 198.18/15", "test_nft_blocked_set_exact"),
    ("N14", NFT, "\t\t\t0.0.0.0/8,\n", "", "放过 0/8", "test_nft_blocked_set_exact"),
    ("N15", NFT, "\t\t\t192.0.0.0/24,\n", "", "放过 192.0.0.0/24", "test_nft_blocked_set_exact"),
    ("U03", UNIT, "[Install]\nWantedBy=multi-user.target\n", "", "隔离单元 enable 不生效 (开机不装规则)", "test_isolation_unit_loads_the_ruleset_before_docker"),
    ("U04", UNIT, "Before=docker.service\n", "Before=docker.service\nAfter=docker.service\n", "隔离单元同时排在 docker 之后", "test_isolation_unit_loads_the_ruleset_before_docker"),
    ("W01", WATCH, "/usr/bin/docker stop sdtm-rag-public-cloudflared; exit 1'", "exit 1'", "规则装不回去时不停连接器", "test_isolation_watchdog_behaviour"),
    ("W02", WATCH, "/usr/bin/docker stop sdtm-rag-public-cloudflared; exit 1'", "/usr/bin/docker stop sdtm-rag-api; exit 1'", "巡检停错容器 (私有站)", "test_isolation_watchdog_behaviour"),
    ("W03", TIMER, "OnCalendar=minutely", "OnCalendar=daily", "巡检一天才跑一次", "test_isolation_watchdog_command_and_timer_pinned"),
    ("W04", TIMER, "[Install]\nWantedBy=timers.target\n", "", "巡检定时器 enable 不生效", "test_isolation_watchdog_command_and_timer_pinned"),
    ("R06", PROBE, "        elif before is not None and before.get(", "        elif False and before.get(", "装规则前就连不上的目标也记 PASS", "test_probe_judge_requires_reachable_before_the_rules"),
    ("R07", PROBE, "        if _in_net(src, isolated_net):\n", "        if True:\n", "不核对隔离侧是在哪个网络里跑的", "test_probe_judge_checks_where_the_isolated_side_ran"),
    ("U05", UNIT, "ExecStop=-/usr/sbin/nft", "ExecStop=/usr/sbin/nft", "表不在时停单元报失败", "test_isolation_unit_loads_the_ruleset_before_docker"),
    ("W05", TIMER, "OnCalendar=minutely", "OnUnitActiveSec=60s", "巡检失败一次后可能不再触发", "test_isolation_watchdog_command_and_timer_pinned"),
    # ── 增量审查之后补的 (两位审查者第二轮做出来存活的变异 + 巡检改成整份重装 + token 输入命令) ──
    ("A14", AUTH, "    if len(values) != 1:\n", "    if len(values) > 1:\n", "连接器不带 CF-Connecting-IP 时抛异常", "test_connector_request_without_cf_connecting_ip_falls_back_to_the_peer"),
    ("W06", WATCH, "isolation.nft && exit 0; echo", "isolation.nft; exit 0; echo", "重装失败也当成功 (不停连接器)", "test_isolation_watchdog_behaviour"),
    ("W07", WATCH, "isolation.nft && exit 0; echo", "isolation.nft; echo", "重装成功也把连接器停掉", "test_isolation_watchdog_behaviour"),
    ("W08", WATCH, "/usr/sbin/nft -f /etc/sdtm-rag-public/isolation.nft && exit 0; sleep 3; /usr/sbin/nft -f /etc/sdtm-rag-public/isolation.nft && exit 0;", "exit 0;", "巡检不重装 (只看表在不在)", "test_isolation_watchdog_behaviour"),
    ("W10", WATCH, "sleep 3; /usr/sbin/nft -f /etc/sdtm-rag-public/isolation.nft && exit 0; ", "", "重装失败一次就停连接器 (不重试)", "test_isolation_watchdog_behaviour"),
    ("W11", WATCH, "isolation.nft && exit 0; sleep 3;", "isolation.nft; sleep 3;", "第一次重装成功了还要再装一次", "test_isolation_watchdog_behaviour"),
    ("D05", OWNER, 'IFS= read -rsp "', 'IFS= read -rp "', "输入 token 时回显", "test_owner_token_command_validates_before_writing"),
    ("D06", OWNER, "sudo bash -c 'umask 077; d=", "sudo bash -c 'd=", "token 文件创建瞬间权限过宽", "test_owner_token_command_validates_before_writing"),
    ("W09", TIMER, "AccuracySec=5s\n", "", "巡检触发精度退回默认的一分钟", "test_isolation_watchdog_command_and_timer_pinned"),
    ("R08", PROBE, "        return s.getsockname()[0]\n", '        return "10.201.8.200"\n', "源地址写死成公开网段里的值", "test_probe_source_address_is_what_the_kernel_would_use"),
    ("R09", PROBE, '    if before is not None and set(before.get("lan", {})) != set(iso_lan):\n', "    if False:\n", "装规则前后目标不一致也给 PASS", "test_probe_judge_requires_reachable_before_the_rules"),
    ("R10", PROBE, "    if before is not None and isolated_net is not None and not _in_net(", "    if False and not _in_net(", "不核对装规则前那份观测的来源", "test_probe_judge_checks_where_the_isolated_side_ran"),
    ("D01", OWNER, "[ ${#T} -ge 100 ] || ", "[ ${#T} -ge 1 ] || ", "token 复制不全也写入", "test_owner_token_command_validates_before_writing"),
    ("D02", OWNER, "*[!A-Za-z0-9+/=_-]*)", "*[!A-Za-z0-9+/=_ -]*)", "token 里混进空格也写入", "test_owner_token_command_validates_before_writing"),
    ("D03", OWNER, 'case "$T" in eyJ*) ;;', 'case "$T" in ?*) ;;', "不以 eyJ 开头也写入", "test_owner_token_command_validates_before_writing"),
    ("D04", OWNER, 'chmod 400 "$f"', 'chmod 644 "$f"', "token 文件权限放宽", "test_owner_token_command_validates_before_writing"),
    ("F01", DOCKERFILE, '"--workers", "1"]', '"--workers", "1", "--forwarded-allow-ips", "*"]', "镜像的启动命令压过 compose 置空的 FORWARDED_ALLOW_IPS", "test_dockerfile_cmd_does_not_override_forwarded_allow_ips"),
    ("A15", AUTH, "PUBLIC_EDGE_LEVEL = 1\n", "PUBLIC_EDGE_LEVEL = 0\n", "镜像下限标记失效 (预检会拒绝本镜像)", "test_image_floor_check_passes_this_build"),
    ("A16", AUTH, "PUBLIC_EDGE_LEVEL = 1\n", "PUBLIC_EDGE = 1\n", "镜像下限标记被改名 (预检按名字找不到)", "test_image_floor_marker"),
    ("F02", FLOOR, 'getattr(auth, "PUBLIC_EDGE_LEVEL", 0) < 1', 'getattr(auth, "PUBLIC_EDGE_LEVEL", 0) < 0', "预检不看标记 (旧镜像走到后面才报错, 原因不对)", "test_image_floor_check_refuses"),
    ("F03", FLOOR, "except RuntimeError:\n    print(\"image-floor: ok\")\n    sys.exit(0)\n", "except RuntimeError:\n    pass\nelse:\n    print(\"image-floor: ok\")\n    sys.exit(0)\n", "预检把「接受网段」当成合格", "test_image_floor_check_passes_this_build"),
    ("F04", FLOOR, 'auth._check_public_trusted("10.201.8.0/24")', 'auth._check_public_trusted("10.201.8.2")', "预检拿单主机地址去试 (试不出实现缺失)", "test_image_floor_check_passes_this_build"),
    ("F05", FLOOR, '    print("image-floor: ok")\n    sys.exit(0)\n', "    sys.exit(0)\n", "预检合格时不打标记 (和「脚本没送进去」分不开)", "test_image_floor_check_passes_this_build"),
    # ── 主人 2026-11-28 裁定「应用里也开全局限流」之后补的 ──
    ("G01", PUB, 'SDTM_RAG_RATE_LIMIT_ENABLED: "true"', 'SDTM_RAG_RATE_LIMIT_ENABLED: "false"', "公开 compose 没开全局限流", "test_public_compose_turns_on_the_global_rate_limit"),
    ("G02", PUB, 'SDTM_RAG_RATE_LIMIT_PER_MIN: "60"', 'SDTM_RAG_RATE_LIMIT_PER_MIN: "6000"', "全局限流的每分钟额度放宽 100 倍", "test_public_compose_turns_on_the_global_rate_limit"),
    ("G03", PUB, 'SDTM_RAG_RATE_LIMIT_BURST: "20"', 'SDTM_RAG_RATE_LIMIT_BURST: "5"', "全局限流的突发额度低于提问限额", "test_global_rate_limit_sits_above_the_question_limits"),
    ("G04", AUTH, "            **pub_kw,\n", "", "公开档全局限流按连接对端计 (所有访客并成连接器一个桶)", "test_public_compose_turns_on_the_global_rate_limit"),
    ("G05", AUTH, "    if _is_public(settings):\n        _check_public_env_case_variants(os.environ)\n", "", "公开档不查大小写变体 (.env 可悄悄关掉全局限流)", "test_public_refuses_case_variant_that_would_override_compose"),
    ("G06", AUTH, "    if _is_public(settings):\n        _check_public_env_case_variants(os.environ)\n", "    if True:\n        _check_public_env_case_variants(os.environ)\n", "大小写变体检查漏到私有档", "test_public_case_variant_check_names_no_values_and_private_is_untouched"),
    ("G07", AUTH, "clash = sorted(sorted(variants) for variants in seen.values()", "clash = sorted(sorted(variants.items()) for variants in seen.values()", "冲突报错里带出取值 (可能是秘密)", "test_public_case_variant_check_names_no_values_and_private_is_untouched"),
    ("G08", AUTH, 'exempt_prefixes: tuple[str, ...] = ("/static/",),', "exempt_prefixes: tuple[str, ...] = (),", "全局限流误伤静态文件", "test_public_compose_turns_on_the_global_rate_limit"),
    ("G09", AUTH, 'exempt: tuple[str, ...] = ("/api/health", "/"),', 'exempt: tuple[str, ...] = ("/",),', "全局限流误伤健康检查", "test_public_compose_turns_on_the_global_rate_limit"),
    ("G10", AUTH, "if len(set(variants.values())) > 1)", "if len(variants) > 1)", "取值相同的大小写变体也拒启动", "test_public_refuses_case_variant_that_would_override_compose"),
    ("G11", AUTH, "            if not name.isascii():\n                raise RuntimeError(f\"public tier: non-ASCII setting name in the environment / .env: {name!r}\")\n", "", "非 ASCII 的键名不拒 (开尔文符号可冒充 k)", "test_public_case_variant_check_names_no_values_and_private_is_untouched"),
    ("G12", AUTH, '        if low.startswith("sdtm_rag_"):\n', '        if name.startswith("SDTM_RAG_"):\n', "只看全大写写法的键 (小写变体漏过去)", "test_public_refuses_case_variant_that_would_override_compose"),
    ("R05", PROBE, '    if not iso_egress:\n        unsure = True\n', "    if not iso_egress:\n        pass\n", "没有外网对照也通过", "test_probe_judge_refuses_to_pass_on_missing_evidence"),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_tests() -> tuple[int, str, list[str], dict[str, str]]:
    for d in ("server/__pycache__", "tests/__pycache__"):
        shutil.rmtree(ROOT / d, ignore_errors=True)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([sys.executable, "-m", "pytest", *TESTS, "-q", "-o", "addopts=", "-p", "no:cacheprovider",
                        "-W", "ignore", "-rfE"], cwd=ROOT, env=env, capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    summary = lines[-1] if lines else "(no output)"
    failed, why, current = [], {}, None
    for ln in lines:
        if ln.startswith(("FAILED ", "ERROR ")):
            failed.append(ln.split(" ", 1)[1].partition(" - ")[0])
        elif re.fullmatch(r"_{3,} .+ _{3,}", ln):          # 每条失败的详情以「___ 用例名 ___」开头
            current = ln.strip("_ ")
        elif ln.startswith("E ") and current and current not in why:
            why[current] = ln[1:].strip()[:150]             # 该用例的第一条 E 行 = 实际的失败信息
    return r.returncode, summary, failed, why


def verdict_of(rc: int, summary: str, failed: list[str], expected: str) -> str:
    if rc == 0:
        return "SURVIVED"
    if " error" in summary or "failed" not in summary:
        return "INVALID(error)"
    if not any(expected in t for t in failed):
        return "INVALID(wrong test)"
    return "killed"


def main() -> int:
    files = sorted({m[1] for m in MUTATIONS})
    frozen = {f: (ROOT / f).read_bytes() for f in files}
    base = {f: sha(b) for f, b in frozen.items()}
    assert len({m[0] for m in MUTATIONS}) == len(MUTATIONS), "变异编号重复"
    rc, summary, _failed, _why = run_tests()
    print(f"BASELINE rc={rc} {summary}")
    if rc != 0:
        print("基线不绿, 拒跑")
        return 2
    bad = []
    for mid, f, old, new, what, expected in MUTATIONS:
        path = ROOT / f
        assert sha(path.read_bytes()) == base[f], f"{mid}: {f} 与基线不符, 拒跑"
        text = frozen[f].decode("utf-8")
        assert text.count(old) == 1, f"{mid}: 原文出现 {text.count(old)} 次, 须恰好 1 次"
        expected_text = text.replace(old, new)
        try:
            path.write_text(expected_text, encoding="utf-8")
            back = path.read_text(encoding="utf-8")
            assert back == expected_text and sha(back.encode("utf-8")) != base[f], f"{mid}: 变异没打上"
            rc, summary, failed, why = run_tests()
        finally:
            path.write_bytes(frozen[f])
        assert sha(path.read_bytes()) == base[f], f"{mid}: 还原后 sha 不符"
        verdict = verdict_of(rc, summary, failed, expected)
        if verdict != "killed":
            bad.append(f"{mid}:{verdict}")
        hit = next((t for t in failed if expected in t), "")
        print(f"{mid} {verdict} | {what} | {summary} | {hit or failed[:1]} | {why.get(hit.rpartition('::')[2], '')}")
    rc, summary, _failed, _why = run_tests()
    print(f"AFTER rc={rc} {summary}")
    print(f"变异 {len(MUTATIONS)} 个, 没被正确打红的 {len(bad)}: {bad}")
    return 1 if bad or rc != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
