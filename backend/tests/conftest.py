from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Iterator

import pytest


class ExternalNetworkBlocked(RuntimeError):
    pass


def _is_loopback_host(host: object) -> bool:
    if host is None:
        return True
    text = str(host).strip().strip("[]").lower()
    if text == "localhost":
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def _guard_host(host: object) -> None:
    if not _is_loopback_host(host):
        raise ExternalNetworkBlocked("non-loopback network access blocked")


@pytest.fixture
def deny_external_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Deny non-loopback socket and asyncio connections for security tests."""

    original_getaddrinfo = socket.getaddrinfo
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection
    original_async_create_connection = asyncio.BaseEventLoop.create_connection
    original_async_datagram = asyncio.BaseEventLoop.create_datagram_endpoint

    def guarded_getaddrinfo(host, *args, **kwargs):
        _guard_host(host)
        return original_getaddrinfo(host, *args, **kwargs)

    def guarded_connect(sock, address):
        if isinstance(address, tuple) and address:
            _guard_host(address[0])
        return original_connect(sock, address)

    def guarded_connect_ex(sock, address):
        if isinstance(address, tuple) and address:
            _guard_host(address[0])
        return original_connect_ex(sock, address)

    def guarded_create_connection(address, *args, **kwargs):
        if isinstance(address, tuple) and address:
            _guard_host(address[0])
        return original_create_connection(address, *args, **kwargs)

    async def guarded_async_create_connection(
        loop, protocol_factory, host=None, port=None, *args, **kwargs
    ):
        _guard_host(host)
        return await original_async_create_connection(
            loop, protocol_factory, host, port, *args, **kwargs
        )

    async def guarded_async_datagram(
        loop, protocol_factory, local_addr=None, remote_addr=None, *args, **kwargs
    ):
        if isinstance(remote_addr, tuple) and remote_addr:
            _guard_host(remote_addr[0])
        return await original_async_datagram(
            loop,
            protocol_factory,
            local_addr=local_addr,
            remote_addr=remote_addr,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    monkeypatch.setattr(
        asyncio.BaseEventLoop, "create_connection", guarded_async_create_connection
    )
    monkeypatch.setattr(
        asyncio.BaseEventLoop, "create_datagram_endpoint", guarded_async_datagram
    )
    yield
