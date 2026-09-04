from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.api.v1.deps import get_current_user
from app.core.db import Base, get_db
from app.domains.device_home.router import router
from app.providers import registry as provider_registry


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


def _world(
    world_id: str,
    *,
    owner_user_id: str,
    status_value: str = "published",
    visibility: str = "public",
    readiness_status: str = "publish_ready",
    updated_at: datetime,
) -> models.World:
    return models.World(
        id=world_id,
        slug=world_id,
        owner_user_id=owner_user_id,
        name=f"World {world_id}",
        tagline=f"tagline {world_id}",
        setting_description="fixture setting",
        daily_life_description="fixture daily life",
        genre_tags=["fixture"],
        tone_tags=["warm"],
        banner_alt_text="",
        timezone="Asia/Seoul",
        language="ko",
        visibility=visibility,
        join_policy="open",
        status=status_value,
        definition_version=1,
        row_version=1,
        contract_version="world-contract-v1",
        contract_hash=(world_id * 64)[:64],
        readiness_status=readiness_status,
        additional_generation_guidance="",
        create_idempotency_key=f"create-{world_id}",
        created_at=updated_at,
        updated_at=updated_at,
        archived_at=updated_at if status_value == "archived" else None,
    )


def _membership(
    membership_id: str,
    *,
    world_id: str,
    user_id: str,
    role: str = "owner",
) -> models.WorldMembership:
    return models.WorldMembership(
        id=membership_id,
        world_id=world_id,
        user_id=user_id,
        role=role,
        status="active",
        joined_at=datetime.now(UTC),
    )


def _fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    principal: dict[str, models.User | None] = {"user": None}
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def db_dependency():
        with Session(engine) as db:
            yield db

    def user_dependency() -> models.User:
        if principal["user"] is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        return principal["user"]

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_user] = user_dependency
    client = TestClient(app, base_url="http://127.0.0.1:3000")
    return client, engine, principal


def _seed(engine, principal) -> tuple[models.User, models.User]:
    owner = _user("owner-a")
    outsider = _user("owner-b")
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    worlds = (
        _world("home-new", owner_user_id=owner.id, updated_at=now),
        _world(
            "home-old",
            owner_user_id=owner.id,
            visibility="unlisted",
            updated_at=now - timedelta(hours=1),
        ),
        _world(
            "private",
            owner_user_id=owner.id,
            visibility="private",
            updated_at=now - timedelta(hours=2),
        ),
        _world(
            "draft",
            owner_user_id=owner.id,
            status_value="draft",
            readiness_status="not_ready",
            updated_at=now - timedelta(hours=3),
        ),
        _world(
            "archived",
            owner_user_id=owner.id,
            status_value="archived",
            updated_at=now - timedelta(hours=4),
        ),
        _world("foreign", owner_user_id=outsider.id, updated_at=now + timedelta(hours=1)),
    )
    with Session(engine, expire_on_commit=False) as db:
        db.add_all([owner, outsider])
        db.flush()
        db.add(
            models.InstallationIdentity(
                singleton_key="local-installation",
                installation_id="fixture-installation",
                owner_user_id=owner.id,
                bootstrap_state="claimed",
                local_label="fixture",
                claimed_at=now,
            )
        )
        db.add_all(worlds)
        db.flush()
        db.add_all(
            [
                _membership(
                    f"membership-{world.id}",
                    world_id=world.id,
                    user_id=world.owner_user_id,
                )
                for world in worlds
            ]
        )
        db.commit()
    principal["user"] = owner
    return owner, outsider


def test_device_home_surface_is_owner_scoped_filtered_and_deterministic() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)

    response = client.get("/api/v1/worlds/mine?surface=device_home")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "local-world-surface-v1"
    assert payload["surface"] == "device_home"
    assert [item["world_id"] for item in payload["items"]] == [
        "home-new",
        "home-old",
    ]
    assert all(item["launchable"] is True for item in payload["items"])
    assert all(item["launch_block_reason"] is None for item in payload["items"])
    serialized = response.text.lower()
    for forbidden in (
        "foreign",
        "private",
        "draft",
        "archived",
        "owner-a@example.test",
        "api_key",
        "app_secret",
    ):
        assert forbidden not in serialized


def test_creator_studio_surface_includes_only_owner_managed_worlds() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)

    response = client.get("/api/v1/worlds/mine?surface=creator_studio")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["world_id"] for item in items] == [
        "home-new",
        "home-old",
        "private",
        "draft",
        "archived",
    ]
    blocked = {item["world_id"]: item["launch_block_reason"] for item in items}
    assert blocked == {
        "home-new": None,
        "home-old": None,
        "private": "world_private",
        "draft": "world_not_published",
        "archived": "world_archived",
    }


