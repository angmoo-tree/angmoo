import asyncio
from datetime import timedelta

from sqlalchemy import select, func

from app.domains.memory.models.batch import MemoryActivationEpoch, MemorySourceDelivery, MemoryBatchRun
from app.domains.memory.models.items import MemoryCandidate, MemoryMaintenanceJob, MemoryItem
from app.domains.memory.policies.batch import MEMORY_CONSENT_VERSION
from app.domains.memory.contracts.provenance import MemorySourceTypeV1, MemoryKindV1
from app.domains.memory.service.items import MemoryWriteLifecycleService
from app.runtime.memory.composition import memory_batch_repository
from app.runtime.memory.source_composition import source_evidence_reader
from app.runtime.memory.episode_batch import run_episode_batch
from memory.test_episode_chat_pipeline import setup, response_session
from memory.test_episode_selection_service import Provider


def prepare(db):
    scope, memory, bundle, done, now = setup(db)
    setting = memory.get_scope_setting(scope)
    repo = memory_batch_repository(db)
    repo.save_settings(scope, expected_version=0, expected_profile_version=0, ai_enabled=True,
        shutdown_enabled=True, schedule_enabled=False, local_time="22:30", consent_version=MEMORY_CONSENT_VERSION,
        model_id="gemini-3.1-flash-lite", idempotency_key="episode-test-settings", now=now)
    source_id = str(done.committed_assistant_message_id)
    candidate = MemoryWriteLifecycleService(memory, source_evidence_reader(db)).propose_candidate(
        scope=scope, source_type=MemorySourceTypeV1.CHAT_MESSAGE, source_id=source_id,
        memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT).candidate
    epoch = db.scalar(select(MemoryActivationEpoch).where(MemoryActivationEpoch.scope_setting_id == setting.id,
        MemoryActivationEpoch.scope_version == setting.version))
    assert epoch is not None
    delivery = MemorySourceDelivery(scope_setting_id=setting.id, epoch_id=epoch.id, source_type="CHAT_MESSAGE",
        source_id=source_id, state="delivered", candidate_id=candidate.id, captured_at=now)
    db.add(delivery)
    db.flush()
    job = repo.enqueue(scope_setting_id=setting.id, candidate_ids=(candidate.id,), cutoff=delivery.sequence,
        trigger="shutdown", now=now, generation_policy="episode_v1")
    db.commit()
    batch = repo.claim(lease_token="episode-test-lease", now=now)
    db.commit()
    assert batch.job_id == job and batch.policy_version == "episode-selection.v1"
    return repo, batch, now


def test_real_claim_through_episode_application_and_queue_completion(response_session):
    db = response_session
    repo, batch, now = prepare(db)
    provider = Provider()
    result = asyncio.run(run_episode_batch(repo, batch, provider_factory=lambda *args: provider, timeout=10, clock=lambda: now))
    assert result == "memory_selection_completed"
    assert provider.calls == 1
    assert db.scalar(select(func.count(MemoryItem.id))) == 1
    assert db.get(MemoryCandidate, batch.candidates[0].id).status == "accepted"
    assert db.get(MemoryMaintenanceJob, batch.job_id).status == "succeeded"


def test_foreground_defers_before_provider_without_spending_retry(response_session):
    db = response_session
    repo, batch, now = prepare(db)
    provider = Provider()
    result = asyncio.run(run_episode_batch(repo, batch, provider_factory=lambda *args: provider,
        timeout=10, clock=lambda: now, foreground_active=lambda *args, **kwargs: True))
    assert result == "memory_foreground_deferred" and provider.calls == 0
    job = db.get(MemoryMaintenanceJob, batch.job_id)
    assert job.status == "pending" and job.attempt_count == 0 and job.lease_token is None
    later = now + timedelta(seconds=6)
    again = repo.claim(lease_token="foreground-ended", now=later)
    db.commit()
    assert again.job_id == batch.job_id
    result = asyncio.run(run_episode_batch(repo, again, provider_factory=lambda *args: provider,
        timeout=10, clock=lambda: later, foreground_active=lambda *args, **kwargs: False))
    assert result == "memory_selection_completed" and provider.calls == 1
    # Per-bundle receipts count episode calls; the old batch-v2 counter is not
    # silently relabeled as an unlimited daily physical-call counter.
    assert db.get(MemoryBatchRun, batch.job_id).physical_calls == 0
    from app.domains.memory.repository.episode_work import SqlAlchemyEpisodeWork
    work, = SqlAlchemyEpisodeWork(db).list(job_id=batch.job_id, setting=batch.setting)
    assert work.calls == 1 and work.state == "completed"
    assert repo.settings(batch.setting.scope).run_saved_count == 1


def test_explicit_retry_keeps_frozen_work_and_prior_call_receipt(response_session):
    db = response_session
    repo, batch, now = prepare(db)
    class Failure(Provider):
        async def select(self, bundle, *, timeout):
            self.calls += 1
            raise RuntimeError("provider failed")
    provider = Failure()
    result = asyncio.run(run_episode_batch(repo, batch, provider_factory=lambda *args: provider, timeout=10, clock=lambda: now))
    assert result == "episode_provider_failed"
    # Simulate exhausting the queue retry lease while retaining bundle history.
    job = db.get(MemoryMaintenanceJob, batch.job_id)
    job.status, job.attempt_count, job.completed_at = "failed", 3, now
    db.commit()
    repo.retry_failed(batch.setting.scope, idempotency_key="user-retry-episode", now=now)
    db.commit()
    from app.domains.memory.repository.episode_work import SqlAlchemyEpisodeWork
    work, = SqlAlchemyEpisodeWork(db).list(job_id=batch.job_id, setting=batch.setting)
    assert work.calls == 1 and work.state == "pending"
    db.commit()
    again = repo.claim(lease_token="retry-episode", now=now)
    db.commit()
    assert again.job_id == batch.job_id
    result = asyncio.run(run_episode_batch(repo, again, provider_factory=lambda *args: Provider(), timeout=10, clock=lambda: now))
    assert result == "memory_selection_completed"
    work, = SqlAlchemyEpisodeWork(db).list(job_id=batch.job_id, setting=batch.setting)
    assert work.calls == 2 and work.state == "completed"
