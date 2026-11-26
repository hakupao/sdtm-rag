"""Custom OpenAI-compatible endpoint guard (private tier only; PLAN 2.6 SSRF).

`validate_custom_base(url)` resolves the host ONCE and accepts it only if every resolved address
is globally routable (IPv4-mapped / 6to4 / NAT64 forms included). The
returned `PinnedBase` is then used by `PinnedTransport`, which connects to that exact IP (TLS SNI
and certificate check stay on the hostname) and refuses any 3xx — so a later DNS answer
(rebinding) or a redirect cannot steer the call anywhere else.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

_BLOCKED_NAMES = {"localhost", "metadata", "metadata.google.internal", "instance-data"}


class UnsafeBase(ValueError):  # noqa: N818 — established name (L1 tests / callers)
    """The custom base URL is not acceptable. Message is safe to show (no key involved)."""


@dataclass(frozen=True)
class PinnedBase:
    url: str        # the base URL as given (SDK builds request URLs from it)
    host: str       # hostname (SNI / Host header / certificate name)
    port: int
    ip: str         # the one address every request connects to


def _address_ok(addr: str) -> bool:
    # Python >= 3.13 ipaddress already classifies IPv4-mapped (::ffff:a.b.c.d) by the embedded
    # address, 6to4 (2002::/16) as private and NAT64 (64:ff9b::/96) as reserved — the SSRF test set
    # pins that, so no hand-rolled unwrapping here.
    ip = ipaddress.ip_address(addr.split("%", 1)[0])
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_unspecified
                                 or ip.is_loopback or ip.is_link_local or ip.is_private)


def validate_custom_base(url: str, resolver=None) -> PinnedBase:
    """-> PinnedBase, or raise UnsafeBase. `resolver(host, port)` -> list of IP strings
    (default: socket.getaddrinfo)."""
    if not isinstance(url, str) or len(url) > 2048 or any(c in url for c in "\r\n\t "):
        raise UnsafeBase("地址格式无效")
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UnsafeBase("只接受 https 地址")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise UnsafeBase("地址不得包含用户名或密码")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeBase("地址缺少主机名")
    try:
        port = parts.port or 443
    except ValueError as e:
        raise UnsafeBase("端口无效") from e
    if host in _BLOCKED_NAMES or host.endswith((".localhost", ".local", ".internal")):
        raise UnsafeBase("不允许内网 / 本机地址")
    addrs = (resolver or _resolve)(host, port)
    if not addrs:
        raise UnsafeBase("无法解析主机名")
    for a in addrs:
        try:
            ok = _address_ok(a)
        except ValueError:
            ok = False
        if not ok:
            raise UnsafeBase("不允许内网 / 本机 / 保留地址")
    return PinnedBase(url=url, host=host, port=port, ip=addrs[0].split("%", 1)[0])


def _resolve(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as e:
        raise UnsafeBase("无法解析主机名") from e
    out: list[str] = []
    for info in infos:
        a = info[4][0]
        if a not in out:
            out.append(a)
    return out


class RedirectRefused(httpx.TransportError):
    pass


def _pin(request: httpx.Request, pin: PinnedBase) -> None:
    if (request.url.scheme != "https" or request.url.host.rstrip(".").lower() != pin.host
            or (request.url.port or 443) != pin.port):
        raise httpx.ConnectError("request target is not the pinned custom base", request=request)
    request.url = request.url.copy_with(host=pin.ip)
    request.extensions = {**request.extensions, "sni_hostname": pin.host}
    # Host header was fixed from the original URL when the request was built; keep it.


def _check_redirect(resp: httpx.Response, request: httpx.Request) -> None:
    if 300 <= resp.status_code < 400:
        resp.close()
        raise RedirectRefused("redirects are refused for custom endpoints", request=request)


class PinnedTransport(httpx.BaseTransport):
    def __init__(self, pin: PinnedBase, inner: httpx.BaseTransport | None = None):
        self.pin = pin
        self.inner = inner or httpx.HTTPTransport(retries=0)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        _pin(request, self.pin)
        resp = self.inner.handle_request(request)
        _check_redirect(resp, request)
        return resp

    def close(self) -> None:
        self.inner.close()


class AsyncPinnedTransport(httpx.AsyncBaseTransport):
    def __init__(self, pin: PinnedBase, inner: httpx.AsyncBaseTransport | None = None):
        self.pin = pin
        self.inner = inner or httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        _pin(request, self.pin)
        resp = await self.inner.handle_async_request(request)
        if 300 <= resp.status_code < 400:
            await resp.aclose()
            raise RedirectRefused("redirects are refused for custom endpoints", request=request)
        return resp

    async def aclose(self) -> None:
        await self.inner.aclose()


# Test seam: the inner (real-socket) transports. Tests swap these for httpx.MockTransport to see
# the exact connect target without touching the network.
SYNC_INNER = None
ASYNC_INNER = None


def openai_client(pin: PinnedBase, api_key: str, *, is_async: bool, timeout: float):
    """OpenAI SDK client bound to the pinned transport (litellm uses a passed `client` as-is).
    follow_redirects=False on httpx; the transport refuses 3xx regardless (the SDK opts in)."""
    import openai

    if is_async:
        http = httpx.AsyncClient(transport=AsyncPinnedTransport(pin, ASYNC_INNER),
                                 follow_redirects=False, timeout=timeout,
                                 trust_env=False)   # no HTTP(S)_PROXY / netrc: the pin is the route
        return openai.AsyncOpenAI(api_key=api_key, base_url=pin.url, http_client=http,
                                  max_retries=0)
    http = httpx.Client(transport=PinnedTransport(pin, SYNC_INNER), follow_redirects=False,
                        timeout=timeout, trust_env=False)
    return openai.OpenAI(api_key=api_key, base_url=pin.url, http_client=http, max_retries=0)
