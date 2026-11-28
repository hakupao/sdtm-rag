"""公开部署的编排 (kbsync.py deploy-public): 先用临时容器验收, 通过后才动正式容器; 之后任何失败都停机。
文件系统子命令在 tmp 目录上真跑; docker / compose 用带容器状态的假实现, 并在关键时刻核对不变量:
换数据 / 退数据时正式容器必须是停的; 临时容器不挂正式数据根; 失败路径上没有任何启动动作。"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tests.test_kbsync import (
    NEW,
    OLD,
    TS,
    FakeDocker,
    _chroma,
    _cols,
    _gated_cand,
    _meta,
    _snapshot,
    ks,
)
from tests.test_kbsync_public import (
    CAND,
    PRIV_MODEL,
    PUB_MODEL,
    _with_mount,
    assert_no_bind_reaches,
)

PREFIX = "192.168.100.58/bojiang/sdtm-rag"
# 隧道那条线改过之后的公开 compose 在部署机上的真实解析结果 (只读采集): 网络写定了子网, 多了两个环境变量
PUB_TUNNEL_MODEL = json.loads((Path(__file__).parent / "fixtures/kbsync/compose_config_public_tunnel.json").read_text())
TAG_NEW, TAG_OLD = "1" * 40, "0" * 40
IMG_NEW, IMG_OLD = f"{PREFIX}:{TAG_NEW}", f"{PREFIX}:{TAG_OLD}"
FORMAL, TEMP = "sdtm-rag-public-api", ks.ACCEPT_CONTAINER
NET, SUBNET = "sdtm-rag-public", "10.201.8.0/24"
LAN = "10.201.8.1:22 192.168.5.15:22 192.168.100.58:443"
EGRESS = "api.anthropic.com:443 api.openai.com:443"
# 隔离探测脚本的替身: 命令行与隧道那条线的 isolation_probe.py 相同 (probe 在容器里跑, 由假 docker 代答; judge 在本机真跑)。
# 判定照搬它的 judge (不含只在首次装规则时用的 --before): 隔离侧能到内网 / 外网不是 open → FAIL (1);
# 源地址不在网段里、清单为空、两侧目标不一致、状态既非可达也非被挡、对照侧连不上 → INCONCLUSIVE (2)。
# 合并之后 test_isolation_check_with_the_real_probe_script 会用真脚本再跑一遍。
PROBE_STANDIN = '''
import argparse, ipaddress, json, sys
p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="cmd")
j = sub.add_parser("judge")
for k in ("--isolated", "--control", "--before", "--isolated-net"):
    j.add_argument(k)
a = p.parse_args()
iso, ctl = json.load(open(a.isolated)), json.load(open(a.control))
REACH, BLOCKED = {"open", "refused"}, {"timeout", "unreachable"}
fail = unsure = False
try:
    in_net = ipaddress.ip_address(iso.get("src", "missing")) in ipaddress.ip_network(a.isolated_net)
except ValueError:
    in_net = False
unsure |= not in_net                                   # 源地址不在公开网段里: 这份观测不算数
iso_lan, ctl_lan = iso.get("lan", {}), ctl.get("lan", {})
unsure |= not iso_lan or set(iso_lan) != set(ctl_lan)
for t, st in iso_lan.items():
    if st in REACH:
        fail = True                                    # 隔离侧能到达内网
    elif st not in BLOCKED or ctl_lan.get(t, "missing") not in REACH:
        unsure = True                                  # 既不是可达也不是被挡 / 对照侧也连不上
egress = iso.get("egress", {})
unsure |= not egress
fail |= any(st != "open" for st in egress.values())    # 需要的出站被挡, 或容器没网
verdict = "FAIL" if fail else "INCONCLUSIVE" if unsure else "PASS"
print(verdict)
sys.exit({"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[verdict])
'''
CLEAN = {"chroma": _cols(4329), CAND: _cols(4333), "stage": _cols(4333)}
OK_KEY = (0, '{"ok": true, "category": "ok", "models": 1}')


class PublicFake(FakeDocker):
    """在 FakeDocker 之上模拟 compose / 容器状态。violations 收集"绝不该发生"的事 (编排会吞异常, 不能靠 raise)。"""

    def __init__(self, pub: Path, env_file: Path, *, formal: str | None, image_fp: str = NEW, cols: dict | None = None,
                 priv_model: dict | None = None):
        super().__init__(pub, collections=dict(cols or CLEAN))
        self.cols.setdefault("chroma", _cols(4329))  # 线上公开 chroma (红线检查在它的副本上读集合)
        self.image_fps = {IMG_NEW: image_fp}
        # 合并后的公开 compose: 隧道那条线给公开网络写定了子网, 并加了两个环境变量
        self.pub_model = _with_mount(_with_mount(PUB_TUNNEL_MODEL, "/app/data", str(pub)), "/app/.env", str(env_file))
        self.net_subnets: dict[str, str] = {NET: SUBNET}   # docker 里实际存在的网络 → 子网
        self.iso_lan_state = "timeout"                       # 隔离侧看到的内网目标状态
        self.iso_src = "10.201.8.130"
        self.iso_egress_state = "open"
        self.ctl_lan_state = "open"
        self.probe_script: bytes | None = None               # 该送进探测容器的脚本内容 (_fake 里填)
        self.priv_model = priv_model or PRIV_MODEL
        self.containers: dict[str, dict] = {}
        if formal:
            self.containers[FORMAL] = {"running": formal == "running", "image": IMG_OLD}
        self.events: list[str] = []
        self.violations: list[str] = []
        self.fail: set[str] = set()          # temp_up / stop / up / create / rm / inspect_formal_after_up
        self.unhealthy: set[str] = set()     # 容器名: 起来了但一直不 healthy
        self.exited: set[str] = set()        # 容器名: 一启动就退出
        self.bad_tier: set[str] = set()
        self.stale: set[str] = set()
        self.answer_results: list[tuple[int, str]] = []
        self.accept_specs: list[dict] = []
        self.at_temp_up: dict = {}
        self.skip_fs: set[str] = set()       # 这些文件系统子命令不执行, 直接报失败 (真的没做成)
        self.after_stop = None               # formal:stop 之后调用一次的钩子
        self.on_temp_up = None               # 临时容器起来时调用一次的钩子 (模拟验收期间有人动了正式容器)
        self.on_main_guard = None            # 停机后的换入核对开始时调用一次的钩子
        self.on_answer_key = None            # 答题 key 探测时调用一次的钩子 (临时验收之后、换入前置核对之前)
        self.logs_text = "startup log\n"      # docker logs 的内容
        self.execs: list[list[str]] = []     # 每一次 docker exec 的参数

    def _one_off_rules(self, args: list[str], what: str) -> None:
        """接在公开网络 (或默认网桥) 里的一次性容器要守的几条 (隧道那条线的集成备注第 3 条)。"""
        head = args[:args.index("--entrypoint")]  # 镜像之前的 docker 选项
        if not ("--cap-drop" in head and head[head.index("--cap-drop") + 1] == "ALL"):
            self.violations.append(f"{what}没有 --cap-drop ALL")
        if "--rm" not in head:
            self.violations.append(f"{what}没有 --rm")
        banned = [x for x in head if x in ("--ip", "--name", "--network-alias", "--hostname", "-p", "--publish",
                                           "--env-file", "--privileged", "--cap-add") or x.startswith(("--ip=", "--name="))]
        if banned:
            self.violations.append(f"{what}带了不该有的选项 {banned}")

    # ── 断言用 ──
    def formal(self) -> dict | None:
        return self.containers.get(FORMAL)

    def starts(self) -> list[str]:
        return [e for e in self.events if e == "formal:up"]

    def check(self) -> None:
        assert not self.violations, self.violations
        assert TEMP not in self.containers, "临时容器没有清掉"
        assert not list(self.D.parent.glob(f"{ks.ACCEPT_PREFIX}*")), "验收副本没有清掉"

    def _formal_running(self) -> bool:
        return bool(self.containers.get(FORMAL, {}).get("running"))

    def run(self, args, *, input=None, env=None):
        ok, err = self._ok, lambda msg, rc=1: subprocess.CompletedProcess([], rc, b"", msg.encode())
        if args[0] == "compose" and "config" in args:
            self.calls.append(args)
            assert env and env.get("IMAGE_TAG"), "compose config 需要 IMAGE_TAG"
            if Path(args[args.index("-f") + 1]).name == "compose.yml":
                return ok(json.dumps(self.priv_model))
            model = copy.deepcopy(self.pub_model)
            model["services"]["api"]["image"] = f"{PREFIX}:{env['IMAGE_TAG']}"
            return ok(json.dumps(model))
        if args[0] == "compose" and "-p" in args:  # 临时验收项目
            self.calls.append(args)
            assert args[args.index("-p") + 1] == ks.ACCEPT_PROJECT and args[-2:] == ["up", "-d"]
            spec = json.loads(Path(args[args.index("-f") + 1]).read_text())
            self.accept_specs.append(spec)
            svc = spec["services"]["api"]
            if "temp_up" in self.fail or not all(Path(v["source"]).exists() for v in svc["volumes"]):
                return err("bind source path does not exist")
            self.at_temp_up = {"formal": copy.deepcopy(self.formal()), "live": _snapshot(self.D),
                               "stage": _snapshot(Path(svc["volumes"][0]["source"]))}
            self.containers[svc["container_name"]] = {"running": TEMP not in self.exited, "image": svc["image"]}
            self.events.append("temp:up")
            if self.on_temp_up:
                hook, self.on_temp_up = self.on_temp_up, None
                hook()
            return ok()
        if args[0] == "compose":  # 正式项目
            self.calls.append(args)
            assert Path(args[args.index("-f") + 1]).name == "compose.public.yml"
            verb = args[3:]
            if verb in (["up", "-d"], ["up", "--no-start"]):
                self.violations.append(f"compose {verb} 没有限定到 api 服务")
            if verb in (["stop"], ["stop", "api"]):  # 换数据前只停 api; 失败 / 中断时停整个项目
                self.events.append("formal:stop")
                if "stop" in self.fail:
                    return err("cannot stop container")
                if FORMAL in self.containers:
                    self.containers[FORMAL]["running"] = False
                if self.after_stop:
                    hook, self.after_stop = self.after_stop, None
                    hook()
                return ok()
            image = f"{PREFIX}:{env['IMAGE_TAG']}"
            if verb == ["up", "-d", "api"]:
                self.events.append("formal:up")
                if "up" in self.fail:
                    return err("pull access denied")
                self.containers[FORMAL] = {"running": True, "image": image}
                return ok()
            if verb == ["up", "--no-start", "api"]:
                self.events.append("formal:create")
                if "create" in self.fail:
                    return err("no space left on device")
                self.containers[FORMAL] = {"running": False, "image": image}
                return ok()
            raise AssertionError(f"编排不该调用 compose {verb}")
        if args[:2] == ["network", "inspect"]:
            self.calls.append(args)
            self.events.append("net_check")
            sub = self.net_subnets.get(args[2])
            return ok(sub + " \n") if sub else err(f"Error response from daemon: network {args[2]} not found")
        if args[0] == "run" and input is not None and "-" in args and args[args.index("-") + 1:][:1] == ["probe"]:
            self.calls.append(args)
            network = args[args.index("--network") + 1]
            if "--mount" in args or "-e" in args:
                self.violations.append("隔离探测容器不该挂数据或带环境变量")
            self._one_off_rules(args, "隔离探测容器")
            if "-i" not in args or input != self.probe_script:
                self.violations.append("送进隔离探测容器的不是探测脚本 (或漏了 -i)")
            if "iso_garbage" in self.fail:
                return ok("123\n")
            lan = [args[i + 1] for i, x in enumerate(args) if x == "--lan"]
            egress = [args[i + 1] for i, x in enumerate(args) if x == "--egress"]
            if network == NET:
                self.events.append("iso:isolated")
                obs = {"src": self.iso_src, "lan": {t: self.iso_lan_state for t in lan},
                       "egress": {t: self.iso_egress_state for t in egress}}
            else:
                assert network == "bridge", network
                self.events.append("iso:control")
                obs = {"src": "172.17.0.2", "lan": {t: self.ctl_lan_state for t in lan}, "egress": {}}
            if "iso_probe_rc" in self.fail:  # 打出了观测, 但容器以非零状态退出
                return subprocess.CompletedProcess([], 1, (json.dumps(obs) + "\n").encode(), b"killed")
            return ok(json.dumps(obs) + "\n") if "iso_probe" not in self.fail else err("boom")
        if args[0] == "inspect":
            assert args[1:3] == ["--type", "container"], args
            name = args[-1]
            if name == FORMAL and "inspect_formal_after_up" in self.fail and "formal:up" in self.events:
                return err("Cannot connect to the Docker daemon")
            c = self.containers.get(name)
            if c is None:
                return err(f"Error response from daemon: No such container: {name}")
            health = "starting" if name in self.unhealthy else ("healthy" if c["running"] else "")
            status = "running" if c["running"] else "exited"
            return ok(f"{'true' if c['running'] else 'false'}|{status}|{health}|{c['image']}\n")
        if args[0] == "exec":
            name = args[1]
            self.execs.append(args)
            if not self.containers.get(name, {}).get("running"):
                return err("container is not running")
            if args[2:4] == ["python", "-c"]:
                assert args[4] == ks.ACCEPT_PY
                return err("tier != public") if name in self.bad_tier else ok("tier=public, /openapi.json 404\n")
            assert args[2:] == ["python", "-m", "scripts.check_index_freshness"]
            return err("STALE", 2) if name in self.stale else ok("OK\n")
        if args[0] == "rm":
            assert args[1:] == ["-f", TEMP], f"只许删临时容器: {args}"
            if "rm" not in self.fail and self.containers.pop(TEMP, None):
                self.events.append("temp:rm")
            return ok()
        if args[0] == "logs":
            return ok(self.logs_text)
        if "-c" in args and args[args.index("-c") + 1] == ks.ANSWER_KEY_PY:
            self.calls.append(args)
            self.events.append("answer_key")
            if self.on_answer_key:
                hook, self.on_answer_key = self.on_answer_key, None
                hook()
            if "--network" not in args or args[args.index("--network") + 1] != NET:
                self.violations.append("答题 key 探测没有接在公开网络里")
            self._one_off_rules(args, "答题 key 探测容器")
            if [args[i + 1] for i, x in enumerate(args) if x == "-e"] != ["SDTM_RAG_INSTANCE=public"]:
                self.violations.append("答题 key 探测容器的 -e 只能有档位 (key 只经只读挂载的 env 文件传入)")
            if TEMP in self.containers:
                self.violations.append("答题 key 探测应在临时容器清掉之后")
            rc, out = self.answer_results.pop(0) if self.answer_results else OK_KEY
            return subprocess.CompletedProcess([], rc, out.encode(), b"x-api-key sk-ant-api03-AbCdEf123456")
        if "-i" in args and "-" in args:  # --via
            fs = args[args.index("-") + 1:]
            mounts = [args[i + 1] for i, a in enumerate(args) if a == "--mount"]
            if fs[0] in ks.STAGE_CMDS:
                want = [f"type=bind,src={self.D.parent},dst={self.D.parent}", f"type=bind,src={self.D},dst={self.D},readonly"]
            else:
                want = [f"type=bind,src={self.D},dst={self.D}"]
            if mounts != want:
                self.violations.append(f"{fs[0]} 的挂载不对: {mounts}")
            if fs[0] in ("swap", "restore") and self._formal_running():
                self.violations.append(f"正式容器还在运行时执行了 {fs[0]}")
            if fs[0] == "accept-stage":
                before = _snapshot(self.D)
            if fs[0] == "guard-copy" and "formal:stop" in self.events and self.on_main_guard:
                hook, self.on_main_guard = self.on_main_guard, None
                hook()
            if fs[0] in self.skip_fs:
                self.calls.append(args)
                self.events.append(f"fs:{fs[0]}:failed")
                return subprocess.CompletedProcess([], 2, b"", b"boom")
            res = super().run(args, input=input, env=env)
            self.events.append(f"fs:{fs[0]}")
            if fs[0] == "accept-stage" and _snapshot(self.D) != before:
                self.violations.append("accept-stage 改动了数据根")
            return res
        return super().run(args, input=input, env=env)


@pytest.fixture
def site(tmp_path):
    """与生产同构: deploy-data/{sdtm-rag,sdtm-rag-public}/data; 私有根带 study, 公开根只有 KB + quota.sqlite。"""
    base = tmp_path / "deploy-data"
    priv, pub = base / "sdtm-rag" / "data", base / "sdtm-rag-public" / "data"
    _chroma(priv / "chroma", OLD, "PRIVATE-chroma-with-study")
    _meta(priv / "meta", "private-meta")
    (priv / "study" / "st01").mkdir(parents=True)
    (priv / "study" / "st01" / "catalog.json").write_text("PRIVATE-study")
    _chroma(pub / "chroma", OLD, "public-chroma")
    _meta(pub / "meta", "public-meta")
    (pub / "quota.sqlite").write_text("quota-live")
    env = tmp_path / "opt" / "sdtm-rag-public" / ".env"
    env.parent.mkdir(parents=True)
    env.write_text("OPENAI_API_KEY=placeholder\n")
    priv_model = copy.deepcopy(PRIV_MODEL)
    for svc in priv_model["services"].values():
        svc["volumes"][0]["source"] = str(priv)
    probe = tmp_path / "public-net" / "isolation_probe.py"
    probe.parent.mkdir()
    probe.write_text(PROBE_STANDIN)
    return {"priv": priv, "pub": pub, "env": env, "touched": tmp_path / "touched", "priv_model": priv_model,
            "probe": probe}


def _fake(site, *, formal, swap: bool, **kw) -> PublicFake:
    if swap:
        _gated_cand(site["pub"])
    fake = PublicFake(site["pub"], site["env"], formal=formal, image_fp=NEW if swap else OLD,
                      priv_model=site["priv_model"], **kw)
    fake.probe_script = site["probe"].read_bytes()
    return fake


def _args(site, **over):
    argv = ["deploy-public", "--data-root", str(site["pub"]), "--env-file", str(site["env"]),
            "--compose-file", "deploy/container/compose.public.yml",
            "--private-compose-file", "deploy/container/compose.yml",
            "--image", IMG_NEW, "--tag", TAG_NEW, "--touched-file", str(site["touched"]), "--ts", TS,
            "--isolation-probe", str(site["probe"]), "--isolation-lan", LAN, "--isolation-egress", EGRESS]
    a = ks.build_parser().parse_args(argv)
    for k, v in over.items():
        setattr(a, k, v)
    return a


def _run(fake: PublicFake, site, **over) -> int:
    return ks.deploy_public(fake, _args(site, **over), sleep=lambda s: None)


def _order(events: list[str], *names: str) -> None:
    idx = [events.index(n) for n in names]
    assert idx == sorted(idx), (names, events)


# ── 正常路径 ──────────────────────────────────────────────────────────────
def test_same_running_temp_first_then_formal(site, capsys):
    before = _snapshot(site["pub"])
    fake = _fake(site, formal="running", swap=False, cols={"stage": _cols(4329)})
    assert _run(fake, site) == 0
    fake.check()
    _order(fake.events, "net_check", "iso:isolated", "iso:control", "fs:accept-stage", "temp:up", "temp:rm", "answer_key",
           "formal:up")
    assert fake.formal() == {"running": True, "image": IMG_NEW}
    assert "formal:stop" not in fake.events and "fs:swap" not in fake.events
    assert _snapshot(site["pub"]) == before  # 没换数据; 临时验收没有往公开数据根写任何东西
    assert fake.at_temp_up["formal"] == {"running": True, "image": IMG_OLD}  # 临时验收期间旧版照常对外
    assert site["touched"].read_text() == FORMAL
    assert "成功" in capsys.readouterr().out


def test_swap_running_full_order(site):
    fake = _fake(site, formal="running", swap=True)
    assert _run(fake, site) == 0
    fake.check()
    _order(fake.events, "fs:accept-stage", "temp:up", "temp:rm", "formal:stop", "fs:swap", "formal:up",
           "fs:finish", "fs:prune")
    assert fake.events.index("fs:guard-copy") < fake.events.index("formal:stop")  # 换入核对先于停正式容器
    # 三次副本核对: 线上数据的红线检查; 停之前的换入前置核对 (只读); 停之后的主闸
    assert fake.events.count("fs:guard-copy") == 3 and fake.events[fake.events.index("formal:stop"):].count("fs:guard-copy") == 1
    assert fake.formal() == {"running": True, "image": IMG_NEW} and len(fake.starts()) == 1
    assert (site["pub"] / "chroma" / "chroma.sqlite3").read_text() == "cand"
    assert (site["pub"] / "meta" / "meta.yaml").read_text() == "new-meta"
    assert not (site["pub"] / ks.JOURNAL).exists()
    assert (site["pub"] / f"chroma_prev_{OLD[:12]}_{TS}" / "chroma.sqlite3").read_text() == "public-chroma"
    assert (site["pub"] / "quota.sqlite").read_text() == "quota-live"


@pytest.mark.parametrize("formal", ["stopped", None])
@pytest.mark.parametrize("swap", [True, False])
def test_stopped_or_absent_is_updated_but_never_started(site, capsys, formal, swap):
    fake = _fake(site, formal=formal, swap=swap, cols=CLEAN if swap else {"stage": _cols(4329)})
    assert _run(fake, site) == 0
    fake.check()
    assert fake.formal() == {"running": False, "image": IMG_NEW}  # 新镜像, 没启动
    assert fake.starts() == [] and "formal:create" in fake.events
    assert ((site["pub"] / "chroma" / "chroma.sqlite3").read_text() == "cand") is swap
    assert not (site["pub"] / ks.JOURNAL).exists()
    out = capsys.readouterr().out
    assert "公开容器保持停止" in out and f"docker start {FORMAL}" in out
    if swap:
        _order(fake.events, "temp:rm", "fs:swap", "formal:create", "fs:finish")


def test_temp_container_is_isolated_from_the_live_instance(site):
    fake = _fake(site, formal="running", swap=True)
    assert _run(fake, site) == 0
    (spec,) = fake.accept_specs
    assert spec["name"] == ks.ACCEPT_PROJECT != fake.pub_model["name"]  # 另一个 compose 项目
    svc = spec["services"]["api"]
    assert svc["container_name"] == TEMP != FORMAL
    assert svc["network_mode"] == "none" and svc["restart"] == "no"
    assert "ports" not in svc and "networks" not in svc and "networks" not in spec
    # 环境变量照抄 compose (隧道那条线加的可信代理、空串的 FORWARDED_ALLOW_IPS、全局限流三个键都在); networks 段不照抄
    env = PUB_TUNNEL_MODEL["services"]["api"]["environment"]
    assert svc["image"] == IMG_NEW and svc["environment"] == env and len(env) >= 6
    assert env["SDTM_RAG_INSTANCE"] == "public" and env["SDTM_RAG_QUOTA_TRUSTED_PROXIES"] == "10.201.8.2"
    assert env["FORWARDED_ALLOW_IPS"] == "" and env["SDTM_RAG_RATE_LIMIT_ENABLED"] == "true"
    assert "ipam" not in json.dumps(spec) and "br-sdtmpub" not in json.dumps(spec) and "10.201.8.0" not in json.dumps(spec)
    data, envm = svc["volumes"]
    stage = Path(data["source"])
    assert data["target"] == "/app/data" and stage.name == "data"
    assert stage.parent.name == f"{ks.ACCEPT_PREFIX}{TS}" and stage.parent.parent == site["pub"].parent  # 数据根的上一级
    assert site["pub"] not in (stage, *stage.parents)  # 不在正式容器的挂载范围内
    assert envm == {"type": "bind", "source": str(site["env"]), "target": "/app/.env", "read_only": True,
                    "bind": {"create_host_path": False}}
    staged = fake.at_temp_up["stage"]
    assert staged["chroma/chroma.sqlite3"] == "cand" and staged["meta/meta.yaml"] == "new-meta"  # 候选的副本
    assert not any("quota" in k for k in staged)  # 临时容器用自己的空额度库
    assert "PRIVATE" not in json.dumps(staged)


def test_same_decision_stages_a_copy_of_live_data(site):
    fake = _fake(site, formal="running", swap=False, cols={"stage": _cols(4329)})
    assert _run(fake, site) == 0
    assert fake.at_temp_up["stage"]["chroma/chroma.sqlite3"] == "public-chroma"


def test_whole_flow_never_mounts_or_touches_the_private_root(site):
    before = _snapshot(site["priv"])
    fake = _fake(site, formal="running", swap=True)
    assert _run(fake, site) == 0
    assert_no_bind_reaches(fake, site["priv"], min_mounts=15)
    assert _snapshot(site["priv"]) == before
    assert "PRIVATE" not in json.dumps(_snapshot(site["pub"]))


# ── 临时验收不过: 正式容器和正式数据都不动 ─────────────────────────────────
def _break_temp(kind: str, fake: PublicFake) -> None:
    if kind == "unhealthy":
        fake.unhealthy.add(TEMP)
    elif kind == "exits":
        fake.exited.add(TEMP)
    elif kind == "tier":
        fake.bad_tier.add(TEMP)
    elif kind == "stale":
        fake.stale.add(TEMP)
    elif kind == "temp_up":
        fake.fail.add("temp_up")
    elif kind == "staged_non_kb":
        fake.cols["stage"] = _cols(4333, study_zz=(5, "d1"))
    elif kind == "staged_no_kb":
        fake.cols["stage"] = {}
    elif kind == "staged_unreadable":
        fake.cols["stage"] = None
    elif kind == "stage_copy":
        fake.skip_fs.add("accept-stage")


TEMP_FAILURES = ["unhealthy", "exits", "tier", "stale", "temp_up", "staged_non_kb", "staged_no_kb",
                 "staged_unreadable", "stage_copy"]


@pytest.mark.parametrize("kind", TEMP_FAILURES)
@pytest.mark.parametrize("formal", ["running", "stopped"])
@pytest.mark.parametrize("swap", [True, False])
def test_temp_acceptance_failure_leaves_formal_untouched(site, capsys, kind, formal, swap):
    fake = _fake(site, formal=formal, swap=swap, cols=CLEAN if swap else {"stage": _cols(4329)})
    _break_temp(kind, fake)
    before, formal_before = _snapshot(site["pub"]), copy.deepcopy(fake.formal())
    assert _run(fake, site) == 1
    fake.check()
    assert fake.formal() == formal_before
    assert not [e for e in fake.events if e.startswith("formal:")]  # 没停、没起、没重建
    assert not [e for e in fake.events if e in ("fs:swap", "fs:restore", "fs:finish", "answer_key")]
    assert fake.events.count("fs:guard-copy") == 1  # 只有线上数据的红线检查那一次, 没有走到换入核对
    assert _snapshot(site["pub"]) == before
    assert not site["touched"].exists()
    out = capsys.readouterr().out
    assert "临时容器验收不通过" in out and "正式容器和正式数据都没有动" in out
    assert ("旧版继续对外" in out) is (formal == "running")
    assert "sk-ant" not in out


def test_answer_key_failure_names_the_cause_without_leaking(site, capsys):
    fake = _fake(site, formal="running", swap=False, cols={"stage": _cols(4329)})
    fake.answer_results = [(1, '{"ok": false, "category": "key_invalid", "status": 401, "error_class": "AuthenticationError"}')]
    assert _run(fake, site) == 1
    out = capsys.readouterr().out
    assert "答题 key 探测不通过" in out and "公开站的答题 key 无效" in out and "401" in out and "sk-" not in out
    assert "旧版继续对外" in out and fake.formal() == {"running": True, "image": IMG_OLD}
    _order(fake.events, "temp:up", "temp:rm", "answer_key")  # 临时验收通过之后才探测
    assert not [e for e in fake.events if e.startswith("formal:")] and not site["touched"].exists()
    call = next(c for c in fake.calls if ks.ANSWER_KEY_PY in c)
    assert call[call.index("--network") + 1] == NET  # 接在公开网络里 (受隔离规则约束)
    assert f"type=bind,src={site['env']},dst=/app/.env,readonly" in call
    assert [call[i + 1] for i, x in enumerate(call) if x == "-e"] == ["SDTM_RAG_INSTANCE=public"]  # 命令行里只有档位
    assert not [x for x in call if x != ks.ANSWER_KEY_PY and ("API_KEY" in x.upper() or "sk-" in x)]  # 没有任何 key


def test_answer_key_transient_error_retries_then_fails_closed(site, capsys):
    fake = _fake(site, formal="running", swap=False, cols={"stage": _cols(4329)})
    fake.answer_results = [(1, '{"ok": false, "category": "network_error"}')] * 3
    assert _run(fake, site) == 1
    assert fake.events.count("answer_key") == 3 and fake.formal() == {"running": True, "image": IMG_OLD}
    assert "探测没有完成" in capsys.readouterr().out
    fake = _fake(site, formal="running", swap=False, cols={"stage": _cols(4329)})
    fake.answer_results = [(1, '{"ok": false, "category": "rate_limited"}'), OK_KEY]
    assert _run(fake, site) == 0


def test_answer_key_probe_without_result_fails_closed(site):
    fake = _fake(site, formal="running", swap=False, cols={"stage": _cols(4329)})
    fake.answer_results = [(0, "")]  # rc 0 但没有结果
    assert _run(fake, site) == 1
    fake.answer_results = [(1, '{"ok": true, "category": "ok"}')]  # 自称 ok 但 rc != 0
    assert _run(fake, site) == 1
    assert fake.events.count("answer_key") == 2
    assert fake.formal() == {"running": True, "image": IMG_OLD}


def test_non_anthropic_default_model_warns_but_continues(site, capsys):
    fake = _fake(site, formal="running", swap=False, cols={"stage": _cols(4329)})
    fake.answer_results = [(0, '{"ok": true, "category": "not_applicable", "providers": ["deepseek"]}')]
    assert _run(fake, site) == 0
    assert "::warning::公开站配置的答题模型里没有 Anthropic 的" in capsys.readouterr().out


# ── 答题 key 探测脚本本身 (与生产容器里跑的是同一段源码; anthropic 与 server.config 用替身, 不读 .env) ──
class _FakeAPIStatusError(Exception):
    def __init__(self, status=500):
        super().__init__("secret-bearing message sk-ant-api03-ShouldNeverLeak")
        self.status_code = status


def _fake_anthropic(raises=None, n=1):
    import types

    mod = types.SimpleNamespace(seen={})
    mod.APIStatusError = _FakeAPIStatusError
    mod.AuthenticationError = type("AuthenticationError", (_FakeAPIStatusError,), {})
    mod.PermissionDeniedError = type("PermissionDeniedError", (_FakeAPIStatusError,), {})
    mod.RateLimitError = type("RateLimitError", (_FakeAPIStatusError,), {})
    mod.APIConnectionError = type("APIConnectionError", (Exception,), {})

    class Anthropic:
        def __init__(self, **kw):
            mod.seen.update(kw)
            self.models = types.SimpleNamespace(list=self._list)

        def _list(self, limit):
            mod.seen["limit"] = limit
            if raises:
                raise raises(mod)
            return iter(["m"] * n)

    mod.Anthropic = Anthropic
    return mod


def _probe_main(monkeypatch, anthropic_mod, *, key="test-key-value", **models):
    import sys
    import types

    cfg = {"default_model": "anthropic/claude-haiku-5-5", "fallback_model": "anthropic/claude-haiku-5-5",
           "hard_model": "anthropic/claude-haiku-5-5", "light_model": "anthropic/claude-haiku-5-5",
           "selectable_models": [types.SimpleNamespace(model="anthropic/claude-haiku-5-5")], **models}
    monkeypatch.setitem(sys.modules, "server.config", types.SimpleNamespace(settings=types.SimpleNamespace(**cfg)))
    monkeypatch.setitem(sys.modules, "anthropic", anthropic_mod)
    if key is None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    ns: dict = {"__name__": "kbsync_answer_key"}
    exec(ks.ANSWER_KEY_PY, ns)  # noqa: S102
    return ns["main"]()


def test_answer_key_script_lists_models_only_and_reports_ok(monkeypatch):
    mod = _fake_anthropic()
    assert _probe_main(monkeypatch, mod) == {"ok": True, "category": "ok", "models": 1}
    assert mod.seen["api_key"] == "test-key-value" and mod.seen["limit"] == 1


@pytest.mark.parametrize("exc,status,want", [
    # 前三个都是 APIStatusError 的子类: 必须先于它被接住, 否则全变成 provider_error
    ("AuthenticationError", 401, "key_invalid"),
    ("PermissionDeniedError", 403, "key_forbidden"),
    ("RateLimitError", 429, "rate_limited"),
    ("APIStatusError", 529, "provider_error"),
    ("APIConnectionError", None, "network_error"),
])
def test_answer_key_script_classifies_errors_without_echoing_them(monkeypatch, exc, status, want):
    def raises(mod):
        cls = getattr(mod, exc)
        return cls(status) if status else cls("connection refused sk-ant-api03-ShouldNeverLeak")

    res = _probe_main(monkeypatch, _fake_anthropic(raises=raises))
    assert res["ok"] is False and res["category"] == want and res.get("status") == status
    assert "sk-" not in json.dumps(res) and "test-key-value" not in json.dumps(res)


def test_answer_key_script_missing_key_and_unexpected_error(monkeypatch):
    assert _probe_main(monkeypatch, _fake_anthropic(), key=None) == {"ok": False, "category": "key_missing"}
    res = _probe_main(monkeypatch, _fake_anthropic(raises=lambda mod: KeyError("x")))
    assert res == {"ok": False, "category": "other", "error_class": "KeyError"}


def test_answer_key_script_probes_when_any_answer_model_is_anthropic(monkeypatch):
    """默认模型不是 Anthropic、但可选模型里有 (公开档用服务端 key 答题走的是可选模型): 必须探测。"""
    import types

    other = {k: "deepseek/deepseek-v4-pro" for k in ("default_model", "fallback_model", "hard_model", "light_model")}
    sel = [types.SimpleNamespace(model="anthropic/claude-haiku-5-5")]
    mod = _fake_anthropic(raises=lambda m: m.AuthenticationError(401))
    assert _probe_main(monkeypatch, mod, **other, selectable_models=sel)["category"] == "key_invalid"
    for field in ("fallback_model", "hard_model", "light_model"):
        mixed = {**other, field: "anthropic/claude-haiku-5-5"}
        mod = _fake_anthropic(raises=lambda m: m.AuthenticationError(401))
        res = _probe_main(monkeypatch, mod, **mixed, selectable_models=[types.SimpleNamespace(model="openai/gpt-x")])
        assert res["category"] == "key_invalid", field
    mod = _fake_anthropic()
    res = _probe_main(monkeypatch, mod, **other, selectable_models=[types.SimpleNamespace(model="openai/gpt-x")])
    assert res == {"ok": True, "category": "not_applicable", "providers": ["deepseek", "openai"]} and mod.seen == {}


# ── 部署前的网络预检: 子网 / 隔离 (都在临时验收之前, 不通过就什么都不动) ───────────
def _assert_nothing_happened(fake: PublicFake, site, before, formal_before) -> None:
    assert fake.formal() == formal_before and _snapshot(site["pub"]) == before and not site["touched"].exists()
    assert not [e for e in fake.events if e.startswith(("formal:", "temp:", "answer_key")) or e in ("fs:accept-stage", "fs:swap")]


@pytest.mark.parametrize("subnets,needle", [
    ({NET: "172.18.0.0/16"}, "先做网络重建那一步"),     # 现状: 网络还是 docker 自动分的网段
    ({}, "不存在或查不出"),
    ({NET: "10.201.8.0/24 10.201.9.0/24"}, "先做网络重建那一步"),
])
def test_public_network_with_the_wrong_subnet_stops_the_deploy(site, capsys, subnets, needle):
    fake = _fake(site, formal="running", swap=True)
    fake.net_subnets = subnets
    before, formal_before = _snapshot(site["pub"]), copy.deepcopy(fake.formal())
    assert _run(fake, site) == 1
    _assert_nothing_happened(fake, site, before, formal_before)
    out = capsys.readouterr().out
    assert "网络预检不通过" in out and needle in out and "P3_4_tunnel_drill.md 第 2 步" in out
    assert "iso:isolated" not in fake.events  # 网段不对就不必测隔离


def _unpinned(model: dict) -> dict:
    """隧道那条线合进来之前的形状: 公开网络没有 ipam 段 (docker 自动分配网段)。"""
    m = copy.deepcopy(model)
    assert m["networks"]["public"].pop("ipam")["config"][0]["subnet"] == SUBNET  # 确实去掉了写定的子网
    return m


def test_compose_without_a_pinned_subnet_stops_the_deploy(site, capsys):
    """隧道那条线没有合进来时, 公开 compose 没有给网络写定子网: 不能部署 (两条线要一起合并)。"""
    fake = _fake(site, formal="running", swap=False)
    fake.pub_model = _with_mount(_with_mount(_unpinned(PUB_MODEL), "/app/data", str(site["pub"])), "/app/.env", str(site["env"]))
    before, formal_before = _snapshot(site["pub"]), copy.deepcopy(fake.formal())
    assert _run(fake, site) == 1
    _assert_nothing_happened(fake, site, before, formal_before)
    assert "没有给公开网络写定子网" in capsys.readouterr().out and "net_check" not in fake.events


@pytest.mark.parametrize("knob,needle", [
    ("leaky", "judge 退出码 1"),           # 公开网络里的容器连得上内网: 规则没装或失效
    ("control_dead", "judge 退出码 2"),    # 对照侧也连不上: 证明不了是规则挡的, 无结论也不放行
    ("wrong_src", "judge 退出码 2"),       # 隔离侧的源地址不在公开网段里: 测的不是公开网络 (无结论, 不放行)
    ("no_egress", "judge 退出码 1"),       # 隔离侧连外网也不通: 整个容器没网, 「内网全不通」没有意义
    ("garbage", "隔离探测没有跑成"),       # 输出是合法 JSON 但不是一份观测
    ("probe_crash", "隔离探测没有跑成"),
    ("probe_rc", "隔离探测没有跑成"),      # 有输出但退出码非零: 不能当成一次完整的观测
    ("no_script", "不存在"),
    ("no_targets", "目标清单不对"),
    ("bad_target", "目标清单不对"),
])
def test_isolation_check_failure_stops_the_deploy(site, capsys, knob, needle):
    fake = _fake(site, formal="running", swap=True)
    over = {}
    if knob == "leaky":
        fake.iso_lan_state = "open"
    elif knob == "control_dead":
        fake.ctl_lan_state = "timeout"
    elif knob == "wrong_src":
        fake.iso_src = "172.17.0.9"
    elif knob == "no_egress":
        fake.iso_egress_state = "timeout"
    elif knob == "garbage":
        fake.fail.add("iso_garbage")
    elif knob == "probe_crash":
        fake.fail.add("iso_probe")
    elif knob == "probe_rc":
        fake.fail.add("iso_probe_rc")
    elif knob == "no_script":
        site["probe"].unlink()
    elif knob == "no_targets":
        over["isolation_lan"] = ""
    elif knob == "bad_target":
        over["isolation_egress"] = "api.anthropic.com:443 $(id):1"
    before, formal_before = _snapshot(site["pub"]), copy.deepcopy(fake.formal())
    assert _run(fake, site, **over) == 1
    _assert_nothing_happened(fake, site, before, formal_before)
    out = capsys.readouterr().out
    assert "网络预检不通过" in out and needle in out and "旧版继续对外" in out
    assert fake.violations == []


def test_isolation_probe_runs_in_the_public_network_with_a_bridge_control(site):
    fake = _fake(site, formal="running", swap=False, cols={"stage": _cols(4329)})
    assert _run(fake, site) == 0
    iso, ctl = [c for c in fake.calls if c[0] == "run" and "probe" in c]
    assert iso[iso.index("--network") + 1] == NET and ctl[ctl.index("--network") + 1] == "bridge"
    lan = [iso[i + 1] for i, x in enumerate(iso) if x == "--lan"]
    assert lan == LAN.split() == [ctl[i + 1] for i, x in enumerate(ctl) if x == "--lan"]
    assert [iso[i + 1] for i, x in enumerate(iso) if x == "--egress"] == EGRESS.split() and "--egress" not in ctl
    assert iso[iso.index("--entrypoint") + 1] == "python" and iso[iso.index(IMG_NEW) + 1:][:2] == ["-", "probe"]


def test_public_network_is_read_from_the_compose_model():
    assert ks.public_network(PUB_TUNNEL_MODEL) == (NET, SUBNET)
    assert ks.public_network(PUB_MODEL) == (NET, SUBNET)  # 合并后两份 fixture 相同 (都是写定子网的 compose)
    assert ks.public_network(_unpinned(PUB_MODEL)) == (NET, None)  # 隧道那条线合进来之前的形状: 没有写定子网
    two = copy.deepcopy(PUB_TUNNEL_MODEL)
    two["services"]["api"]["networks"]["other"] = None
    with pytest.raises(RuntimeError):
        ks.public_network(two)
    multi = copy.deepcopy(PUB_TUNNEL_MODEL)
    multi["networks"]["public"]["ipam"]["config"].append({"subnet": "10.9.9.0/24"})
    assert ks.public_network(multi) == (NET, None)  # 说不清是哪个网段时不猜


# ── 预检阶段就结束的情况 ──────────────────────────────────────────────────
@pytest.mark.parametrize("image_fp,decision", [(NEW, "missing"), (None, "unknown")])
def test_missing_candidate_is_a_warning_and_nothing_is_touched(site, capsys, image_fp, decision):
    fake = PublicFake(site["pub"], site["env"], formal="stopped", priv_model=site["priv_model"])
    fake.image_fps = {IMG_NEW: image_fp} if image_fp else {}
    before = _snapshot(site["pub"])
    assert _run(fake, site) == 0  # D1: 只告警, 不让运行变红
    out = capsys.readouterr().out
    assert f"::warning::公开 chroma 与镜像 KB 指纹不一致 ({decision})" in out
    assert fake.formal() == {"running": False, "image": IMG_OLD} and _snapshot(site["pub"]) == before
    assert not [e for e in fake.events if e.startswith(("formal:", "temp:", "answer_key"))]
    assert not site["touched"].exists()


def test_journal_pending_fails_and_nothing_is_touched(site, capsys):
    fake = _fake(site, formal="running", swap=True)
    (site["pub"] / ks.JOURNAL).write_text("{}")
    before = _snapshot(site["pub"])
    assert _run(fake, site) == 1
    assert "kbsync_swap.json" in capsys.readouterr().out
    assert fake.formal() == {"running": True, "image": IMG_OLD} and _snapshot(site["pub"]) == before
    assert not [e for e in fake.events if e.startswith(("formal:", "temp:"))]


def test_paths_mismatch_refuses_before_any_mount(site, capsys):
    fake = _fake(site, formal="running", swap=True)
    other = site["pub"].parent / "elsewhere"
    assert _run(fake, site, data_root=str(other)) == 1
    assert "路径不一致" in capsys.readouterr().out
    assert not [c for c in fake.calls if "--mount" in c] and fake.events == []


def test_public_root_pointing_into_private_root_is_refused(site):
    """公开 compose 与 workflow 一起指到私有根: 两边"一致", 只有与私有 compose 的比对能拦。"""
    fake = _fake(site, formal="running", swap=False)
    fake.pub_model = _with_mount(fake.pub_model, "/app/data", str(site["priv"]))
    assert _run(fake, site, data_root=str(site["priv"])) == 1
    assert not [c for c in fake.calls if "--mount" in c]


def test_image_must_match_compose(site):
    fake = _fake(site, formal="running", swap=False)
    assert _run(fake, site, image="registry.example/other:" + TAG_NEW) == 1
    assert fake.events == []


def test_unknown_formal_state_stops_before_touching(site, capsys):
    fake = _fake(site, formal="running", swap=False)
    fake.fail.add("inspect_formal_after_up")
    fake.events.append("formal:up")  # 让 inspect 从一开始就报 daemon 错误 (不是"容器不存在")
    assert _run(fake, site) == 1
    assert fake.formal() == {"running": True, "image": IMG_OLD} and not site["touched"].exists()
    assert fake.events == ["formal:up", "fs:accept-clean", "fs:predeploy-check"]  # 查不出状态就到此为止
    out = capsys.readouterr().out
    assert "部署前检查出错" in out and "正式容器和正式数据都没有动" in out


def test_predeploy_infrastructure_error_is_a_clean_failure(site, capsys):
    fake = _fake(site, formal="running", swap=True)
    fake.skip_fs.add("predeploy-check")
    assert _run(fake, site) == 1
    assert "部署前检查出错" in capsys.readouterr().out and fake.formal() == {"running": True, "image": IMG_OLD}
    assert not site["touched"].exists() and not Path(str(site["touched"]) + ".pid").exists()


def test_stale_marker_from_an_earlier_run_does_not_trigger_the_abort_stop(site):
    """上一次运行留下的「已动过」标记 + 这一次在临时验收阶段失败: 兜底步骤不能因此停掉没被动过的正式容器。"""
    site["touched"].write_text(FORMAL)
    fake = _fake(site, formal="running", swap=False)
    fake.stale.add(TEMP)
    assert _run(fake, site) == 1 and not site["touched"].exists()
    abort = ["public-abort", "--compose-file", "deploy/container/compose.public.yml", "--touched-file", str(site["touched"])]
    assert ks.main(abort, docker=fake) == 0
    assert fake.formal() == {"running": True, "image": IMG_OLD} and "formal:stop" not in fake.events


# ── 验收期间正式容器的状态被人改了: 以动手那一刻为准 ───────────────────────────
@pytest.mark.parametrize("swap", [True, False])
def test_site_stopped_by_an_operator_during_acceptance_is_not_brought_back_up(site, capsys, swap):
    fake = _fake(site, formal="running", swap=swap, cols=CLEAN if swap else {"stage": _cols(4329)})
    fake.on_temp_up = lambda: fake.containers[FORMAL].update(running=False)  # 紧急下线
    assert _run(fake, site) == 0
    fake.check()
    assert fake.starts() == [] and fake.formal() == {"running": False, "image": IMG_NEW}
    out = capsys.readouterr().out
    assert "验收期间正式容器的状态变了" in out and "公开容器保持停止" in out


def test_site_started_by_an_operator_during_acceptance_is_treated_as_running(site):
    fake = _fake(site, formal="stopped", swap=True)
    fake.on_temp_up = lambda: fake.containers[FORMAL].update(running=True)
    assert _run(fake, site) == 0
    fake.check()  # 含不变量: 换数据时正式容器必须是停的
    _order(fake.events, "formal:stop", "fs:swap", "formal:up", "fs:finish")
    assert fake.formal() == {"running": True, "image": IMG_NEW}


# ── 红线: 线上的公开 chroma 里出现 KB 以外的集合 → 停站并失败 (不管这次换不换数据) ──────
# 三个多出来的集合: 两个是本仓约定的代号形态 (可以原样写进日志), 一个名字不按约定 (可能带真实研究的标识, 只写指纹)
ODD_NAME = "Trial-ACME-2031-oncology"
DIRTY_LIVE = {**_cols(4329, study_st01=(5, "d1"), sdtm_kb_v2=(9, "d2")), ODD_NAME: {"count": 3, "digest": "d3"}}


@pytest.mark.parametrize("swap", [False, True])
def test_non_kb_collection_in_live_public_data_stops_the_site(site, capsys, swap):
    cols = {"chroma": DIRTY_LIVE, CAND: _cols(4333), "stage": _cols(4333 if swap else 4329)}
    fake = _fake(site, formal="running", swap=swap, cols=cols)
    before = _snapshot(site["pub"])
    assert _run(fake, site) == 1
    fake.check()
    assert fake.formal() == {"running": False, "image": IMG_OLD} and fake.starts() == []  # 停了, 没有换镜像, 没有再起
    _order(fake.events, "fs:guard-copy", "fs:swap-status", "formal:stop")  # 在副本上读集合 → 先看 journal → 才停
    assert not [e for e in fake.events if e.startswith(("temp:", "iso:", "answer_key")) or e in ("fs:swap", "fs:restore", "fs:accept-stage")]
    assert _snapshot(site["pub"]) == before  # 只停站, 不改数据
    assert [c for c in fake.calls if c[:1] == ["compose"] and "config" not in c][-1][3:] == ["stop"]  # 整个公开项目
    out = capsys.readouterr().out
    assert "发现 sdtm_kb_v1 以外的集合（3 个：" in out and "sdtm_kb_v2、study_st01" in out  # 写明发现了哪些
    assert ODD_NAME not in out and "ACME" not in out  # 不按约定的名字不进日志
    assert f"<名字不按约定，已隐去：sha256 前 10 位 {hashlib.sha256(ODD_NAME.encode()).hexdigest()[:10]}，长 {len(ODD_NAME)}>" in out
    assert f"docker start {FORMAL}" in out  # 处理完之后怎么恢复
    assert "公开实例已停止" in out and "数据没有改动" in out
    assert "故意偏严" in out and "KB_COLLECTION" in out and "server/instance.py" in out  # 正当新增要改哪里
    assert site["touched"].read_text() == FORMAL  # 中断兜底也知道正式容器被动过


def test_non_kb_collection_in_live_data_keeps_a_stopped_site_stopped(site, capsys):
    fake = _fake(site, formal="stopped", swap=False, cols={"chroma": DIRTY_LIVE})
    assert _run(fake, site) == 1
    assert fake.formal() == {"running": False, "image": IMG_OLD} and fake.starts() == []
    assert "formal:create" not in fake.events and "发现 sdtm_kb_v1 以外的集合" in capsys.readouterr().out


@pytest.mark.parametrize("why,needle", [("unknown", "状态判不出"), ("pending", "有残留")])
def test_contaminated_live_data_with_unclear_journal_takes_no_action(site, capsys, why, needle):
    """先看 journal: 判不出或有残留时保持现状并失败, 不停站、不改数据。"""
    fake = _fake(site, formal="running", swap=False, cols={"chroma": DIRTY_LIVE})
    if why == "unknown":
        fake.skip_fs.add("swap-status")
    else:  # 预检之后才出现的 journal (预检时没有, 否则早就按 journal_pending 结束了)
        orig = fake.run

        def run(args, **kw):
            res = orig(args, **kw)
            if "guard-clean" in args:
                (site["pub"] / ks.JOURNAL).write_text("{}")
            return res

        fake.run = run
    before = {k: v for k, v in _snapshot(site["pub"]).items() if k != ks.JOURNAL}
    assert _run(fake, site) == 1
    assert fake.formal() == {"running": True, "image": IMG_OLD}
    assert not [e for e in fake.events if e.startswith("formal:")] and not site["touched"].exists()
    assert {k: v for k, v in _snapshot(site["pub"]).items() if k != ks.JOURNAL} == before
    out = capsys.readouterr().out
    assert needle in out and "保持现状，没有停站、没有改数据" in out and "sdtm_kb_v2" in out and ODD_NAME not in out


def test_contaminated_live_data_when_the_stop_does_not_take_effect(site, capsys):
    fake = _fake(site, formal="running", swap=False, cols={"chroma": DIRTY_LIVE})
    fake.fail.add("stop")
    assert _run(fake, site) == 1
    out = capsys.readouterr().out
    assert "没有确认它停下来了，请立即人工确认" in out and "公开实例已停止" not in out
    assert fake.starts() == [] and site["touched"].exists()


def test_many_extra_collections_are_listed_up_to_a_limit(site, capsys):
    many = _cols(4329, **{f"sdtm_c{i:02d}": (1, "d") for i in range(14)})
    fake = _fake(site, formal="running", swap=False, cols={"chroma": many})
    assert _run(fake, site) == 1
    out = capsys.readouterr().out
    assert "14 个：sdtm_c00、sdtm_c01" in out and "sdtm_c09 等共 14 个" in out and "sdtm_c10" not in out


@pytest.mark.parametrize("name,shown", [
    ("study_st01", True), ("study_st01_docs", True), ("study_st123_cards_v2", True), ("sdtm_kb_v2", True),
    ("study_ACME", False), ("study_st1", False), ("study_st01-real", False), ("Trial 2031", False), ("sdtm_kb_v2\nx", False),
    ("st01", False), ("", False),
])
def test_only_conventional_collection_names_are_printed(name, shown):
    out = ks._show_collection(name)
    assert (out == name) is shown
    if not shown:
        assert (name not in out or name == "") and "sha256 前 10 位" in out and f"长 {len(name)}" in out


@pytest.mark.parametrize("image_fp,decision", [(NEW, "missing"), (None, "unknown")])
def test_red_line_check_also_runs_when_the_deploy_would_be_skipped(site, capsys, image_fp, decision):
    """公开数据落后、又没有过闸候选 (最常见的「这次不换数据」): 以前只告警跳过; 现在先做红线检查, 脏了照样停站。"""
    fake = PublicFake(site["pub"], site["env"], formal="running", priv_model=site["priv_model"], cols={"chroma": DIRTY_LIVE})
    fake.probe_script = site["probe"].read_bytes()
    fake.image_fps = {IMG_NEW: image_fp} if image_fp else {}
    before = _snapshot(site["pub"])
    assert _run(fake, site) == 1
    fake.check()
    assert fake.formal() == {"running": False, "image": IMG_OLD} and _snapshot(site["pub"]) == before
    out = capsys.readouterr().out
    assert "发现 sdtm_kb_v1 以外的集合" in out and "公开实例已停止" in out and "::warning::公开 chroma 与镜像 KB 指纹不一致" not in out
    # 干净时照旧: 只告警跳过, 不停站
    clean = PublicFake(site["pub"], site["env"], formal="running", priv_model=site["priv_model"])
    clean.image_fps = {IMG_NEW: image_fp} if image_fp else {}
    assert _run(clean, site) == 0 and clean.formal() == {"running": True, "image": IMG_OLD}
    assert f"::warning::公开 chroma 与镜像 KB 指纹不一致 ({decision})" in capsys.readouterr().out


@pytest.mark.parametrize("dirty", [True, False])
def test_failing_to_remove_the_guard_copy_does_not_lose_the_finding(site, capsys, dirty):
    """已经读出了集合, 副本却删不掉: 结论不能丢 —— 脏的照样停站, 干净的照常继续; 两种情况都告警有副本残留。"""
    cols = {"chroma": DIRTY_LIVE if dirty else _cols(4329), "stage": _cols(4329)}
    fake = _fake(site, formal="running", swap=False, cols=cols)
    fake.skip_fs.add("guard-clean")
    assert _run(fake, site) == (1 if dirty else 0)
    out = capsys.readouterr().out
    assert "::warning::核对用的副本 kbsync_guard_" in out and "请人工删除" in out
    if dirty:
        assert fake.formal() == {"running": False, "image": IMG_OLD} and "公开实例已停止" in out
    else:
        assert fake.formal() == {"running": True, "image": IMG_NEW}


def test_unreadable_live_collections_is_a_clean_failure_without_stopping(site, capsys):
    """读不出线上数据的集合 (副本打不开): 不是「发现了非 KB 集合」, 不停站; 按部署前检查出错处理。"""
    fake = _fake(site, formal="running", swap=False, cols={"chroma": None})
    assert _run(fake, site) == 1
    assert fake.formal() == {"running": True, "image": IMG_OLD} and "formal:stop" not in fake.events
    assert "部署前检查出错" in capsys.readouterr().out and not list(site["pub"].glob("kbsync_guard_*"))


# ── 换入核对不过 (正式容器还没停) ───────────────────────────────────────────
def test_swap_guard_refusal_happens_before_formal_is_stopped(site, capsys):
    """临时验收之后、停机之前, 换入源里多出一个非 KB 集合 (线上是干净的, 验收用的副本也是干净的):
    只有 kb-only 的换入前置核对能拦, 而且拦在停机之前。"""
    fake = _fake(site, formal="running", swap=True)
    fake.on_answer_key = lambda: fake.cols.update({CAND: _cols(4333, study_zz=(5, "d1"))})
    before = _snapshot(site["pub"])
    assert _run(fake, site) == 1
    fake.check()
    assert fake.formal() == {"running": True, "image": IMG_OLD}
    assert not [e for e in fake.events if e.startswith("formal:")] and "fs:swap" not in fake.events
    assert _snapshot(site["pub"]) == before and not site["touched"].exists()
    out = capsys.readouterr().out
    assert "换入前置核对不通过" in out and "旧版继续对外" in out and "study_zz" not in out


@pytest.mark.parametrize("change", ["source_lost_kb", "both_gained_the_same"])
def test_kb_only_pre_guard_catches_what_the_equality_check_lets_through(site, capsys, change):
    """临时验收之后数据又变了, 而且变成「线上与换入源的非 KB 集合相同」的样子 —— 私有站用的那道相等比较会放行,
    只有 kb-only 能拦: 换入源丢了 KB 集合 (两边的非 KB 集合都是空, 相等); 或两边多出同一个非 KB 集合。"""
    fake = _fake(site, formal="running", swap=True)
    same_extra = {"chroma": _cols(4329, study_zz=(5, "d1")), CAND: _cols(4333, study_zz=(5, "d1"))}
    fake.on_answer_key = lambda: fake.cols.update({CAND: {}} if change == "source_lost_kb" else same_extra)
    before = _snapshot(site["pub"])
    assert _run(fake, site) == 1
    fake.check()
    assert fake.formal() == {"running": True, "image": IMG_OLD} and _snapshot(site["pub"]) == before
    assert not [e for e in fake.events if e.startswith("formal:")] and "fs:swap" not in fake.events
    assert "换入前置核对不通过" in capsys.readouterr().out


# ── 验收脚本本身 (与容器里跑的是同一段源码; urlopen 用替身, 数实际发出的请求) ─────────
def _run_accept_py(monkeypatch, *, tier="public", openapi=404):
    import io
    import urllib.error
    import urllib.request

    calls = []

    def fake_urlopen(url, timeout=None):
        calls.append(url)
        if url.endswith("/api/info"):
            return io.BytesIO(json.dumps({"tier": tier}).encode())
        if openapi == 200:
            return io.BytesIO(b"{}")
        raise urllib.error.HTTPError(url, openapi, "x", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    try:
        exec(ks.ACCEPT_PY, {"__name__": "kbsync_accept"})  # noqa: S102
        return 0, calls
    except SystemExit as e:
        return e.code, calls


def test_acceptance_script_sends_exactly_two_requests(monkeypatch, capsys):
    """数的是实际发出的请求 (不是源码里的字样): 公开档带全局限流, 验收多发请求会逼近突发上限。"""
    rc, calls = _run_accept_py(monkeypatch)
    assert rc == 0 and calls == ["http://127.0.0.1:8000/api/info", "http://127.0.0.1:8000/openapi.json"]
    assert "tier=public, /openapi.json 404" in capsys.readouterr().out
    burst = int(PUB_TUNNEL_MODEL["services"]["api"]["environment"]["SDTM_RAG_RATE_LIMIT_BURST"])
    assert len(calls) * 4 <= burst


@pytest.mark.parametrize("kw,needle", [
    ({"tier": "private"}, "tier != public"),       # 档位不对
    ({"tier": None}, "tier != public"),
    ({"openapi": 200}, "/openapi.json 未关闭"),     # 内部接口没有关
    ({"openapi": 500}, "/openapi.json 返回 500"),   # 不是 404 也不算关闭
    ({"openapi": 403}, "/openapi.json 返回 403"),
])
def test_acceptance_script_fails_on_wrong_tier_or_open_internals(monkeypatch, kw, needle):
    rc, calls = _run_accept_py(monkeypatch, **kw)
    assert rc == needle and len(calls) <= 2


# ── 动过正式容器之后失败: 停机, 数据按 journal 退回, 绝不启动 ─────────────────
def _assert_halted(fake: PublicFake, site, *, data_restored: bool = True) -> None:
    assert fake.formal() is None or fake.formal()["running"] is False
    assert site["touched"].exists()
    if data_restored:
        assert (site["pub"] / "chroma" / "chroma.sqlite3").read_text() == "public-chroma"
        assert (site["pub"] / "meta" / "meta.yaml").read_text() == "public-meta"
        assert not (site["pub"] / ks.JOURNAL).exists()
        assert not list(site["pub"].glob("chroma_prev_*"))
    last_fail = max(i for i, e in enumerate(fake.events) if e == "formal:stop")
    assert "formal:up" not in fake.events[last_fail:] and "formal:create" not in fake.events[last_fail:]


def test_swap_refused_after_stop_stays_stopped_with_data_intact(site, capsys):
    """停机之后主闸才发现问题 (停机前的预检是干净的): 数据没动, 保持停止, 不重启旧容器。"""
    fake = _fake(site, formal="running", swap=True)
    fake.after_stop = lambda: fake.cols.update({CAND: _cols(4333, study_zz=(5, "d1"))})
    before = _snapshot(site["pub"])
    assert _run(fake, site) == 1
    fake.check()
    _assert_halted(fake, site)
    assert fake.starts() == [] and "fs:swap" not in fake.events and "fs:restore" not in fake.events
    assert _snapshot(site["pub"]) == before
    assert ks.detect(site["pub"], NEW)["result"] == "gated"  # 候选还在
    out = capsys.readouterr().out
    assert "换入被拒绝或失败" in out and "数据根没有 journal" in out and "已停止" in out
    # 容器没有被替换: 摘要说的是旧镜像, 不能说成「没有通过的新镜像」
    assert f"正式容器仍是镜像 {IMG_OLD}（没有被替换）" in out and "不要直接 docker start" not in out


def test_swap_crash_midway_is_rolled_back_and_stays_stopped(site, capsys):
    fake = _fake(site, formal="running", swap=True)
    fake.fail_fs = {"swap"}  # 真的换了, 然后报错: journal 在, 数据是新的
    assert _run(fake, site) == 1
    fake.check()
    _assert_halted(fake, site)
    assert fake.starts() == []
    _order(fake.events, "formal:stop", "fs:swap-status", "fs:restore")
    out = capsys.readouterr().out
    assert "已按 journal 把 chroma / meta 退回部署前状态" in out and f"正式容器仍是镜像 {IMG_OLD}" in out


@pytest.mark.parametrize("kind", ["unhealthy", "tier", "stale", "exits"])
def test_formal_recheck_failure_after_swap_restores_data_and_halts(site, capsys, kind):
    fake = _fake(site, formal="running", swap=True)
    {"unhealthy": fake.unhealthy, "tier": fake.bad_tier, "stale": fake.stale, "exits": fake.exited}[kind].add(FORMAL)
    if kind == "exits":
        fake.unhealthy.add(FORMAL)
    assert _run(fake, site) == 1
    fake.check()
    _assert_halted(fake, site)
    assert len(fake.starts()) == 1  # 只有部署本身那一次启动, 失败之后没有第二次
    assert fake.events.count("formal:stop") == 2 and "fs:finish" not in fake.events
    tail = fake.events[fake.events.index("formal:up"):]  # 起来之后: 停 → 看 journal → 退数据
    _order(tail, "formal:up", "formal:stop", "fs:swap-status", "fs:restore")
    assert fake.events.index("fs:swap") < fake.events.index("formal:up")
    assert ks.detect(site["pub"], NEW)["result"] == "gated"
    out = capsys.readouterr().out
    assert "正式容器复验不通过" in out and "不要直接 docker start" in out
    assert f"正式容器现在是镜像 {IMG_NEW}（没有通过的那一版），部署前是 {IMG_OLD}" in out


def test_formal_recheck_failure_without_swap_halts(site):
    fake = _fake(site, formal="running", swap=False, cols={"stage": _cols(4329)})
    fake.stale.add(FORMAL)
    before = _snapshot(site["pub"])
    assert _run(fake, site) == 1
    _assert_halted(fake, site)
    assert _snapshot(site["pub"]) == before and "fs:restore" not in fake.events


@pytest.mark.parametrize("formal,knob", [("running", "up"), ("stopped", "create"), (None, "create")])
def test_container_replacement_failure_after_swap_restores_and_halts(site, formal, knob):
    fake = _fake(site, formal=formal, swap=True)
    fake.fail.add(knob)
    assert _run(fake, site) == 1
    fake.check()
    _assert_halted(fake, site)
    assert "fs:restore" in fake.events and "fs:finish" not in fake.events


def test_originally_stopped_is_never_started_on_any_failure(site):
    for knob in ("create", None):
        fake = _fake(site, formal="stopped", swap=True) if knob else PublicFake(
            site["pub"], site["env"], formal="stopped", priv_model=site["priv_model"])
        if knob:
            fake.fail.add(knob)
        else:
            fake.fail_fs = {"swap"}
        assert _run(fake, site) == 1
        assert fake.starts() == [] and fake.formal()["running"] is False
        assert (site["pub"] / "chroma" / "chroma.sqlite3").read_text() == "public-chroma"


def test_restore_failure_keeps_journal_and_blocks_the_next_run(site, capsys):
    fake = _fake(site, formal="running", swap=True)
    fake.stale.add(FORMAL)
    fake.skip_fs.add("restore")  # 退回没做成
    assert _run(fake, site) == 1
    _assert_halted(fake, site, data_restored=False)
    assert (site["pub"] / ks.JOURNAL).exists() and len(fake.starts()) == 1
    assert "退回数据失败，journal 保留" in capsys.readouterr().out
    # 下一次公开部署与 kb-sync 公开腿都被 journal_pending 拦住; 私有根与此无关
    fake2 = PublicFake(site["pub"], site["env"], formal="stopped", priv_model=site["priv_model"])
    fake2.containers[FORMAL]["image"] = IMG_NEW
    assert _run(fake2, site) == 1 and fake2.starts() == []
    assert ks.detect(site["pub"], NEW) == {"result": "journal_pending"}
    assert ks.detect(site["priv"], NEW)["result"] == "changed"


def test_unknown_journal_state_touches_no_data(site, capsys):
    fake = _fake(site, formal="running", swap=True)
    fake.stale.add(FORMAL)
    fake.skip_fs.add("swap-status")
    assert _run(fake, site) == 1
    _assert_halted(fake, site, data_restored=False)
    assert "fs:restore" not in fake.events and (site["pub"] / ks.JOURNAL).exists()
    assert "无法判断 journal 状态，没有改动数据" in capsys.readouterr().out


def test_no_restore_while_formal_cannot_be_confirmed_stopped(site, capsys):
    fake = _fake(site, formal="running", swap=True)
    fake.stale.add(FORMAL)
    orig = fake.run

    def run(args, **kw):  # 第二次 stop (失败处理里的那次) 停不下来
        if args[0] == "compose" and args[3:] == ["stop"] and "formal:up" in fake.events:
            fake.events.append("formal:stop")
            return subprocess.CompletedProcess([], 1, b"", b"cannot stop")
        return orig(args, **kw)

    fake.run = run
    assert _run(fake, site) == 1
    assert fake.violations == [] and "fs:restore" not in fake.events and "fs:swap-status" not in fake.events
    assert (site["pub"] / ks.JOURNAL).exists()
    out = capsys.readouterr().out
    assert "状态不明，请立即人工确认" in out and "没有确认正式容器已停止" in out


def test_stop_failure_before_swap_leaves_data_alone(site):
    fake = _fake(site, formal="running", swap=True)
    fake.fail.add("stop")
    before = _snapshot(site["pub"])
    assert _run(fake, site) == 1
    assert "fs:swap" not in fake.events and _snapshot(site["pub"]) == before and fake.violations == []


def test_unexpected_error_after_touching_formal_also_halts(site, capsys):
    fake = _fake(site, formal="running", swap=True)
    fake.fail.add("inspect_formal_after_up")  # up 之后 docker 查不出状态 → RuntimeError
    assert _run(fake, site) == 1
    assert "fs:finish" not in fake.events and fake.events[-1] != "formal:up"
    assert "RuntimeError" in capsys.readouterr().out


def _raising_on(fake: PublicFake, pred, exc):
    orig = fake.run

    def run(args, **kw):
        if pred(args):
            raise exc
        return orig(args, **kw)

    fake.run = run


def test_error_inside_the_failure_handler_is_not_reported_as_untouched(site, capsys):
    """复验不过 → 失败处理里的 compose stop 自己也出错 (docker 不见了): 摘要不能说「都没有动」。"""
    fake = _fake(site, formal="running", swap=True)
    fake.stale.add(FORMAL)
    _raising_on(fake, lambda a: a[0] == "compose" and a[3:] == ["stop"] and "formal:up" in fake.events,
                FileNotFoundError("docker"))
    assert _run(fake, site) == 1
    out = capsys.readouterr().out
    assert "都没有动" not in out and "部署前检查出错" not in out
    assert "状态不明，请立即人工确认" in out and "没有确认正式容器已停止" in out
    assert "fs:restore" not in fake.events and site["touched"].exists()  # 没确认停止 → 不退数据; 标记在 → 兜底会停


def test_error_escaping_after_formal_was_touched_is_reported_as_touched(site, capsys, monkeypatch):
    fake = _fake(site, formal="running", swap=True)
    fake.stale.add(FORMAL)

    def boom(*a, **k):
        raise OSError("disk gone")

    monkeypatch.setattr(ks, "public_halt", boom)  # 假设最后一道处理本身也坏了
    assert _run(fake, site) == 1
    out = capsys.readouterr().out
    assert "动过正式容器之后出错" in out and "都没有动" not in out and "确认之前不要 docker start" in out


def test_prune_oserror_after_a_successful_deploy_does_not_fail_it(site, capsys):
    fake = _fake(site, formal="running", swap=True)
    _raising_on(fake, lambda a: "-i" in a and "-" in a and a[a.index("-") + 1] == "prune", FileNotFoundError("docker"))
    assert _run(fake, site) == 0
    out = capsys.readouterr().out
    assert "::warning::prune 失败" in out and "成功：公开实例已换成镜像" in out
    assert fake.formal() == {"running": True, "image": IMG_NEW}


def test_site_restarted_during_the_post_stop_guard_is_not_swapped(site, capsys):
    """停机之后的换入核对要复制 chroma, 要一会儿; 期间容器又被人起来了 → 不换数据, 停机。"""
    fake = _fake(site, formal="running", swap=True)
    fake.on_main_guard = lambda: fake.containers[FORMAL].update(running=True)
    before = _snapshot(site["pub"])
    assert _run(fake, site) == 1
    assert fake.violations == [] and "fs:swap" not in fake.events and _snapshot(site["pub"]) == before
    assert fake.formal()["running"] is False and fake.starts() == []
    assert "换入之前正式容器又在运行" in capsys.readouterr().out


def test_prune_failure_after_finish_is_only_a_warning(site, capsys):
    fake = _fake(site, formal="running", swap=True)
    fake.skip_fs.add("prune")
    assert _run(fake, site) == 0
    assert "::warning::prune 失败" in capsys.readouterr().out
    assert fake.formal() == {"running": True, "image": IMG_NEW} and not (site["pub"] / ks.JOURNAL).exists()


# ── 清理: 成功、失败、上次被杀留下的 ─────────────────────────────────────────
def test_leftovers_from_a_killed_run_are_swept_first(site):
    old_stage = site["pub"].parent / f"{ks.ACCEPT_PREFIX}20261101T000000Z" / "data" / "chroma"
    old_stage.mkdir(parents=True)
    fake = _fake(site, formal="running", swap=False, cols={"stage": _cols(4329)})
    fake.containers[TEMP] = {"running": True, "image": IMG_OLD}
    assert _run(fake, site) == 0
    fake.check()
    _order(fake.events, "temp:rm", "fs:accept-clean", "net_check", "temp:up")
    assert not old_stage.exists()


def test_cleanup_problems_are_reported_not_hidden(site, capsys):
    fake = _fake(site, formal="running", swap=False, cols={"stage": _cols(4329)})
    fake.fail.add("rm")
    assert _run(fake, site) == 0
    assert f"::warning::临时容器 {TEMP} 删不掉" in capsys.readouterr().out


def test_accept_down_cli_and_public_abort(site, capsys):
    stage = site["pub"].parent / f"{ks.ACCEPT_PREFIX}{TS}" / "data"
    stage.mkdir(parents=True)
    fake = _fake(site, formal="running", swap=False)
    fake.containers[TEMP] = {"running": True, "image": IMG_NEW}
    assert ks.main(["accept-down", "--data-root", str(site["pub"]), "--image", IMG_NEW], docker=fake) == 0
    fake.check()
    abort = ["public-abort", "--compose-file", "deploy/container/compose.public.yml", "--touched-file", str(site["touched"])]
    assert ks.main(abort, docker=fake) == 0
    assert fake.formal()["running"] is True and "formal:stop" not in fake.events  # 没动过正式容器 → 不停
    site["touched"].write_text(FORMAL)
    assert ks.main(abort, docker=fake) == 0
    assert fake.formal()["running"] is False and "fs:restore" not in fake.events  # 只停机, 不碰数据
    assert fake.events[-1] == "formal:stop" and [c for c in fake.calls if c[:1] == ["compose"]][-1][3:] == ["stop"]  # 整个项目
    fake.containers[FORMAL]["running"] = True
    fake.fail.add("stop")  # stop 没生效: 以容器的实际状态为准, 不看 stop 的退出码
    assert ks.main(abort, docker=fake) == 1
    assert "没有确认公开实例已停止" in capsys.readouterr().out


def test_abort_first_ends_a_deploy_process_that_is_still_alive(site):
    """job 被取消后 deploy-public 进程可能还活着: 兜底先结束它 (否则它会在兜底之后继续动正式容器), 哪怕还没动过。"""
    import os as _os
    import signal as _signal
    import sys as _sys
    import time as _time

    # 编排进程 + 它起的子进程 (相当于还在跑的 docker compose up), 同一个进程组
    code = ("import subprocess, sys, time; c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
            "print(c.pid, flush=True); time.sleep(60)")
    # 多带的两个参数只为了让命令行里有 kbsync 与 deploy-public (兜底在 Linux 上会核对 /proc/<pid>/cmdline)
    proc = subprocess.Popen([_sys.executable, "-c", code, "kbsync.py", "deploy-public"], stdout=subprocess.PIPE,
                            text=True, start_new_session=True)
    child = int(proc.stdout.readline())
    try:
        Path(str(site["touched"]) + ".pid").write_text(f"{proc.pid} {_os.getpgid(proc.pid)}")
        fake = _fake(site, formal="running", swap=False)
        a = ks.build_parser().parse_args(["public-abort", "--compose-file", "deploy/container/compose.public.yml",
                                          "--touched-file", str(site["touched"])])
        assert ks.public_abort(fake, a, sleep=lambda s: proc.wait(timeout=5) if proc.poll() is None else None) == 0
        assert proc.poll() is not None  # 编排进程已结束

        def zombie(pid):  # 已经被结束、只是没人回收: /proc/<pid>/stat 里的状态是 Z (没有 /proc 的系统上无从判断, 算不是)
            try:
                return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] == "Z"
            except (OSError, IndexError):
                return False

        def alive(pid):  # 被结束但还没被收尸的进程 kill(0) 仍成功: 等到它真正消失, 最多 5 秒
            for _ in range(50):
                try:
                    _os.kill(pid, 0)
                except ProcessLookupError:
                    return False
                if zombie(pid):  # CI 的 job 容器里 1 号进程是 sleep, 不回收孤儿: 僵尸会一直留着, 但它不会再执行任何东西
                    return False
                _time.sleep(0.1)
            return True

        assert not alive(child), "编排进程起的子进程还活着: 它会在兜底之后继续动正式容器"
        assert fake.formal()["running"] is True and "formal:stop" not in fake.events  # 没动过 → 不停
        assert not Path(str(site["touched"]) + ".pid").exists()
    finally:
        for pid in (proc.pid, child):
            try:
                _os.kill(pid, _signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize("content", ["0", "1", "0 0", "1 1", "-5 -5", "{self}", "{self} {self}", "999999999", "999999999 7", "x y", ""])
def test_abort_never_signals_an_implausible_pid(site, monkeypatch, content):
    """pid 文件内容是 0 / 1 / 本进程 / 早已不在的进程 / 乱码: 一个信号都不发 (kill(0) 会打到自己整个进程组)。"""
    import os as _os

    sent = []
    monkeypatch.setattr(ks.os, "killpg", lambda pg, sig: sent.append(("killpg", pg, sig)))
    real_kill = _os.kill
    monkeypatch.setattr(ks.os, "kill", lambda pid, sig: sent.append(("kill", pid, sig)) if sig else real_kill(pid, 0))
    Path(str(site["touched"]) + ".pid").write_text(content.replace("{self}", str(_os.getpid())))
    fake = _fake(site, formal="running", swap=False)
    a = ks.build_parser().parse_args(["public-abort", "--compose-file", "x", "--touched-file", str(site["touched"])])
    assert ks.public_abort(fake, a, sleep=lambda s: None) == 0
    assert sent == [] and "formal:stop" not in fake.events


def test_abort_with_a_dead_group_leader_and_no_group_left_returns_quietly():
    """组长已经不在、组里也没有进程了: 对那个组发信号得到「没有这个进程」, 直接算干净 (真实的 killpg, 不是替身)。"""
    slept = []
    assert ks._end_process_group(999999999, 999999999, slept.append) is True and slept == []


def test_abort_does_not_signal_a_pid_now_owned_by_an_unrelated_process(site, monkeypatch):
    """pid 文件里的 pid 还活着, 但已经不是 deploy-public (pid 被复用): 不碰它。"""
    import sys as _sys

    other = subprocess.Popen([_sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        monkeypatch.setattr(ks, "_proc_kind", lambda pid: "other")
        assert ks._end_process_group(other.pid, other.pid, lambda s: None) is True
        assert other.poll() is None  # 还活着
    finally:
        other.kill()


def test_abort_never_signals_its_own_process_group(monkeypatch):
    """记下的组就是兜底步骤自己所在的组 (runner 没有给每个步骤单独分组): 只结束那一个进程, 不对整组发信号。"""
    import sys as _sys

    victim = subprocess.Popen([_sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    groups = []
    try:
        monkeypatch.setattr(ks, "_proc_kind", lambda pid: "deploy")
        monkeypatch.setattr(ks.os, "getpgrp", lambda: victim.pid)  # 假装我们和它同组
        monkeypatch.setattr(ks.os, "killpg", lambda pg, sig: groups.append((pg, sig)))
        assert ks._end_process_group(victim.pid, victim.pid, lambda s: victim.wait(timeout=5)) is True
        assert groups == [] and victim.poll() is not None  # 进程本身被结束了, 但没有对整组发过信号
    finally:
        victim.kill()


def test_proc_kind_reads_the_command_line_when_proc_exists(tmp_path, monkeypatch):
    real = ks.Path

    def fake_path(p):
        p = str(p)
        return real(str(tmp_path / p.lstrip("/"))) if p.startswith("/proc/") else real(p)

    monkeypatch.setattr(ks, "Path", fake_path)
    assert ks._proc_kind(4242) == "unknown"  # 没有 /proc 的系统: 无从核对
    (tmp_path / "proc/self").mkdir(parents=True)
    (tmp_path / "proc/self/cmdline").write_bytes(b"python\0x")
    assert ks._proc_kind(4242) == "gone"  # 有 /proc 而这个 pid 读不到: 进程不在
    (tmp_path / "proc/4242").mkdir()
    (tmp_path / "proc/4242/cmdline").write_bytes(b"python3\0deploy/kbsync/kbsync.py\0deploy-public\0--data-root\0/x")
    assert ks._proc_kind(4242) == "deploy"
    (tmp_path / "proc/4242/cmdline").write_bytes(b"python3\0-m\0http.server")
    assert ks._proc_kind(4242) == "other"
    (tmp_path / "proc/4242/cmdline").write_bytes(b"")  # 已退出但还没被回收: 命令行是空的
    assert ks._proc_kind(4242) == "gone"


def test_abort_ends_the_group_of_an_exited_but_unreaped_leader(monkeypatch):
    """编排进程已经退出但还没被回收 (kill(pid, 0) 仍成功, 命令行是空的), 它起的 docker 子进程还在同一组里: 整组结束。"""
    import os as _os
    import sys as _sys

    kid = subprocess.Popen([_sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        monkeypatch.setattr(ks, "_proc_kind", lambda pid: "gone")
        assert ks._end_process_group(kid.pid, _os.getpgid(kid.pid), lambda s: kid.wait(timeout=5)) is True
        assert kid.poll() is not None
        monkeypatch.setattr(ks, "_proc_kind", lambda pid: "gone")
        solo = subprocess.Popen([_sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        assert ks._end_process_group(solo.pid, 0, lambda s: None) is True and solo.poll() is None  # 不是组长: 不发信号
        solo.kill()
    finally:
        kid.kill()


def test_isolation_check_with_the_real_probe_script(site):
    """合并隧道那条线之后才有真脚本; 在那之前 skip。用真脚本的 judge 把替身钉过的几种情形再跑一遍。"""
    real = Path(__file__).resolve().parent.parent / "deploy/public-net/isolation_probe.py"
    if not real.is_file():
        pytest.skip("deploy/public-net/isolation_probe.py 在隧道那条线的分支上, 合并后本测试生效")
    cases = [({}, None), ({"iso_lan_state": "open"}, "退出码 1"), ({"ctl_lan_state": "timeout"}, "退出码 2"),
             ({"iso_src": "172.17.0.9"}, "退出码 2"), ({"iso_egress_state": "refused"}, "退出码 1")]
    for attrs, want in cases:
        fake = _fake(site, formal="running", swap=False)
        fake.probe_script = real.read_bytes()
        for k, v in attrs.items():
            setattr(fake, k, v)
        got = ks.isolation_check(fake, IMG_NEW, NET, SUBNET, str(real), LAN.split(), EGRESS.split())
        assert (got is None) if want is None else (got and want in got), (attrs, got)
        assert fake.violations == []


def test_container_state_with_empty_output_is_an_error_not_a_crash(site):
    fake = _fake(site, formal="running", swap=False)
    orig = fake.run
    fake.run = lambda args, **kw: subprocess.CompletedProcess([], 0, b"", b"") if args[0] == "inspect" else orig(args, **kw)
    with pytest.raises(RuntimeError, match="无法解析"):
        ks.container_state(fake, FORMAL)
    site["touched"].write_text(FORMAL)
    a = ks.build_parser().parse_args(["public-abort", "--compose-file", "deploy/container/compose.public.yml",
                                      "--touched-file", str(site["touched"])])
    assert ks.public_abort(fake, a, sleep=lambda s: None) == 1  # 查不出状态 = 没有确认已停, 不是崩溃


def test_abort_stops_again_when_the_site_comes_back_up_after_the_first_stop(site, capsys):
    """兜底停下之后, 一个没来得及被结束的 compose up 又把容器起来了: 隔几秒再确认时发现, 再停一次。"""
    site["touched"].write_text(FORMAL)
    fake = _fake(site, formal="running", swap=False)
    fake.after_stop = lambda: fake.containers[FORMAL].update(running=True)  # 第一次停完又被起来
    a = ks.build_parser().parse_args(["public-abort", "--compose-file", "deploy/container/compose.public.yml",
                                      "--touched-file", str(site["touched"])])
    slept = []
    assert ks.public_abort(fake, a, sleep=slept.append) == 0
    assert fake.events.count("formal:stop") == 2 and fake.formal()["running"] is False and slept == [3, 3]
    fake.containers[FORMAL]["running"] = True
    fake.fail.add("stop")  # 怎么都停不下来
    assert ks.public_abort(fake, a, sleep=slept.append) == 1
    assert fake.events.count("formal:stop") == 5 and "没有确认公开实例已停止" in capsys.readouterr().out


def test_deploy_public_leaves_no_pid_file_behind(site):
    fake = _fake(site, formal="running", swap=False, cols={"stage": _cols(4329)})
    assert _run(fake, site) == 0
    assert not Path(str(site["touched"]) + ".pid").exists()
    site["touched"].unlink()
    Path(str(site["touched"]) + ".pid").write_text("999999999")  # pid 文件在, 进程早已不在
    a = ks.build_parser().parse_args(["public-abort", "--compose-file", "x", "--touched-file", str(site["touched"])])
    assert ks.public_abort(fake, a, sleep=lambda s: None) == 0
    assert not Path(str(site["touched"]) + ".pid").exists() and "formal:stop" not in fake.events
    Path(str(site["touched"]) + ".pid").write_text("not-a-pid")  # 内容坏了也不影响后面的判断
    assert ks.public_abort(fake, a, sleep=lambda s: None) == 0


# ── 小件 ─────────────────────────────────────────────────────────────────
def test_accept_spec_takes_only_whitelisted_keys():
    model = copy.deepcopy(PUB_MODEL)
    api = model["services"]["api"]
    api.update(ports=[{"target": 8000, "published": "8000"}], labels={"x": "y"}, cap_add=["NET_ADMIN"],
               network_mode="host", privileged=True, command=["uvicorn", "server.main:app", "--proxy-headers"])
    api["networks"] = {"public": {"aliases": ["sdtm-rag-public-api"]}, "tunnel": None}
    model["services"]["cloudflared"] = {"image": "cloudflare/cloudflared", "networks": {"public": None}}
    spec, ignored = ks.accept_spec(model, "/stage/data")
    assert set(spec) == {"name", "services"} and set(spec["services"]) == {"api"}
    svc = spec["services"]["api"]
    assert set(svc) == {"image", "environment", "mem_limit", "healthcheck", "command", "container_name",
                        "network_mode", "restart", "volumes"}
    assert svc["network_mode"] == "none" and svc["command"][-1] == "--proxy-headers"
    assert svc["healthcheck"] == api["healthcheck"] and svc["mem_limit"] == api["mem_limit"]
    assert ignored == ["cap_add", "labels", "network_mode", "ports", "privileged"]
    assert "cloudflared" not in json.dumps(spec) and "aliases" not in json.dumps(spec)


def test_accept_spec_refuses_what_it_cannot_isolate():
    def model(fn):
        m = copy.deepcopy(PUB_MODEL)
        fn(m["services"]["api"])
        return m

    with pytest.raises(RuntimeError, match="共用状态"):  # 第二个可写挂载
        ks.accept_spec(model(lambda a: a["volumes"].append(
            {"type": "bind", "source": "/x/logs", "target": "/app/logs"})), "/s")
    with pytest.raises(RuntimeError, match="共用状态"):  # env 文件不再只读
        ks.accept_spec(model(lambda a: a["volumes"][1].pop("read_only")), "/s")
    with pytest.raises(RuntimeError, match="非 bind"):
        ks.accept_spec(model(lambda a: a["volumes"].append({"type": "volume", "source": "v", "target": "/v"})), "/s")
    with pytest.raises(RuntimeError, match="SDTM_RAG_INSTANCE"):
        ks.accept_spec(model(lambda a: a["environment"].update(SDTM_RAG_INSTANCE="private")), "/s")
    with pytest.raises(RuntimeError, match="/app/data"):
        ks.accept_spec(model(lambda a: a["volumes"].pop(0)), "/s")
    with pytest.raises(RuntimeError):
        ks.accept_spec({"services": {"web": {}}}, "/s")
    ro = model(lambda a: a["volumes"].append({"type": "bind", "source": "/x/ca.pem", "target": "/ca.pem", "read_only": True}))
    assert [v["target"] for v in ks.accept_spec(ro, "/s")[0]["services"]["api"]["volumes"]] == ["/app/data", "/app/.env", "/ca.pem"]


def test_accept_names_do_not_collide_with_the_formal_instance():
    formal = PUB_MODEL["services"]["api"]["container_name"]
    assert formal != ks.ACCEPT_CONTAINER and PUB_MODEL["name"] != ks.ACCEPT_PROJECT
    assert ks.ACCEPT_PROJECT not in PUB_MODEL["networks"]["public"]["name"].split()


def test_accept_stage_and_clean(site):
    pub = site["pub"]
    before = _snapshot(pub)
    res = ks.accept_stage(pub, TS, "chroma", "meta")
    stage = pub.parent / res["stage_dir"]
    assert res["data"] == str(stage / "data") and (stage / "data" / "chroma" / "chroma.sqlite3").read_text() == "public-chroma"
    assert sorted(p.name for p in (stage / "data").iterdir()) == ["chroma", "meta"]
    assert _snapshot(pub) == before
    with pytest.raises(FileExistsError):  # 同一时间戳的副本已在: 不覆盖
        ks.accept_stage(pub, TS, "chroma", "meta")
    # 越界的名字指向一个**真实存在**的目录 (私有根的 chroma / meta): 只有名字校验能拦, 不是"目录不存在"在拦
    escape = "../../sdtm-rag/data/chroma"
    assert (pub / escape).is_dir() and (pub / "../../sdtm-rag/data/meta").is_dir()
    for bad in ((escape, "meta"), ("chroma", "../../sdtm-rag/data/meta"), ("nope", "meta")):
        with pytest.raises(SystemExit):
            ks.accept_stage(pub, "20261128T000001Z", *bad)
    assert not (pub.parent / f"{ks.ACCEPT_PREFIX}20261128T000001Z").exists()  # 什么都没复制出来
    with pytest.raises(SystemExit):
        ks.accept_stage(pub, "not-a-ts", "chroma", "meta")
    keep = pub.parent / "kbsync_accept_notes"
    keep.mkdir()
    assert ks.accept_clean(pub) == {"removed": [stage.name]}
    assert keep.is_dir() and pub.is_dir() and _snapshot(pub) == before
    assert _snapshot(site["priv"])["chroma/chroma.sqlite3"] == "PRIVATE-chroma-with-study"


def test_container_state_distinguishes_absent_from_unknown(site):
    fake = _fake(site, formal="stopped", swap=False)
    assert ks.container_state(fake, "nope") is None
    assert ks.container_state(fake, FORMAL) == {"running": False, "status": "exited", "health": "", "image": IMG_OLD}
    fake.fail.add("inspect_formal_after_up")
    fake.events.append("formal:up")
    with pytest.raises(RuntimeError):
        ks.container_state(fake, FORMAL)


def test_acceptance_stays_far_below_the_public_rate_limit(site):
    """公开档带全局限流 (临时容器照抄 compose 的环境变量, 同样带着): 每个来源每分钟 60 个、突发 20, /api/health 不计。
    验收脚本一共发 2 个请求, 每次验收每个容器只跑一遍; 健康状态看 docker 的健康检查 (/api/health)。留足余量: 4 倍仍在突发之内。"""
    burst = int(PUB_TUNNEL_MODEL["services"]["api"]["environment"]["SDTM_RAG_RATE_LIMIT_BURST"])
    n = ks.ACCEPT_PY.count("urlopen(")
    assert n == 2 and n * 4 <= burst
    assert "/api/info" in ks.ACCEPT_PY and "/openapi.json" in ks.ACCEPT_PY
    health = PUB_TUNNEL_MODEL["services"]["api"]["healthcheck"]["test"]
    assert "/api/health" in " ".join(health)  # 健康检查打的是不计入限流的路径
    fake = _fake(site, formal="running", swap=True)
    assert _run(fake, site) == 0
    runs = [c[1] for c in fake.execs if ks.ACCEPT_PY in c]
    assert sorted(runs) == sorted([TEMP, FORMAL])  # 临时容器一遍, 正式容器复验一遍; 各是各的进程, 各有各的限流计数
    # 除了这段脚本, 没有别的 exec 会发 HTTP 请求 (另一类 exec 只有新鲜度检查, 它不走 HTTP)
    others = [c[2:] for c in fake.execs if ks.ACCEPT_PY not in c]
    assert others == [["python", "-m", "scripts.check_index_freshness"]] * 2


def test_startup_refusal_is_carried_verbatim_into_the_failure_reason(site, capsys):
    """公开档启动自检拒绝启动 (例如 env 文件里有大小写不同的同名键): 容器直接退出。验收判失败, 并把那条报错原样带出来。"""
    refusal = ("RuntimeError: SDTM_RAG_INSTANCE=public refuses to start: .env has case-variant keys: "
               "sdtm_rag_rate_limit_enabled, Sdtm_Rag_Quota_Trusted_Proxies")
    fake = _fake(site, formal="running", swap=False, cols={"stage": _cols(4329)})
    fake.exited.add(TEMP)
    fake.logs_text = "INFO: Started server process\nTraceback (most recent call last):\n  File ...\n" + refusal + "\n"
    before = _snapshot(site["pub"])
    assert _run(fake, site) == 1
    fake.check()
    out = capsys.readouterr().out
    assert f"临时容器验收不通过 —— 容器没有进入 healthy 状态；启动报错：{refusal}" in out  # 原样, 在失败原因里
    assert "旧版继续对外" in out and fake.formal() == {"running": True, "image": IMG_OLD} and _snapshot(site["pub"]) == before
    # 没有报错行时不硬凑
    fake2 = _fake(site, formal="running", swap=False, cols={"stage": _cols(4329)})
    fake2.unhealthy.add(TEMP)
    assert _run(fake2, site) == 1
    out = capsys.readouterr().out
    assert "容器没有进入 healthy 状态" in out and "启动报错" not in out


def test_accept_check_gives_up_at_once_when_the_container_exits(site):
    fake = _fake(site, formal="running", swap=False)
    fake.containers[FORMAL]["running"] = False
    slept = []
    assert ks.accept_check(fake, FORMAL, sleep=slept.append) == "容器没有进入 healthy 状态"
    assert slept == []
    fake.containers[FORMAL]["running"] = True
    fake.unhealthy.add(FORMAL)
    assert ks.accept_check(fake, FORMAL, tries=5, sleep=slept.append) is not None and slept == [3] * 5
