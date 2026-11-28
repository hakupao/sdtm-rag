"""P3.4: 公开档的 HTTPS 行为 (HSTS / cookie Secure / 只信隧道连接器) 与私有档不变。

每一项「只在公开档生效」都有两档各一条, 且都从 `create_app` (或 `install_security`) 走到真实响应:
只手工构造中间件的测试, 把接线条件改反照样绿。变异记录见
.work/10_split_and_public/evidence/checkpoints/p3_step3.4_tunnel.md。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server import quota
from server.auth import install_security
from server.config import Settings
from server.main import create_app
from tests.conftest import set_public_quota_env
from tests.test_p2_9_public_e2e import pub  # noqa: F401 — fixture: create_app(public settings)
from tests.test_p2_l2_integration import (
    engines,  # noqa: F401 — module fixture (tiny chroma + fakes)
)
from tests.test_p2_seam_characterization import _FakeRouter
from tests.test_phase3_security import _app, _auth_settings

ROOT = Path(__file__).resolve().parent.parent
HSTS = "max-age=31536000"
# 私有档经 create_app 的响应头名 = 改动前 (9a8ad43) 的行为; 公开档 = 这些 + strict-transport-security。
# 复核: 把 server/auth.py 换成 `git show 9a8ad43:server/auth.py` 再跑本文件 (在仓库副本里做) ——
# 公开档的用例红, 名字含 private 的用例 (session cookie 那条除外, 它一条里测两档) 照样绿。
PRIVATE_HEADERS = {
    "/": {"accept-ranges", "cache-control", "content-length", "content-security-policy", "content-type",
          "etag", "last-modified", "referrer-policy", "x-content-type-options", "x-frame-options"},
    "/api/health": {"content-length", "content-security-policy", "content-type", "referrer-policy",
                    "x-content-type-options", "x-frame-options"},
    "/nope": {"content-length", "content-security-policy", "content-type", "referrer-policy",
              "x-content-type-options", "x-frame-options"},
}
CONNECTOR = "10.201.8.2"          # deploy/container/compose.tunnel.yml 的静态地址 (下面有一条测试核对)


@pytest.fixture
def priv(engines, tmp_path, monkeypatch):  # noqa: F811
    """priv(**settings) -> TestClient。私有档 create_app; 与 pub 同样只伪造线路, 不跑 lifespan。"""
    for k in list(os.environ):
        if k.startswith("SDTM_RAG_"):
            monkeypatch.delenv(k)
    base, rag, rec, _root = engines

    def _make(client=("testclient", 50000), base_url="http://testserver", **kw):
        quota._STORES.clear()
        s = Settings(chroma_dir=base.chroma_dir, kb_root=base.kb_root, collection_name="cdisc_t", top_k=3,
                     dogfood_log_override=str(tmp_path / "dogfood.md"), **kw)
        app = create_app(s)
        app.state.rag, app.state.llm_router = rag, _FakeRouter(rec)
        return TestClient(app, base_url=base_url, client=client)

    yield _make
    quota._STORES.clear()


def _cookie_attrs(header: str) -> set[str]:
    """`name=value; Path=/; Secure` → {"path=/", "secure"} (去掉 name=value, 小写)。"""
    return {p.strip().lower() for p in header.split(";")[1:]}


def _set_cookies(resp) -> list[str]:
    return resp.headers.get_list("set-cookie")


# ── 镜像下限标记: 部署预检按它拒绝 P3.4 之前的镜像 ───────────────────────────

IMAGE_FLOOR_CHECK = ROOT / "deploy/public-net/image_floor_check.py"   # 部署预检经标准输入把它送进要部署的镜像里跑


FLOOR_OK = "image-floor: ok\n"       # 预检要同时核对退出码 0 和这行输出


def _run_floor_check(cwd, script: str | None = None) -> tuple[int, str, str]:
    import subprocess
    import sys

    text = IMAGE_FLOOR_CHECK.read_text() if script is None else script
    r = subprocess.run([sys.executable, "-"], input=text, cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def _fake_server(tmp_path, auth_source: str):
    (tmp_path / "server").mkdir()
    (tmp_path / "server" / "__init__.py").write_text("")
    (tmp_path / "server" / "auth.py").write_text(auth_source)
    return tmp_path


def test_image_floor_marker():
    from server import auth

    assert auth.PUBLIC_EDGE_LEVEL == 1
    # 预检脚本按名字用到的两样东西都在 (改名 / 挪走时这里会响, 提醒同步 deploy/public-net/image_floor_check.py)
    assert auth._HSTS == HSTS and callable(auth._check_public_trusted)


def test_image_floor_check_passes_this_build():
    assert _run_floor_check(ROOT) == (0, FLOOR_OK, "")


def test_image_floor_check_needs_the_marker_not_just_exit_zero():
    """docker run 漏写 -i 时脚本根本没送进去: python 读到空输入, 以 0 退出。这时没有那行输出, 预检据此判不合格。"""
    assert _run_floor_check(ROOT, script="") == (0, "", "")
    # 脚本里合格的出口只有一个, 而且紧跟在打印标记之后
    src = IMAGE_FLOOR_CHECK.read_text()
    assert src.count("sys.exit(0)") == 1 and 'print("image-floor: ok")\n    sys.exit(0)\n' in src
    assert src.count('"image-floor: ok"') == 2          # 说明里给预检照抄的那一行 + 实际打印的那一行


@pytest.mark.parametrize(("auth_source", "why"), [
    ("_HSTS = None\n", "predates P3.4"),                                             # P3.4 之前: 没有这个属性
    ("PUBLIC_EDGE_LEVEL = 0\n", "predates P3.4"),
    ("PUBLIC_EDGE_LEVEL = 1\ndef _check_public_trusted(t):\n    return None\n", "wider than one host"),   # 标记在, 实现不在
    ("PUBLIC_EDGE_LEVEL = 1\n", "AttributeError"),                                   # 标记在, 函数没了
    ("PUBLIC_EDGE_LEVEL = '1'\n", "TypeError"),                                      # 标记写成了字符串
    ("import nonexistent_module_xyz\n", "ModuleNotFoundError"),                     # 导入失败
])
def test_image_floor_check_refuses(tmp_path, auth_source, why):
    rc, out, err = _run_floor_check(_fake_server(tmp_path, auth_source))
    assert rc == 1 and out == "" and why in err, (rc, out, err)


# ── HSTS: 公开档每个响应都有, 私有档没有 ─────────────────────────────────────

@pytest.mark.parametrize("path", sorted(PRIVATE_HEADERS))
def test_public_every_response_carries_hsts(pub, path):  # noqa: F811
    client, _router, _s = pub()
    r = client.get(path)
    assert r.headers.get("strict-transport-security") == HSTS
    # 只多这一个头: 其余头名与私有档逐个相同 (公开档的 /api/* 另有 set-cookie, 这里的三条路径里
    # 只有 /api/health 会带)
    extra = {"strict-transport-security"} | ({"set-cookie"} if path.startswith("/api/") else set())
    assert set(r.headers.keys()) == PRIVATE_HEADERS[path] | extra, sorted(r.headers.keys())


def test_public_hsts_binds_this_hostname_only():
    # 不带 includeSubDomains / preload: 那是整棵子域树的承诺, 本站只为自己的主机名负责
    from server.auth import _HSTS

    assert _HSTS == HSTS
    assert "includesubdomains" not in _HSTS.lower() and "preload" not in _HSTS.lower()


@pytest.mark.parametrize("path", sorted(PRIVATE_HEADERS))
def test_private_responses_unchanged_no_hsts(priv, path):
    r = priv().get(path)
    assert "strict-transport-security" not in r.headers
    assert set(r.headers.keys()) == PRIVATE_HEADERS[path], sorted(r.headers.keys())


# ── cookie Secure: 公开档强制, 私有档默认不带 ────────────────────────────────

def test_public_every_cookie_is_secure(pub):  # noqa: F811
    client, _router, _s = pub()
    cookies = _set_cookies(client.get("/api/info"))
    assert len(cookies) >= 1, "没有 set-cookie: 下面的断言会变成永真式"
    for c in cookies:
        assert _cookie_attrs(c) == {"path=/", "max-age=31536000", "httponly", "samesite=lax", "secure"}, c


def test_private_visitor_cookie_not_secure_by_default(priv, monkeypatch):
    monkeypatch.setenv("SDTM_RAG_QUOTA_ENABLED", "true")
    monkeypatch.setenv("SDTM_RAG_VISITOR_SECRET", "v" * 32)
    cookies = _set_cookies(priv().get("/api/info"))
    assert len(cookies) == 1, cookies
    assert _cookie_attrs(cookies[0]) == {"path=/", "max-age=31536000", "httponly", "samesite=lax"}, cookies


def test_private_can_still_opt_in_to_secure(priv, monkeypatch):
    monkeypatch.setenv("SDTM_RAG_QUOTA_ENABLED", "true")
    monkeypatch.setenv("SDTM_RAG_VISITOR_SECRET", "v" * 32)
    monkeypatch.setenv("SDTM_RAG_VISITOR_COOKIE_SECURE", "true")
    cookies = _set_cookies(priv().get("/api/info"))
    assert len(cookies) == 1 and "secure" in _cookie_attrs(cookies[0]), cookies


@pytest.mark.parametrize("raw", ["false", "0", "off"])
def test_public_refuses_insecure_visitor_cookie(pub, monkeypatch, raw):  # noqa: F811
    monkeypatch.setenv("SDTM_RAG_VISITOR_COOKIE_SECURE", raw)
    with pytest.raises(RuntimeError, match="VISITOR_COOKIE_SECURE"):
        pub()


def test_public_accepts_explicit_secure(pub, monkeypatch):  # noqa: F811
    monkeypatch.setenv("SDTM_RAG_VISITOR_COOKIE_SECURE", "true")
    client, _router, _s = pub()
    assert "secure" in _cookie_attrs(_set_cookies(client.get("/api/info"))[0])


def test_private_accepts_explicit_insecure(priv, monkeypatch):
    # 私有档显式关: 不拒启动 (局域网走 HTTP)
    monkeypatch.setenv("SDTM_RAG_QUOTA_ENABLED", "true")
    monkeypatch.setenv("SDTM_RAG_VISITOR_SECRET", "v" * 32)
    monkeypatch.setenv("SDTM_RAG_VISITOR_COOKIE_SECURE", "false")
    cookies = _set_cookies(priv().get("/api/info"))
    assert len(cookies) == 1 and "secure" not in _cookie_attrs(cookies[0]), cookies


def _login_cookie(settings, base_url) -> str:
    client = TestClient(_app(settings), base_url=base_url)
    r = client.post("/login", data={"password": "s3cret-pw"}, follow_redirects=False)
    assert r.status_code == 303, r.text
    cookies = [c for c in _set_cookies(r) if c.startswith(settings.session_cookie_name + "=")]
    assert len(cookies) == 1, _set_cookies(r)
    return cookies[0]


def test_session_cookie_secure_follows_tier(monkeypatch):
    """登录门的 session cookie: 私有档不带 Secure (局域网 HTTP, 改动前行为)。公开档的 create_app 拒绝
    开登录门 (instance.check_startup), 这里绕过它直接装中间件, 只为钉住「真出现也带 Secure」。"""
    for k in list(os.environ):
        if k.startswith("SDTM_RAG_"):
            monkeypatch.delenv(k)
    assert "secure" not in _cookie_attrs(_login_cookie(_auth_settings(), "http://testserver"))
    set_public_quota_env(monkeypatch)
    assert "secure" in _cookie_attrs(_login_cookie(_auth_settings(instance="public"), "https://testserver"))


# ── 可信代理: compose 里写的那一个地址, 经真实中间件 ──────────────────────────

def _compose_trusted() -> str:
    pub_compose = yaml.safe_load((ROOT / "deploy/container/compose.public.yml").read_text())
    return pub_compose["services"]["api"]["environment"]["SDTM_RAG_QUOTA_TRUSTED_PROXIES"]


def _rate_limited_public(pub, monkeypatch, peer):  # noqa: F811
    monkeypatch.setenv("SDTM_RAG_QUOTA_TRUSTED_PROXIES", _compose_trusted())
    client, _router, _s = pub(rate_limit_enabled=True, rate_limit_per_min=1, rate_limit_burst=1)
    app = client.app
    return TestClient(app, base_url="https://testserver", client=(peer, 40000))


def _hit(client, visitor_ip: str) -> int:
    return client.get("/api/info", headers={"CF-Connecting-IP": visitor_ip}).status_code


def test_connector_address_is_the_only_trusted_peer(pub, monkeypatch):  # noqa: F811
    assert _compose_trusted() == CONNECTOR
    client = _rate_limited_public(pub, monkeypatch, CONNECTOR)
    assert _hit(client, "198.51.100.1") == 200
    assert _hit(client, "198.51.100.2") == 200      # 隧道后的另一位访客: 自己的桶
    assert _hit(client, "198.51.100.1") == 429      # 第一位访客的桶已空


@pytest.mark.parametrize("peer", ["10.201.8.1", "10.201.8.3", "10.201.8.130", "172.22.0.5", "192.168.5.15"])
def test_other_peers_cannot_set_the_visitor_ip(pub, monkeypatch, peer):  # noqa: F811
    """同一 docker 网络里的别的地址 (网关 / 公开实例自己的动态段 / 以后加进来的容器) 和网络外的地址,
    带 CF-Connecting-IP 来也只按连接对端计: 换头值不换桶。"""
    client = _rate_limited_public(pub, monkeypatch, peer)
    assert _hit(client, "198.51.100.1") == 200
    assert _hit(client, "198.51.100.2") == 429


def _hit_twice_headers(client, *values: str) -> int:
    return client.get("/api/info", headers=[("CF-Connecting-IP", v) for v in values]).status_code


def test_duplicate_cf_connecting_ip_from_the_connector_is_not_trusted(pub, monkeypatch):  # noqa: F811
    """连接器送来两条 CF-Connecting-IP (上游追加而不是覆盖): 哪条都不采信, 按连接对端计。
    否则访客自带一条就能给自己挑 IP。"""
    client = _rate_limited_public(pub, monkeypatch, CONNECTOR)
    assert _hit_twice_headers(client, "198.51.100.1", "198.51.100.2") == 200
    assert _hit_twice_headers(client, "198.51.100.3", "198.51.100.4") == 429     # 同一个桶 (对端)
    # 对照: 单条头仍按访客分桶 (上面的 429 不是因为连接器整体被限)
    assert _hit(client, "198.51.100.9") == 200


def test_connector_request_without_cf_connecting_ip_falls_back_to_the_peer(pub, monkeypatch):  # noqa: F811
    """连接器送来的请求一条 CF-Connecting-IP 都没有 (例如后台开了去掉访客 IP 头的开关): 不报错, 按连接对端计。"""
    client = _rate_limited_public(pub, monkeypatch, CONNECTOR)
    assert client.get("/api/info").status_code == 200
    assert client.get("/api/info").status_code == 429          # 同一个桶 (对端)
    assert _hit(client, "198.51.100.9") == 200                 # 带头的访客仍有自己的桶


def test_public_compose_disables_uvicorn_proxy_headers():
    """uvicorn 默认采信来自 127.0.0.1 的 X-Forwarded-For 并改写连接对端: 容器内的请求带
    `X-Forwarded-For: <连接器地址>` 就成了「可信代理」。compose 把 FORWARDED_ALLOW_IPS 置空 = 谁的都不信。"""
    import asyncio

    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    pub_compose = yaml.safe_load((ROOT / "deploy/container/compose.public.yml").read_text())
    value = pub_compose["services"]["api"]["environment"]["FORWARDED_ALLOW_IPS"]
    assert value == ""

    def client_seen(allow_ips: str):
        seen = {}

        async def app(scope, receive, send):
            seen["client"] = scope["client"]

        scope = {"type": "http", "client": ("127.0.0.1", 5), "headers": [(b"x-forwarded-for", CONNECTOR.encode())]}
        asyncio.run(ProxyHeadersMiddleware(app, trusted_hosts=allow_ips)(scope, None, None))
        return seen["client"][0]

    assert client_seen(value) == "127.0.0.1"                   # compose 的取值: 不改写
    assert client_seen("127.0.0.1") == CONNECTOR               # uvicorn 的默认取值: 会被改写 (本测试有分辨力)


def test_uvicorn_reads_forwarded_allow_ips_from_env(monkeypatch):
    from uvicorn.config import Config

    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "")
    assert Config("server.main:app").forwarded_allow_ips == ""
    monkeypatch.delenv("FORWARDED_ALLOW_IPS")
    assert Config("server.main:app").forwarded_allow_ips == "127.0.0.1"


def test_private_ignores_cf_connecting_ip_without_trusted_proxies(priv):
    client = priv(client=(CONNECTOR, 40000), rate_limit_enabled=True, rate_limit_per_min=1, rate_limit_burst=1)
    assert _hit(client, "198.51.100.1") == 200
    assert _hit(client, "198.51.100.2") == 429


# ── 全局限流: 公开 compose 打开, 私有档没有 ──────────────────────────────────

def _compose_env() -> dict:
    pub_compose = yaml.safe_load((ROOT / "deploy/container/compose.public.yml").read_text())
    return pub_compose["services"]["api"]["environment"]


def _public_with_compose_env(pub, monkeypatch, peer=CONNECTOR):  # noqa: F811
    """按 compose.public.yml 的 environment 起公开档应用 (Settings 从环境变量读), 连接对端 = peer。"""
    for k, v in _compose_env().items():
        monkeypatch.setenv(k, v)
    client, _router, s = pub()
    return TestClient(client.app, base_url="https://testserver", client=(peer, 40000)), s


def test_public_compose_turns_on_the_global_rate_limit(pub, monkeypatch):  # noqa: F811
    from server.auth import RateLimitMiddleware

    client, s = _public_with_compose_env(pub, monkeypatch)
    assert (s.rate_limit_enabled, s.rate_limit_per_min, s.rate_limit_burst) == (True, 60, 20)
    mws = [m for m in client.app.user_middleware if m.cls is RateLimitMiddleware]
    assert len(mws) == 1, [m.cls.__name__ for m in client.app.user_middleware]
    kw = mws[0].kwargs
    assert (kw["limiter"].burst, kw["limiter"].rate * 60) == (20, 60)
    assert kw["trusted_proxies"] == CONNECTOR           # 按连接器传来的访客 IP 计, 不是按连接器的地址

    codes = [_hit(client, "198.51.100.1") for _ in range(20)]
    assert codes == [200] * 20, codes                   # 突发 20 个都放行
    r = client.get("/api/info", headers={"CF-Connecting-IP": "198.51.100.1"})
    assert r.status_code == 429 and r.text == "Too Many Requests" and int(r.headers["retry-after"]) >= 1
    assert _hit(client, "198.51.100.2") == 200          # 另一位访客不受牵连 (没有被并成连接器一个桶)
    # 页面外壳和健康检查不计入: 第一位访客的桶空了, 这些照样能取
    for path in ("/", "/static/app.js", "/static/style.css", "/api/health"):
        assert client.get(path, headers={"CF-Connecting-IP": "198.51.100.1"}).status_code == 200, path


def test_private_has_no_global_rate_limit(priv):
    from server.auth import RateLimitMiddleware

    client = priv()
    assert not [m for m in client.app.user_middleware if m.cls is RateLimitMiddleware]
    assert [client.get("/api/info").status_code for _ in range(40)] == [200] * 40


def test_global_rate_limit_sits_above_the_question_limits():
    """全局这一层必须比提问接口自己的限额宽: 否则正常用户先撞上的是全局的那条没有说明的 429,
    而不是提问限额那条带「剩余额度 / 多久后再试」的拒绝。两边各钉字面值, 谁改了都要回来重算。"""
    env = _compose_env()
    per_min, burst = int(env["SDTM_RAG_RATE_LIMIT_PER_MIN"]), int(env["SDTM_RAG_RATE_LIMIT_BURST"])
    assert (per_min, burst) == (60, 20)
    d = quota._DEFAULTS
    asks = (d["quota_ip_rate_per_min"], d["quota_ip_rate_burst"])     # 每 IP 提问
    flags = (d["flag_rate_per_min"], d["flag_rate_burst"])            # 每 IP 反馈
    assert (asks, flags) == ((20, 6), (5, 3))
    # 一个 IP 每分钟最多 20 题 + 5 条反馈会被各自的限额放行; 全局留出一倍以上的余量给页面加载 (/api/info) 和重试
    assert per_min >= 2 * (asks[0] + flags[0]) and burst >= 2 * (asks[1] + flags[1])


@pytest.mark.parametrize("variant", ["sdtm_rag_rate_limit_enabled", "Sdtm_Rag_Rate_Limit_Enabled"])
def test_public_refuses_case_variant_that_would_override_compose(pub, monkeypatch, variant):  # noqa: F811
    """`.env` 里写一个大小写不同的同名键 (load_dotenv 会把它加进环境): pydantic 不分大小写, 后来的那个赢,
    compose 钉的全局限流就被悄悄关掉。公开档发现这种冲突就拒绝启动, 报错里只有键名。"""
    for k, v in _compose_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv(variant, "false")
    assert Settings().rate_limit_enabled is False, "变体没有压过 compose 的值: 这条测试没在测它要测的情形"
    with pytest.raises(RuntimeError, match="conflicting case variants") as e:
        pub()
    assert variant in str(e.value) and "SDTM_RAG_RATE_LIMIT_ENABLED" in str(e.value)
    assert "false" not in str(e.value) and "'true'" not in str(e.value)       # 只报键名, 不报取值
    # 取值相同的变体不算冲突
    monkeypatch.setenv(variant, "true")
    pub()


def test_public_case_variant_check_names_no_values_and_private_is_untouched(priv, monkeypatch):
    from server.auth import _check_public_env_case_variants

    env = {"SDTM_RAG_VISITOR_SECRET": "s3cret-A", "sdtm_rag_visitor_secret": "s3cret-B", "PATH": "/bin", "path": "/x",
           "SDTM_RAG_TOP_K": "5", "sdtm_rag_top_k": "5"}
    with pytest.raises(RuntimeError) as e:
        _check_public_env_case_variants(env)
    msg = str(e.value)
    assert "SDTM_RAG_VISITOR_SECRET" in msg and "s3cret" not in msg       # 值可能是秘密
    assert "TOP_K" not in msg and "PATH" not in msg                       # 取值相同 / 不是本服务的键: 不管
    _check_public_env_case_variants({"SDTM_RAG_TOP_K": "5", "sdtm_rag_top_k": "5"})
    # 键名按 .lower() 归并 (和 pydantic 一样); 非 ASCII 的键名直接拒: 开尔文符号 U+212A 小写后就是普通的 k,
    # pydantic 会把 `sdtm_rag_top_\u212a` 当成 top_k, 而 .upper() 认不出它
    kelvin = "sdtm_rag_top_\u212a"
    assert kelvin.lower() == "sdtm_rag_top_k" and kelvin.upper() != "SDTM_RAG_TOP_K"
    for env in ({"SDTM_RAG_TOP_K": "5", kelvin: "77"}, {kelvin: "77"}, {kelvin: "5", "SDTM_RAG_TOP_K": "5"}):
        with pytest.raises(RuntimeError, match="non-ASCII setting name") as e:
            _check_public_env_case_variants(env)
        assert "77" not in str(e.value)
    # 私有档不做这项检查 (行为不变): 同样的冲突照常启动
    monkeypatch.setenv("SDTM_RAG_TOP_K", "5")
    monkeypatch.setenv("sdtm_rag_top_k", "6")
    priv()


def test_dotenv_same_name_cannot_turn_the_global_rate_limit_off(tmp_path, monkeypatch):
    """`.env` 里同名 (大小写也相同) 的键: load_dotenv 不覆盖已有环境变量, compose 的值赢。"""
    env_file = tmp_path / ".env"
    env_file.write_text("SDTM_RAG_RATE_LIMIT_ENABLED=false\nSDTM_RAG_RATE_LIMIT_PER_MIN=100000\n")
    for k in ("SDTM_RAG_RATE_LIMIT_ENABLED", "SDTM_RAG_RATE_LIMIT_PER_MIN"):
        monkeypatch.setenv(k, _compose_env()[k])
    load_dotenv(env_file)
    assert (Settings().rate_limit_enabled, Settings().rate_limit_per_min) == (True, 60)
    for k in ("SDTM_RAG_RATE_LIMIT_ENABLED", "SDTM_RAG_RATE_LIMIT_PER_MIN"):
        monkeypatch.delenv(k)
    load_dotenv(env_file)                                # 对照: compose 没设时 .env 的值会生效 (文件确实被读了)
    assert (Settings().rate_limit_enabled, Settings().rate_limit_per_min) == (False, 100000)
    for k in ("SDTM_RAG_RATE_LIMIT_ENABLED", "SDTM_RAG_RATE_LIMIT_PER_MIN"):
        monkeypatch.delenv(k)


# ── compose 的值压过 .env 里的同名键 (真机制: load_dotenv 不覆盖已有环境变量) ──

KEY = "SDTM_RAG_QUOTA_TRUSTED_PROXIES"


def test_compose_env_wins_over_dotenv_same_key_and_case_variant(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(f"{KEY}=127.0.0.1\n{KEY.lower()}=0.0.0.0/0\n")
    monkeypatch.delenv(KEY.lower(), raising=False)
    # 方向一: compose 已设 → .env 同名键不生效; 小写变体进了环境但 quota.cfg 只读大写名
    monkeypatch.setenv(KEY, CONNECTOR)
    load_dotenv(env_file)
    assert os.environ[KEY.lower()] == "0.0.0.0/0", "小写变体没进环境: 这条测试没在测它"
    assert quota.cfg(Settings(), "quota_trusted_proxies") == CONNECTOR
    # 方向二: compose 没设 → 用 .env 的值 (证明上面不是 load_dotenv 没读到文件)
    monkeypatch.delenv(KEY)
    load_dotenv(env_file)
    assert quota.cfg(Settings(), "quota_trusted_proxies") == "127.0.0.1"
    monkeypatch.delenv(KEY)
    monkeypatch.delenv(KEY.lower())


def test_config_loads_dotenv_without_override_and_key_is_not_a_settings_field():
    # server/config.py 必须保持 load_dotenv 的默认 (不覆盖): 改成 override=True, compose 钉的档位和可信代理
    # 都会被 .env 压过。
    src = (ROOT / "server/config.py").read_text()
    calls = [ln.strip() for ln in src.splitlines() if ln.strip().startswith("load_dotenv(")]
    assert calls == ['load_dotenv(_SDTM_RAG_ROOT / ".env")'], calls
    # 该键若成了 Settings 字段, pydantic 会按大小写不敏感匹配 .env 的变体 (3.2 审查 H1 的同类洞)
    assert "quota_trusted_proxies" not in Settings.model_fields


def test_public_install_refuses_trusted_network_wider_than_one_host(engines):  # noqa: F811
    from tests.test_p2_l2_integration import S

    pub_kw = dict(instance="public", visitor_secret="t" * 32)
    install_security(FastAPI(), S(engines[0], quota_trusted_proxies=CONNECTOR, **pub_kw))
    with pytest.raises(RuntimeError, match="too broad"):
        install_security(FastAPI(), S(engines[0], quota_trusted_proxies="10.201.8.0/24", **pub_kw))
    # 私有档不受这条约束
    install_security(FastAPI(), S(engines[0], quota_enabled=True, visitor_secret="t" * 32,
                                  quota_trusted_proxies="10.201.8.0/24"))
