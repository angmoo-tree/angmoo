from __future__ import annotations

import math
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response, status

from app.core.config import Settings, settings


SESSION_COOKIE_NAME = "angmoo_browser_session"
GOOGLE_PENDING_COOKIE_NAME = "angmoo_google_signup_pending"
BOOTSTRAP_CHALLENGE_COOKIE_NAME = "angmoo_local_owner_challenge"
LOCAL_FRONTEND_ORIGIN_HEADER = "x-angmoo-frontend-origin"
COOKIE_PATH = "/api"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
GOOGLE_PENDING_MAX_AGE_SECONDS = 15 * 60
BOOTSTRAP_CHALLENGE_MAX_AGE_SECONDS = 10 * 60
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class BrowserSessionConfigurationError(ValueError):
    pass


def canonical_origin(value: str) -> str:
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise BrowserSessionConfigurationError("invalid_browser_session_origin") from exc
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise BrowserSessionConfigurationError("invalid_browser_session_origin")

    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    return f"{scheme}://{host}"


def allowed_origins(config: Settings = settings) -> tuple[str, ...]:
    raw_origins = [
        item.strip()
        for item in config.BROWSER_SESSION_ALLOWED_ORIGINS.split(",")
        if item.strip()
    ]
    if not raw_origins:
        raise BrowserSessionConfigurationError("missing_browser_session_origin")
    origins = tuple(dict.fromkeys(canonical_origin(item) for item in raw_origins))
    desktop_origin = (
        canonical_origin(config.desktop_allowed_origin)
        if config.desktop_launch_token
        else None
    )
    if config.app_env == "production" and any(
        not origin.startswith("https://") and origin != desktop_origin
        for origin in origins
    ):
        raise BrowserSessionConfigurationError("invalid_browser_session_origin")
    return origins


def validate_browser_session_settings(config: Settings = settings) -> None:
    allowed_origins(config)


def require_browser_origin(request: Request, config: Settings = settings) -> None:
    origins = request.headers.getlist("origin")
    if len(origins) != 1:
        raise _csrf_error()
    try:
        origin = canonical_origin(origins[0])
        configured = allowed_origins(config)
    except BrowserSessionConfigurationError as exc:
        raise _csrf_error() from exc
    if origin not in configured:
        raise _csrf_error()
    if request.headers.get("sec-fetch-site", "").strip().lower() == "cross-site":
        raise _csrf_error()


def require_local_frontend_request(
    request: Request,
    *,
    mutation: bool,
    config: Settings = settings,
) -> None:
    forwarded_values = request.headers.getlist(LOCAL_FRONTEND_ORIGIN_HEADER)
    if len(forwarded_values) > 1:
        raise _csrf_error()

    if forwarded_values:
        try:
            frontend_origin = canonical_origin(forwarded_values[0])
            configured = allowed_origins(config)
        except BrowserSessionConfigurationError as exc:
            raise _csrf_error() from exc
    else:
        host_values = request.headers.getlist("host")
        if len(host_values) != 1:
            raise _csrf_error()
        scheme = urlsplit(allowed_origins(config)[0]).scheme
        try:
            frontend_origin = canonical_origin(f"{scheme}://{host_values[0]}")
            configured = allowed_origins(config)
        except BrowserSessionConfigurationError as exc:
            raise _csrf_error() from exc

    parsed = urlsplit(frontend_origin)
    permitted_hosts = {"127.0.0.1", "localhost", "::1"}
    if config.desktop_launch_token:
        desktop_origin = canonical_origin(config.desktop_allowed_origin)
        if frontend_origin == desktop_origin:
            permitted_hosts.add(urlsplit(desktop_origin).hostname or "")
    if frontend_origin not in configured or parsed.hostname not in permitted_hosts:
        raise _csrf_error()

    if mutation:
        require_browser_origin(request, config)
        origin_values = request.headers.getlist("origin")
        try:
            if len(origin_values) != 1 or canonical_origin(origin_values[0]) != frontend_origin:
                raise _csrf_error()
        except BrowserSessionConfigurationError as exc:
            raise _csrf_error() from exc


def require_cookie_mutation_origin(
    request: Request,
    *,
    cookie_authenticated: bool,
    config: Settings = settings,
) -> None:
    if cookie_authenticated and request.method.upper() in UNSAFE_METHODS:
        require_browser_origin(request, config)


def session_cookie_token(request: Request) -> str | None:
    cookies = getattr(request, "cookies", {})
    value = cookies.get(SESSION_COOKIE_NAME)
    return value.strip() if value and value.strip() else None


def bootstrap_challenge_cookie_token(request: Request) -> str | None:
    cookies = getattr(request, "cookies", {})
    value = cookies.get(BOOTSTRAP_CHALLENGE_COOKIE_NAME)
    return value.strip() if value and value.strip() else None


def google_pending_cookie_token(request: Request) -> str | None:
    cookies = getattr(request, "cookies", {})
    value = cookies.get(GOOGLE_PENDING_COOKIE_NAME)
    return value.strip() if value and value.strip() else None


def set_session_cookie(
    response: Response,
    token: str,
    *,
    max_age_seconds: int | None = None,
    config: Settings = settings,
) -> None:
    max_age = SESSION_MAX_AGE_SECONDS if max_age_seconds is None else max_age_seconds
    if max_age < 0:
        raise ValueError("session cookie max age must not be negative")
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        path=COOKIE_PATH,
        secure=config.app_env == "production",
        httponly=True,
        samesite="lax",
    )


def delete_session_cookie(
    response: Response,
    *,
    config: Settings = settings,
) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path=COOKIE_PATH,
        secure=config.app_env == "production",
        httponly=True,
        samesite="lax",
    )


def set_bootstrap_challenge_cookie(
    response: Response,
    token: str,
    *,
    max_age_seconds: int = BOOTSTRAP_CHALLENGE_MAX_AGE_SECONDS,
    config: Settings = settings,
) -> None:
    response.set_cookie(
        key=BOOTSTRAP_CHALLENGE_COOKIE_NAME,
        value=token,
        max_age=max(0, max_age_seconds),
        path=COOKIE_PATH,
        secure=config.app_env == "production",
        httponly=True,
        samesite="lax",
    )


def delete_bootstrap_challenge_cookie(
    response: Response,
    *,
    config: Settings = settings,
) -> None:
    response.delete_cookie(
        key=BOOTSTRAP_CHALLENGE_COOKIE_NAME,
        path=COOKIE_PATH,
        secure=config.app_env == "production",
        httponly=True,
        samesite="lax",
    )


def seconds_until(expires_at: datetime, *, now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    normalized_expiry = expires_at
    if normalized_expiry.tzinfo is None:
        normalized_expiry = normalized_expiry.replace(tzinfo=timezone.utc)
    return max(0, math.ceil((normalized_expiry - current).total_seconds()))


def set_google_pending_cookie(
    response: Response,
    token: str,
    *,
    config: Settings = settings,
) -> None:
    response.set_cookie(
        key=GOOGLE_PENDING_COOKIE_NAME,
        value=token,
        max_age=GOOGLE_PENDING_MAX_AGE_SECONDS,
        path=COOKIE_PATH,
        secure=config.app_env == "production",
        httponly=True,
        samesite="lax",
    )


def delete_google_pending_cookie(
    response: Response,
    *,
    config: Settings = settings,
) -> None:
    response.delete_cookie(
        key=GOOGLE_PENDING_COOKIE_NAME,
        path=COOKIE_PATH,
        secure=config.app_env == "production",
        httponly=True,
        samesite="lax",
    )


def _csrf_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="csrf_origin_invalid",
    )
