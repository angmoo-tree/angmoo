from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
import ipaddress
import re
import socket
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


_REQUEST_ID_HEADERS = (
    "X-Request-Id",
    "Request-Id",
    "X-Correlation-Id",
    "Traceparent",
)
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")
_SAFE_DIAGNOSTIC_HINTS = frozenset(
    {
        "auth_or_quota",
        "provider_input_or_model_policy",
        "provider_unstable",
        "relay_infra",
        "safe_filter_possible",
    }
)


class ProviderUrlError(ValueError):
    pass


@dataclass(frozen=True)
class SafeProviderDiagnostic:
    status_code: int | None
    content_type: str | None
    request_id: str | None
    diagnostic_hint: str | None


def read_safe_http_error_diagnostic(
    error: HTTPError,
    *,
    classify_body: Callable[[str, str | None], str | None] | None = None,
    max_body_bytes: int = 2048,
) -> SafeProviderDiagnostic:
    content_type = _content_type(error.headers)
    diagnostic_hint = None
    try:
        raw = error.read(max_body_bytes)
    except Exception:
        raw = b""
    try:
        if raw and classify_body is not None:
            candidate = classify_body(
                raw.decode("utf-8", errors="replace"),
                content_type,
            )
            if candidate in _SAFE_DIAGNOSTIC_HINTS:
                diagnostic_hint = candidate
    finally:
        raw = b""
        try:
            error.close()
        except Exception:
            pass
    return SafeProviderDiagnostic(
        status_code=getattr(error, "code", None),
        content_type=content_type,
        request_id=_request_id(error.headers),
        diagnostic_hint=diagnostic_hint,
    )


def validate_public_https_url(
    url: str,
    *,
    allowed_hosts: Collection[str] | None = None,
    allowed_path_prefixes: Collection[str] | None = None,
) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ProviderUrlError("provider URL must be public HTTPS")
    try:
        host = parsed.hostname.encode("ascii").decode("ascii").lower()
        port = parsed.port
    except (UnicodeError, ValueError) as exc:
        raise ProviderUrlError("provider URL is invalid") from exc
    if port not in {None, 443}:
        raise ProviderUrlError("provider URL port is not allowed")
    if allowed_hosts is not None and host not in {
        value.lower() for value in allowed_hosts
    }:
        raise ProviderUrlError("provider URL host is not allowed")
    if allowed_path_prefixes is not None and not any(
        parsed.path == prefix.rstrip("/")
        or parsed.path.startswith(f"{prefix.rstrip('/')}/")
        for prefix in allowed_path_prefixes
    ):
        raise ProviderUrlError("provider URL path is not allowed")

    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ProviderUrlError("provider URL could not be resolved") from exc
    if not addresses:
        raise ProviderUrlError("provider URL could not be resolved")
    for address in addresses:
        try:
            resolved = ipaddress.ip_address(address[4][0].split("%", 1)[0])
        except ValueError as exc:
            raise ProviderUrlError("provider URL resolved to an invalid address") from exc
        if not resolved.is_global:
            raise ProviderUrlError("provider URL resolved to a non-public address")


class ValidatedRedirectHandler(HTTPRedirectHandler):
    def __init__(
        self,
        *,
        redirect_validator: Callable[[str], None],
        sensitive_headers: Collection[str],
        allow_cross_origin_redirects: bool = False,
    ) -> None:
        super().__init__()
        self._redirect_validator = redirect_validator
        self._sensitive_headers = {name.lower() for name in sensitive_headers}
        self._allow_cross_origin_redirects = allow_cross_origin_redirects

    def redirect_request(
        self,
        request,
        file_pointer,
        code,
        message,
        headers,
        new_url,
    ):
        self._redirect_validator(new_url)
        cross_origin = _origin(request.full_url) != _origin(new_url)
        if cross_origin and not self._allow_cross_origin_redirects:
            raise ProviderUrlError("cross-origin provider redirect was not allowed")
        redirected = super().redirect_request(
            request,
            file_pointer,
            code,
            message,
            headers,
            new_url,
        )
        if redirected is not None and cross_origin:
            _remove_sensitive_headers(redirected, self._sensitive_headers)
        return redirected


def open_validated_request(
    request: Request,
    *,
    timeout_seconds: float,
    initial_validator: Callable[[str], None],
    redirect_validator: Callable[[str], None],
    sensitive_headers: Collection[str],
    allow_cross_origin_redirects: bool = False,
):
    initial_validator(request.full_url)
    response = build_opener(
        ValidatedRedirectHandler(
            redirect_validator=redirect_validator,
            sensitive_headers=sensitive_headers,
            allow_cross_origin_redirects=allow_cross_origin_redirects,
        )
    ).open(request, timeout=max(1, int(timeout_seconds)))
    try:
        redirect_validator(response.geturl())
    except Exception:
        response.close()
        raise
    return response


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlparse(url)
    port = parsed.port
    if port is None and parsed.scheme == "https":
        port = 443
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), port


def _remove_sensitive_headers(request: Request, sensitive_headers: set[str]) -> None:
    for name, _value in tuple(request.header_items()):
        if name.lower() in sensitive_headers:
            request.remove_header(name)
    for name in tuple(request.unredirected_hdrs):
        if name.lower() in sensitive_headers:
            request.unredirected_hdrs.pop(name, None)


def _content_type(headers) -> str | None:
    if not headers:
        return None
    value = headers.get("Content-Type", "")
    return value.split(";", 1)[0].strip().lower() or None


def _request_id(headers) -> str | None:
    if not headers:
        return None
    for header in _REQUEST_ID_HEADERS:
        value = headers.get(header)
        if isinstance(value, str) and _SAFE_REQUEST_ID.fullmatch(value.strip()):
            return value.strip()
    return None
