"""AI selection on the canonical maintenance queue, with fail-closed commits."""

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime

from app.domains.memory.application.write_lifecycle import (
    MemoryWriteLifecycleService,
    memory_evidence_blocked_code,
)
from app.domains.memory.domain.batch_policy import (
    MAX_SELECTION_INPUT_CHARACTERS,
    MAX_SELECTION_INPUT_UTF8_BYTES,
    MEMORY_PROVIDER_TIMEOUT_SECONDS,
)
from app.domains.memory.domain.errors import MemoryDomainError, MemoryValidationError
from app.domains.memory.domain.selection import MemorySelectionSource
from app.domains.memory.ports.batch import (
    MemoryBatchRepositoryPort,
    MemorySelectionProviderPort,
)
from app.domains.memory.ports.source_reader import MemorySourceEvidenceReaderPort


class MemoryBatchSelectionService:
    def __init__(
        self,
        *,
        repository: MemoryBatchRepositoryPort,
        source_reader: MemorySourceEvidenceReaderPort,
        write_lifecycle: MemoryWriteLifecycleService,
        provider_factory: Callable[[str, str], MemorySelectionProviderPort],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.reader = source_reader
        self.writer = write_lifecycle
        self.provider_factory = provider_factory
        self.clock = clock or (lambda: datetime.now(UTC))

    async def run_next(
        self, *, lease_token: str, timeout: float = MEMORY_PROVIDER_TIMEOUT_SECONDS
    ) -> str:
        repo = self.repository
        batch = repo.claim(lease_token=lease_token, now=self.clock())
        if batch is None:
            repo.commit()
            return "memory_batch_queue_empty"
        repo.commit()
        try:
            eligible = []
            sources = []
            invalid = []
            for candidate in batch.candidates:
                evidence = self.reader.read_evidence(
                    scope=batch.setting.scope,
                    source_type=candidate.source_type,
                    source_id=candidate.source_id,
                )
                code = memory_evidence_blocked_code(
                    scope=batch.setting.scope,
                    source_type=candidate.source_type,
                    source_id=candidate.source_id,
                    evidence=evidence,
                )
                if (
                    code is not None
                    or evidence is None
                    or evidence.source_digest != candidate.source_digest
                ):
                    invalid.append((candidate, code or "memory_source_digest_conflict"))
                    continue
                # Different private conversations never share a provider prompt.
                if eligible and evidence.thread_id != eligible[0][1].thread_id:
                    raise MemoryValidationError(
                        "memory_selection_privacy_partition_invalid"
                    )
                eligible.append((candidate, evidence))
                number = len(sources) + 1
                text = evidence.deterministic_summary
                # Metadata IDs never become natural-language memory content.
                for identity in (
                    batch.setting.scope.owner_id,
                    batch.setting.scope.world_id,
                    batch.setting.scope.subject_world_character_id,
                    evidence.actor_world_character_id,
                    evidence.target_world_character_id,
                    candidate.source_id,
                ):
                    if identity and len(str(identity)) > 8:
                        text = text.replace(str(identity), "[참여자/근거]")
                sources.append(
                    MemorySelectionSource(
                        f"candidate-{number}",
                        f"source-{number}",
                        candidate.memory_kind_hint.value,
                        text,
                        evidence.subjective_context,
                    )
                )
            texts = [
                source.text + (source.subjective_context or "") for source in sources
            ]
            if (
                sum(len(text) for text in texts) > MAX_SELECTION_INPUT_CHARACTERS
                or sum(len(text.encode("utf-8")) for text in texts)
                > MAX_SELECTION_INPUT_UTF8_BYTES
            ):
                raise MemoryValidationError("memory_selection_input_budget_exceeded")
            decisions = ()
            if sources:
                provider = self.provider_factory(
                    batch.setting.scope.owner_id, batch.model_id
                )
                validator = getattr(provider, "validate_sources", None)
                if validator is not None:
                    validator(tuple(sources))
                repo.record_call(batch, now=self.clock())
                repo.commit()
                started = time.monotonic()
                async with asyncio.timeout(
                    max(0.1, min(timeout, MEMORY_PROVIDER_TIMEOUT_SECONDS))
                ):
                    decisions = await provider.select(tuple(sources), timeout=timeout)
                repo.record_telemetry(
                    batch,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    usage=getattr(provider, "usage", None),
                )
                # Treat a faulty in-process adapter as untrusted too.
                if len(decisions) != len(sources) or {
                    d.candidate_ref for d in decisions
                } != {s.candidate_ref for s in sources}:
                    raise MemoryValidationError("memory_selection_decisions_incomplete")
            repo.fence(batch, now=self.clock())
            for candidate, code in invalid:
                self.writer.reject_candidate(
                    scope=batch.setting.scope,
                    candidate_id=candidate.id,
                    expected_candidate_version=candidate.version,
                    reason_code=code,
                    now=self.clock(),
                )
                repo.record_decision(
                    batch,
                    candidate,
                    decision="invalidated",
                    reason=code,
                    item_id=None,
                    now=self.clock(),
                )
            by_ref = {d.candidate_ref: d for d in decisions}
            for index, (candidate, _evidence) in enumerate(eligible, 1):
                current = self.reader.read_evidence(
                    scope=batch.setting.scope,
                    source_type=candidate.source_type,
                    source_id=candidate.source_id,
                )
                if (
                    current is None
                    or current.source_digest != candidate.source_digest
                    or memory_evidence_blocked_code(
                        scope=batch.setting.scope,
                        source_type=candidate.source_type,
                        source_id=candidate.source_id,
                        evidence=current,
                    )
                    is not None
                ):
                    raise MemoryValidationError("memory_selection_source_changed")
                decision = by_ref[f"candidate-{index}"]
                item_id = None
                if decision.decision == "retain" and decision.summary:
                    result = self.writer.accept_candidate(
                        scope=batch.setting.scope,
                        candidate_id=candidate.id,
                        expected_candidate_version=candidate.version,
                        expected_scope_version=batch.scope_version,
                        summary_proposal=decision.summary,
                        enqueue_maintenance=False,
                        now=self.clock(),
                    )
                    if result.item is None:
                        raise MemoryValidationError("memory_selection_source_changed")
                    item_id = result.item.id
                elif decision.decision == "skip" and decision.summary is None:
                    # A rejected candidate with this explicit terminal reason is
                    # a normal AI skip, not a failed provider request.
                    self.writer.reject_candidate(
                        scope=batch.setting.scope,
                        candidate_id=candidate.id,
                        expected_candidate_version=candidate.version,
                        reason_code="memory_selection_skipped",
                        now=self.clock(),
                    )
                else:
                    raise MemoryValidationError("memory_selection_output_invalid")
                repo.record_decision(
                    batch,
                    candidate,
                    decision=decision.decision,
                    reason=decision.reason_code,
                    item_id=item_id,
                    now=self.clock(),
                )
            repo.complete(batch, now=self.clock())
            repo.commit()
            return "memory_selection_completed"
        except BaseException as exc:
            repo.rollback()
            code = (
                str(exc)
                if isinstance(exc, MemoryDomainError)
                else "memory_selection_provider_failed"
            )
            if isinstance(exc, asyncio.CancelledError):
                code = "memory_selection_interrupted"
            if (
                not code.startswith("memory_")
                or len(code) > 80
                or not code.replace("_", "").isalnum()
            ):
                code = "memory_selection_failed"
            repo.fail(batch, code=code, now=self.clock())
            repo.commit()
            if isinstance(exc, asyncio.CancelledError):
                raise
            if not isinstance(exc, Exception):
                raise
            return code
