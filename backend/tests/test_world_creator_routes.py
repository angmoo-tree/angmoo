from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.api.v1 import deps as api_deps
from app.api.v1.routes import worlds as world_routes
from app.core.db import Base


def _app():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(world_routes.router, prefix="/api/v1")
    principal: dict[str, models.User | None] = {"user": None}

    def get_db():
        with Session(engine) as db:
            yield db

    def current_user() -> models.User:
        assert principal["user"] is not None
        return principal["user"]

    app.dependency_overrides[api_deps.get_db] = get_db
    app.dependency_overrides[api_deps.get_current_user] = current_user
    app.dependency_overrides[api_deps.get_optional_current_user] = (
        lambda: principal["user"]
    )
    return app, engine, principal


def _request(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    async def call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(call())


def _user(user_id: str) -> models.User:
    return models.User(
        id=user_id,
        email=f"{user_id}@example.test",
        display_name=user_id,
        display_name_normalized=user_id,
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )


def _payload(**overrides):
    values = {
        "name": "비늘항구의 밤",
        "tagline": "달빛 아래 서로 다른 종족이 일상을 나누는 항구 도시",
        "setting_description": "세계" * 100,
        "daily_life_description": "일상" * 75,
        "genre_tags": ["fantasy"],
        "tone_tags": ["warm"],
        "idempotency_key": "route-create-world",
    }
    values.update(overrides)
    return values


def test_creator_route_lifecycle_and_stable_conflict() -> None:
    app, engine, principal = _app()
    owner = _user("owner")
    with Session(engine, expire_on_commit=False) as db:
        db.add(owner)
        db.commit()
    principal["user"] = owner

    created = _request(app, "POST", "/api/v1/worlds", json=_payload())
    assert created.status_code == 201
    world_id = created.json()["world"]["id"]
    assert created.json()["readiness"]["ready_for_publish"] is True

    published = _request(
        app,
        "POST",
        f"/api/v1/worlds/{world_id}/publish",
        json={"row_version": created.json()["world"]["row_version"]},
    )
    assert published.status_code == 200
    assert published.json()["world"]["status"] == "published"

    replayed_publish = _request(
        app,
        "POST",
        f"/api/v1/worlds/{world_id}/publish",
        json={"row_version": created.json()["world"]["row_version"]},
    )
    assert replayed_publish.status_code == 200
    assert (
        replayed_publish.json()["world"]["row_version"]
        == published.json()["world"]["row_version"]
    )

    stale = _request(
        app,
        "PATCH",
        f"/api/v1/worlds/{world_id}",
        json={"row_version": 1, "tagline": "stale update must fail"},
    )
    assert stale.status_code == 409
    assert stale.json() == {"detail": "row_version_conflict"}


def test_private_world_is_hidden_and_member_cannot_mutate() -> None:
    app, engine, principal = _app()
    owner, member, outsider = _user("owner"), _user("member"), _user("outsider")
    with Session(engine, expire_on_commit=False) as db:
        db.add_all([owner, member, outsider])
        db.commit()
    principal["user"] = owner
    created = _request(app, "POST", "/api/v1/worlds", json=_payload())
    world_id = created.json()["world"]["id"]
    with Session(engine, expire_on_commit=False) as db:
        db.add(
            models.WorldMembership(
                id="membership-member",
                world_id=world_id,
                user_id=member.id,
                role="member",
                status="active",
                joined_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    principal["user"] = outsider
    hidden = _request(app, "GET", f"/api/v1/worlds/{world_id}")
    assert hidden.status_code == 404

    principal["user"] = member
    forbidden = _request(
        app,
        "PATCH",
        f"/api/v1/worlds/{world_id}",
        json={"row_version": 1, "tagline": "member cannot edit this world"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json() == {"detail": "creator_role_required"}


def test_api_rejects_unknown_fields_and_frontend_uses_new_creator_routes() -> None:
    app, engine, principal = _app()
    owner = _user("owner")
    with Session(engine, expire_on_commit=False) as db:
        db.add(owner)
        db.commit()
    principal["user"] = owner

    invalid = _request(
        app,
        "POST",
        "/api/v1/worlds",
        json={**_payload(), "provider_api_key": "must-not-be-accepted"},
    )
    assert invalid.status_code == 422

    frontend_root = Path(__file__).parents[2] / "frontend" / "src"
    client = (frontend_root / "components" / "world-creator-client.tsx").read_text(
        encoding="utf-8"
    )
    navigation = (frontend_root / "lib" / "safe-navigation.ts").read_text(
        encoding="utf-8"
    )
    assert "World Creator · P1" in client
    assert "activity-templates" not in client
    assert "^\\/worlds\\/new$" in navigation
    assert "creator\\/$" not in navigation
