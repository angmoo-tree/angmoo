from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from app.domains.identity.browser_session import allowed_origins
from app.domains.identity.browser_session import require_local_frontend_request
from app.domains.identity.browser_session import set_bootstrap_challenge_cookie
from app.domains.identity.browser_session import set_session_cookie
from app.config import Settings
from app.core.desktop_loopback import (
    DesktopLoopbackPolicy,
    DesktopLoopbackSecurityMiddleware,
    is_authenticated_desktop_webview_request,
)
from app.runtime import desktop_sidecar
from app.runtime.desktop_sidecar import RuntimeOwnership, _stable_fatal_code


TOKEN = "a" * 64
ORIGIN = "http://tauri.localhost"


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(
        DesktopLoopbackSecurityMiddleware,
        policy=DesktopLoopbackPolicy(TOKEN, ORIGIN),
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/mutation")
    async def mutation() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/desktop-webview-auth")
    async def desktop_webview_auth(request: Request) -> dict[str, bool]:
        return {
            "authenticated": is_authenticated_desktop_webview_request(request)
        }

    return TestClient(app)


def test_desktop_loopback_rejects_missing_token_and_wrong_origin() -> None:
    client = _client()
    assert client.get("/health").status_code == 401
    assert (
        client.get(
            "/health",
            headers={"X-Angmoo-Launcher-Token": TOKEN, "Origin": "https://evil.test"},
        ).status_code
        == 403
    )


def test_desktop_loopback_accepts_exact_token_and_strict_cors() -> None:
    client = _client()
    response = client.get(
        "/health",
        headers={"X-Angmoo-Launcher-Token": TOKEN, "Origin": ORIGIN},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"

    preflight = client.options(
        "/mutation",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "content-type, idempotency-key, x-angmoo-launcher-token"
            ),
        },
    )
    assert preflight.status_code == 204
    assert "idempotency-key" in preflight.headers[
        "access-control-allow-headers"
    ]
    assert "x-angmoo-launcher-token" in preflight.headers[
        "access-control-allow-headers"
    ]

    rejected_preflight = client.options(
        "/mutation",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-untrusted-header",
        },
    )
    assert rejected_preflight.status_code == 403
    assert rejected_preflight.json() == {"detail": "desktop_headers_invalid"}

    assert client.get(
        "/desktop-webview-auth",
        headers={"X-Angmoo-Launcher-Token": TOKEN},
    ).json() == {"authenticated": False}
    assert client.get(
        "/desktop-webview-auth",
        headers={"X-Angmoo-Launcher-Token": TOKEN, "Origin": ORIGIN},
    ).json() == {"authenticated": True}


@pytest.mark.parametrize(
    ("method", "capability_headers"),
    [
        (
            "GET",
            "x-angmoo-launcher-token, x-world-package-download-token, "
            "x-world-package-delivery-mode",
        ),
        (
            "POST",
            "content-type, x-angmoo-launcher-token, "
            "x-world-package-download-token",
        ),
        (
            "DELETE",
            "x-angmoo-launcher-token, x-world-package-download-token",
        ),
        (
            "POST",
            "content-type, idempotency-key, x-angmoo-launcher-token, "
            "x-world-package-preview-token",
        ),
        (
            "DELETE",
            "x-angmoo-launcher-token, x-world-package-preview-token",
        ),
    ],
)
def test_desktop_loopback_allows_exact_world_package_capability_preflights(
    method: str,
    capability_headers: str,
) -> None:
    response = _client().options(
        "/mutation",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": capability_headers,
        },
    )

    assert response.status_code == 204
    allowed_headers = {
        item.strip().lower()
        for item in response.headers["access-control-allow-headers"].split(",")
    }
    assert {
        item.strip().lower() for item in capability_headers.split(",")
    } <= allowed_headers
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_desktop_loopback_world_package_preflight_stays_fail_closed() -> None:
    client = _client()
    wildcard = client.options(
        "/mutation",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "*",
        },
    )
    query_token_substitute = client.options(
        "/mutation?preview_token=unsafe",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "x-untrusted-capability-token",
        },
    )

    assert wildcard.status_code == 403
    assert wildcard.json() == {"detail": "desktop_headers_invalid"}
    assert query_token_substitute.status_code == 403
    assert query_token_substitute.json() == {"detail": "desktop_headers_invalid"}


