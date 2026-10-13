"""Explicit, resumable full preparation; regular accepted content stays incremental."""
from datetime import UTC, datetime
import hashlib
from uuid import uuid4
from sqlalchemy import select, update

from app.domains.memory.exceptions import MemoryConflictError, MemoryValidationError
from app.domains.memory.models.activity_configuration import MemoryIndexPreparation
from app.domains.memory.models.embedding import MemoryEmbeddingSetting, MemoryVectorEligibility
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.memory.repository.recall_records import _item_retrievable
from app.domains.memory.repository.vector_eligibility import register_content


def status(session, setting_id):
    row = session.get(MemoryIndexPreparation, setting_id) if setting_id else None
    return {"state": row.state if row else "needs_preparation", "revision": row.revision if row else 0,
            "last_code": None if row is None else row.last_code}


def mark_needed(session, setting, profile):
    row = session.get(MemoryIndexPreparation, setting.id)
    if row is None:
        row = MemoryIndexPreparation(scope_setting_id=setting.id, state="needs_preparation", revision=1,
            profile=profile, source_generation="", cursor=None)
        session.add(row)
    elif row.profile != profile:
        row.state, row.profile, row.cursor = "needs_preparation", profile, None
        row.revision += 1
    return row


def start(session, memory, scope, *, expected_revision, credential_revision, now):
    memory.validate_scope(scope)
    setting = memory.get_scope_setting(scope)
    config = session.get(MemoryEmbeddingSetting, setting.id) if setting else None
    if not setting or not setting.enabled or not config or not config.enabled:
        raise MemoryValidationError("memory_embedding_preparation_disabled")
    session.execute(update(MemoryScopeSettingModel).where(MemoryScopeSettingModel.id == setting.id).values(id=setting.id))
    row = mark_needed(session, setting, config.profile)
    if row.revision != expected_revision:
        raise MemoryConflictError("memory_embedding_preparation_conflict")
    if row.state == "running":
        return status(session, setting.id)
    # The timestamp in the durable request identifies the admitted source cutoff.
    row.state, row.cursor, row.last_code = "running", None, None
    row.request_key = now.isoformat() + "|" + uuid4().hex
    row.source_generation = hashlib.sha256((setting.id + row.request_key + config.profile).encode()).hexdigest()
    row.credential_revision, row.revision = credential_revision, row.revision + 1
    session.flush()
    return status(session, setting.id)


def advance(session, row, *, now, limit=64):
    setting = session.get(MemoryScopeSettingModel, row.scope_setting_id)
    config = session.get(MemoryEmbeddingSetting, row.scope_setting_id)
    if setting is None or not setting.enabled or config is None or not config.enabled or config.profile != row.profile:
        row.state, row.last_code = "error", "memory_embedding_preparation_changed"
        return ()
    cutoff = datetime.fromisoformat(row.request_key.split("|", 1)[0])
    items = session.scalars(select(MemoryItem).where(MemoryItem.owner_id == setting.owner_id,
        MemoryItem.world_id == setting.world_id, MemoryItem.subject_world_character_id == setting.subject_world_character_id,
        MemoryItem.created_at <= cutoff, MemoryItem.id > (row.cursor or "")).order_by(MemoryItem.id).limit(limit)).all()
    result = []
    for item in items:
        if _item_retrievable(item, now):
            registration = register_content(session, item, now=now)
            registration.registration_revision = "memory-vector.prepared.v2"
        result.append(item.id)
    # Enrollment is not completion. The worker moves this cursor only after
    # every item in the page has been indexed or canonically excluded.
    session.flush()
    return tuple(result)