def test_surface_requires_session_and_claimed_installation_owner() -> None:
    client, engine, principal = _fixture()
    owner, outsider = _seed(engine, principal)

    principal["user"] = None
    unauthenticated = client.get("/api/v1/worlds/mine?surface=device_home")
    assert unauthenticated.status_code == 401

    principal["user"] = outsider
    forbidden = client.get("/api/v1/worlds/mine?surface=device_home")
    assert forbidden.status_code == 403
    assert forbidden.json() == {"detail": "local_owner_required"}

    principal["user"] = owner
    invalid_surface = client.get("/api/v1/worlds/mine?surface=public_discovery")
    assert invalid_surface.status_code == 422


def test_surface_read_is_bounded_cursor_safe_and_write_free() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)
    writes: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _capture_writes(_conn, _cursor, statement, _parameters, _context, _many):
        operation = statement.lstrip().split(None, 1)[0].upper()
        if operation in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(operation)

    first = client.get("/api/v1/worlds/mine?surface=device_home&limit=1")
    assert first.status_code == 200
    assert [item["world_id"] for item in first.json()["items"]] == ["home-new"]
    cursor = first.json()["next_cursor"]
    assert cursor

    second = client.get(
        "/api/v1/worlds/mine",
        params={"surface": "device_home", "limit": 1, "cursor": cursor},
    )
    assert second.status_code == 200
    assert [item["world_id"] for item in second.json()["items"]] == ["home-old"]
    assert second.json()["next_cursor"] is None
    assert writes == []

    invalid = client.get(
        "/api/v1/worlds/mine?surface=device_home&cursor=not-a-valid-cursor"
    )
    assert invalid.status_code == 422
    assert invalid.json() == {"detail": "invalid_world_surface_cursor"}


def test_world_app_read_is_exact_owner_scoped_and_launchable() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)

    response = client.get("/api/v1/worlds/mine/home-new")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "local-world-app-v1"
    assert payload["surface"] == "world_app"
    assert payload["world"]["world_id"] == "home-new"
    assert payload["world"]["launchable"] is True
    assert "home-old" not in response.text
    assert "foreign" not in response.text


def test_world_app_read_fails_closed_for_foreign_and_blocked_worlds() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)

    for world_id in ("foreign", "private", "draft", "archived", "missing"):
        response = client.get(f"/api/v1/worlds/mine/{world_id}")
        assert response.status_code == 404
        assert response.json() == {"detail": "world_app_unavailable"}
        assert world_id not in response.text


def test_world_app_read_requires_owner_and_active_membership() -> None:
    client, engine, principal = _fixture()
    owner, outsider = _seed(engine, principal)

    principal["user"] = None
    assert client.get("/api/v1/worlds/mine/home-new").status_code == 401

    principal["user"] = outsider
    forbidden = client.get("/api/v1/worlds/mine/home-new")
    assert forbidden.status_code == 403
    assert forbidden.json() == {"detail": "local_owner_required"}

    principal["user"] = owner
    with Session(engine) as db:
        membership = db.get(models.WorldMembership, "membership-home-new")
        assert membership is not None
        membership.status = "left"
        db.commit()
    unavailable = client.get("/api/v1/worlds/mine/home-new")
    assert unavailable.status_code == 404
    assert unavailable.json() == {"detail": "world_app_unavailable"}


def test_world_app_read_has_zero_writes_and_zero_provider_calls(
    monkeypatch,
) -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)
    writes: list[str] = []
    provider_calls: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _capture_writes(_conn, _cursor, statement, _parameters, _context, _many):
        operation = statement.lstrip().split(None, 1)[0].upper()
        if operation in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(operation)

    def _provider_forbidden(*_args, **_kwargs):
        provider_calls.append("provider")
        raise AssertionError("World App read must not call a provider")

    monkeypatch.setattr(provider_registry, "get_provider_adapter", _provider_forbidden)
    monkeypatch.setattr(provider_registry, "get_embedding_adapter", _provider_forbidden)

    response = client.get("/api/v1/worlds/mine/home-new")

    assert response.status_code == 200
    assert writes == []
    assert provider_calls == []


def test_internal_world_lookup_preserves_internal_read_contract() -> None:
    from app.domains.device_home.service import get_device_home_world

    client, engine, principal = _fixture()
    owner, outsider = _seed(engine, principal)
    with Session(engine) as db:
        launchable = get_device_home_world(db, owner_user_id=owner.id, world_id="home-new")
        assert launchable is not None and launchable.launchable
        private = get_device_home_world(db, owner_user_id=owner.id, world_id="private")
        assert private is not None and private.launch_block_reason == "world_private"
        assert get_device_home_world(db, owner_user_id=owner.id, world_id="missing") is None
        foreign = get_device_home_world(db, owner_user_id=outsider.id, world_id="foreign")
        assert foreign is not None and foreign.world_id == "foreign"
    assert client.get("/api/v1/worlds/mine/private").status_code == 404
    principal["user"] = outsider
    assert client.get("/api/v1/worlds/mine/foreign").json() == {"detail": "local_owner_required"}


