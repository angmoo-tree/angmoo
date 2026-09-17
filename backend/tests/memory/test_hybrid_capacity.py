"""Real 100,000-item admission boundary; no lowered test quota."""
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, select, func

from app.domains.memory.models.items import MemoryItem, MemoryCandidate, MemoryScopeSettingModel
from app.domains.memory.models.embedding import MemoryVectorEligibility
from app.domains.memory.repository.capacity import stored_count
from memory.test_p8_l_o_memory_consolidation import memory_session
from memory.test_p8_l_r_memory_batch_runtime import batch_stack


def test_two_independent_sqlite_writers_cannot_both_take_last_slot(memory_session, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    import sqlite3
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.domains.memory.exceptions import MemoryCapacityReached
    from app.domains.memory.service.items import MemoryWriteLifecycleService
    from app.runtime.memory.composition import memory_repository

    scope, _, _, _, service = batch_stack(memory_session)
    seed_holdings(memory_session, scope, 99_999)
    candidates = list(memory_session.scalars(select(MemoryCandidate)))
    candidate_versions = [(row.id, row.version) for row in candidates]
    setting = memory_session.scalar(select(MemoryScopeSettingModel))
    setting_version = setting.version
    memory_session.commit()
    database = tmp_path / "concurrent.sqlite3"
    with sqlite3.connect(database) as target:
        memory_session.connection().connection.driver_connection.backup(target)
    engine = create_engine(f"sqlite:///{database.as_posix()}", connect_args={"timeout": 20})
    gate = Barrier(2)

    def accept(candidate):
        with Session(engine) as session:
            writer = MemoryWriteLifecycleService(memory_repository(session), service.reader)
            gate.wait(timeout=10)
            try:
                result = writer.accept_candidate(scope=scope, candidate_id=candidate[0],
                    expected_candidate_version=candidate[1], expected_scope_version=setting_version,
                    enqueue_maintenance=False, now=datetime.now(UTC))
                session.commit()
                return "accepted" if result.item is not None else "unexpected"
            except MemoryCapacityReached:
                session.rollback()
                return "capacity"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(accept, candidate_versions)) == ["accepted", "capacity"]
        with Session(engine) as check:
            assert stored_count(check, scope, now=datetime.now(UTC)) == 100_000
            assert sorted(check.scalars(select(MemoryCandidate.status))) == ["accepted", "pending"]
            assert check.scalar(select(func.count()).select_from(MemoryVectorEligibility)) == 1
    finally:
        engine.dispose()


def seed_holdings(session, scope, count):
    values = dict(owner_id=scope.owner_id, world_id=scope.world_id,
                  subject_world_character_id=scope.subject_world_character_id,
                  memory_kind="AUTOBIOGRAPHICAL_EVENT", summary="Existing retained memory",
                  status="active", confidence=1.0, salience=0.5, version=1,
                  valid_from=datetime.now(UTC)-timedelta(days=1))
    for offset in range(0, count, 5000):
        session.execute(insert(MemoryItem), [dict(values, id=f"held-{i}")
                        for i in range(offset, min(offset+5000, count))])
    session.commit()


def test_99999_partial_acceptance_preserves_pending_and_suppresses_repeat_ai(memory_session):
    scope, repo, job, selector, service = batch_stack(memory_session)
    seed_holdings(memory_session, scope, 99_999)
    assert asyncio.run(service.run_next(lease_token="boundary")) == "memory_capacity_reached"
    assert stored_count(memory_session, scope, now=datetime.now(UTC)) == 100_000
    assert selector.calls == 1
    statuses = list(memory_session.scalars(select(MemoryCandidate.status)))
    assert sorted(statuses) == ["accepted", "pending"]
    # Pre-existing rows remain ineligible; only the new accepted item registers.
    assert memory_session.scalar(select(func.count()).select_from(MemoryVectorEligibility)) == 1
    settings = repo.settings(scope)
    assert settings.capacity_blocked and not settings.can_run and not settings.retryable
    assert settings.run_saved_count == 1 and settings.run_pending_count == 1
    memory_session.rollback()
    for index in range(3):
        assert asyncio.run(service.run_next(lease_token=f"blocked-{index}")) == "memory_batch_queue_empty"
    assert selector.calls == 1
    # OFF does not change the count. Expiry actually frees capacity.
    setting = memory_session.scalar(select(MemoryScopeSettingModel))
    setting.enabled = False
    memory_session.commit()
    assert repo.settings(scope).stored_count == 100_000
    setting.enabled = True
    item = memory_session.get(MemoryItem, "held-0")
    item.valid_until = datetime.now(UTC)-timedelta(hours=1)
    memory_session.commit()
    assert asyncio.run(service.run_next(lease_token="capacity-freed")) == "memory_selection_completed"
    assert selector.calls == 2
    assert stored_count(memory_session, scope, now=datetime.now(UTC)) == 100_000
    assert memory_session.scalar(select(func.count()).select_from(MemoryVectorEligibility)) == 2
