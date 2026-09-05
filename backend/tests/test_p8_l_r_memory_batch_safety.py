import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import models
from app.domains.memory.application.batch_selection import MemoryBatchSelectionService
from app.domains.memory.application.scope_control import MemoryScopeService
from app.domains.memory.domain.batch_policy import MEMORY_CONSENT_VERSION
from app.domains.memory.domain.errors import MemoryConflictError
from app.domains.memory.infrastructure.batch_models import (
    MemoryActivationEpoch,
    MemoryBatchRun,
    MemoryBatchSetting,
    MemorySourceDelivery,
    MemorySelectionDecisionModel,
)
from app.domains.memory.infrastructure.batch_repository import (
    SqlAlchemyMemoryBatchRepository,
)
from app.domains.memory.infrastructure.sqlalchemy_models import (
    MemoryCandidate,
    MemoryMaintenanceJob,
    MemoryScopeSettingModel,
)
from app.runtime.memory.batch_runtime import (
    MemoryBatchRuntime,
    reconcile_sources,
    deliver_candidates,
    schedule_batches,
)
from app.runtime.memory.shutdown import MemoryShutdownCoordinator
from app.runtime.memory.source_delivery import (
    install_memory_delivery,
    uninstall_memory_delivery,
)
from test_p8_l_o_memory_consolidation import memory_session, _stack
from test_p8_l_r_memory_batch_runtime import Selector, batch_stack


def _save(repo, scope, *, now=None, **overrides):
    saved = repo.settings(scope)
    return repo.save_settings(
        scope,
        **{
            "expected_version": saved.version,
            "expected_profile_version": saved.profile_version,
            "ai_enabled": True,
            "shutdown_enabled": True,
            "schedule_enabled": False,
            "local_time": "22:30",
            "consent_version": MEMORY_CONSENT_VERSION,
            "model_id": "fixture-model",
            "idempotency_key": "test-save-" + str(saved.version),
            "now": now or datetime.now(UTC),
            **overrides,
        },
    )


def _post(session, scope, identity, *, created_at=None):
    post = models.Post(
        id=identity,
        world_id=scope.world_id,
        author_world_character_id=scope.subject_world_character_id,
        author_name="subject",
        title="팀 연습",
        body="동료와 함께 훈련 목표를 달성했다.",
    )
    if created_at is not None:
        post.created_at = created_at
    session.add(post)
    session.commit()
    return post


def test_complete_source_schedule_selection_brief_and_reopen_are_causal(memory_session):
    scope, setting, *_ = _stack(memory_session)
    repo = SqlAlchemyMemoryBatchRepository(memory_session)
    _save(repo, scope)
    memory_session.commit()
    factory = sessionmaker(bind=memory_session.bind)
    selector = Selector()
    runtime = MemoryBatchRuntime(factory, lambda owner, model: selector)
    install_memory_delivery(factory)
    try:
        with factory() as db:
            _post(db, scope, "actual-causal-source")
        # Ordinary ticks only deliver durable candidates. No paid selection.
        assert asyncio.run(runtime.tick()) == "memory_batch_queue_empty"
        assert selector.calls == 0
        assert asyncio.run(runtime.tick(shutdown=True)) == "memory_selection_completed"
        runtime.prepare()
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(models.MemoryItem)) == 1
            assert (
                db.scalar(select(func.count()).select_from(models.MemoryHotBrief)) == 1
            )
            assert (
                db.scalar(
                    select(func.count()).select_from(MemorySelectionDecisionModel)
                )
                == 1
            )
            evidence = db.scalar(select(models.MemoryItemEvidence))
            assert evidence.source_id == "actual-causal-source"
        reopened = MemoryBatchRuntime(factory, lambda owner, model: selector)
        assert asyncio.run(reopened.tick(shutdown=True)) == "memory_batch_queue_empty"
        assert selector.calls == 1
    finally:
        uninstall_memory_delivery(factory)


