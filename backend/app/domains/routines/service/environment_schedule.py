"""Bounded per-character reconciliation; never alter a running claim."""
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.domains.routines.models import AgentSlot, AgentActivitySetting
from app.domains.routines.constants import DUE_SLOT_STATUSES
from app.domains.routines.service.tick_schedule import initial_tick_schedule
from app.domains.identity.service.environment import installation_snapshot


def reconcile_environment_schedules(db, *, now, limit=32, settings_reader=None):
    environment = installation_snapshot(db)
    rows = list(db.scalars(select(AgentSlot).where(
        AgentSlot.assigned_character_id.is_not(None),
        AgentSlot.status.in_(DUE_SLOT_STATUSES),
        AgentSlot.locked_by_run_id.is_(None),
        AgentSlot.timezone_revision < environment.timezone_revision,
    ).order_by(AgentSlot.agent_id).limit(limit).with_for_update(skip_locked=True)))
    for row in rows:
        setting = db.get(AgentActivitySetting, row.assigned_character_id)
        if setting is None:
            continue
        if settings_reader is not None:
            from app.domains.routines.exceptions import ActivityRuntimeValidationError
            try:
                setting = settings_reader(setting, row.assigned_character_id)
            except ActivityRuntimeValidationError:
                continue
        # A cooldown/deferred retry is an elapsed-time contract. Only idle future
        # cadence is rebuilt; a due retry keeps its original admission timestamp.
        from app.domains.routines.constants import SLOT_STATUS_ASSIGNED_IDLE
        if row.status == SLOT_STATUS_ASSIGNED_IDLE:
            row.next_tick_at = initial_tick_schedule(setting,
                character_id=row.assigned_character_id, now=now,
                timezone=ZoneInfo(environment.timezone)).next_tick_at
        row.timezone_revision = environment.timezone_revision
    db.flush()
    return len(rows)
