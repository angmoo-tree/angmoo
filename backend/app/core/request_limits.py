from collections.abc import Awaitable, Callable
import re
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from app.exceptions import RequestBodyTooLargeError

DEFAULT_REQUEST_BODY_MAX_BYTES = 1024 * 1024
LORE_UPLOAD_REQUEST_BODY_MAX_BYTES = 10 * 1024 * 1024 + 256 * 1024
PROFILE_MEDIA_REQUEST_BODY_MAX_BYTES = 8_000_000 + 256 * 1024
WORLD_PACKAGE_UPLOAD_REQUEST_BODY_MAX_BYTES = 128 * 1024 * 1024 + 512 * 1024

_LORE_UPLOAD_PATH = re.compile(r"^/api/v1/agents/[^/]+/lore-sources/?$")
_DRAFT_MEDIA_PATH = re.compile(r"^/api/v1/agents/drafts/[^/]+/media/?$")
_PROFILE_MEDIA_PATH = re.compile(r"^/api/v1/agents/[^/]+/media/?$")
_IMAGE_SEED_PATH = re.compile(
    r"^/api/v1/agents/[^/]+/image-settings/seed/?$"
)
_WORLD_PACKAGE_STAGE_PATH = re.compile(
    r"^/api/v1/world-package-imports/stage/?$"
)


class RequestBodyLimitMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = request_body_limit(
            path=str(scope.get("path") or ""),
            method=str(scope.get("method") or "GET"),
        )
        content_length = _content_length(scope)
        if content_length is not None and content_length > limit:
            await _send_too_large(scope, receive, send)
            return

        received_bytes = 0

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] != "http.request":
                return message
            received_bytes += len(message.get("body", b""))
            if received_bytes > limit:
                raise RequestBodyTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLargeError:
            await _send_too_large(scope, receive, send)


def request_body_limit(*, path: str, method: str) -> int:
    normalized_method = method.upper()
    if normalized_method == "POST" and _LORE_UPLOAD_PATH.fullmatch(path):
        return LORE_UPLOAD_REQUEST_BODY_MAX_BYTES
    if normalized_method == "POST" and _WORLD_PACKAGE_STAGE_PATH.fullmatch(path):
        return WORLD_PACKAGE_UPLOAD_REQUEST_BODY_MAX_BYTES
    if normalized_method in {"POST", "PUT", "PATCH"} and any(
        pattern.fullmatch(path)
        for pattern in (
            _DRAFT_MEDIA_PATH,
            _PROFILE_MEDIA_PATH,
            _IMAGE_SEED_PATH,
        )
    ):
        return PROFILE_MEDIA_REQUEST_BODY_MAX_BYTES
    return DEFAULT_REQUEST_BODY_MAX_BYTES


def _content_length(scope: Scope) -> int | None:
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.lower() != b"content-length":
            continue
        try:
            value = int(raw_value.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            return None
        return value if value >= 0 else None
    return None


async def _send_too_large(scope: Scope, receive: Receive, send: Send) -> None:
    response = JSONResponse(
        {"detail": "Request body exceeds the allowed limit."},
        status_code=413,
    )
    await response(scope, receive, send)
