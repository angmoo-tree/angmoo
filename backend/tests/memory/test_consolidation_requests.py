import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from app.database import create_session_factory
from app.domains.memory.contracts.items import as_utc
from app.domains.memory.exceptions import MemoryConflictError
from app.domains.memory.models.batch import MemoryBatchSetting, MemorySourceDelivery, MemoryBatchRun
from app.domains.memory.models.consolidation_request import MemoryConsolidationRequest
from app.domains.memory.repository.consolidation_requests import manual, progress
from app.domains.memory.schemas.batch import MemoryBatchStart
from app.runtime.memory.batch_runtime import MemoryBatchRuntime
from app.runtime.memory.composition import memory_batch_repository
from app.runtime.memory.source_delivery import install_memory_delivery, uninstall_memory_delivery
from memory.test_p8_l_r_memory_batch_safety import memory_session, _stack, _save, _post
from memory.test_episode_selection_service import Provider


def start(db, repo, scope, setting, *, key=None, now=None):
    saved = repo.settings(scope)
    data = MemoryBatchStart(idempotency_key=key or uuid4().hex, expected_version=saved.version,
        expected_profile_version=saved.profile_version, expected_scope_version=setting.version)
    row, outcome = manual(db, repository=repo, scope=scope, data=data, now=now or datetime.now(UTC))
    db.commit()
    return row, outcome, data


def test_same_day_changed_schedule_and_unchanged_overdue_deadline(memory_session):
    db = memory_session
    scope, setting, *_ = _stack(db)
    repo = memory_batch_repository(db)
    now = datetime(2026, 9, 17, 4, 10, tzinfo=UTC)  # Seoul 13:10
    _save(repo, scope, now=now, schedule_enabled=True, local_time="14:00")
    config = db.get(MemoryBatchSetting, setting.id)
    config.last_consumed_date = "2026-09-17"
    _save(repo, scope, now=now, schedule_enabled=True, local_time="15:00")
    assert as_utc(config.next_due_at) == datetime(2026, 9, 17, 6, tzinfo=UTC)
    deadline = now - timedelta(minutes=1)
    config.next_due_at = deadline
    _save(repo, scope, now=now, schedule_enabled=True, local_time="15:00")
    assert as_utc(config.next_due_at) == deadline
    _save(repo, scope, now=now, schedule_enabled=True, local_time="12:00")
    assert as_utc(config.next_due_at) == datetime(2026, 9, 18, 3, tzinfo=UTC)


def test_manual_receipt_replay_coalescing_and_late_material(memory_session):
    db = memory_session
    scope, setting, *_ = _stack(db)
    repo = memory_batch_repository(db)
    _save(repo, scope, schedule_enabled=True)
    db.commit()
    factory = create_session_factory(db.bind)
    provider = Provider()
    runtime = MemoryBatchRuntime(factory, lambda *args: None, generation_policy="episode_v1", episode_provider_factory=lambda *args: provider)
    install_memory_delivery(factory)
    try:
        with factory() as writer:
            _post(writer, scope, "manual-before")
        due = repo.settings(scope).next_due_at
        row, outcome, data = start(db, repo, scope, setting)
        assert outcome == "accepted"
        accepted, cutoff = row.accepted_at, row.cutoff_sequence
        with factory() as writer:
            _post(writer, scope, "manual-after", created_at=datetime.now(UTC) + timedelta(seconds=1))
        replay, outcome = manual(db, repository=repo, scope=scope, data=data, now=datetime.now(UTC))
        assert outcome == "reused" and replay.id == row.id
        assert (replay.accepted_at, replay.cutoff_sequence) == (accepted, cutoff)
        coalesced, outcome, _ = start(db, repo, scope, setting)
        assert outcome == "already_active" and coalesced.coalesced_to_request_id == row.id
        assert asyncio.run(runtime.tick()) == "memory_selection_completed"
        db.expire_all()
        result = progress(db, db.get(MemoryConsolidationRequest, row.id))
        assert result["state"] == "completed" and result["saved_count"] == 1
        assert provider.calls == 1
        assert repo.settings(scope).next_due_at == due
        late = db.scalar(select(MemorySourceDelivery).where(MemorySourceDelivery.source_id == "manual-after"))
        assert late.batch_job_id is None
        assert asyncio.run(runtime.tick()) == "memory_batch_queue_empty"
        assert provider.calls == 1
        with pytest.raises(MemoryConflictError):
            manual(db, repository=repo, scope=scope, data=data.model_copy(update={"expected_version": 999}), now=datetime.now(UTC))
    finally:
        uninstall_memory_delivery(factory)


def test_empty_request_restarts_without_provider_or_schedule_change(memory_session):
    db = memory_session
    scope, setting, *_ = _stack(db)
    repo = memory_batch_repository(db)
    _save(repo, scope)
    db.commit()
    row, _, _ = start(db, repo, scope, setting)
    provider = Provider()
    runtime = MemoryBatchRuntime(create_session_factory(db.bind), lambda *args: None, generation_policy="episode_v1", episode_provider_factory=lambda *args: provider)
    assert asyncio.run(runtime.tick()) == "memory_batch_queue_empty"
    db.expire_all()
    assert progress(db, db.get(MemoryConsolidationRequest, row.id))["state"] == "no_work"
    assert provider.calls == 0
    assert db.scalar(select(func.count()).select_from(MemoryBatchRun)) == 0


