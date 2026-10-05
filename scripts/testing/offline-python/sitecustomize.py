"""Offline product-test processes: no implicit user dotenv or provider secrets."""
import ipaddress
import os
import socket
from pydantic_settings import BaseSettings

for name in tuple(os.environ):
    if any(part in name.upper() for part in ("API_KEY", "ACCESS_TOKEN", "LAUNCH_TOKEN", "KMS_KEY")):
        os.environ.pop(name, None)

_settings_init = BaseSettings.__init__


def _without_user_dotenv(self, *args, **kwargs):
    kwargs.setdefault("_env_file", None)
    return _settings_init(self, *args, **kwargs)


BaseSettings.__init__ = _without_user_dotenv
_getaddrinfo = socket.getaddrinfo
_connect = socket.socket.connect


def _loopback(host):
    if host in (None, "localhost"):
        return True
    try:
        return ipaddress.ip_address(str(host).strip("[]")).is_loopback
    except ValueError:
        return False


def _guarded_getaddrinfo(host, *args, **kwargs):
    if not _loopback(host):
        raise RuntimeError("task_external_network_blocked")
    return _getaddrinfo(host, *args, **kwargs)


def _guarded_connect(self, address):
    if isinstance(address, tuple) and address and not _loopback(address[0]):
        raise RuntimeError("task_external_network_blocked")
    return _connect(self, address)


socket.getaddrinfo = _guarded_getaddrinfo
socket.socket.connect = _guarded_connect
