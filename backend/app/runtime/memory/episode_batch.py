"""Bind episode input, provider and apply to an already claimed Memory job."""

import asyncio
import logging
from datetime import UTC, datetime

from app.domains.memory.exceptions import MemoryDomainError, MemoryConflictError, MemoryCapacityReached
from app.domains.memory.models.batch import MemoryBatchProfile
from app.domains.memory.repository.episode_apply import SqlAlchemyEpisodeApply
from app.domains.memory.repository.episode_completion import complete_episode_candidates
from app.domains.memory.repository.episode_work import SqlAlchemyEpisodeWork
from app.domains.memory.service.episode_selection import EpisodeSelectionService
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from app.runtime.memory.episode_job_inputs import build_episode_job_inputs
from app.runtime.memory.episode_revalidation import revalidate_episode_bundle


async def run_episode_batch(repository, batch, *, provider_factory, timeout, clock=None, foreground_active=None, prior_search=None):
    clock = clock or (lambda: datetime.now(UTC))
    db = repository.session
    def fence():
        repository.fence(batch, now=clock())
        profile = db.get(MemoryBatchProfile, batch.setting.scope.owner_id)
        if (profile.version != batch.profile_version or profile.model_id != batch.model_id
            or profile.thinking_level != batch.thinking_level):
            raise MemoryConflictError("episode_profile_changed")
    try:
        works = SqlAlchemyEpisodeWork(db)
        pending = works.list(job_id=batch.job_id, setting=batch.setting)
        if not pending and batch.candidates:
            bundles = build_episode_job_inputs(db, batch, now=clock(), prior_search=prior_search)
            pending = works.plan(job_id=batch.job_id, setting=batch.setting, bundles=bundles,
                candidate_ids=tuple(c.id for c in batch.candidates), now=clock(), job_fence=fence)
            repository.commit()
        service = EpisodeSelectionService(works=works, applier=SqlAlchemyEpisodeApply(db, repository.memory),
            detail_reader=RuntimeEpisodeDetailReader(db), revalidate=lambda value: revalidate_episode_bundle(db, value),
            commit=repository.commit, rollback=repository.rollback, clock=clock)
        while True:
            pending = works.list(job_id=batch.job_id, setting=batch.setting)
            next_work = next((row for row in pending if row.state not in {"completed", "split"}), None)
            if next_work is None:
                break
            if foreground_active is not None and foreground_active(db, now=clock()):
                repository.defer_foreground(batch, now=clock())
                repository.commit()
                return "memory_foreground_deferred"
            provider = provider_factory(batch.setting.scope.owner_id, batch.model_id, batch.thinking_level)
            if hasattr(provider, "phase_observer"):
                def observe(phase):
                    # Best-effort telemetry uses a separate short transaction;
                    # failures must never reissue a successfully completed AI call.
                    from sqlalchemy.orm import Session
                    from app.domains.memory.repository.consolidation_requests import set_phase
                    try:
                        with Session(db.get_bind()) as telemetry:
                            set_phase(telemetry, job_id=batch.job_id, phase=phase, now=clock(),
                                work_id=next_work.id, call_number=next_work.calls + 1, lease_token=batch.lease_token)
                            telemetry.commit()
                    except Exception:
                        logging.getLogger(__name__).warning("memory_phase_record_unavailable")
                provider.phase_observer = observe
            code = await service.run_work(work=next_work, setting=batch.setting, provider=provider,
                model_id=batch.model_id, thinking_level=batch.thinking_level, profile_version=batch.profile_version,
                timeout=timeout, job_fence=fence)
            if code not in {"episode_selection_completed", "episode_needs_split", "episode_work_already_processed"}:
                raise MemoryConflictError(code)
            # Release the event loop between committed units. There is no open
            # writer transaction during model generation or this yield.
            await asyncio.sleep(0)
        fence()
        complete_episode_candidates(repository, batch, pending, now=clock())
        usage = works.usage(job_id=batch.job_id, setting=batch.setting)
        repository.commit()
        logging.getLogger(__name__).info("episode_batch_completed", extra={"episode_usage": usage})
        return "memory_selection_completed"
    except BaseException as error:
        repository.rollback()
        code = str(error) if isinstance(error, MemoryDomainError) else "memory_selection_provider_failed"
        if isinstance(error, asyncio.CancelledError):
            code = "memory_selection_interrupted"
        elif isinstance(error, TimeoutError):
            code = "memory_selection_timeout"
        if code == "memory_capacity_reached":
            repository.defer_capacity(batch, now=clock())
        else:
            repository.fail(batch, code=code, now=clock())
        repository.commit()
        if not isinstance(error, Exception) or isinstance(error, asyncio.CancelledError):
            raise
        return code
