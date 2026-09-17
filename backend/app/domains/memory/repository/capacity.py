"""One current-holdings definition for UI, admission and serialized writes."""
from datetime import datetime
from sqlalchemy import func, or_, select, text
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.exceptions import MemoryCapacityReached
from app.domains.memory.policies.capacity import MEMORY_STORAGE_LIMIT

STORAGE_LIMIT = MEMORY_STORAGE_LIMIT


def current_item_predicates(scope: MemoryScope, *, now: datetime):
    return (
        MemoryItem.owner_id == scope.owner_id,
        MemoryItem.world_id == scope.world_id,
        MemoryItem.subject_world_character_id == scope.subject_world_character_id,
        MemoryItem.status == "active", MemoryItem.deleted_at.is_(None),
        MemoryItem.superseded_by_id.is_(None),
        or_(MemoryItem.pinned_at.is_not(None), MemoryItem.valid_until.is_(None), MemoryItem.valid_until > now),
    )


def stored_count(session, scope: MemoryScope, *, now: datetime) -> int:
    return int(session.scalar(select(func.count(MemoryItem.id)).where(*current_item_predicates(scope, now=now))) or 0)


def require_new_slot(session, setting, *, now: datetime, replacing_item_id: str | None = None):
    # An actual write serializes SQLite writers, including deferred transactions.
    # It changes no scope version/timestamp and finishes in the caller's commit.
    session.execute(text("UPDATE memory_scope_settings SET id=id WHERE id=:id"), {"id": setting.id})
    if replacing_item_id is not None and session.scalar(
        select(MemoryItem.id).where(MemoryItem.id == replacing_item_id,
                                   *current_item_predicates(setting.scope, now=now))
    ) is not None:
        return
    if stored_count(session, setting.scope, now=now) >= STORAGE_LIMIT:
        raise MemoryCapacityReached()