def test_recovery_excludes_off_gap_and_pre_upgrade_records(memory_session):
    scope, setting, *_ = _stack(memory_session)
    epoch = memory_session.scalar(select(MemoryActivationEpoch))
    now = datetime.now(UTC)
    epoch.opened_at, epoch.closed_at = (
        now - timedelta(hours=3),
        now - timedelta(hours=2),
    )
    memory_session.add(
        MemoryActivationEpoch(
            id="after-off",
            scope_setting_id=setting.id,
            scope_version=99,
            opened_at=now - timedelta(hours=1),
        )
    )
    for identity, age in (
        ("old-before-on", 4),
        ("on-first", 2.5),
        ("off-gap", 1.5),
        ("on-second", 0.5),
    ):
        _post(memory_session, scope, identity, created_at=now - timedelta(hours=age))
    reconcile_sources(memory_session, now=now)
    assert set(memory_session.scalars(select(MemorySourceDelivery.source_id))) == {
        "on-first",
        "on-second",
    }
    reconcile_sources(memory_session, now=now + timedelta(seconds=1))
    assert (
        memory_session.scalar(select(func.count()).select_from(MemorySourceDelivery))
        == 2
    )


def test_recovered_hole_before_shutdown_is_resumed_but_new_activity_waits(
    memory_session,
):
    scope, setting, *_ = _stack(memory_session)
    repo = SqlAlchemyMemoryBatchRepository(memory_session)
    now = datetime.now(UTC)
    epoch = memory_session.scalar(select(MemoryActivationEpoch))
    epoch.opened_at = now - timedelta(hours=2)
    _save(repo, scope, now=now)
    memory_session.commit()
    # Simulate termination before the normal delivery marker was written.
    _post(memory_session, scope, "lost-marker", created_at=now - timedelta(hours=1))
    schedule_batches(memory_session, now=now, shutdown=True)
    _post(
        memory_session, scope, "later-activity", created_at=now + timedelta(seconds=1)
    )
    reconcile_sources(memory_session, now=now + timedelta(seconds=2))
    deliver_candidates(memory_session)
    schedule_batches(memory_session, now=now + timedelta(seconds=2))
    rows = {
        row.source_id: row.batch_job_id
        for row in memory_session.scalars(select(MemorySourceDelivery))
    }
    assert rows["lost-marker"] is not None
    assert rows["later-activity"] is None


def test_daily_due_is_coalesced_and_does_not_schedule_new_sources_twice(memory_session):
    scope, setting, *_ = _stack(memory_session)
    now = datetime.now(UTC)
    memory_session.scalar(select(MemoryActivationEpoch)).opened_at = now - timedelta(
        days=5
    )
    _save(
        SqlAlchemyMemoryBatchRepository(memory_session),
        scope,
        now=now - timedelta(days=4),
        schedule_enabled=True,
    )
    _post(
        memory_session, scope, "before-missed-slots", created_at=now - timedelta(days=2)
    )
    reconcile_sources(memory_session, now=now)
    deliver_candidates(memory_session)
    schedule_batches(memory_session, now=now)
    first = memory_session.scalar(
        select(MemorySourceDelivery).where(
            MemorySourceDelivery.source_id == "before-missed-slots"
        )
    )
    assert first.batch_job_id is not None
    config = memory_session.get(MemoryBatchSetting, setting.id)
    slot = config.last_consumed_date
    _post(
        memory_session,
        scope,
        "after-missed-slots",
        created_at=now + timedelta(seconds=1),
    )
    reconcile_sources(memory_session, now=now + timedelta(seconds=2))
    deliver_candidates(memory_session)
    schedule_batches(memory_session, now=now + timedelta(seconds=2))
    later = memory_session.scalar(
        select(MemorySourceDelivery).where(
            MemorySourceDelivery.source_id == "after-missed-slots"
        )
    )
    assert later.batch_job_id is None
    assert config.last_consumed_date == slot
    assert memory_session.scalar(select(func.count()).select_from(MemoryBatchRun)) == 1


