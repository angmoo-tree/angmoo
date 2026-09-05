"""Deterministic SQLite visibility window between slug selection and validation."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import get_ident

import pytest
from sqlalchemy import event

from app import models
from app.domains.world_packages.policies.collision import (
    WorldPackageCollisionPlan, WorldPackageDuplicateState,
)
from app.domains.world_packages.exceptions import WorldPackageContractError
from app.runtime.world_packages.seed import (
    SqlAlchemyWorldPackageDestinationSeed,
)
from app.domains.world_packages.service.registry import (
    SqlAlchemyWorldPackageRegistry,
)
from app.runtime.world_packages.seed_uow import (
    SqlAlchemyWorldPackageSeedUnitOfWork,
)
from app.domains.worlds.service import creator
from app.domains.worlds.service import WorldDefinitionValidationError
from test_uow_registry import _count, _request, _session_factory


@pytest.mark.parametrize("digest_conflict", [False, True])
def test_completed_import_after_slug_selection_is_resolved_once(
    tmp_path, monkeypatch, digest_conflict,
):
    engine, factory = _session_factory(tmp_path)
    request = _request()
    request = replace(request, world=request.world.model_copy(update={"name":"Package Replay Race"}))
    winner_request = replace(request, content_digest="b" * 64) if digest_conflict else request
    original_slug = creator._available_slug
    original_find = SqlAlchemyWorldPackageRegistry.find_import
    main_thread = get_ident()
    observed, order, winner = [], [], []
    triggered = False

    def find_import(registry, **scope):
        record = original_find(registry, **scope)
        if get_ident() == main_thread:
            observed.append((registry._db, scope, record))
            order.append("replay" if record is not None else "miss")
        return record

    def commit_between_slug_reads(db, **arguments):
        nonlocal triggered
        slug = original_slug(db, **arguments)
        if not triggered:
            triggered = True
            event.listen(db, "after_rollback", lambda *_: order.append("rollback"))
            with ThreadPoolExecutor(max_workers=1) as executor:
                winner.append(executor.submit(
                    SqlAlchemyWorldPackageSeedUnitOfWork(factory).execute, winner_request,
                ).result(timeout=10))
            order.append("winner_committed")
        return slug

    monkeypatch.setattr(SqlAlchemyWorldPackageRegistry, "find_import", find_import)
    monkeypatch.setattr(creator, "_available_slug", commit_between_slug_reads)
    uow = SqlAlchemyWorldPackageSeedUnitOfWork(factory, max_attempts=1)
    if digest_conflict:
        with pytest.raises(WorldPackageContractError, match="world_package_commit_conflict"):
            uow.execute(request)
    else:
        replay = uow.execute(request)
        assert replay.replayed is True
        assert replay.import_id == winner[0].import_id
        assert replay.imported_world_id == winner[0].imported_world_id
        assert replay.id_mappings == winner[0].id_mappings
    assert order == ["miss", "winner_committed", "rollback", "replay"]
    assert len(observed) == 2 and observed[0][0] is not observed[1][0]
    assert observed[0][2] is None and observed[1][2].import_id == winner[0].import_id
    assert observed[1][1] == {"local_owner_id":request.local_owner_id,
                              "idempotency_key":request.idempotency_key}
    with factory() as db:
        for model in (models.World, models.Character, models.WorldCharacter, models.WorldPackageImport):
            assert _count(db, model) == 1
    engine.dispose()


@pytest.mark.parametrize("different_scope", ["owner", "key"])
def test_slug_conflict_without_same_scope_registry_is_not_retried(
    tmp_path, monkeypatch, different_scope,
):
    engine, factory = _session_factory(tmp_path)
    request = _request()
    first = SqlAlchemyWorldPackageSeedUnitOfWork(factory).execute(request)
    with factory() as db:
        slug = db.get(models.World, first.imported_world_id).slug
        if different_scope == "owner":
            db.add(models.User(id="another-owner",email="another@example.test",
                display_name="Another", display_name_normalized="another",
                privacy_policy_version="test",terms_version="test",profile_setup_completed=True))
            db.commit()
    plan = WorldPackageCollisionPlan(slug, (), WorldPackageDuplicateState.NEW_PACKAGE, True)
    request = replace(request, collision_plan=plan, **(
        {"local_owner_id":"another-owner"} if different_scope == "owner"
        else {"idempotency_key":"another-import"}
    ))
    attempts, sessions = [], []
    original_seed = SqlAlchemyWorldPackageDestinationSeed.seed

    def seed(adapter, request):
        attempts.append(request)
        return original_seed(adapter, request)

    def tracked_factory():
        session = factory()
        sessions.append(session)
        return session

    monkeypatch.setattr(SqlAlchemyWorldPackageDestinationSeed, "seed", seed)
    with pytest.raises(WorldDefinitionValidationError, match="^world_slug_unavailable$"):
        SqlAlchemyWorldPackageSeedUnitOfWork(tracked_factory, max_attempts=4).execute(request)
    assert len(attempts) == 1
    assert len(sessions) == 2 and sessions[0] is not sessions[1]
    with factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.WorldPackageImport) == 1
    engine.dispose()


@pytest.mark.parametrize("reason", ["reserved_world_role", "world_slug_unavailable_extra"])
def test_other_validation_does_not_observe_or_replay_even_with_completed_import(
    tmp_path, monkeypatch, reason,
):
    engine, factory = _session_factory(tmp_path)
    request = _request()
    SqlAlchemyWorldPackageSeedUnitOfWork(factory).execute(request)
    error = WorldDefinitionValidationError(reason)
    sessions = []

    def reject(_adapter, _request):
        raise error

    def tracked_factory():
        session = factory()
        sessions.append(session)
        return session

    monkeypatch.setattr(SqlAlchemyWorldPackageDestinationSeed, "seed", reject)
    with pytest.raises(WorldDefinitionValidationError) as caught:
        SqlAlchemyWorldPackageSeedUnitOfWork(tracked_factory, max_attempts=4).execute(request)
    assert caught.value is error
    assert len(sessions) == 1
    with factory() as db:
        assert _count(db, models.World) == 1
        assert _count(db, models.WorldPackageImport) == 1
    engine.dispose()
