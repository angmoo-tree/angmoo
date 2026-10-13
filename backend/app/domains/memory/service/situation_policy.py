"""Freeze the memory policy at activity admission, independently of model calls."""
from dataclasses import asdict
from datetime import UTC, datetime
from app.domains.memory.contracts.activity_situation import SITUATION_POLICY, SituationPolicySnapshot
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.repository.situation_admission import snapshot_for


def capture(session, *, owner_id, world_id, actor_id, environment, policy):
    if policy != "activity_situation":
        return None
    value = snapshot_for(session, MemoryScope(owner_id, world_id, actor_id),
        locale=environment.memory_search_locale, environment_revision=environment.environment_revision)
    if value is not None:
        from app.domains.memory.repository.situation_runs import get_or_create_settings
        from app.domains.memory.repository.situation_transition import retire_admission
        retire_admission(session, value.setting_id, now=datetime.now(UTC))
        get_or_create_settings(session, value.setting_id, timezone=environment.timezone, now=datetime.now(UTC))
    return {"policy": SITUATION_POLICY, "snapshot": asdict(value) if value else None}


def restore(value):
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("policy") != SITUATION_POLICY:
        raise ValueError("situation_admission_policy_invalid")
    raw = value.get("snapshot")
    if raw is None:
        return None
    return SituationPolicySnapshot(**{**raw, "scope": MemoryScope(**raw["scope"])})
