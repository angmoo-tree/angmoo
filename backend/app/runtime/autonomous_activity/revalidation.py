"""Current memory rights at the action boundary; historical text stays frozen."""
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from sqlalchemy import select
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.repository.experience import guard_metadata, rights_columns


def _rows(value):
    if not isinstance(value,(list,tuple)) or any(not isinstance(row,(list,tuple)) or len(row)!=3 for row in value):
        raise ValueError("activity_memory_validation_unavailable")
    return tuple(tuple(row) for row in value)


def _assert_snapshot_current(db, *, scope, result, snapshot, now, validation=None):
    if (not isinstance(snapshot,dict) or snapshot.get("schema_version")!=2
            or snapshot.get("policy_version")!="memory-experience-v1" or snapshot.get("scope")!=asdict(scope)):
        raise ValueError("activity_memory_snapshot_policy_changed")
    ids=tuple(result.get("ranked_memory_ids",()))
    if not ids:return
    from app.domains.memory.contracts.activity_situation import stable_digest
    if snapshot.get("delivered_packet_digest") != stable_digest(result.get("packets", [])):
        raise ValueError("activity_memory_input_integrity_invalid")
    if len(ids)>12 or any(not isinstance(value,str) for value in ids):
        raise ValueError("activity_memory_validation_unavailable")
    revisions={identifier:(version,digest) for identifier,version,digest in _rows(snapshot.get("item_revisions"))}
    try:digests=dict(snapshot["memory_snapshot_digests"])
    except (KeyError,ValueError,TypeError):raise ValueError("activity_memory_validation_unavailable") from None
    items=list(db.scalars(select(MemoryItem).options(rights_columns()).where(MemoryItem.id.in_(ids)).execution_options(populate_existing=True)))
    rights=guard_metadata(db,scope,items,now,captured=True)
    if len(items)!=len(set(ids)) or set(ids)-rights.keys():
        raise ValueError("activity_memory_changed")
    allowed_threads=snapshot.get("allowed_thread_ids")
    for item in items:
        if (item.id not in revisions
                or item.id not in digests or digests[item.id]!=rights[item.id]
                or item.thread_id is not None and allowed_threads is not None and item.thread_id not in allowed_threads):
            raise ValueError("activity_memory_changed")


def assert_memories_current(db, *, owner_id, world_id, actor_id, memories, validations=None):
    scope=MemoryScope(owner_id,world_id,actor_id)
    now=datetime.now(UTC)
    for target,result in memories.items():
        if not result.get("ranked_memory_ids") or not result.get("packets"):
            continue
        _assert_snapshot_current(db,scope=scope,result=result,snapshot=(validations or {}).get(target),now=now)
