"""Explicit cross-owner maintenance; no provider or automatic startup call."""
from app.domains.memory.repository.situation_transition import discard_legacy, inspect_discard
from app.domains.relationships.repository.legacy_memory_followups import detach_discarded_memory_requests


def discard(session, plan, *, request_key, now):
    from app.domains.memory.models.items import MemoryScopeSettingModel
    from app.domains.memory.models.activity_situation import MemorySituationTransition
    from app.domains.memory.exceptions import MemoryConflictError
    from sqlalchemy import update
    session.execute(update(MemoryScopeSettingModel).where(MemoryScopeSettingModel.id == plan.setting_id).values(id=MemoryScopeSettingModel.id, updated_at=MemoryScopeSettingModel.updated_at).execution_options(memory_scope_lock_only=True))
    existing = session.get(MemorySituationTransition, plan.setting_id)
    if existing is not None and existing.discard_key == request_key:
        return existing
    if inspect_discard(session, plan.setting_id) != plan:
        raise MemoryConflictError("situation_discard_inventory_changed")
    detach_discarded_memory_requests(session, plan.request_ids)
    return discard_legacy(session, plan, request_key=request_key, now=now)