def test_internal_world_lookup_participates_in_caller_transaction(tmp_path, monkeypatch) -> None:
    from app.domains.device_home.service import get_device_home_world

    # A file DB gives a separate Session a separate connection: a replacement
    # Session cannot accidentally see the caller's uncommitted writes.
    engine = create_engine(f"sqlite:///{(tmp_path / 'caller.sqlite3').as_posix()}")
    Base.metadata.create_all(engine)
    now = datetime(2026, 9, 5, tzinfo=UTC)
    with Session(engine) as setup:
        setup.add(_user("transaction-owner"))
        setup.commit()
    with Session(engine) as db:
        db.add(_world("pending", owner_user_id="transaction-owner", status_value="draft", updated_at=now))
        db.flush()
        db.add(_membership("pending-member", world_id="pending", user_id="transaction-owner"))
        db.flush()
        writes: list[str] = []
        boundaries: list[str] = []

        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            operation = statement.lstrip().split(None, 1)[0].upper()
            if operation in {"INSERT", "UPDATE", "DELETE"}:
                writes.append(operation)

        def forbidden(*_args, **_kwargs):
            raise AssertionError("Internal projection must not call a provider")

        monkeypatch.setattr(provider_registry, "get_provider_adapter", forbidden)
        monkeypatch.setattr(provider_registry, "get_embedding_adapter", forbidden)
        event.listen(engine, "before_cursor_execute", capture)
        event.listen(db, "after_commit", lambda _db: boundaries.append("commit"))
        event.listen(db, "after_rollback", lambda _db: boundaries.append("rollback"))
        transaction = db.get_transaction()
        result = get_device_home_world(db, owner_user_id="transaction-owner", world_id="pending")
        assert result is not None and result.world_id == "pending"
        assert result.launch_block_reason == "world_not_published"
        assert db.get_transaction() is transaction and transaction.is_active
        assert boundaries == [] and writes == []
        event.remove(engine, "before_cursor_execute", capture)
        db.rollback()
    with Session(engine) as check:
        assert check.get(models.World, "pending") is None
        assert check.get(models.WorldMembership, "pending-member") is None
    engine.dispose()


def test_membership_scope_and_equal_timestamp_cursor_are_preserved() -> None:
    client, engine, principal = _fixture()
    owner, outsider = _seed(engine, principal)
    now = datetime(2026, 9, 5, tzinfo=UTC)
    with Session(engine) as db:
        db.add_all([_world(name, owner_user_id=outsider.id, updated_at=now) for name in ("tie-a", "tie-b")])
        db.flush()
        db.add_all([
            _membership("tie-a-member", world_id="tie-a", user_id=owner.id, role="editor"),
            _membership("tie-b-member", world_id="tie-b", user_id=owner.id, role="member"),
        ])
        db.commit()
    first = client.get("/api/v1/worlds/mine", params={"surface": "device_home", "limit": 1}).json()
    assert [item["world_id"] for item in first["items"]] == ["tie-a"]
    second = client.get("/api/v1/worlds/mine", params={"surface": "device_home", "limit": 1, "cursor": first["next_cursor"]}).json()
    assert [item["world_id"] for item in second["items"]] == ["tie-b"]
    studio = client.get("/api/v1/worlds/mine?surface=creator_studio").json()
    ids = {item["world_id"] for item in studio["items"]}
    assert "tie-a" in ids and "tie-b" not in ids
    assert client.get("/api/v1/worlds/mine/tie-b").status_code == 200


def test_stale_readiness_remains_hidden_from_home_and_explained_in_studio() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)
    with Session(engine) as db:
        db.get(models.World, "home-new").readiness_status = "stale"
        db.commit()
    home = client.get("/api/v1/worlds/mine?surface=device_home").json()
    assert "home-new" not in {item["world_id"] for item in home["items"]}
    studio = client.get("/api/v1/worlds/mine?surface=creator_studio").json()
    world = next(item for item in studio["items"] if item["world_id"] == "home-new")
    assert not world["launchable"] and world["launch_block_reason"] == "world_not_ready"
    assert client.get("/api/v1/worlds/mine/home-new").json() == {"detail": "world_app_unavailable"}


def test_surface_http_bounds_and_local_frontend_origin_remain_enforced() -> None:
    from app.core.browser_session import LOCAL_FRONTEND_ORIGIN_HEADER

    client, engine, principal = _fixture()
    _seed(engine, principal)
    for value in (0, 51):
        assert client.get("/api/v1/worlds/mine", params={"surface": "device_home", "limit": value}).status_code == 422
    too_long = client.get("/api/v1/worlds/mine", params={"surface": "device_home", "cursor": "x" * 513})
    assert too_long.status_code == 422 and isinstance(too_long.json()["detail"], list)
    for path in ("/api/v1/worlds/mine?surface=device_home", "/api/v1/worlds/mine/home-new"):
        assert client.get(path, headers={"host": "outside.example"}).status_code == 403
        assert client.get(path, headers={LOCAL_FRONTEND_ORIGIN_HEADER: "https://outside.example"}).status_code == 403
        duplicate = [(LOCAL_FRONTEND_ORIGIN_HEADER, "http://127.0.0.1:3000")] * 2
        assert client.get(path, headers=duplicate).status_code == 403
