"""Opt-in isolated contributor runtime for Next/static language regressions.

Only synthetic data is admitted. Production routers, cookie authentication,
Identity CAS and SQLite persistence are exercised without external AI calls.
Fixture controls exist only in this loopback test process, never in the app.
"""
import argparse
from datetime import UTC, datetime, timedelta
import ipaddress
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18399)
    args = parser.parse_args()
    root = args.data_root.resolve()
    boundary = (ROOT / "artifacts" / "multilingual-gemini-20261003").resolve()
    if boundary not in root.parents:
        raise SystemExit("synthetic_data_root_required")
    origins = "http://127.0.0.1:3361,http://127.0.0.1:3362"
    os.environ.update(APP_ENV="development", BROWSER_SESSION_ALLOWED_ORIGINS=origins,
        RESIDENT_TICK_SCHEDULER_ENABLED="false", POST_IMAGE_JOB_WORKER_ENABLED="false",
        SEED_DEMO_DATA="false", SIGNUP_ENABLED="false")
    sys.path.insert(0, str(ROOT / "backend"))

    # Any accidental AI/network request fails closed, before a physical send.
    import httpx
    send, async_send = httpx.Client.send, httpx.AsyncClient.send
    def allowed(request):
        host = urlsplit(str(request.url)).hostname
        try:
            if host == "localhost" or ipaddress.ip_address(host or "").is_loopback:
                return
        except ValueError:
            pass
        raise RuntimeError("fixture_external_network_forbidden")
    def local_send(client, request, *a, **kw):
        allowed(request)
        return send(client, request, *a, **kw)
    async def local_async_send(client, request, *a, **kw):
        allowed(request)
        return await async_send(client, request, *a, **kw)
    httpx.Client.send, httpx.AsyncClient.send = local_send, local_async_send

    from app.runtime.contributor_backend import create_contributor_runtime_app
    from app.domains.identity.service.local_owner import LocalIdentityService
    from app.domains.identity.models import AuthSession, InstallationIdentity, User
    from app.domains.identity.models_environment import LocalEnvironment, EnvironmentTimezoneChange
    from app.domains.identity.constants import LOCAL_INSTALLATION_KEY
    from app.config import settings
    from fastapi import Request, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from sqlalchemy import delete
    import uvicorn

    app = create_contributor_runtime_app(data_root=root, frontend_origin=origins.split(",")[0])
    # Both browser projects are explicit permitted test clients.
    settings.BROWSER_SESSION_ALLOWED_ORIGINS = origins
    app.add_middleware(CORSMiddleware, allow_origins=origins.split(","),
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    sessions = app.state.runtime_composition.session_factory
    with sessions() as db:
        identity = db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
        if identity.bootstrap_state == "unclaimed":
            workflow = LocalIdentityService(db)
            challenge = workflow.create_bootstrap_challenge()
            workflow.claim_local_owner(challenge_token=challenge.token, owner_user_id=None,
                display_name="Synthetic User · 原文 A-17", local_label="Multilingual fixture",
                privacy_acknowledged=True)

    def fixture_request(request):
        if request.client.host not in {"127.0.0.1", "::1"} or request.headers.get("x-fixture-control") != "synthetic-only":
            raise HTTPException(403, "fixture_control_required")

    @app.post("/__fixture/reset")
    async def reset(request: Request):
        fixture_request(request)
        with sessions() as db:
            db.execute(delete(EnvironmentTimezoneChange))
            db.execute(delete(LocalEnvironment))
            db.execute(delete(AuthSession))
            identity = db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
            owner = db.get(User, identity.owner_user_id)
            owner.ui_language = None
            owner.ui_preference_revision = 0
            db.commit()
        return {"reset": True, "external_calls": 0}

    @app.post("/__fixture/expire-lease")
    async def expire(request: Request):
        fixture_request(request)
        with sessions() as db:
            identity = db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
            row = db.get(LocalEnvironment, identity.owner_user_id)
            if row:
                row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
                db.commit()
        return {"expired": True}

    @app.get("/__fixture/state")
    async def state(request: Request):
        fixture_request(request)
        from app.domains.identity.service.environment import read_environment
        with sessions() as db:
            identity = db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
            owner = db.get(User, identity.owner_user_id)
            environment = read_environment(db, owner.id).model_dump(mode="json")
            return {"environment": environment, "ui_language": owner.ui_language,
                "ui_preference_revision": owner.ui_preference_revision,
                "display_name": owner.display_name, "external_calls": 0}

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, access_log=False))

    @app.post("/__fixture/stop")
    async def stop(request: Request):
        fixture_request(request)
        server.should_exit = True
        return {"stopping": True}

    server.run()


if __name__ == "__main__":
    main()
