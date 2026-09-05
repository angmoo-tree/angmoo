"""Failure and compatibility contracts at the moved World boundaries."""
from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app import models as registered_models
from app.config import settings
from app.core.db import Base
from app.domains.worlds import contracts, models, schemas, service
from app.domains.worlds.service import creator, definition, reserved_roles


@pytest.fixture
def world_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = registered_models.User(
            id="world-transition-owner",
            email="world-transition@example.test",
            display_name="world owner",
            display_name_normalized="world owner",
            privacy_policy_version="test",
            terms_version="test",
            profile_setup_completed=True,
        )
        db.add(owner)
        db.commit()
        created = service.create_world(
            db, user=owner,
            data=schemas.WorldDraftCreate(name="Transition World", idempotency_key="transition-world"),
        )
        yield db, owner, db.get(models.World, created.world.id)
    engine.dispose()


def test_frozen_migration_imports_resolve_to_identical_models_and_functions() -> None:
    from app.domains.worlds.domain import reserved_roles as old_contracts
    from app.domains.worlds.infrastructure import definition_repository as old_definition
    from app.domains.worlds.infrastructure import sqlalchemy_models as old_models
    from app.domains.worlds.infrastructure import sqlalchemy_reserved_roles as old_roles

    assert old_models.World is models.World is registered_models.World
    assert old_models.WorldMembership is models.WorldMembership
    assert old_models.WorldRole is models.WorldRole
    assert old_models.World.metadata is Base.metadata
    assert Base.metadata.tables["worlds"] is models.World.__table__
    assert old_definition.refresh_world_contract is definition.refresh_world_contract
    assert old_roles.ensure_no_specific_role is reserved_roles.ensure_no_specific_role
    assert old_roles.ReservedWorldRoleConflictError is service.ReservedWorldRoleConflictError
    assert old_contracts.is_canonical_no_specific_role is contracts.is_canonical_no_specific_role
    assert not hasattr(service, "World")
    assert not hasattr(service, "WorldMembership")


def test_banner_commit_failure_removes_new_file_and_preserves_previous_banner(
    world_session, tmp_path, monkeypatch,
) -> None:
    db, owner, world = world_session
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    previous_url = f"/media/worlds/{world.id}/banner-previous.webp"
    previous_file = tmp_path / previous_url.removeprefix("/media/")
    previous_file.parent.mkdir(parents=True)
    previous_file.write_bytes(b"previous verified image")
    world.banner_media_id = previous_url
    world.banner_alt_text = "previous banner"
    db.commit()
    original_version = world.row_version
    buffer = BytesIO()
    Image.new("RGB", (48, 24), (30, 70, 120)).save(buffer, format="PNG")

    def fail_commit():
        raise RuntimeError("injected database commit failure")

    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="injected database commit failure"):
        service.upload_world_banner(
            db, world_id=world.id, user=owner,
            data=schemas.WorldBannerUpload(
                row_version=original_version, content_type="image/png",
                data_base64=base64.b64encode(buffer.getvalue()).decode("ascii"),
                alt_text="replacement banner",
            ),
        )
    assert list(previous_file.parent.iterdir()) == [previous_file]
    assert previous_file.read_bytes() == b"previous verified image"
    db.rollback()
    assert world.banner_media_id == previous_url
    assert world.banner_alt_text == "previous banner"
    assert world.row_version == original_version


