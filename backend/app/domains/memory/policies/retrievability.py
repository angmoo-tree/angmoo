"""Current lifecycle eligibility, independent of hydration and source access."""
from datetime import UTC
from app.domains.memory.contracts.provenance import MemoryItemStatus


def item_retrievable(item, now):
    def utc(value):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return (item.status == MemoryItemStatus.ACTIVE.value and item.deleted_at is None
        and item.superseded_by_id is None and utc(item.valid_from) <= utc(now)
        and (item.valid_until is None or utc(item.valid_until) > utc(now)))
