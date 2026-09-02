"""Bounded background Memory consolidation and hot-brief orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import hashlib

from app.domains.memory.application.write_lifecycle import (
    MemoryWriteLifecycleService,
    memory_evidence_blocked_code,
)
from app.domains.memory.domain.consolidation import (
    MAINTENANCE_LEASE_DURATION,
    MAX_HOT_BRIEF_SOURCE_ITEMS,
    MAX_MAINTENANCE_ATTEMPTS,
    MAX_MAINTENANCE_BATCH_CANDIDATES,
    MAX_MAINTENANCE_PROVIDER_INPUT_CHARACTERS,
    MAX_SHUTDOWN_DRAIN_JOBS,
    MEMORY_CONSOLIDATION_CONTRACT_VERSION,
    MEMORY_CONSOLIDATION_POLICY_V1,
    MEMORY_HOT_BRIEF_CONTRACT_VERSION,
    MemoryConsolidationOutcome,
    MemoryConsolidationPolicy,
    MemoryConsolidationRunResult,
    MemoryConsolidationScheduleResult,
    MemoryMaintenanceLane,
    MemoryMaintenanceProviderTelemetry,
    deterministic_hot_brief,
    evaluate_memory_consolidation,
    validate_consolidation_summary,
)
from app.domains.memory.domain.errors import MemoryConflictError, MemoryDomainError
from app.domains.memory.domain.lifecycle import (
    as_utc,
    validate_source_digest,
    validate_source_kind,
)
from app.domains.memory.domain.policies import validate_memory_item_shape
from app.domains.memory.domain.provenance import MemoryProviderMode
from app.domains.memory.ports.consolidation_provider import (
    MemoryConsolidationProviderError,
    MemoryConsolidationProviderPort,
    MemoryConsolidationProviderRequest,
    MemoryConsolidationSource,
)
from app.domains.memory.ports.consolidation_repository import (
    MemoryConsolidationRepositoryPort,
)
from app.domains.memory.ports.maintenance_queue import MemoryMaintenanceQueuePort
from app.domains.memory.ports.maintenance_unit_of_work import (
    MemoryMaintenanceUnitOfWorkPort,
)
from app.domains.memory.ports.source_reader import MemorySourceEvidenceReaderPort


class MemoryConsolidationService:
    """Code owns threshold, scope, acceptance, retry, and derived cache writes."""

    def __init__(
        self,
        *,
        repository: MemoryConsolidationRepositoryPort,
        queue: MemoryMaintenanceQueuePort,
        unit_of_work: MemoryMaintenanceUnitOfWorkPort,
        source_reader: MemorySourceEvidenceReaderPort,
        write_lifecycle: MemoryWriteLifecycleService,
        provider: MemoryConsolidationProviderPort | None = None,
        policy: MemoryConsolidationPolicy = MEMORY_CONSOLIDATION_POLICY_V1,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._queue = queue
        self._unit_of_work = unit_of_work
        self._source_reader = source_reader
        self._write_lifecycle = write_lifecycle
        self._provider = provider
        self._policy = policy
        self._clock = clock or (lambda: datetime.now(UTC))

    def schedule_if_due(
        self,
        *,
        scope_setting_id: str,
        now: datetime | None = None,
    ) -> MemoryConsolidationScheduleResult:
        return self._schedule(
            scope_setting_id=scope_setting_id,
            lane=MemoryMaintenanceLane.AUTOMATIC,
            request_key=None,
            now=now,
        )

    def schedule_immediate(
        self,
        *,
        scope_setting_id: str,
        request_key: str,
        now: datetime | None = None,
    ) -> MemoryConsolidationScheduleResult:
        """Use a separate idempotent lane for an explicit remember request."""

        return self._schedule(
            scope_setting_id=scope_setting_id,
            lane=MemoryMaintenanceLane.IMMEDIATE,
            request_key=request_key,
            now=now,
        )

    async def run_next(
        self,
        *,
        lease_token: str,
    ) -> MemoryConsolidationRunResult:
        claimed_at = as_utc(self._clock())
        work = self._queue.claim(
            lease_token=lease_token,
            now=claimed_at,
            lease_for=MAINTENANCE_LEASE_DURATION,
        )
        if work is None:
            self._unit_of_work.rollback()
            return MemoryConsolidationRunResult(
                outcome=MemoryConsolidationOutcome.SKIPPED,
                code="memory_maintenance_queue_empty",
            )
        self._unit_of_work.commit()
        lane = _lane_for_reason(work.reason)
        provider_call_count = 0
        provider_failure_code: str | None = None
        provider_telemetry: MemoryMaintenanceProviderTelemetry | None = None
        accepted_ids: list[str] = []
        rejected_ids: list[str] = []
        try:
            setting = self._repository.get_scope_setting_by_id(work.scope_setting_id)
            if setting is None or not setting.enabled:
                self._queue.complete(
                    job_id=work.job_id,
                    lease_token=lease_token,
                    now=as_utc(self._clock()),
                )
                self._unit_of_work.commit()
                return MemoryConsolidationRunResult(
                    outcome=MemoryConsolidationOutcome.SKIPPED,
                    code="memory_opt_out" if setting is not None else "memory_scope_missing",
                    job_id=work.job_id,
                    lane=lane,
                )

            snapshot = self._repository.maintenance_snapshot(
                scope_setting_id=setting.id,
                now=as_utc(self._clock()),
                candidate_limit=MAX_MAINTENANCE_BATCH_CANDIDATES,
            )
            eligible = []
            for candidate in snapshot.pending_candidates:
                evidence = self._source_reader.read_evidence(
                    scope=setting.scope,
                    source_type=candidate.source_type,
                    source_id=candidate.source_id,
                )
                blocked_code = memory_evidence_blocked_code(
                    scope=setting.scope,
                    source_type=candidate.source_type,
                    source_id=candidate.source_id,
                    evidence=evidence,
                )
                if blocked_code is None and evidence is not None:
                    try:
                        validate_source_kind(
                            source_type=candidate.source_type,
                            memory_kind=candidate.memory_kind_hint,
                        )
                        if (
                            validate_source_digest(evidence.source_digest)
                            != candidate.source_digest
                        ):
                            raise MemoryConflictError(
                                "memory_source_digest_conflict"
                            )
                        validate_memory_item_shape(
                            kind=candidate.memory_kind_hint,
                            counterpart_world_character_id=(
                                evidence.counterpart_world_character_id
                            ),
                            thread_id=evidence.thread_id,
                        )
                    except MemoryDomainError as exc:
                        blocked_code = _safe_error_code(exc)
                if blocked_code is not None:
                    self._write_lifecycle.reject_candidate(
                        scope=setting.scope,
                        candidate_id=candidate.id,
                        expected_candidate_version=candidate.version,
                        reason_code=blocked_code,
                        now=as_utc(self._clock()),
                    )
                    rejected_ids.append(candidate.id)
                    continue
                assert evidence is not None
                eligible.append((candidate, evidence))

            provider_sources, provider_refs = _provider_sources(eligible)
            proposals: dict[str, str] = {}
            if (
                setting.provider_mode is MemoryProviderMode.OPTIONAL_CONFIGURED
                and provider_sources
            ):
                if self._provider is None:
                    provider_failure_code = "memory_maintenance_provider_unavailable"
                else:
                    # Commit canonical rejections and the renewed lease before
                    # waiting on external work.  The source is re-read below.
                    renewed_at = as_utc(self._clock())
                    self._queue.renew(
                        job_id=work.job_id,
                        lease_token=lease_token,
                        now=renewed_at,
                        lease_for=MAINTENANCE_LEASE_DURATION,
                    )
                    self._unit_of_work.commit()
                    try:
                        provider_result = await self._provider.consolidate(
                            MemoryConsolidationProviderRequest(
                                batch_ref=f"maintenance-{work.job_id}",
                                lane=lane,
                                sources=provider_sources,
                            )
                        )
                        if provider_result.physical_call_count != 1:
                            raise MemoryConsolidationProviderError(
                                "memory_maintenance_provider_call_count_invalid",
                                physical_call_count=provider_result.physical_call_count,
                            )
                        provider_call_count = 1
                        provider_telemetry = MemoryMaintenanceProviderTelemetry(
                            provider=provider_result.provider,
                            model=provider_result.model,
                            physical_call_count=1,
                            prompt_token_count=provider_result.prompt_token_count,
                            output_token_count=provider_result.output_token_count,
                            total_token_count=provider_result.total_token_count,
                            latency_ms=provider_result.latency_ms,
                        )
                        proposals = _validated_proposals(
                            provider_result.proposals,
                            allowed_refs=frozenset(provider_refs.values()),
                        )
                    except MemoryConsolidationProviderError as exc:
                        provider_call_count = min(1, max(0, exc.physical_call_count))
                        provider_failure_code = exc.code
                    except Exception:
                        provider_call_count = 1
                        provider_failure_code = "memory_maintenance_provider_failed"

            for candidate, _evidence in eligible:
                provider_ref = provider_refs.get(candidate.id)
                result = self._write_lifecycle.accept_candidate(
                    scope=setting.scope,
                    candidate_id=candidate.id,
                    expected_candidate_version=candidate.version,
                    expected_scope_version=setting.version,
                    summary_proposal=(
                        None if provider_ref is None else proposals.get(provider_ref)
                    ),
                    enqueue_maintenance=False,
                    now=as_utc(self._clock()),
                )
                if result.item is not None:
                    accepted_ids.append(result.item.id)
                elif result.candidate is not None:
                    rejected_ids.append(result.candidate.id)

            # Re-read setting and selected items after provider latency and
            # source acceptance.  replace_hot_brief fences exact item versions.
            current_setting = self._repository.get_scope_setting_by_id(setting.id)
            if (
                current_setting is None
                or not current_setting.enabled
                or current_setting.version != setting.version
            ):
                raise MemoryConflictError("memory_scope_changed_during_maintenance")
            source_items = self._repository.hot_brief_source_items(
                setting=current_setting,
                now=as_utc(self._clock()),
                limit=MAX_HOT_BRIEF_SOURCE_ITEMS,
            )
            hot_brief = None
            if source_items:
                hot_brief = self._repository.replace_hot_brief(
                    setting=current_setting,
                    expected_source_items=source_items,
                    summary=deterministic_hot_brief(source_items),
                    contract_version=MEMORY_HOT_BRIEF_CONTRACT_VERSION,
                    now=as_utc(self._clock()),
                )
            continuation_job_id = self._enqueue_batch_continuation_if_pending(
                scope_setting_id=current_setting.id,
                expected_scope_version=current_setting.version,
                now=as_utc(self._clock()),
            )
            self._queue.complete(
                job_id=work.job_id,
                lease_token=lease_token,
                now=as_utc(self._clock()),
            )
            self._unit_of_work.commit()
            return MemoryConsolidationRunResult(
                outcome=(
                    MemoryConsolidationOutcome.DEGRADED
                    if provider_failure_code is not None
                    else MemoryConsolidationOutcome.COMPLETED
                ),
                code=(
                    "memory_maintenance_completed_with_deterministic_fallback"
                    if provider_failure_code is not None
                    else "memory_maintenance_completed"
                ),
                job_id=work.job_id,
                lane=lane,
                accepted_item_ids=tuple(accepted_ids),
                rejected_candidate_ids=tuple(rejected_ids),
                hot_brief=hot_brief,
                provider_call_count=provider_call_count,
                provider_failure_code=provider_failure_code,
                provider_telemetry=provider_telemetry,
                continuation_job_id=continuation_job_id,
            )
        except Exception as exc:
            self._unit_of_work.rollback()
            retryable = work.attempt_count < MAX_MAINTENANCE_ATTEMPTS
            failure_code = _safe_error_code(exc)
            self._queue.fail(
                job_id=work.job_id,
                lease_token=lease_token,
                error_code=failure_code,
                retryable=retryable,
                now=as_utc(self._clock()),
            )
            self._unit_of_work.commit()
            return MemoryConsolidationRunResult(
                outcome=(
                    MemoryConsolidationOutcome.RETRY_SCHEDULED
                    if retryable
                    else MemoryConsolidationOutcome.FAILED
                ),
                code=failure_code,
                job_id=work.job_id,
                lane=lane,
                provider_call_count=provider_call_count,
                provider_failure_code=provider_failure_code,
                provider_telemetry=provider_telemetry,
            )

    async def drain(
        self,
        *,
        lease_token_prefix: str,
        deadline: datetime,
        max_jobs: int = MAX_SHUTDOWN_DRAIN_JOBS,
    ) -> tuple[MemoryConsolidationRunResult, ...]:
        if max_jobs < 1 or max_jobs > MAX_SHUTDOWN_DRAIN_JOBS:
            raise ValueError("memory_shutdown_drain_limit_invalid")
        prefix = lease_token_prefix.strip()
        if not prefix or len(prefix) > 48:
            raise ValueError("memory_shutdown_lease_prefix_invalid")
        results: list[MemoryConsolidationRunResult] = []
        for index in range(max_jobs):
            if as_utc(self._clock()) >= as_utc(deadline):
                break
            result = await self.run_next(lease_token=f"{prefix}-{index + 1}")
            if result.job_id is None:
                break
            results.append(result)
        return tuple(results)

    def _schedule(
        self,
        *,
        scope_setting_id: str,
        lane: MemoryMaintenanceLane,
        request_key: str | None,
        now: datetime | None,
    ) -> MemoryConsolidationScheduleResult:
        evaluated_at = as_utc(now or self._clock())
        snapshot = self._repository.maintenance_snapshot(
            scope_setting_id=scope_setting_id,
            now=evaluated_at,
            candidate_limit=MAX_MAINTENANCE_BATCH_CANDIDATES,
        )
        if not snapshot.setting.enabled:
            self._unit_of_work.rollback()
            return MemoryConsolidationScheduleResult(
                outcome=MemoryConsolidationOutcome.NOT_DUE,
                code="memory_opt_out",
                lane=lane,
            )
        pending_characters = 0
        for candidate in snapshot.pending_candidates:
            evidence = self._source_reader.read_evidence(
                scope=snapshot.setting.scope,
                source_type=candidate.source_type,
                source_id=candidate.source_id,
            )
            if (
                memory_evidence_blocked_code(
                    scope=snapshot.setting.scope,
                    source_type=candidate.source_type,
                    source_id=candidate.source_id,
                    evidence=evidence,
                )
                is None
                and evidence is not None
            ):
                pending_characters += len(evidence.deterministic_summary)
        decision = evaluate_memory_consolidation(
            snapshot,
            pending_character_count=pending_characters,
            now=evaluated_at,
            policy=self._policy,
            lane=lane,
            request_key=request_key,
        )
        if not decision.due:
            self._unit_of_work.rollback()
            return MemoryConsolidationScheduleResult(
                outcome=MemoryConsolidationOutcome.NOT_DUE,
                code=decision.reason,
                lane=lane,
            )
        assert decision.idempotency_key is not None
        try:
            job_id = self._queue.enqueue(
                scope_setting_id=snapshot.setting.id,
                reason=decision.reason,
                idempotency_key=decision.idempotency_key,
            )
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise
        return MemoryConsolidationScheduleResult(
            outcome=MemoryConsolidationOutcome.ENQUEUED,
            code=decision.reason,
            lane=lane,
            job_id=job_id,
        )

    def _enqueue_batch_continuation_if_pending(
        self,
        *,
        scope_setting_id: str,
        expected_scope_version: int,
        now: datetime,
    ) -> str | None:
        """Drain every bounded batch, including a final sub-threshold tail."""

        snapshot = self._repository.maintenance_snapshot(
            scope_setting_id=scope_setting_id,
            now=now,
            candidate_limit=MAX_MAINTENANCE_BATCH_CANDIDATES,
        )
        if (
            not snapshot.setting.enabled
            or snapshot.setting.version != expected_scope_version
            or snapshot.pending_count == 0
        ):
            return None
        material = "\x1f".join(
            (
                MEMORY_CONSOLIDATION_CONTRACT_VERSION,
                snapshot.setting.id,
                str(snapshot.setting.version),
                "batch_continuation",
                snapshot.pending_high_watermark or str(snapshot.pending_count),
                str(snapshot.pending_count),
            )
        )
        idempotency_key = "mc1:" + hashlib.sha256(
            material.encode("utf-8")
        ).hexdigest()
        return self._queue.enqueue(
            scope_setting_id=snapshot.setting.id,
            reason="batch_continuation",
            idempotency_key=idempotency_key,
        )


def _provider_sources(eligible) -> tuple[tuple[MemoryConsolidationSource, ...], dict[str, str]]:
    sources: list[MemoryConsolidationSource] = []
    refs: dict[str, str] = {}
    used = 0
    for candidate, evidence in eligible:
        candidate_ref = f"candidate-{len(sources) + 1}"
        addition = len(evidence.deterministic_summary)
        if sources and used + addition > MAX_MAINTENANCE_PROVIDER_INPUT_CHARACTERS:
            break
        sources.append(
            MemoryConsolidationSource(
                candidate_ref=candidate_ref,
                memory_kind=candidate.memory_kind_hint.value,
                deterministic_summary=evidence.deterministic_summary,
            )
        )
        refs[candidate.id] = candidate_ref
        used += addition
    return tuple(sources), refs


def _validated_proposals(proposals, *, allowed_refs: frozenset[str]) -> dict[str, str]:
    rendered: dict[str, str] = {}
    for proposal in proposals:
        if proposal.candidate_ref not in allowed_refs:
            raise MemoryConsolidationProviderError(
                "memory_maintenance_provider_reference_invalid",
                physical_call_count=1,
            )
        if proposal.candidate_ref in rendered:
            raise MemoryConsolidationProviderError(
                "memory_maintenance_provider_duplicate_reference",
                physical_call_count=1,
            )
        rendered[proposal.candidate_ref] = validate_consolidation_summary(
            proposal.summary
        )
    return rendered


def _lane_for_reason(reason: str) -> MemoryMaintenanceLane:
    return (
        MemoryMaintenanceLane.IMMEDIATE
        if reason == "explicit_memory_request"
        else MemoryMaintenanceLane.AUTOMATIC
    )


def _safe_error_code(exc: BaseException) -> str:
    if isinstance(exc, MemoryDomainError):
        candidate = str(exc).strip()
        if candidate and len(candidate) <= 80 and candidate.replace("_", "").isalnum():
            return candidate
    return "memory_maintenance_internal_error"


__all__ = ["MemoryConsolidationService"]
