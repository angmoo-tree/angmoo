"""Typed canonical primitive registry and provider-free recall executor."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from app.domains.memory.domain.errors import MemoryValidationError
from app.domains.memory.domain.recall import (
    CanonicalRecallOperation,
    CanonicalRecallQuery,
    CanonicalRecallResult,
    CanonicalRecallStatus,
    MAX_CANONICAL_RECALL_RESULTS,
    MemoryRecallSearchQuery,
    RecallDocumentKind,
)
from app.domains.memory.ports.recall import (
    CanonicalRecallRepositoryPort,
    MemoryRecallIndexPort,
)


@dataclass(frozen=True, slots=True)
class CanonicalPrimitiveSpec:
    operation: CanonicalRecallOperation
    requires_text: bool = False
    requires_source_references: bool = False
    requires_character_references: bool = False
    projection_kinds: tuple[RecallDocumentKind, ...] = ()


CANONICAL_PRIMITIVE_REGISTRY = {
    CanonicalRecallOperation.SEARCH_THREAD_MESSAGES: CanonicalPrimitiveSpec(
        operation=CanonicalRecallOperation.SEARCH_THREAD_MESSAGES,
        requires_text=True,
        projection_kinds=(
            RecallDocumentKind.THREAD_MESSAGE,
            RecallDocumentKind.OWNER_MEMORY_REQUEST,
        ),
    ),
    CanonicalRecallOperation.SEARCH_POSTS: CanonicalPrimitiveSpec(
        operation=CanonicalRecallOperation.SEARCH_POSTS,
        requires_text=True,
        projection_kinds=(RecallDocumentKind.POST, RecallDocumentKind.REPLY),
    ),
    CanonicalRecallOperation.SEARCH_MEMORY_ITEMS: CanonicalPrimitiveSpec(
        operation=CanonicalRecallOperation.SEARCH_MEMORY_ITEMS,
        requires_text=True,
        projection_kinds=(RecallDocumentKind.MEMORY_ITEM,),
    ),
    CanonicalRecallOperation.LIST_SOCIAL_EVENTS: CanonicalPrimitiveSpec(
        operation=CanonicalRecallOperation.LIST_SOCIAL_EVENTS,
    ),
    CanonicalRecallOperation.CANONICAL_EVENT_DETAILS: CanonicalPrimitiveSpec(
        operation=CanonicalRecallOperation.CANONICAL_EVENT_DETAILS,
        requires_source_references=True,
    ),
    CanonicalRecallOperation.GET_POST_THREAD: CanonicalPrimitiveSpec(
        operation=CanonicalRecallOperation.GET_POST_THREAD,
        requires_source_references=True,
    ),
    CanonicalRecallOperation.LIST_ACTIVITY_EPISODES: CanonicalPrimitiveSpec(
        operation=CanonicalRecallOperation.LIST_ACTIVITY_EPISODES,
    ),
    CanonicalRecallOperation.LIST_RELATIONSHIP_CHANGES: CanonicalPrimitiveSpec(
        operation=CanonicalRecallOperation.LIST_RELATIONSHIP_CHANGES,
    ),
    CanonicalRecallOperation.GET_CHARACTER_SUMMARIES: CanonicalPrimitiveSpec(
        operation=CanonicalRecallOperation.GET_CHARACTER_SUMMARIES,
        requires_character_references=True,
    ),
}


class CanonicalRecallValidator:
    def validate(self, query: CanonicalRecallQuery) -> CanonicalRecallQuery:
        if not isinstance(query.operation, CanonicalRecallOperation):
            raise MemoryValidationError("canonical_recall_operation_invalid")
        spec = CANONICAL_PRIMITIVE_REGISTRY.get(query.operation)
        if spec is None:
            raise MemoryValidationError("canonical_recall_operation_unknown")
        if query.limit < 1 or query.limit > MAX_CANONICAL_RECALL_RESULTS:
            raise MemoryValidationError("canonical_recall_limit_invalid")
        text = None if query.text is None else " ".join(query.text.split())
        if spec.requires_text and not text:
            raise MemoryValidationError("canonical_recall_text_required")
        if text is not None and len(text) > 1_000:
            raise MemoryValidationError("canonical_recall_text_too_long")
        if spec.requires_source_references and not query.source_references:
            raise MemoryValidationError("canonical_recall_source_reference_required")
        if spec.requires_character_references and not query.world_character_references:
            raise MemoryValidationError("canonical_recall_character_reference_required")
        if len(query.source_references) > MAX_CANONICAL_RECALL_RESULTS:
            raise MemoryValidationError("canonical_recall_source_reference_limit")
        if len(query.world_character_references) > MAX_CANONICAL_RECALL_RESULTS:
            raise MemoryValidationError("canonical_recall_character_reference_limit")
        if (
            query.occurred_from is not None
            and query.occurred_to is not None
            and _as_utc(query.occurred_from) >= _as_utc(query.occurred_to)
        ):
            raise MemoryValidationError("canonical_recall_time_range_invalid")
        return replace(
            query,
            text=text,
            source_references=_bounded_refs(query.source_references),
            world_character_references=_bounded_refs(
                query.world_character_references
            ),
        )


class CanonicalRecallService:
    """Execute allowlisted reads; no provider, SQL, or Planner is accepted."""

    def __init__(
        self,
        repository: CanonicalRecallRepositoryPort,
        index: MemoryRecallIndexPort,
        *,
        validator: CanonicalRecallValidator | None = None,
    ) -> None:
        self._repository = repository
        self._index = index
        self._validator = validator or CanonicalRecallValidator()

    def execute(
        self,
        query: CanonicalRecallQuery,
        *,
        now: datetime | None = None,
    ) -> CanonicalRecallResult:
        validated = self._validator.validate(query)
        if not self._repository.memory_enabled(validated.scope):
            return CanonicalRecallResult(
                operation=validated.operation,
                status=CanonicalRecallStatus.DISABLED,
                records=(),
                reason_code="memory_opt_out",
            )
        executed_at = _as_utc(now or datetime.now(UTC))
        spec = CANONICAL_PRIMITIVE_REGISTRY[validated.operation]
        if spec.projection_kinds:
            try:
                doctor = self._index.doctor()
                if not doctor.healthy:
                    raise RuntimeError("memory_recall_projection_unhealthy")
                candidates = self._index.search(
                    MemoryRecallSearchQuery(
                        scope=validated.scope,
                        text=validated.text or "",
                        kinds=spec.projection_kinds,
                        limit=validated.limit,
                        counterpart_world_character_id=(
                            validated.counterpart_world_character_id
                        ),
                        thread_id=validated.thread_id,
                    )
                )
            except (OSError, RuntimeError, ValueError):
                return CanonicalRecallResult(
                    operation=validated.operation,
                    status=CanonicalRecallStatus.DEGRADED,
                    records=(),
                    reason_code="memory_recall_projection_unavailable",
                )
            records = self._repository.revalidate_candidates(
                scope=validated.scope,
                candidates=candidates,
                now=executed_at,
            )[: validated.limit]
            return CanonicalRecallResult(
                operation=validated.operation,
                status=CanonicalRecallStatus.READY,
                records=records,
                candidate_count=len(candidates),
                excluded_count=max(0, len(candidates) - len(records)),
                truncated=len(records) >= validated.limit,
            )

        records = self._repository.execute_direct(
            query=validated,
            now=executed_at,
        )[: validated.limit]
        return CanonicalRecallResult(
            operation=validated.operation,
            status=CanonicalRecallStatus.READY,
            records=records,
            candidate_count=len(records),
            truncated=len(records) >= validated.limit,
        )


def _bounded_refs(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or len(item) > 256:
            raise MemoryValidationError("canonical_recall_reference_invalid")
        normalized.append(item)
    return tuple(dict.fromkeys(normalized))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "CANONICAL_PRIMITIVE_REGISTRY",
    "CanonicalPrimitiveSpec",
    "CanonicalRecallService",
    "CanonicalRecallValidator",
]