def test_user_retry_creates_one_audited_run_without_resetting_old_attempts(
    memory_session,
):
    scope, repo, job, provider, service = batch_stack(
        memory_session, provider=Selector(fail=True)
    )
    now = datetime.now(UTC)
    config = repo.memory.get_scope_setting(scope)
    epoch = memory_session.scalar(select(MemoryActivationEpoch))
    for number, candidate in enumerate(
        memory_session.scalars(select(MemoryCandidate)).all()
    ):
        memory_session.add(
            MemorySourceDelivery(
                scope_setting_id=config.id,
                epoch_id=epoch.id,
                source_type=candidate.source_type,
                source_id=candidate.source_id,
                candidate_id=candidate.id,
                state="delivered",
                batch_job_id=job,
                captured_at=now,
            )
        )
    memory_session.commit()
    for attempt in range(3):
        memory_session.rollback()
        service.clock = lambda attempt=attempt: now + timedelta(minutes=3 * attempt)
        asyncio.run(service.run_next(lease_token=f"failure-{attempt}"))
    for _ in range(2):
        repo.retry_failed(
            scope, idempotency_key="user-retry-once", now=now + timedelta(days=1)
        )
        repo.commit()
    runs = memory_session.scalars(select(MemoryBatchRun)).all()
    assert len(runs) == 2
    assert memory_session.get(MemoryBatchRun, job).physical_calls == 3
    assert memory_session.get(MemoryMaintenanceJob, job).attempt_count == 3
    new_run = next(run for run in runs if run.job_id != job)
    assert new_run.trigger == "explicit" and new_run.physical_calls == 0
    assert set(memory_session.scalars(select(MemorySourceDelivery.batch_job_id))) == {
        new_run.job_id
    }


def test_backlog_tail_is_admitted_after_first_32(memory_session):
    scope, setting, *_ = _stack(memory_session)
    now = datetime.now(UTC)
    epoch = memory_session.scalar(select(MemoryActivationEpoch))
    epoch.opened_at = now - timedelta(hours=2)
    _save(SqlAlchemyMemoryBatchRepository(memory_session), scope, now=now)
    for index in range(35):
        _post(
            memory_session,
            scope,
            f"backlog-{index:03}",
            created_at=now - timedelta(minutes=30),
        )
    schedule_batches(memory_session, now=now, shutdown=True)
    for index in range(3):
        reconcile_sources(memory_session, now=now + timedelta(seconds=index))
        deliver_candidates(memory_session)
        schedule_batches(memory_session, now=now + timedelta(seconds=index))
    assert (
        memory_session.scalar(
            select(func.count())
            .select_from(MemorySourceDelivery)
            .where(MemorySourceDelivery.batch_job_id.is_not(None))
        )
        == 35
    )
    assert (
        memory_session.scalar(
            select(func.count())
            .select_from(MemoryMaintenanceJob)
            .where(MemoryMaintenanceJob.reason == "memory_selection_v2")
        )
        == 18
    )


def test_attempt_limit_survives_restarting_services_and_expired_leases(memory_session):
    scope, repo, job_id, provider, service = batch_stack(
        memory_session, provider=Selector(fail=True)
    )
    now = datetime.now(UTC)
    for attempt in range(3):
        memory_session.rollback()
        service.clock = lambda attempt=attempt: now + timedelta(minutes=attempt * 3)
        assert (
            asyncio.run(service.run_next(lease_token=f"attempt-{attempt}"))
            == "memory_selection_provider_failed"
        )
    memory_session.rollback()
    service.clock = lambda: now + timedelta(days=1)
    assert (
        asyncio.run(service.run_next(lease_token="reopened"))
        == "memory_batch_queue_empty"
    )
    assert provider.calls == 3
    assert memory_session.get(MemoryMaintenanceJob, job_id).status == "failed"
    assert memory_session.get(MemoryBatchRun, job_id).physical_calls == 3


