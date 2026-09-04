import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import models
from app.domains.memory.application.batch_selection import MemoryBatchSelectionService
from app.domains.memory.domain.batch_policy import MEMORY_CONSENT_VERSION
from app.domains.memory.domain.selection import MemorySelectionDecision
from app.domains.memory.infrastructure.batch_models import (
    MemoryBatchRun,
    MemorySelectionDecisionModel,
    MemorySourceDelivery,
)
from app.domains.memory.infrastructure.batch_repository import (
    SqlAlchemyMemoryBatchRepository,
)
from app.domains.memory.infrastructure.sqlalchemy_models import (
    MemoryCandidate,
    MemoryItem,
    MemoryMaintenanceJob,
)
from app.runtime.memory.batch_runtime import (
    deliver_candidates,
    enqueue_scope,
    rebuild_briefs,
    schedule_batches,
)
from app.runtime.memory.source_delivery import (
    install_memory_delivery,
    uninstall_memory_delivery,
)
from test_p8_l_o_memory_consolidation import memory_session, _stack, _propose


class Selector:
    def __init__(self, *, fail=False, skip=False, callback=None):
        self.calls = 0
        self.fail, self.skip, self.callback = fail, skip, callback

    async def select(self, sources, *, timeout):
        self.calls += 1
        if self.callback:
            self.callback()
        if self.fail:
            raise RuntimeError("untrusted raw provider error")
        return tuple(
            MemorySelectionDecision(
                source.candidate_ref,
                "skip" if self.skip else "retain",
                "routine_low_salience" if self.skip else "meaningful_experience",
                None if self.skip else "동료와 함께 훈련했다.",
            )
            for source in sources
        )


def batch_stack(session, *, provider=None):
    scope, setting, reader, repository, writer, _ = _stack(session)
    _propose(writer, reader, scope, 2)
    session.commit()
    repo = SqlAlchemyMemoryBatchRepository(session)
    now = datetime.now(UTC)
    repo.save_settings(
        scope,
        expected_version=0,
        expected_profile_version=0,
        ai_enabled=True,
        shutdown_enabled=True,
        schedule_enabled=False,
        local_time="22:30",
        consent_version=MEMORY_CONSENT_VERSION,
        model_id="fixture-model",
        idempotency_key="batch-setup",
        now=now,
    )
    ids = tuple(session.scalars(select(MemoryCandidate.id)).all())
    job = repo.enqueue(
        scope_setting_id=setting.id,
        candidate_ids=ids,
        cutoff=0,
        trigger="shutdown",
        now=now,
    )
    session.commit()
    selector = provider or Selector()
    service = MemoryBatchSelectionService(
        repository=repo,
        source_reader=reader,
        write_lifecycle=writer,
        provider_factory=lambda owner, model: selector,
    )
    return scope, repo, job, selector, service


def test_selection_persists_items_and_audit_once(memory_session):
    scope, repo, job, selector, service = batch_stack(memory_session)
    assert (
        asyncio.run(service.run_next(lease_token="first"))
        == "memory_selection_completed"
    )
    assert selector.calls == 1
    assert memory_session.scalar(select(func.count()).select_from(MemoryItem)) == 2
    assert (
        memory_session.scalar(
            select(func.count()).select_from(MemorySelectionDecisionModel)
        )
        == 2
    )
    memory_session.rollback()
    assert (
        asyncio.run(service.run_next(lease_token="second"))
        == "memory_batch_queue_empty"
    )
    assert selector.calls == 1
    rebuild_briefs(memory_session, now=datetime.now(UTC), source_reader=service.reader)
    assert (
        memory_session.scalar(select(func.count()).select_from(models.MemoryHotBrief))
        == 1
    )


def test_skip_is_success_not_failed_or_repeated(memory_session):
    _, repo, job, selector, service = batch_stack(
        memory_session, provider=Selector(skip=True)
    )
    assert (
        asyncio.run(service.run_next(lease_token="skip"))
        == "memory_selection_completed"
    )
    assert memory_session.get(MemoryMaintenanceJob, job).status == "succeeded"
    assert memory_session.scalar(select(func.count()).select_from(MemoryItem)) == 0
    assert [
        r.decision for r in memory_session.scalars(select(MemorySelectionDecisionModel))
    ] == ["skip", "skip"]


def test_provider_failure_never_falls_back_to_accept_all(memory_session):
    _, repo, job, selector, service = batch_stack(
        memory_session, provider=Selector(fail=True)
    )
    assert (
        asyncio.run(service.run_next(lease_token="fail"))
        == "memory_selection_provider_failed"
    )
    assert memory_session.scalar(select(func.count()).select_from(MemoryItem)) == 0
    assert memory_session.get(MemoryBatchRun, job).physical_calls == 1
    assert memory_session.get(MemoryMaintenanceJob, job).status == "pending"
    memory_session.rollback()
    assert (
        asyncio.run(service.run_next(lease_token="backoff"))
        == "memory_batch_queue_empty"
    )
    assert selector.calls == 1


def test_post_commit_captures_delivery_without_ai(memory_session):
    scope, setting, *_ = _stack(memory_session)
    factory = sessionmaker(bind=memory_session.bind)
    install_memory_delivery(factory)
    try:
        with factory() as session:
            session.add(
                models.Post(
                    id="batch-post",
                    world_id=scope.world_id,
                    author_world_character_id=scope.subject_world_character_id,
                    author_name="subject",
                    title="함께 훈련",
                    body="동료와 과제를 마쳤다.",
                )
            )
            session.commit()
        with factory() as session:
            assert (
                session.scalar(select(func.count()).select_from(MemorySourceDelivery))
                == 1
            )
            assert session.scalar(select(func.count()).select_from(MemoryItem)) == 0
            assert deliver_candidates(session) == 1
            assert (
                session.scalar(select(func.count()).select_from(MemoryCandidate)) == 1
            )
            assert deliver_candidates(session) == 0
    finally:
        uninstall_memory_delivery(factory)


def test_saved_schedule_does_not_generate_or_trigger_past_time(memory_session):
    scope, *_ = _stack(memory_session)
    repo = SqlAlchemyMemoryBatchRepository(memory_session)
    now = datetime(2026, 9, 4, 14, tzinfo=UTC)
    value = repo.save_settings(
        scope,
        expected_version=0,
        expected_profile_version=0,
        ai_enabled=True,
        shutdown_enabled=True,
        schedule_enabled=True,
        local_time="22:30",
        consent_version=MEMORY_CONSENT_VERSION,
        model_id="fixture-model",
        idempotency_key="schedule-save",
        now=now,
    )
    memory_session.commit()
    assert value.next_due_at == datetime(2026, 9, 5, 13, 30, tzinfo=UTC)
    schedule_batches(memory_session, now=now)
    assert (
        memory_session.scalar(select(func.count()).select_from(MemoryMaintenanceJob))
        == 0
    )
