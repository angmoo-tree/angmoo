"""Bounded consolidation and derived hot-brief contracts for Memory v1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import hashlib

from app.domains.memory.domain.errors import MemoryValidationError
from app.domains.memory.domain.lifecycle import (
    MemoryCandidateRecord,
    MemoryItemRecord,
    as_utc,
    normalize_memory_summary,
)
from app.domains.memory.domain.scope import MemoryScopeSetting


MEMORY_CONSOLIDATION_CONTRACT_VERSION = "memory-consolidation.v1"
MEMORY_HOT_BRIEF_CONTRACT_VERSION = "memory-hot-brief.v1"
MAX_MAINTENANCE_BATCH_CANDIDATES = 32
MAX_HOT_BRIEF_SOURCE_ITEMS = 24
MAX_HOT_BRIEF_SUMMARY_LENGTH = 4_000
MAX_MAINTENANCE_PROVIDER_INPUT_CHARACTERS = 12_000
MAX_MAINTENANCE_ATTEMPTS = 3
MAX_SHUTDOWN_DRAIN_JOBS = 8
MAINTENANCE_LEASE_DURATION = timedelta(minutes=2)


class MemoryMaintenanceLane(str, Enum):
    AUTOMATIC = "automatic"
    IMMEDIATE = "immediate"


class MemoryConsolidationOutcome(str, Enum):
    NOT_DUE = "not_due"
    ENQUEUED = "enqueued"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    SKIPPED = "skipped"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MemoryConsolidationPolicy:
    """Reviewed v1 thresholds; callers cannot silently substitute defaults."""

    pending_candidate_threshold: int
    pending_character_threshold: int
    minimum_interval: timedelta
    active_item_refresh_threshold: int

    def __post_init__(self) -> None:
        if not 1 <= self.pending_candidate_threshold <= MAX_MAINTENANCE_BATCH_CANDIDATES:
            raise MemoryValidationError("memory_consolidation_candidate_threshold_invalid")
        if not 1 <= self.pending_character_threshold <= MAX_MAINTENANCE_PROVIDER_INPUT_CHARACTERS:
            raise MemoryValidationError("memory_consolidation_character_threshold_invalid")
        if self.minimum_interval < timedelta(minutes=1) or self.minimum_interval > timedelta(days=1):
            raise MemoryValidationError("memory_consolidation_interval_invalid")
        if not 1 <= self.active_item_refresh_threshold <= MAX_HOT_BRIEF_SOURCE_ITEMS:
            raise MemoryValidationError("memory_hot_brief_refresh_threshold_invalid")


# These values are intentionally named and inventory-frozen.  They are not
# hidden environment defaults; changing one requires a contract/inventory PR.
MEMORY_CONSOLIDATION_POLICY_V1 = MemoryConsolidationPolicy(
    pending_candidate_threshold=8,
    pending_character_threshold=4_000,
    minimum_interval=timedelta(minutes=15),
    active_item_refresh_threshold=16,
)


@dataclass(frozen=True, slots=True)
class MemoryMaintenanceSnapshot:
    setting: MemoryScopeSetting
    pending_candidates: tuple[MemoryCandidateRecord, ...]
    pending_count: int
    active_item_count: int
    pending_high_watermark: str | None
    last_consolidated_at: datetime | None
    active_hot_brief_valid: bool

    def __post_init__(self) -> None:
        if self.pending_count < len(self.pending_candidates) or self.pending_count < 0:
            raise MemoryValidationError("memory_pending_count_invalid")
        if self.active_item_count < 0:
            raise MemoryValidationError("memory_active_item_count_invalid")


@dataclass(frozen=True, slots=True)
class MemoryConsolidationDecision:
    due: bool
    reason: str
    lane: MemoryMaintenanceLane
    idempotency_key: str | None


@dataclass(frozen=True, slots=True)
class MemoryConsolidationScheduleResult:
    outcome: MemoryConsolidationOutcome
    code: str
    lane: MemoryMaintenanceLane
    job_id: str | None = None
    provider_call_count: int = 0


@dataclass(frozen=True, slots=True)
class MemoryHotBriefRecord:
    id: str
    scope_setting_id: str
    summary: str
    generation: int
    source_item_high_watermark: str
    source_item_set_digest: str
    contract_version: str
    generated_at: datetime
    source_items: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class MemoryMaintenanceProviderTelemetry:
    provider: str
    model: str
    physical_call_count: int
    prompt_token_count: int | None
    output_token_count: int | None
    total_token_count: int | None
    latency_ms: int | None

    def __post_init__(self) -> None:
        if self.physical_call_count != 1:
            raise MemoryValidationError("memory_provider_telemetry_call_count_invalid")


@dataclass(frozen=True, slots=True)
class MemoryConsolidationRunResult:
    outcome: MemoryConsolidationOutcome
    code: str
    job_id: str | None = None
    lane: MemoryMaintenanceLane | None = None
    accepted_item_ids: tuple[str, ...] = ()
    rejected_candidate_ids: tuple[str, ...] = ()
    hot_brief: MemoryHotBriefRecord | None = None
    provider_call_count: int = 0
    provider_failure_code: str | None = None
    provider_telemetry: MemoryMaintenanceProviderTelemetry | None = None
    continuation_job_id: str | None = None


def evaluate_memory_consolidation(
    snapshot: MemoryMaintenanceSnapshot,
    *,
    pending_character_count: int,
    now: datetime,
    policy: MemoryConsolidationPolicy,
    lane: MemoryMaintenanceLane = MemoryMaintenanceLane.AUTOMATIC,
    request_key: str | None = None,
) -> MemoryConsolidationDecision:
    """Choose one deterministic lane without invoking a provider."""

    if not snapshot.setting.enabled:
        return MemoryConsolidationDecision(False, "memory_opt_out", lane, None)
    if pending_character_count < 0:
        raise MemoryValidationError("memory_pending_character_count_invalid")
    if lane is MemoryMaintenanceLane.IMMEDIATE:
        if not request_key or len(request_key.strip()) > 128:
            raise MemoryValidationError("memory_immediate_request_key_invalid")
        reason = "explicit_memory_request"
        material = request_key.strip()
    elif snapshot.pending_count >= policy.pending_candidate_threshold:
        reason = "pending_candidate_threshold"
        material = snapshot.pending_high_watermark or str(snapshot.pending_count)
    elif pending_character_count >= policy.pending_character_threshold:
        reason = "pending_character_threshold"
        material = snapshot.pending_high_watermark or str(pending_character_count)
    elif (
        snapshot.pending_count > 0
        and snapshot.last_consolidated_at is not None
        and as_utc(now) - as_utc(snapshot.last_consolidated_at) >= policy.minimum_interval
    ):
        reason = "minimum_interval_elapsed"
        material = snapshot.pending_high_watermark or str(snapshot.pending_count)
    elif (
        snapshot.active_item_count >= policy.active_item_refresh_threshold
        and not snapshot.active_hot_brief_valid
    ):
        reason = "hot_brief_refresh"
        material = snapshot.pending_high_watermark or str(snapshot.active_item_count)
    else:
        return MemoryConsolidationDecision(False, "memory_consolidation_not_due", lane, None)

    digest = hashlib.sha256(
        "\x1f".join(
            (
                MEMORY_CONSOLIDATION_CONTRACT_VERSION,
                snapshot.setting.id,
                str(snapshot.setting.version),
                lane.value,
                reason,
                material,
            )
        ).encode("utf-8")
    ).hexdigest()
    return MemoryConsolidationDecision(
        True,
        reason,
        lane,
        f"mc1:{digest}",
    )


def memory_item_set_digest(items: tuple[MemoryItemRecord, ...]) -> str:
    material = "\n".join(f"{item.id}:{item.version}" for item in items)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def memory_item_high_watermark(items: tuple[MemoryItemRecord, ...]) -> str:
    if not items:
        return "empty"
    latest = max(items, key=lambda item: (as_utc(item.updated_at), item.id))
    return f"{as_utc(latest.updated_at).isoformat()}|{latest.id}"


def deterministic_hot_brief(items: tuple[MemoryItemRecord, ...]) -> str:
    if not items:
        return "기억으로 정리된 항목이 아직 없습니다."
    lines: list[str] = []
    used = 0
    for item in items[:MAX_HOT_BRIEF_SOURCE_ITEMS]:
        summary = normalize_memory_summary(item.summary)
        line = f"- [{item.memory_kind.value}] {summary}"
        addition = len(line) + (1 if lines else 0)
        if used + addition > MAX_HOT_BRIEF_SUMMARY_LENGTH:
            break
        lines.append(line)
        used += addition
    if not lines:
        # A single canonical summary can be longer than the brief budget while
        # still valid as an item.  Preserve a bounded deterministic prefix.
        first = normalize_memory_summary(items[0].summary)
        return first[:MAX_HOT_BRIEF_SUMMARY_LENGTH].rstrip()
    return "\n".join(lines)


def validate_consolidation_summary(value: str) -> str:
    return normalize_memory_summary(value)


__all__ = [
    "MAINTENANCE_LEASE_DURATION",
    "MAX_HOT_BRIEF_SOURCE_ITEMS",
    "MAX_HOT_BRIEF_SUMMARY_LENGTH",
    "MAX_MAINTENANCE_ATTEMPTS",
    "MAX_MAINTENANCE_BATCH_CANDIDATES",
    "MAX_MAINTENANCE_PROVIDER_INPUT_CHARACTERS",
    "MAX_SHUTDOWN_DRAIN_JOBS",
    "MEMORY_CONSOLIDATION_CONTRACT_VERSION",
    "MEMORY_CONSOLIDATION_POLICY_V1",
    "MEMORY_HOT_BRIEF_CONTRACT_VERSION",
    "MemoryConsolidationDecision",
    "MemoryConsolidationOutcome",
    "MemoryConsolidationPolicy",
    "MemoryConsolidationRunResult",
    "MemoryConsolidationScheduleResult",
    "MemoryHotBriefRecord",
    "MemoryMaintenanceLane",
    "MemoryMaintenanceProviderTelemetry",
    "MemoryMaintenanceSnapshot",
    "deterministic_hot_brief",
    "evaluate_memory_consolidation",
    "memory_item_high_watermark",
    "memory_item_set_digest",
    "validate_consolidation_summary",
]