@pytest.mark.parametrize("change", ["off", "settings", "source", "model", "departed"])
def test_changed_policy_or_source_cannot_commit_old_provider_response(
    memory_session, change
):
    scope, repo, job_id, provider, service = batch_stack(memory_session)

    def alter():
        if change == "off":
            setting = repo.memory.get_scope_setting(scope)
            MemoryScopeService(repo.memory).update(
                scope,
                expected_version=setting.version,
                enabled=False,
                retention_days=180,
            )
            memory_session.commit()
        elif change in {"settings", "model"}:
            _save(
                repo,
                scope,
                model_id="other-fixture-model"
                if change == "model"
                else "fixture-model",
                local_time="23:30",
            )
            memory_session.commit()
        elif change == "departed":
            memory_session.get(
                models.WorldCharacter, scope.subject_world_character_id
            ).status = "left"
            memory_session.commit()
        else:
            key = next(iter(service.reader.values))
            service.reader.values[key] = replace(
                service.reader.values[key], visible=False
            )

    provider.callback = alter
    assert (
        asyncio.run(service.run_next(lease_token="original"))
        != "memory_selection_completed"
    )
    assert provider.calls == 1
    assert (
        memory_session.scalar(select(func.count()).select_from(models.MemoryItem)) == 0
    )
    assert (
        memory_session.scalar(
            select(func.count()).select_from(MemorySelectionDecisionModel)
        )
        == 0
    )


def test_two_workers_cannot_claim_same_installation(memory_session):
    _, repo, job, provider, service = batch_stack(memory_session)
    now = datetime.now(UTC)
    first = repo.claim(lease_token="one", now=now)
    repo.commit()
    second = SqlAlchemyMemoryBatchRepository(memory_session).claim(
        lease_token="two", now=now
    )
    repo.commit()
    assert first is not None and second is None
    assert provider.calls == 0


def test_legacy_worker_cannot_accept_v2_candidates(memory_session):
    _, repo, job, _, _ = batch_stack(memory_session)
    assert (
        repo.queue.claim(
            lease_token="legacy", now=datetime.now(UTC), lease_for=timedelta(seconds=30)
        )
        is None
    )


def test_expired_final_attempt_becomes_attention_without_invalid_lease(memory_session):
    _, repo, job_id, provider, service = batch_stack(memory_session)
    now = datetime.now(UTC)
    batch = repo.claim(lease_token="killed-attempt", now=now)
    job = memory_session.get(MemoryMaintenanceJob, job_id)
    job.attempt_count = 3
    memory_session.get(MemoryBatchRun, job_id).physical_calls = 3
    repo.commit()
    service.clock = lambda: now + timedelta(days=1)
    assert (
        asyncio.run(service.run_next(lease_token="reopened"))
        == "memory_batch_queue_empty"
    )
    memory_session.expire_all()
    job = memory_session.get(MemoryMaintenanceJob, job_id)
    assert job.status == "failed" and job.lease_token is None
    assert job.last_error_code == "memory_selection_attempts_exhausted"
    assert batch is not None and provider.calls == 0


def test_oversized_request_fails_before_physical_call_reservation(memory_session):
    _, repo, job, provider, service = batch_stack(memory_session)

    def reject(_sources):
        from app.domains.memory.domain.errors import MemoryValidationError

        raise MemoryValidationError("memory_selection_input_budget_exceeded")

    provider.validate_sources = reject
    assert (
        asyncio.run(service.run_next(lease_token="bounded"))
        == "memory_selection_input_budget_exceeded"
    )
    assert provider.calls == 0
    assert memory_session.get(MemoryBatchRun, job).physical_calls == 0


