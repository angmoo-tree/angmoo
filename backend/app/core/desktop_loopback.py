from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


LAUNCH_TOKEN_HEADER = "x-angmoo-launcher-token"
_ALLOWED_REQUEST_HEADERS = (
    "content-type",
    LAUNCH_TOKEN_HEADER,
    "x-angmoo-frontend-origin",
)
_ALLOWED_METHODS = "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS"


class DesktopLoopbackConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class DesktopLoopbackPolicy:
    launch_token: str
    allowed_origin: str

    def __post_init__(self) -> None:
        if len(self.launch_token) < 32:
            raise DesktopLoopbackConfigurationError("desktop_launch_token_too_short")
        parsed = urlsplit(self.allowed_origin)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "tauri.localhost"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise DesktopLoopbackConfigurationError("desktop_origin_invalid")


class DesktopLoopbackSecurityMiddleware:
    """Authenticate the private dynamic-port API owned by the Tauri host.

    The middleware is installed only by the packaged desktop sidecar. Browser
    development and Docker continue to use their existing proxy/CSRF boundary.
    """

    def __init__(self, app: ASGIApp, *, policy: DesktopLoopbackPolicy) -> None:
        self.app = app
        self.policy = policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        origin = headers.get("origin")
        method = str(scope.get("method", "GET")).upper()
        if origin is not None and origin != self.policy.allowed_origin:
            await self._reject(send, 403, "desktop_origin_invalid")
            return
        if method == "OPTIONS":
            if origin != self.policy.allowed_origin:
                await self._reject(send, 403, "desktop_origin_required")
                return
            requested_headers = {
                item.strip().lower()
                for item in headers.get("access-control-request-headers", "").split(",")
                if item.strip()
            }
            if not requested_headers.issubset(set(_ALLOWED_REQUEST_HEADERS)):
                await self._reject(send, 403, "desktop_headers_invalid")
                return
            await self._preflight(send)
            return

        supplied = headers.get(LAUNCH_TOKEN_HEADER, "")
        if not hmac.compare_digest(supplied, self.policy.launch_token):
            await self._reject(send, 401, "desktop_token_invalid")
            return

        # Existing local-owner mutation guards consume this trusted internal
        # header. A caller cannot reach them before passing the launch token.
        raw_headers = list(scope.get("headers", []))
        raw_headers = [
            (key, value)
            for key, value in raw_headers
            if key.lower() != b"x-angmoo-frontend-origin"
        ]
        raw_headers.append(
            (b"x-angmoo-frontend-origin", self.policy.allowed_origin.encode("ascii"))
        )
        scoped = dict(scope)
        scoped["headers"] = raw_headers

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start" and origin:
                response_headers = MutableHeaders(scope=message)
                self._apply_cors(response_headers)
            await send(message)

        await self.app(scoped, receive, send_with_cors)

    def _apply_cors(self, headers: MutableHeaders) -> None:
        headers["Access-Control-Allow-Origin"] = self.policy.allowed_origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"

    async def _preflight(self, send: Send) -> None:
        headers = MutableHeaders()
        self._apply_cors(headers)
        headers["Access-Control-Allow-Methods"] = _ALLOWED_METHODS
        headers["Access-Control-Allow-Headers"] = ", ".join(_ALLOWED_REQUEST_HEADERS)
        headers["Access-Control-Max-Age"] = "600"
        await send(
            {
                "type": "http.response.start",
                "status": 204,
                "headers": headers.raw,
            }
        )
        await send({"type": "http.response.body", "body": b""})

    async def _reject(self, send: Send, status: int, code: str) -> None:
        body = (f'{{"detail":"{code}"}}').encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
