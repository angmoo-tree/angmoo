"""One bounded provider call, fenced application and durable per-input progress."""

import asyncio
import logging
from datetime import UTC, datetime
from time import monotonic

from app.domains.memory.exceptions import MemoryDomainError
from app.domains.memory.service.episode_manifest import restore_episode_input

logger = logging.getLogger(__name__)


class EpisodeSelectionService:
    def __init__(self, *, works, applier, detail_reader, revalidate, commit, rollback, clock=None):
        self.works, self.applier, self.details = works, applier, detail_reader
        self.revalidate, self.commit, self.rollback = revalidate, commit, rollback
        self.clock = clock or (lambda: datetime.now(UTC))

    async def run_work(self, *, work, setting, provider, model_id, thinking_level, profile_version,
                       timeout, job_fence):
        if work.state in {"completed", "split"}:
            return "episode_work_already_processed"
        number = None
        started = monotonic()
        try:
            job_fence()
            bundle = restore_episode_input(work.manifest, scope=setting.scope, detail_reader=self.details)
            provider.validate_bundle(bundle)
            number = self.works.start_call(work, model_id=model_id, thinking_level=thinking_level,
                profile_version=profile_version, now=self.clock(), job_fence=job_fence)
            self.commit()
            async with asyncio.timeout(max(0.1, min(timeout, 180))):
                selection = await provider.select(bundle, timeout=max(0.1, min(timeout, 180)))
            validate = getattr(provider, "validate_credential", None)
            if validate:
                validate()
            job_fence()
            self.works.finish_call(work, call_number=number, code="episode_selection_completed",
                elapsed_ms=(monotonic() - started) * 1000, usage=getattr(provider, "usage", None), job_fence=job_fence,
                physical_calls=getattr(provider, "physical_calls", None))
            if selection.needs_split:
                self.works.split(work, bundle=bundle, setting=setting, now=self.clock(), job_fence=job_fence)
                result = "episode_needs_split"
            else:
                self.applier.apply(bundle=bundle, selection=selection, setting=setting, now=self.clock(),
                    revalidate=self.revalidate, job_fence=job_fence)
                result = "episode_selection_completed"
            self.commit()
            logger.info("episode_selection_result", extra={"episode_result": result,
                "episode_elapsed_ms": int((monotonic() - started) * 1000),
                "episode_physical_calls": getattr(provider, "physical_calls", None),
                "episode_new_units": len(bundle.new_units), "episode_context_units": len(bundle.context_units),
                "episode_created_count": len(selection.episodes)})
            return result
        except BaseException as error:
            self.rollback()
            code = str(error) if isinstance(error, MemoryDomainError) else "episode_provider_failed"
            if isinstance(error, asyncio.CancelledError):
                code = "episode_interrupted"
            elif isinstance(error, TimeoutError):
                code = "episode_timeout"
            if number is not None:
                try:
                    self.works.finish_call(work, call_number=number, code=code,
                        elapsed_ms=(monotonic() - started) * 1000, usage=getattr(provider, "usage", None), job_fence=job_fence,
                        physical_calls=getattr(provider, "physical_calls", None))
                    self.commit()
                except MemoryDomainError:
                    # A lost lease/changed scope cannot write a success or late
                    # failure. Its already committed attempt still survives.
                    self.rollback()
            if not isinstance(error, Exception) or isinstance(error, asyncio.CancelledError):
                raise
            return code