def test_account_scrub_removes_private_memory_batches_not_other_owner(memory_session):
    from app.runtime.account_deletion import _scrub_account_data
    from app.domains.memory.infrastructure.batch_models import (
        MemoryBatchProfile,
        MEMORY_BATCH_TABLES,
    )
    from app.core.db import Base
    from sqlalchemy import event
    from app.runtime.memory.recall_projection import EmbeddedMemoryRecallProjection

    scope, repo, job, _, service = batch_stack(memory_session)
    assert (
        asyncio.run(service.run_next(lease_token="before-scrub"))
        == "memory_selection_completed"
    )
    from app.runtime.memory.batch_runtime import rebuild_briefs

    rebuild_briefs(memory_session, now=datetime.now(UTC), source_reader=service.reader)
    outsider = models.User(
        id="unrelated-owner", email="unrelated@example.test", display_name="unrelated"
    )
    memory_session.add(outsider)
    memory_session.flush()
    memory_session.add(
        MemoryBatchProfile(owner_id=outsider.id, model_id="fixture-model")
    )
    memory_session.commit()
    owner = memory_session.get(models.User, scope.owner_id)
    # Real bulk-delete hook records exact removed IDs for FTS cleanup on commit.
    old_item_ids = set(memory_session.scalars(select(models.MemoryItem.id)))
    event.listen(
        memory_session, "do_orm_execute", EmbeddedMemoryRecallProjection._do_orm_execute
    )
    _scrub_account_data(memory_session, owner, [], [])
    assert memory_session.info["angmoo_memory_recall_pending_item_ids"] == old_item_ids
    event.remove(
        memory_session, "do_orm_execute", EmbeddedMemoryRecallProjection._do_orm_execute
    )
    memory_session.commit()
    memory_session.expire_all()
    for name in MEMORY_BATCH_TABLES:
        expected = 1 if name == "memory_batch_profiles" else 0
        assert (
            memory_session.scalar(
                select(func.count()).select_from(Base.metadata.tables[name])
            )
            == expected
        )
    for model in (
        MemoryCandidate,
        models.MemoryItem,
        models.MemoryHotBrief,
        MemoryMaintenanceJob,
        MemoryScopeSettingModel,
    ):
        assert memory_session.scalar(select(func.count()).select_from(model)) == 0
    assert memory_session.get(MemoryBatchProfile, outsider.id) is not None


def test_character_scrub_removes_its_batches_and_preserves_other_character(
    memory_session,
):
    from app.services.agents import _scrub_agent_data
    from app.domains.memory.infrastructure.batch_models import MemoryBatchProfile
    from app.domains.memory.domain.scope import MemoryScope

    scope, repo, _, _, service = batch_stack(memory_session)
    assert (
        asyncio.run(service.run_next(lease_token="before-character-scrub"))
        == "memory_selection_completed"
    )
    counterpart_scope = MemoryScope(
        scope.owner_id, scope.world_id, "consolidation-counterpart"
    )
    other = MemoryScopeService(repo.memory).get_or_create(counterpart_scope)
    _save(repo, counterpart_scope)
    memory_session.commit()
    character = memory_session.get(models.Character, "consolidation-subject-character")
    _scrub_agent_data(memory_session, character)
    memory_session.commit()
    memory_session.expire_all()
    assert (
        memory_session.scalar(select(func.count()).select_from(models.MemoryItem)) == 0
    )
    assert memory_session.scalar(select(func.count()).select_from(MemoryBatchRun)) == 0
    assert (
        memory_session.scalar(
            select(func.count()).select_from(MemorySelectionDecisionModel)
        )
        == 0
    )
    assert set(memory_session.scalars(select(MemoryBatchSetting.scope_setting_id))) == {
        other.id
    }
    assert set(memory_session.scalars(select(MemoryScopeSettingModel.id))) == {other.id}
    assert (
        memory_session.get(MemoryBatchProfile, scope.owner_id).model_id
        == "fixture-model"
    )


def test_departed_scope_is_not_called_and_does_not_block_healthy_delivery(
    memory_session,
):
    from app.domains.memory.domain.scope import MemoryScope

    scope, repo, job_id, provider, service = batch_stack(memory_session)
    other_scope = MemoryScope(
        scope.owner_id, scope.world_id, "consolidation-counterpart"
    )
    other = MemoryScopeService(repo.memory).get_or_create(other_scope)
    MemoryScopeService(repo.memory).update(
        other_scope, expected_version=other.version, enabled=True, retention_days=180
    )
    _save(repo, other_scope)
    _post(memory_session, scope, "left-source", created_at=datetime.now(UTC))
    _post(memory_session, other_scope, "healthy-source", created_at=datetime.now(UTC))
    reconcile_sources(memory_session, now=datetime.now(UTC))
    memory_session.get(
        models.WorldCharacter, scope.subject_world_character_id
    ).status = "left"
    memory_session.commit()
    deliver_candidates(memory_session)
    states = {
        row.source_id: row.state
        for row in memory_session.scalars(select(MemorySourceDelivery))
    }
    assert states["left-source"] == "invalidated"
    assert states["healthy-source"] == "delivered"
    schedule_batches(memory_session, now=datetime.now(UTC), shutdown=True)
    memory_session.rollback()
    claimed = repo.claim(lease_token="only-active-subject", now=datetime.now(UTC))
    repo.commit()
    assert claimed is not None and claimed.setting.scope == other_scope
    assert (
        memory_session.get(MemoryMaintenanceJob, job_id).last_error_code
        == "memory_selection_scope_unavailable"
    )
    assert memory_session.get(MemoryBatchRun, job_id).physical_calls == 0
    assert provider.calls == 0


