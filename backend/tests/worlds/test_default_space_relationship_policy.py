"""Default SNS policy enrollment crosses real persistence and registration."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from sqlalchemy import delete, event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from test_local_creator_v2 import db
from app.domains.identity.models import User
from app.domains.relationships.models.personalization import RelationshipPolicy
from app.domains.worlds.models import OwnerDefaultWorld, World, WorldMembership
from app.domains.worlds.service.default_space import ensure_default_space
from app.runtime.relationships.policy_activation import (
    activate_relationship_policies, initialize_default_space_policy,
)


def ensure(session, owner_id, initialize=initialize_default_space_policy):
    return ensure_default_space(session, owner_id=owner_id, initialize=initialize)


def test_new_policy_is_committed_and_repeat_and_startup_preserve_it(db):
    session, owner = db
    world = ensure(session, owner.id)
    world_id = world.id
    policy = session.get(RelationshipPolicy, world_id)
    assert policy.mode == "interpreted" and policy.version == 1
    initial = policy.activated_at
    with Session(session.bind) as reader:
        assert reader.get(RelationshipPolicy, world_id).activated_at == initial
        assert reader.get(OwnerDefaultWorld, owner.id).world_id == world_id
    statements = []
    def record(_conn, _cursor, statement, *_):
        statements.append(statement.lstrip().split()[0].upper())
    event.listen(session.bind, "before_cursor_execute", record)
    try:
        assert ensure(session, owner.id).id == world_id
    finally:
        event.remove(session.bind, "before_cursor_execute", record)
    assert not {"INSERT", "UPDATE", "DELETE"}.intersection(statements)
    session.rollback()
    activate_relationship_policies(sessionmaker(session.bind))
    assert session.get(RelationshipPolicy, world_id).activated_at == initial


@pytest.mark.parametrize("mode", ["legacy", "interpreted"])
def test_existing_policy_keeps_version_mode_and_activation(db, mode):
    session, owner = db
    world = ensure(session, owner.id)
    policy = session.get(RelationshipPolicy, world.id)
    saved_time = datetime(2020, 1, 2, tzinfo=UTC)
    policy.mode, policy.version, policy.activated_at = mode, 7, saved_time
    session.commit()
    ensure(session, owner.id)
    assert (policy.mode, policy.version, policy.activated_at.replace(tzinfo=UTC)) == (mode, 7, saved_time)


@pytest.mark.parametrize("repair", [False, True])
def test_independent_sessions_converge_on_one_world_and_policy(db, repair):
    session, owner = db
    owner_id = owner.id
    if repair:
        world = ensure(session, owner_id)
        session.execute(delete(RelationshipPolicy).where(RelationshipPolicy.world_id == world.id))
    session.commit()
    barrier = Barrier(2)
    def submit(_):
        with Session(session.bind) as worker:
            barrier.wait(timeout=10)
            world = ensure(worker, owner_id)
            policy = worker.get(RelationshipPolicy, world.id)
            return world.id, policy.activated_at
    with ThreadPoolExecutor(2) as pool:
        first, second = pool.map(submit, range(2))
    assert first == second
    assert session.scalar(select(func.count()).select_from(World)) == 1
    assert session.scalar(select(func.count()).select_from(RelationshipPolicy)) == 1


@pytest.mark.parametrize("repair", [False, True])
@pytest.mark.parametrize("failure", ["callback", "commit", "policy_constraint"])
def test_initializer_and_final_save_failures_are_atomic(db, monkeypatch, repair, failure):
    session, owner = db
    owner_id = owner.id
    original_world = None
    if repair:
        original_world = ensure(session, owner_id).id
        session.execute(delete(RelationshipPolicy))
        session.commit()
    def initialize(db, world):
        initialize_default_space_policy(db, world)
        if failure == "callback":
            raise RuntimeError("injected initializer failure")
        if failure == "policy_constraint":
            db.get(RelationshipPolicy, world.id).mode = "invalid"
            db.flush()
        return True
    if failure == "commit":
        monkeypatch.setattr(session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("injected commit failure")))
    with pytest.raises(IntegrityError if failure == "policy_constraint" else RuntimeError):
        ensure(session, owner_id, initialize)
    with Session(session.bind) as reader:
        assert reader.scalar(select(func.count()).select_from(RelationshipPolicy)) == 0
        assert reader.scalar(select(func.count()).select_from(World)) == int(repair)
        binding = reader.get(OwnerDefaultWorld, owner_id)
        assert (binding.world_id if binding else None) == original_world


@pytest.mark.parametrize("write", ["pending", "flushed", "core"])
def test_caller_writes_are_neither_committed_nor_discarded(db, write):
    session, owner = db
    owner_id = owner.id
    if write == "core":
        session.execute(update(User).where(User.id == owner_id).values(display_name="Uncommitted"))
    else:
        owner.display_name = "Uncommitted"
        if write == "flushed":
            session.flush()
    with pytest.raises(RuntimeError, match="default_space_requires_clean_unit_of_work"):
        ensure(session, owner_id)
    assert session.scalar(select(User.display_name).where(User.id == owner_id)) == "Uncommitted"
    with Session(session.bind) as reader:
        assert reader.get(User, owner_id).display_name == "Owner"
        assert reader.scalar(select(func.count()).select_from(World)) == 0
    session.rollback()


def test_valid_legacy_adoption_and_post_lock_recheck_both_enroll(db, monkeypatch):
    from app.domains.worlds.service import default_space
    from app.domains.worlds.service.foundation import ANGMOO_GLOBAL_WORLD_ID, ensure_global_world
    session, owner = db
    world = ensure_global_world(session, owner_user_id=owner.id)
    session.add(WorldMembership(id="legacy-owner", world_id=world.id, user_id=owner.id,
        role="owner", status="active", joined_at=datetime.now(UTC)))
    session.commit()
    assert world.readiness_status == "publish_ready"
    assert session.get(RelationshipPolicy, world.id) is None
    assert ensure(session, owner.id).id == ANGMOO_GLOBAL_WORLD_ID
    session.execute(delete(RelationshipPolicy))
    session.commit()
    original = default_space._existing_space
    calls = 0
    def race(db, owner_id):
        nonlocal calls
        calls += 1
        return None if calls == 1 else original(db, owner_id)
    monkeypatch.setattr(default_space, "_existing_space", race)
    assert ensure(session, owner.id).id == world.id
    assert session.get(RelationshipPolicy, world.id) is not None


def test_binding_primary_key_race_reloads_and_initializes_real_winner(db, monkeypatch):
    from app.domains.worlds.service import default_space
    session, owner = db
    winner_id = ensure(session, owner.id).id
    session.get(World, winner_id).create_idempotency_key = "preexisting-default"
    session.execute(delete(RelationshipPolicy))
    session.commit()
    original = default_space._existing_space
    calls = 0
    def competing_read(db, owner_id):
        nonlocal calls
        calls += 1
        return None if calls <= 2 else original(db, owner_id)
    monkeypatch.setattr(default_space, "_existing_space", competing_read)
    assert ensure(session, owner.id).id == winner_id
    assert session.get(RelationshipPolicy, winner_id) is not None
    assert session.scalar(select(func.count()).select_from(World)) == 1


def test_owner_environment_archive_and_broken_membership_fail_without_repair(db):
    from app.domains.identity.models_environment import LocalEnvironment
    from app.domains.worlds.exceptions import WorldServiceError
    session, owner = db
    owner_id = owner.id
    with pytest.raises(WorldServiceError, match="local_owner_required"):
        ensure(session, "other-owner")
    environment = session.get(LocalEnvironment, owner_id)
    confirmed = environment.confirmed_at
    environment.confirmed_at = None
    session.commit()
    with pytest.raises(WorldServiceError, match="environment_not_ready"):
        ensure(session, owner_id)
    assert session.scalar(select(func.count()).select_from(World)) == 0
    environment.confirmed_at = confirmed
    session.commit()
    world = ensure(session, owner_id)
    session.execute(delete(RelationshipPolicy))
    membership = session.scalar(select(WorldMembership).where(WorldMembership.world_id == world.id))
    membership.status = "left"
    session.commit()
    with pytest.raises(WorldServiceError, match="default_space_recovery_required"):
        ensure(session, owner_id)
    assert session.get(RelationshipPolicy, world.id) is None
    membership.status = "active"
    world.status = "archived"
    session.commit()
    with pytest.raises(WorldServiceError, match="default_space_recovery_required"):
        ensure(session, owner_id)
    assert session.get(RelationshipPolicy, world.id) is None


def test_http_ensure_uses_real_initializer_and_get_does_not_repair(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.domains.worlds.router import router
    from app.database import get_db
    from app.api.identity_dependencies import get_current_user, get_optional_current_user
    session, owner = db
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_optional_current_user] = lambda: owner
    with TestClient(app) as client:
        response = client.post("/api/v1/worlds/default-space/ensure")
        assert response.status_code == 200, response.text
        world_id = response.json()["id"]
        assert session.get(RelationshipPolicy, world_id) is not None
        session.execute(delete(RelationshipPolicy))
        session.commit()
        assert client.get(f"/api/v1/worlds/{world_id}").status_code == 200
        assert session.get(RelationshipPolicy, world_id) is None
        assert client.post("/api/v1/worlds/default-space/ensure").status_code == 200
        assert session.get(RelationshipPolicy, world_id) is not None


@pytest.mark.parametrize("kind", ["direct", "card"])
def test_keyless_registration_repairs_old_draft_policy_with_preparation_off(db, monkeypatch, kind):
    from dataclasses import replace
    from app.config import settings
    from app.domains.characters import schemas
    from app.domains.characters.service import drafts, card_import
    from app.runtime.characters.creator import build_creator_workflows
    from test_creator_card_registration import card_bytes
    session, owner = db
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", False)
    async def forbidden(**kwargs):
        pytest.fail("policy enrollment must not call AI")
    workflows = replace(build_creator_workflows(), run_llm=forbidden)
    draft = asyncio.run(drafts.create_draft(session, owner, schemas.AgentCreationDraftCreate(), workflows=workflows))
    assert session.get(RelationshipPolicy, draft.target_world_id) is not None
    if kind == "card":
        draft = card_import.import_card(session, owner, draft.id, revision=draft.revision,
            content=card_bytes(), workflows=workflows)["draft"]
    draft = drafts.update_draft(session, owner, draft.id, schemas.AgentCreationDraftUpdate(
        revision=draft.revision, name="Test", worldview="A quiet fictional observer."), workflows=workflows)
    session.execute(delete(RelationshipPolicy))
    session.commit()
    result = drafts.complete_draft(session, owner, draft.id,
        schemas.AgentCreationDraftComplete(revision=draft.revision), workflows=workflows)
    assert session.get(RelationshipPolicy, draft.target_world_id) is not None
    assert result.credential is None and result.settings.auto_enabled is False
