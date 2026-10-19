"""Compose existing recovery scheduling with canonical unfinished graph identity."""
from datetime import timedelta
from app.contracts.activity_cancellation import CancellationReason, RECOVERY_POLICY_KEY, RECOVERY_REVISION
from app.domains.world_characters.service.activity_interruption import unfinished, interrupt
from app.domains.routines.service.tick_schedule import recovery_tick_schedule, aware_utc


def routine_deadline(db, row):
    if row is None:
        return None
    saved = (row.result or {}).get("_routine_recovery")
    if not isinstance(saved, dict) or saved.get("revision") != "routine-recovery.v1":
        return None
    from app.domains.routines.models.plans import ActivityBeat, ActivityEpisode, DailyActivityPlanItem
    beat = db.get(ActivityBeat, saved.get("beat_id"), populate_existing=True)
    if beat is None or beat.world_character_id != row.world_character_id or beat.world_id != row.world_id:
        return None
    episode = db.get(ActivityEpisode, beat.episode_id)
    item = db.get(DailyActivityPlanItem, episode.plan_item_id) if episode else None
    return aware_utc(item.scheduled_end_at) if item else None


def recovery_due(schedule, *, now, deadline):
    # Only deterministic jitter is removed; actual expiry/cooldown are not extended.
    if deadline is not None and now < deadline <= schedule.next_tick_at:
        return now
    return schedule.next_tick_at


def cancellation_schedule(db, slot, now, *, run_id, reason, heartbeat_interval, setting, timezone):
    row = interrupt(db, owner_id=slot.assigned_user_id, character_id=slot.assigned_character_id,
        lease_run_id=run_id, reason=reason, now=now)
    if row is not None and (row.result or {}).get(RECOVERY_POLICY_KEY) == RECOVERY_REVISION and reason in {CancellationReason.HEARTBEAT, CancellationReason.LEASE_LOST} and setting is not None:
        schedule = recovery_tick_schedule(setting, character_id=slot.assigned_character_id, now=now, timezone=timezone)
        return recovery_due(schedule, now=now, deadline=routine_deadline(db, row))
    return now + timedelta(seconds=heartbeat_interval)


def has_supported_recovery(db, slot):
    row = unfinished(db, owner_id=slot.assigned_user_id, character_id=slot.assigned_character_id)
    return row is not None and (row.result or {}).get(RECOVERY_POLICY_KEY) == RECOVERY_REVISION