def test_marker_failure_does_not_roll_back_successful_post(memory_session, monkeypatch):
    from app.runtime.memory import source_delivery

    scope, *_ = _stack(memory_session)
    factory = sessionmaker(bind=memory_session.bind)
    install_memory_delivery(factory)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic marker fault")

    monkeypatch.setattr(source_delivery, "capture_delivery", fail)
    try:
        with factory() as db:
            _post(db, scope, "marker-failed")
        with factory() as db:
            assert db.get(models.Post, "marker-failed") is not None
            reconcile_sources(db, now=datetime.now(UTC))
            assert (
                db.scalar(select(func.count()).select_from(MemorySourceDelivery)) == 1
            )
    finally:
        uninstall_memory_delivery(factory)


def test_shutdown_skip_is_idempotent_and_does_not_start_ai(memory_session):
    _stack(memory_session)
    factory = sessionmaker(bind=memory_session.bind)
    provider = Selector()
    runtime = MemoryBatchRuntime(factory, lambda owner, model: provider)

    async def run():
        coordinator = MemoryShutdownCoordinator(runtime, budget_seconds=0.1)
        assert coordinator.start()["phase"] == "QUIESCING"
        original = coordinator.task
        coordinator.start()
        coordinator.skip()
        await asyncio.wait_for(coordinator.task, timeout=1)
        assert coordinator.task is original
        assert coordinator.status() == {"phase": "EXIT_READY", "deferred": True}

    asyncio.run(run())
    assert provider.calls == 0


def test_shutdown_database_failure_still_reaches_exit_ready():
    class UnavailableRuntime:
        async def pause(self):
            pass

        def prepare(self, **kwargs):
            raise RuntimeError("synthetic database unavailable")

        def session_factory(self):
            raise RuntimeError("synthetic database unavailable")

    async def run():
        coordinator = MemoryShutdownCoordinator(UnavailableRuntime())
        coordinator.start()
        await asyncio.wait_for(coordinator.task, timeout=1)
        assert coordinator.status() == {"phase": "EXIT_READY", "deferred": True}

    asyncio.run(run())


def test_shutdown_deadline_cancels_late_provider_and_preserves_candidates(
    memory_session,
):
    scope, repo, job, _, service = batch_stack(memory_session)
    factory = sessionmaker(bind=memory_session.bind)

    class Slow:
        async def select(self, sources, *, timeout):
            await asyncio.sleep(10)

    runtime = MemoryBatchRuntime(factory, lambda owner, model: Slow())

    # Use the fixture evidence source while keeping the real durable queue.
    async def tick(**kwargs):
        memory_session.rollback()
        service.provider_factory = lambda owner, model: Slow()
        return await service.run_next(
            lease_token="slow", timeout=kwargs.get("timeout", 30)
        )

    runtime.tick = tick

    async def run():
        coordinator = MemoryShutdownCoordinator(runtime, budget_seconds=0.2)
        coordinator.start()
        await asyncio.wait_for(coordinator.task, timeout=1)
        assert coordinator.phase == "EXIT_READY"

    asyncio.run(run())
    memory_session.expire_all()
    assert (
        memory_session.scalar(select(func.count()).select_from(models.MemoryItem)) == 0
    )
    assert memory_session.get(MemoryMaintenanceJob, job).status != "running"
    assert (
        memory_session.scalar(
            select(func.count())
            .select_from(MemoryCandidate)
            .where(MemoryCandidate.status == "pending")
        )
        == 2
    )