def test_stale_versions_reject_without_creating_receipt(memory_session):
    db = memory_session
    scope, setting, *_ = _stack(db)
    repo = memory_batch_repository(db)
    _save(repo, scope)
    with pytest.raises(MemoryConflictError):
        manual(db, repository=repo, scope=scope, data=MemoryBatchStart(idempotency_key=uuid4().hex,
            expected_version=999, expected_profile_version=1, expected_scope_version=setting.version), now=datetime.now(UTC))
    assert db.scalar(select(func.count()).select_from(MemoryConsolidationRequest)) == 0


@pytest.mark.parametrize("prepared", [False, True])
@pytest.mark.parametrize("manual_alias", [False, True])
def test_schedule_off_preserves_manual_interest_only(memory_session, prepared, manual_alias):
    from app.domains.memory.repository.consolidation_requests import admit
    db = memory_session
    scope, setting, *_ = _stack(db)
    repo = memory_batch_repository(db)
    _save(repo, scope, schedule_enabled=True)
    db.commit()
    factory = create_session_factory(db.bind)
    provider = Provider()
    runtime = MemoryBatchRuntime(factory, lambda *args: None, generation_policy="episode_v1",
        episode_provider_factory=lambda *args: provider)
    install_memory_delivery(factory)
    try:
        with factory() as writer:
            _post(writer, scope, "schedule-off-source")
        now = datetime.now(UTC)
        row, _ = admit(db, setting=setting, kind="scheduled", key="scheduled:test-off", now=now, scheduled_for=now)
        db.commit()
        if manual_alias:
            alias, outcome, _ = start(db, repo, scope, setting)
            assert outcome == "already_active" and alias.coalesced_to_request_id == row.id
        if prepared:
            runtime.prepare()
            db.expire_all()
        _save(repo, scope, schedule_enabled=False)
        db.commit()
        result = asyncio.run(runtime.tick())
        db.expire_all()
        assert provider.calls == int(manual_alias)
        assert progress(db, db.get(MemoryConsolidationRequest, row.id))["state"] == ("completed" if manual_alias else "cancelled")
        assert result == ("memory_selection_completed" if manual_alias else "memory_batch_queue_empty")
    finally:
        uninstall_memory_delivery(factory)


def test_request_recovers_more_than_one_page_without_premature_completion(memory_session):
    from app.domains.memory.models.batch import MemoryActivationEpoch
    db = memory_session
    scope, setting, *_ = _stack(db)
    repo = memory_batch_repository(db)
    now = datetime.now(UTC)
    db.scalar(select(MemoryActivationEpoch)).opened_at = now - timedelta(hours=1)
    _save(repo, scope)
    for index in range(140):
        _post(db, scope, f"recovered-manual-{index}", created_at=now - timedelta(minutes=1))
    row, _, _ = start(db, repo, scope, setting)
    runtime = MemoryBatchRuntime(create_session_factory(db.bind), lambda *args: None, generation_policy="episode_v1")
    runtime.prepare()
    db.expire_all()
    assert db.get(MemoryConsolidationRequest, row.id).state == "preparing"
    for _ in range(4):
        runtime.prepare()
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(MemorySourceDelivery).where(MemorySourceDelivery.batch_job_id.is_not(None))) == 140
    assert progress(db, db.get(MemoryConsolidationRequest, row.id))["state"] == "queued"


def test_provider_barrier_preserves_concurrency_one_and_observable_phase(memory_session, monkeypatch):
    from app.domains.memory.models.consolidation_request import MemoryConsolidationJob
    from app.runtime.memory import foreground_priority
    db = memory_session
    scope, setting, *_ = _stack(db)
    repo = memory_batch_repository(db)
    _save(repo, scope)
    db.commit()
    factory = create_session_factory(db.bind)
    active = [False]
    monkeypatch.setattr(foreground_priority, "chat_is_active", lambda *args, **kwargs: active[0])
    install_memory_delivery(factory)
    try:
        with factory() as writer:
            _post(writer, scope, "barrier-source")
        row, _, _ = start(db, repo, scope, setting)
        async def scenario():
            started, release = asyncio.Event(), asyncio.Event()
            class Barrier(Provider):
                phase_observer = None
                async def select(self, bundle, *, timeout):
                    self.phase_observer("ai_running")
                    started.set()
                    await release.wait()
                    self.phase_observer("applying")
                    return await super().select(bundle, timeout=timeout)
            provider = Barrier()
            runtime = MemoryBatchRuntime(factory, lambda *args: None, generation_policy="episode_v1", episode_provider_factory=lambda *args: provider)
            running = asyncio.create_task(runtime.tick())
            await asyncio.wait_for(started.wait(), 5)
            with factory() as observer:
                snapshot = progress(observer, observer.get(MemoryConsolidationRequest, row.id))
                assert snapshot["state"] == "ai_running"
            active[0] = True
            other = MemoryBatchRuntime(factory, lambda *args: None, generation_policy="episode_v1", episode_provider_factory=lambda *args: provider)
            assert await other.tick() == "memory_foreground_deferred"
            assert provider.calls == 0
            release.set()
            assert await running == "memory_selection_completed"
            assert provider.calls == 1
            with factory() as observer:
                assert progress(observer, observer.get(MemoryConsolidationRequest, row.id))["state"] == "completed"
        asyncio.run(scenario())
    finally:
        uninstall_memory_delivery(factory)
