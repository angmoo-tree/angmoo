"""Read-only Memory list, detail, and canonical provenance use cases."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domains.memory.domain.lifecycle import MemoryItemRecord
from app.domains.memory.domain.provenance import MemoryItemStatus, MemorySourceTypeV1
from app.domains.memory.domain.read_surface import (
    MAX_MEMORY_READ_PAGE_SIZE,
    MemoryEvidenceAvailability,
    MemoryEvidenceRead,
    MemoryItemDetail,
    MemoryItemPage,
    MemoryLifecycle,
)
from app.domains.memory.domain.retention import is_memory_expired
from app.domains.memory.domain.scope import MemoryScope, MemoryScopeSetting
from app.domains.memory.ports.repository import MemoryRepositoryPort
from app.domains.memory.ports.source_reader import MemorySourceEvidenceReaderPort


class MemoryReadService:
    def __init__(
        self,
        repository: MemoryRepositoryPort,
        source_reader: MemorySourceEvidenceReaderPort,
    ) -> None:
        self._repository = repository
        self._source_reader = source_reader

    def setting(self, scope: MemoryScope) -> MemoryScopeSetting | None:
        """Read the setting without creating an implicit opt-in row."""

        self._repository.validate_scope(scope)
        return self._repository.get_scope_setting(scope)

    def list_items(
        self,
        scope: MemoryScope,
        *,
        cursor: str | None,
        limit: int,
    ) -> MemoryItemPage:
        self._repository.validate_scope(scope)
        bounded_limit = max(1, min(limit, MAX_MEMORY_READ_PAGE_SIZE))
        return self._repository.list_items(
            scope=scope,
            cursor=cursor,
            limit=bounded_limit,
        )

    def detail(
        self,
        scope: MemoryScope,
        *,
        item_id: str,
        now: datetime | None = None,
    ) -> MemoryItemDetail:
        self._repository.validate_scope(scope)
        item = self._repository.get_item(scope=scope, item_id=item_id)
        evidence_rows = self._repository.list_item_evidence(
            scope=scope,
            item_id=item_id,
        )
        evidence: list[MemoryEvidenceRead] = []
        for row in evidence_rows:
            fresh = self._source_reader.read_evidence(
                scope=scope,
                source_type=row.source_type,
                source_id=row.source_id,
            )
            if fresh is None:
                evidence.append(
                    MemoryEvidenceRead(
                        source_type=row.source_type,
                        source_created_at=row.source_created_at,
                        availability=MemoryEvidenceAvailability.UNAVAILABLE,
                        excerpt=None,
                    )
                )
                continue
            same_world = fresh.source_world_id == scope.world_id
            same_source = (
                fresh.source_type is row.source_type
                and fresh.source_id == row.source_id
                and fresh.source_digest == row.source_digest
                and row.source_world_id == scope.world_id
            )
            accepted = all(
                (
                    same_source,
                    fresh.successful,
                    fresh.visible,
                    fresh.observed_by_subject,
                    fresh.membership_active,
                    not fresh.blocked,
                    same_world,
                )
            )
            if accepted:
                availability = MemoryEvidenceAvailability.AVAILABLE
                excerpt = _bounded_excerpt(fresh.deterministic_summary)
            elif (
                row.source_type in {MemorySourceTypeV1.POST, MemorySourceTypeV1.REPLY}
                and not fresh.visible
            ):
                availability = MemoryEvidenceAvailability.DELETED
                excerpt = None
            else:
                availability = MemoryEvidenceAvailability.UNAVAILABLE
                excerpt = None
            evidence.append(
                MemoryEvidenceRead(
                    source_type=row.source_type,
                    source_created_at=fresh.source_created_at,
                    availability=availability,
                    excerpt=excerpt,
                    actor_world_character_id=(
                        fresh.actor_world_character_id if accepted else None
                    ),
                    target_world_character_id=(
                        fresh.target_world_character_id if accepted else None
                    ),
                    counterpart_world_character_id=(
                        fresh.counterpart_world_character_id if accepted else None
                    ),
                    thread_id=fresh.thread_id if accepted else None,
                    source_id=fresh.source_id if accepted else None,
                )
            )
        return MemoryItemDetail(
            item=item,
            lifecycle=memory_lifecycle(item, now=now or datetime.now(UTC)),
            evidence=tuple(evidence),
        )


def memory_lifecycle(item: MemoryItemRecord, *, now: datetime) -> MemoryLifecycle:
    if item.status is MemoryItemStatus.DELETED:
        return MemoryLifecycle.DELETED
    if item.status is MemoryItemStatus.SUPERSEDED:
        return MemoryLifecycle.SUPERSEDED
    if is_memory_expired(
        valid_until=item.valid_until,
        pinned_at=item.pinned_at,
        now=now,
    ):
        return MemoryLifecycle.EXPIRED
    return MemoryLifecycle.ACTIVE


def _bounded_excerpt(value: str) -> str:
    normalized = " ".join(value.split())
    return normalized[:500]


__all__ = ["MemoryReadService", "memory_lifecycle"]