def test_desktop_origin_is_allowed_only_with_process_launch_token() -> None:
    config = Settings(
        APP_ENV="production",
        APP_SECRET="x" * 48,
        DESKTOP_LAUNCH_TOKEN=TOKEN,
        DESKTOP_ALLOWED_ORIGIN=ORIGIN,
        BROWSER_SESSION_ALLOWED_ORIGINS=ORIGIN,
    )
    assert allowed_origins(config) == (ORIGIN,)

    app = FastAPI()
    app.add_middleware(
        DesktopLoopbackSecurityMiddleware,
        policy=DesktopLoopbackPolicy(TOKEN, ORIGIN),
    )

    @app.post("/mutation")
    async def mutation(request: Request):
        require_local_frontend_request(request, mutation=True, config=config)
        return {"status": "ok"}

    @app.post("/cookies")
    async def cookies(request: Request):
        require_local_frontend_request(request, mutation=True, config=config)
        response = Response(status_code=204)
        set_bootstrap_challenge_cookie(response, "challenge", config=config)
        set_session_cookie(response, "session", config=config)
        return response

    client = TestClient(app, base_url="http://127.0.0.1:49152")
    response = client.post(
        "/mutation",
        headers={
            "Origin": ORIGIN,
            "Sec-Fetch-Site": "cross-site",
            "X-Angmoo-Launcher-Token": TOKEN,
        },
    )
    assert response.status_code == 200

    cookie_response = client.post(
        "/cookies",
        headers={
            "Origin": ORIGIN,
            "Sec-Fetch-Site": "cross-site",
            "X-Angmoo-Launcher-Token": TOKEN,
        },
    )
    assert cookie_response.status_code == 204
    cookies = cookie_response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert all("HttpOnly" in cookie for cookie in cookies)
    assert all("Path=/api" in cookie for cookie in cookies)
    assert all("SameSite=none" in cookie for cookie in cookies)
    assert all("Secure" in cookie for cookie in cookies)

    missing_token = client.post(
        "/mutation",
        headers={"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"},
    )
    assert missing_token.status_code == 401


def test_runtime_metadata_never_persists_launch_token(tmp_path: Path) -> None:
    ownership = RuntimeOwnership(tmp_path, launch_id="launch-fixture")
    ownership.acquire()
    ownership.publish_endpoint(49152)
    lock = json.loads(ownership.lock_path.read_text(encoding="utf-8"))
    endpoint = json.loads(ownership.endpoint_path.read_text(encoding="utf-8"))
    assert lock == {
        "schema_version": 1,
        "pid": ownership.pid,
        "process_start_token": ownership.process_start_token,
        "generation": "launch-fixture",
    }
    assert endpoint["host"] == "127.0.0.1"
    assert endpoint["dynamic_port"] == 49152
    assert endpoint["logical_sidecar_pid"] == ownership.pid
    assert endpoint["generation"] == "launch-fixture"
    assert TOKEN not in ownership.lock_path.read_text(encoding="utf-8")
    assert TOKEN not in ownership.endpoint_path.read_text(encoding="utf-8")
    ownership.release()
    assert not ownership.lock_path.exists()
    assert not ownership.endpoint_path.exists()


def test_runtime_ownership_rejects_duplicate_and_replaces_stale_owner(
    tmp_path: Path,
) -> None:
    ownership = RuntimeOwnership(tmp_path, launch_id="launch-a")
    ownership.acquire()
    duplicate = RuntimeOwnership(tmp_path, launch_id="launch-b")
    with pytest.raises(RuntimeError, match="desktop_sidecar_already_owned"):
        duplicate.acquire()
    ownership.release()

    ownership.lock_path.write_text(
        json.dumps({"schema_version": 1, "pid": 2_147_483_647}),
        encoding="utf-8",
    )
    ownership.endpoint_path.write_text("{}", encoding="utf-8")
    replacement = RuntimeOwnership(tmp_path, launch_id="launch-c")
    replacement.acquire()
    assert json.loads(replacement.lock_path.read_text(encoding="utf-8"))["pid"] == replacement.pid
    assert not replacement.endpoint_path.exists()
    replacement.release()


def test_runtime_ownership_replaces_pid_reuse_with_different_start_token(
    tmp_path: Path,
) -> None:
    ownership = RuntimeOwnership(tmp_path, launch_id="launch-a")
    ownership.acquire()
    stale = json.loads(ownership.lock_path.read_text(encoding="utf-8"))
    stale["process_start_token"] = "reused-pid-from-an-older-process"
    ownership.lock_path.write_text(json.dumps(stale), encoding="utf-8")
    ownership.endpoint_path.write_text("{}", encoding="utf-8")

    replacement = RuntimeOwnership(tmp_path, launch_id="launch-b")
    replacement.acquire()

    current = json.loads(replacement.lock_path.read_text(encoding="utf-8"))
    assert current["generation"] == "launch-b"
    assert current["process_start_token"] == replacement.process_start_token
    assert not replacement.endpoint_path.exists()
    replacement.release()


def test_runtime_release_cleans_own_endpoint_even_when_lock_was_removed(
    tmp_path: Path,
) -> None:
    ownership = RuntimeOwnership(tmp_path, launch_id="launch-a")
    ownership.acquire()
    ownership.publish_endpoint(49152)
    ownership.lock_path.unlink()

    ownership.release()

    assert not ownership.endpoint_path.exists()


def test_shutdown_endpoint_has_no_request_parameters() -> None:
    source = Path(desktop_sidecar.__file__).read_text(encoding="utf-8")

    assert 'async def shutdown() -> dict[str, str]:' in source
    assert "server.should_exit = True" in source
    assert "BackgroundTasks" not in source


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "unsupported SQLite schema version: 2",
            "desktop_sidecar_schema_unsupported",
        ),
        ("desktop_sidecar_already_owned", "desktop_sidecar_already_owned"),
        (
            "embedded_data_migration_failed:private-path",
            "desktop_sidecar_data_migration_failed",
        ),
        ("C:/private/path failed", "desktop_sidecar_startup_failed"),
    ],
)
def test_fatal_boundary_emits_only_stable_content_free_codes(
    message: str,
    expected: str,
) -> None:
    assert _stable_fatal_code(RuntimeError(message)) == expected
