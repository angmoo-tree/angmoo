"""A captured experience survives ordinary revision, but current use rights apply."""
from datetime import timedelta
import pytest
from sqlalchemy import select, event
from memory.test_experience_snapshots import captured, real_source, apply, stack, NOW
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.repository.experience import rights_columns, guard_metadata, tombstone
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel


@pytest.mark.parametrize("change", ["summary", "superseded", "deleted", "disabled", "expired", "tombstone"])
def test_metadata_guard_has_no_source_reads_and_keeps_revocation(stack, change):
    db, scope, setting, memory = stack
    post = real_source(db, scope)
    manifest, draft, result = captured(db, scope, post)
    receipt = admit(db, manifest=manifest, draft=draft, result=result, now=NOW)
    apply(db, setting, memory)
    item = db.get(MemoryItem, receipt.applied_item_id)
    identifier = item.id
    if change == "summary":
        item.summary = "New consolidation summary"
        item.version += 1
    elif change == "superseded":
        values = {column.key: getattr(item, column.key) for column in MemoryItem.__table__.columns}
        values["id"] = "corrected-item"
        db.add(MemoryItem(**values))
        db.flush()
        item.status, item.superseded_by_id = "superseded", "corrected-item"
    elif change == "deleted": item.status, item.deleted_at = "deleted", NOW
    elif change == "disabled": db.get(MemoryScopeSettingModel, setting.id).enabled = False
    elif change == "expired":
        item.valid_from, item.valid_until = NOW - timedelta(days=2), NOW - timedelta(seconds=1)
    else: tombstone(db, item, setting.id, now=NOW)
    db.commit()
    db.expunge_all()
    queries = []
    def observe(_conn, _cursor, statement, *_): queries.append(statement.lower())
    event.listen(db.bind, "before_cursor_execute", observe)
    try:
        current = db.scalar(select(MemoryItem).options(rights_columns()).where(MemoryItem.id == identifier))
        allowed = guard_metadata(db, scope, (current,), NOW, captured=True)
    finally:
        event.remove(db.bind, "before_cursor_execute", observe)
    assert (identifier in allowed) == (change in {"summary", "superseded"})
    assert not any("from posts" in query or "from messages" in query or "memory_items.summary" in query for query in queries)
