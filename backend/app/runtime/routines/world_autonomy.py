"""Schedule saved World intent through the existing bounded Resident slot pool."""
from sqlalchemy import inspect, select
from datetime import UTC, datetime

from app.config import settings
from app.domains.characters.models import Character
from app.domains.identity.models import User
from app.domains.identity.service.environment import lock_environment_admission
from app.domains.routines.models import AgentSlot, AgentActivitySetting
from app.domains.routines.repository.autonomy import _lock_server_llm_autonomy_capacity
from app.domains.routines.service.slot_assignments import release_resident_slot_assignment
from app.domains.routines.service.tick_schedule import tick_interval_seconds, initial_tick_schedule
from app.domains.routines.exceptions import AgentSlotUnavailableError, ActivityRuntimeValidationError
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.runtime.routines.configuration_reads import read_effective_setting


def reconcile_world_autonomy(db, *, workflows, limit=32, allowed_character_ids=None):
    if limit <= 0 or not inspect(db.connection()).has_table(WorldCharacterConfiguration.__tablename__):
        return 0
    lock_environment_admission(db)
    _lock_server_llm_autonomy_capacity(db)
    configured = select(WorldCharacter.character_id).join(WorldCharacterConfiguration,
        WorldCharacterConfiguration.world_character_id == WorldCharacter.id)
    idle = list(db.scalars(select(AgentSlot).where(AgentSlot.assigned_character_id.in_(configured),
        AgentSlot.status != "running", AgentSlot.locked_by_run_id.is_(None)).order_by(AgentSlot.agent_id).limit(limit)))
    changed = 0
    for slot in idle:
        setting = db.get(AgentActivitySetting, slot.assigned_character_id)
        try:
            effective = read_effective_setting(db, character_id=slot.assigned_character_id, setting=setting)
        except ActivityRuntimeValidationError:
            effective = None
        if effective is not None and effective.auto_enabled:
            if slot.next_tick_at is None:
                from app.runtime.routines.activity_policy import activity_timezone
                slot.next_tick_at = initial_tick_schedule(effective, character_id=slot.assigned_character_id,
                    now=datetime.now(UTC), timezone=activity_timezone(db, character_id=slot.assigned_character_id)).next_tick_at
                changed += 1
            continue
        credential = workflows.get_credential(db, slot.assigned_character_id)
        if credential is not None and workflows.sync_enabled():
            workflows.release_profile(slot, user_id=slot.assigned_user_id, character_id=slot.assigned_character_id, credential=credential)
            workflows.reload_secrets()
        release_resident_slot_assignment(db, user_id=slot.assigned_user_id, character_id=slot.assigned_character_id, commit=False)
        changed += 1
    # Capacity constrains assignments and execution, independently of saved ON.
    global_available = max(0, settings.server_llm_autonomy_max_active_agents - workflows.count_effective_agents(db))
    if not global_available:
        db.commit()
        return changed
    query = select(WorldCharacter).join(WorldCharacterConfiguration,
        WorldCharacterConfiguration.world_character_id == WorldCharacter.id).join(Character,
        Character.id == WorldCharacter.character_id).where(WorldCharacter.status == "active",
        WorldCharacter.control_mode == "autonomous", WorldCharacter.autonomous_enabled.is_(True),
        Character.execution_mode == "llm", Character.deleted_at.is_(None), Character.moderation_status != "suspended",
        ~select(AgentSlot.agent_id).where(AgentSlot.assigned_character_id == WorldCharacter.character_id).exists())
    if allowed_character_ids is not None:
        query = query.where(WorldCharacter.character_id.in_(allowed_character_ids))
    roles = list(db.scalars(query.order_by(WorldCharacter.created_at, WorldCharacter.id).limit(limit)))
    counts = {}
    for wid, _agent in db.execute(select(WorldCharacter.world_id, AgentSlot.agent_id).join(AgentSlot,
        AgentSlot.assigned_character_id == WorldCharacter.character_id)):
        counts[wid] = counts.get(wid, 0) + 1
    for role in roles:
        if global_available <= 0:
            break
        if counts.get(role.world_id, 0) >= settings.world_autonomy_max_active_characters:
            continue
        character = db.get(Character, role.character_id)
        user = db.get(User, character.owner_id)
        credential = workflows.get_credential(db, role.character_id)
        setting = db.get(AgentActivitySetting, role.character_id)
        if credential is None or not credential.enabled or setting is None:
            continue
        try:
            effective = read_effective_setting(db, character_id=role.character_id, setting=setting)
            if not effective.auto_enabled:
                continue
            workflows.ensure_not_suspended(character)
            workflows.ensure_llm_mode(character)
            workflows.ensure_auto_ticks_available(db)
            readiness = workflows.evaluate_readiness(db, character=character, setting=effective)
            if not readiness.ready:
                continue
            with db.begin_nested():
                slot = workflows.assign_slot(db, user_id=user.id, character_id=role.character_id,
                    credential_id=credential.id, heartbeat_interval_seconds=tick_interval_seconds(effective), commit=False)
                if workflows.sync_enabled():
                    workflows.bind_profile(slot, user_id=user.id, character=character, credential=credential)
                    workflows.reload_secrets()
        except (ActivityRuntimeValidationError, AgentSlotUnavailableError):
            continue
        counts[role.world_id] = counts.get(role.world_id, 0) + 1
        global_available -= 1
        changed += 1
    db.commit()
    return changed