@pytest.mark.parametrize("fail_schedule", [False, True])
def test_timezone_update_and_rescheduling_share_one_transaction(
    world_session, monkeypatch, fail_schedule,
) -> None:
    db, owner, world = world_session
    world_id, original_timezone, original_version = world.id, world.timezone, world.row_version
    callbacks, commits = [], []
    event.listen(db, "after_commit", lambda session: commits.append(session))

    def reschedule(session, *, world_id, timezone_name):
        callbacks.append((session, world_id, timezone_name))
        assert session is db
        assert session.in_transaction()
        assert session.get(models.World, world_id).timezone == "America/New_York"
        # A cooperating write must commit/roll back with the World mutation.
        world.banner_alt_text = "schedule applied"
        session.flush()
        if fail_schedule:
            raise RuntimeError("injected schedule failure")
        return 1

    monkeypatch.setattr(creator, "reschedule_world_autonomy_slots", reschedule)
    arguments = dict(db=db, world_id=world_id, user=owner,
                     data=schemas.WorldUpdate(row_version=original_version, timezone="America/New_York"))
    if fail_schedule:
        with pytest.raises(RuntimeError, match="injected schedule failure"):
            service.update_world(**arguments)
        assert commits == []
        db.rollback()
        assert world.timezone == original_timezone
        assert world.row_version == original_version
        assert world.banner_alt_text == ""
    else:
        updated = service.update_world(**arguments)
        assert commits == [db]
        assert updated.world.timezone == "America/New_York"
        assert world.row_version == original_version + 1
        db.expire_all()
        assert db.get(models.World, world_id).banner_alt_text == "schedule applied"
    assert callbacks == [(db, world_id, "America/New_York")]


def test_seed_flushes_without_owning_the_callers_commit(world_session) -> None:
    db, owner, _ = world_session
    commits = []
    event.listen(db, "after_commit", lambda session: commits.append(session))
    seeded = service.seed_world(
        db, user=owner,
        data=schemas.WorldDraftCreate(name="Imported pending World", idempotency_key="caller-owned-seed"),
        status="published", membership_reason="world_package_import",
    )
    identifier = seeded.world.id
    assert commits == []
    assert seeded.membership.world_id == identifier
    assert db.get(models.World, identifier) is seeded.world
    db.rollback()
    assert db.get(models.World, identifier) is None
    assert db.scalar(select(models.WorldMembership).where(models.WorldMembership.world_id == identifier)) is None


def test_split_router_preserves_all_fourteen_world_and_resident_endpoints() -> None:
    from app.api.v1.routes.worlds import router as resident_router
    from app.domains.worlds.router import router as creator_router
    from app.api.v1 import main, public

    resident = {(route.path, method) for route in resident_router.routes for method in route.methods}
    creator_routes = {(route.path, method) for route in creator_router.routes for method in route.methods}
    assert len(resident) == 4
    assert len(creator_routes) == 10
    assert resident.isdisjoint(creator_routes)
    for routers in (main.PUBLIC_ROUTERS, public.PUBLIC_ROUTERS):
        assert routers.count(resident_router) == 1
        assert routers.count(creator_router) == 1
        assert routers.index(creator_router) == routers.index(resident_router) + 1


def test_resident_leave_still_translates_errors_from_the_world_service(world_session, monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.v1.routes import worlds as resident_routes
    from app.api.identity_dependencies import get_current_user
    from app.core.db import get_db

    db, owner, world = world_session
    world_id = world.id
    owner_id = owner.id
    application = FastAPI()
    application.include_router(resident_routes.router, prefix="/api/v1")
    application.dependency_overrides[get_current_user] = lambda: owner
    application.dependency_overrides[get_db] = lambda: db
    invoked = []

    def absent_world(_lifecycle, **arguments):
        invoked.append(arguments)
        raise service.WorldNotFoundError(arguments["world_id"])

    from app.domains.world_characters.service.lifecycle import WorldCharacterLifecycleService

    monkeypatch.setattr(WorldCharacterLifecycleService, "leave", absent_world)
    with TestClient(application, base_url="http://127.0.0.1:3000") as client:
        response = client.post(
            f"/api/v1/worlds/{world_id}/characters/resident-a/leave",
            headers={"Origin": "http://127.0.0.1:3000"},
            json={"world_character_id": "world-resident-a", "version": 1,
                  "confirmation_name": "resident", "idempotency_key": "leave-world-missing"},
        )
    assert response.status_code == 404
    assert response.json() == {"detail": "world_not_found"}
    assert invoked[0]["world_id"] == world_id
    assert invoked[0]["current_user_id"] == owner_id
