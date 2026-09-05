from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import httpx
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.domains.identity import dependencies as api_deps
from app.api.v1.routes import worlds as world_routes
from app.core.config import settings
from app.core.db import Base
from app.domains.worlds.infrastructure.sqlalchemy_reserved_roles import (
    ensure_no_specific_role,
)


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

    with Session(engine) as db:
        assert db.query(models.Post).count() == 0
        assert db.query(models.AgentRun).count() == 0


def test_reserved_no_role_is_system_owned_and_survives_user_definition_sync() -> None:
    app, engine, principal = _app()
    owner = _user("reserved-role-owner")
    with Session(engine, expire_on_commit=False) as db:
        db.add(owner)
        db.commit()
    principal["user"] = owner

    created = _request(
        app,
        "POST",
        "/api/v1/worlds",
        json=_payload(idempotency_key="reserved-role-world"),
    )
    assert created.status_code == 201
    world = created.json()["world"]
    with Session(engine) as db:
        ensure_no_specific_role(db, world_id=world["id"])
        db.commit()

    omitted = _request(
        app,
        "PATCH",
        f"/api/v1/worlds/{world['id']}",
        json={"row_version": world["row_version"], "roles": []},
    )
    assert omitted.status_code == 200, omitted.text
    with Session(engine) as db:
        reserved = db.query(models.WorldRole).filter_by(
            world_id=world["id"], role_key="no_specific_role"
        ).one()
        assert reserved.status == "enabled"

    managed = _request(
        app,
        "PATCH",
        f"/api/v1/worlds/{world['id']}",
        json={
            "row_version": omitted.json()["world"]["row_version"],
            "roles": [
                {
                    "key": "no_specific_role",
                    "name": "역할 없음",
                    "description": "별도의 World 역할을 지정하지 않은 캐릭터",
                    "responsibilities": [],
                    "allowed_activity_scope": [],
                    "autonomous_allowed": True,
                }
            ],
        },
    )
    assert managed.status_code == 422
    assert managed.json() == {"detail": "world_definition_incomplete"}


def test_world_banner_round_trip_stays_inside_worlds_domain_storage(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    app, engine, principal = _app()
    owner = _user("owner")
    with Session(engine, expire_on_commit=False) as db:
        db.add(owner)
        db.commit()
    principal["user"] = owner

    created = _request(app, "POST", "/api/v1/worlds", json=_payload())
    world = created.json()["world"]
    image = Image.new("RGB", (320, 120), (120, 80, 200))
    output = BytesIO()
    image.save(output, format="PNG")

    uploaded = _request(
        app,
        "POST",
        f"/api/v1/worlds/{world['id']}/banner",
        json={
            "row_version": world["row_version"],
            "content_type": "image/png",
            "data_base64": base64.b64encode(output.getvalue()).decode("ascii"),
            "alt_text": "비늘항구의 야경",
        },
    )
    assert uploaded.status_code == 200
    uploaded_world = uploaded.json()["world"]
    media_url = uploaded_world["banner_media_id"]
    assert media_url.startswith(f"/media/worlds/{world['id']}/banner-")
    media_path = tmp_path / media_url.removeprefix("/media/")
    assert media_path.is_file()
    assert media_path.read_bytes().startswith(b"RIFF")

    removed = _request(
        app,
        "DELETE",
        f"/api/v1/worlds/{world['id']}/banner",
        json={"row_version": uploaded_world["row_version"]},
    )
    assert removed.status_code == 200
    assert removed.json()["world"]["banner_media_id"] is None
    assert not media_path.exists()


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
