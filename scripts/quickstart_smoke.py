"""Run a synthetic, provider-free quickstart persistence smoke."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4


SESSION_COOKIE_NAME = "angmoo_browser_session"


class SmokeError(RuntimeError):
    pass


def _request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    token: str | None = None,
    cookie: str | None = None,
    origin: str | None = None,
) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if cookie:
        headers["Cookie"] = cookie
    if origin:
        headers["Origin"] = origin
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SmokeError(f"{method} {path} returned {exc.code}: {body[:240]}") from exc


def _expect(status: int, expected: int, label: str) -> None:
    if status != expected:
        raise SmokeError(f"{label} returned {status}, expected {expected}")


def _require_loopback_backend(backend_url: str) -> None:
    if urlparse(backend_url).hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise SmokeError("local session bootstrap requires a loopback backend URL")


def _bootstrap_local_session(marker: str, backend_url: str) -> str:
    _require_loopback_backend(backend_url)
    backend_root = Path(__file__).resolve().parents[1] / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from sqlalchemy.engine import make_url

    from app import models
    from app.core import security
    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.domains.identity.domain.local_owner import LOCAL_INSTALLATION_KEY

    if make_url(settings.database_url).host not in {"127.0.0.1", "::1", "localhost"}:
        raise SmokeError("local session bootstrap requires a loopback database")

    now = datetime.now(UTC)
    user_id = f"user-{uuid4().hex}"
    token = security.create_token()
    with SessionLocal() as db:
        db.add(
            models.User(
                id=user_id,
                email=f"{marker}@example.test",
                google_sub=f"quickstart-{uuid4().hex}",
                password_hash=None,
                display_name=marker,
                display_name_normalized=marker,
                privacy_policy_agreed_at=now,
                terms_agreed_at=now,
                privacy_policy_version="2026-06-22",
                terms_version="2026-06-22",
                profile_setup_completed=True,
            )
        )
        db.add(
            models.InstallationIdentity(
                singleton_key=LOCAL_INSTALLATION_KEY,
                installation_id=f"installation-{uuid4().hex}",
                owner_user_id=user_id,
                bootstrap_state="claimed",
                claimed_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            models.AuthSession(
                token_hash=security.hash_token(token),
                user_id=user_id,
                auth_method="local_owner",
                created_at=now,
                expires_at=now + timedelta(days=7),
            )
        )
        db.commit()
    return token


def run_smoke(
    backend_url: str,
    frontend_url: str | None,
    *,
    bootstrap_local_session: bool = False,
) -> dict[str, object]:
    marker = f"m4-quickstart-{uuid4().hex[:12]}"
    status, health = _request(backend_url, "/health")
    _expect(status, 200, "health")
    status, posts = _request(backend_url, "/api/v1/posts")
    _expect(status, 200, "posts")
    if not isinstance(posts, list):
        raise SmokeError("posts response is not a list")
    if not any(item.get("id") == "post-001" for item in posts):
        raise SmokeError("seed post-001 is missing")

    if bootstrap_local_session:
        token = _bootstrap_local_session(marker, backend_url)
    else:
        status, auth = _request(
            backend_url,
            "/api/v1/auth/signup",
            method="POST",
            payload={
                "email": f"{marker}@example.test",
                "password": "synthetic-password-1234",
                "display_name": marker,
                "privacy_policy_agreed": True,
                "terms_agreed": True,
            },
        )
        _expect(status, 201, "signup")
        token = str(auth["token"])
    status, agent = _request(
        backend_url,
        "/api/v1/agents",
        method="POST",
        token=token,
        payload={
            "execution_mode": "local",
            "name": marker,
            "handle": f"m4-{uuid4().hex[:10]}",
        },
    )
    _expect(status, 201, "local agent create")
    character_id = str(agent["character"]["id"])

    write_base = frontend_url or backend_url
    write_prefix = "/api/backend" if frontend_url else "/api/v1"
    write_token = token
    write_cookie = None
    write_origin = None
    if frontend_url:
        parsed_frontend_url = urlparse(frontend_url)
        if (
            parsed_frontend_url.scheme not in {"http", "https"}
            or not parsed_frontend_url.netloc
        ):
            raise SmokeError("frontend URL must include an HTTP origin")
        write_origin = (
            f"{parsed_frontend_url.scheme}://{parsed_frontend_url.netloc}"
        )
        write_token = None
        write_cookie = f"{SESSION_COOKIE_NAME}={token}"
    status, reply = _request(
        write_base,
        f"{write_prefix}/posts/post-001/replies",
        method="POST",
        token=write_token,
        cookie=write_cookie,
        origin=write_origin,
        payload={"body": marker, "author_character_id": character_id},
    )
    _expect(status, 201, "reply create")
    if reply.get("body") != marker:
        raise SmokeError("reply marker was not returned")
    reply_id = str(reply["id"])
    status, reply_readback = _request(
        backend_url, f"/api/v1/posts/{reply_id}"
    )
    _expect(status, 200, "reply readback")
    if reply_readback.get("body") != marker:
        raise SmokeError("reply marker was not persisted")

    status, state = _request(
        write_base,
        f"{write_prefix}/characters/{character_id}/state",
        method="POST",
        token=write_token,
        cookie=write_cookie,
        origin=write_origin,
        payload={
            "mood": "curious",
            "summary": marker,
            "memory_note": "synthetic M4 quickstart state",
        },
    )
    _expect(status, 200, "state save")
    if state.get("summary") != marker:
        raise SmokeError("state marker was not returned")

    status, activity = _request(
        backend_url, f"/api/v1/characters/{character_id}/activity"
    )
    _expect(status, 200, "activity readback")
    if activity.get("state", {}).get("summary") != marker:
        raise SmokeError("state marker was not persisted")

    status, local_key = _request(
        backend_url,
        f"/api/v1/agents/{character_id}/local-key",
        method="POST",
        token=token,
        payload={},
    )
    _expect(status, 201, "Local Bot token issue")
    local_token = str(local_key["token"])
    status, bot_me = _request(
        backend_url, "/api/v1/bot/me", token=local_token
    )
    _expect(status, 200, "Local Bot me")
    if bot_me.get("character", {}).get("id") != character_id:
        raise SmokeError("Local Bot token resolved the wrong character")

    frontend_checks: dict[str, int] = {}
    if frontend_url:
        for path in ("/", "/posts", "/posts/post-001", f"/characters/{character_id}/activity"):
            request = Request(f"{frontend_url.rstrip('/')}{path}", method="GET")
            with urlopen(request, timeout=20) as response:
                frontend_checks[path] = response.status
                if response.status != 200:
                    raise SmokeError(f"frontend {path} returned {response.status}")

    return {
        "marker": marker,
        "health": health,
        "character_id": character_id,
        "reply_persisted": True,
        "state_persisted": True,
        "local_bot_contract": True,
        "frontend": frontend_checks,
        "completed_at_epoch": int(time.time()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", default="http://127.0.0.1:8080")
    parser.add_argument("--frontend-url")
    parser.add_argument(
        "--bootstrap-local-session",
        action="store_true",
        help="seed a synthetic local-owner session in a loopback disposable database",
    )
    args = parser.parse_args()
    try:
        result = run_smoke(
            args.backend_url,
            args.frontend_url,
            bootstrap_local_session=args.bootstrap_local_session,
        )
    except (OSError, KeyError, TypeError, SmokeError, json.JSONDecodeError) as exc:
        print(f"Quickstart smoke failed: {exc}")
        return 1
    safe_result = dict(result)
    safe_result.pop("marker", None)
    print(json.dumps(safe_result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
