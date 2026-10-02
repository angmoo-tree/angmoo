"""Settle expired claims of an identified retired SNS run without executing it."""
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.domains.routines.constants import SLOT_STATUS_ASSIGNED_IDLE
from app.domains.routines.models import AgentRun, AgentSlot, AgentPublicActionExecution
from app.domains.routines.models.plans import ActivityBeat, ActivityEventConsumption, ActivityEpisode
from app.domains.routines.service.slot_state import _clear_resident_slot


def aware(value):
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


def claim_hold(db, *, character_id, run_ids, now, entry_run_id=None, lock=True):
    """A new gateway lease cannot be mistaken for an old executing owner."""
    query = select(AgentSlot).where(AgentSlot.assigned_character_id == character_id)
    slots = list(db.scalars(query.with_for_update() if lock else query))
    for slot in slots:
        if slot.locked_by_run_id and slot.locked_by_run_id != entry_run_id:
            if slot.lease_expires_at is None or aware(slot.lease_expires_at) > now:
                return "legacy_execution_owner_active"
    pending = db.scalar(select(AgentPublicActionExecution.id).where(
        AgentPublicActionExecution.run_id.in_(run_ids),
        AgentPublicActionExecution.status.not_in(("succeeded", "failed", "skipped", "cancelled"))).limit(1))
    if pending is not None:
        return "legacy_public_effect_unconfirmed"
    for beat in db.scalars(select(ActivityBeat).where(ActivityBeat.claim_run_id.in_(run_ids),
                                                     ActivityBeat.status == "claimed")):
        if beat.claim_expires_at is None or aware(beat.claim_expires_at) > now:
            return "legacy_routine_claim_active"
        if beat.source_post_id or beat.state_after_snapshot:
            return "legacy_routine_effect_unconfirmed"
    for consumption in db.scalars(select(ActivityEventConsumption).where(
            ActivityEventConsumption.claim_run_id.in_(run_ids), ActivityEventConsumption.status == "claimed")):
        if consumption.claim_expires_at is None or aware(consumption.claim_expires_at) > now:
            return "legacy_event_claim_active"
    return None


def settle_expired_claims(db, *, run_ids, now, reason):
    """Caller holds the single writer; no commit or destructive evidence reset."""
    episode_ids = list(db.scalars(select(ActivityBeat.episode_id).where(
        ActivityBeat.claim_run_id.in_(run_ids), ActivityBeat.status == "claimed").distinct().order_by(ActivityBeat.episode_id)))
    for episode_id in episode_ids:
        # The existing claim/publish owner locks the episode before its beats.
        episode = db.scalar(select(ActivityEpisode).where(ActivityEpisode.id == episode_id).with_for_update())
        beats = list(db.scalars(select(ActivityBeat).where(ActivityBeat.episode_id == episode_id,
            ActivityBeat.claim_run_id.in_(run_ids), ActivityBeat.status == "claimed").order_by(ActivityBeat.id).with_for_update()))
        for beat in beats:
            _settle_beat(db, beat, episode, now=now, reason=reason)
    _settle_events_and_slots(db, run_ids=run_ids, now=now, reason=reason)
    db.flush()


def _settle_beat(db, beat, episode, *, now, reason):
    expected_run = beat.claim_run_id
    count = db.execute(update(ActivityBeat).where(ActivityBeat.id == beat.id, ActivityBeat.status == "claimed",
        ActivityBeat.claim_run_id == expected_run, ActivityBeat.claim_expires_at <= now).values(
            status="failed", failure_reason_code=reason, completed_at=now,
            claim_run_id=None, claim_expires_at=None).execution_options(synchronize_session=False)).rowcount
    if count != 1:
        raise ValueError("legacy_routine_claim_conflict")
    if episode is not None:
        episode.next_sequence_no = max(episode.next_sequence_no, beat.sequence_no + 1)
        episode.version += 1
    db.expire(beat)


def _settle_events_and_slots(db, *, run_ids, now, reason):
    for row in db.scalars(select(ActivityEventConsumption).where(
            ActivityEventConsumption.claim_run_id.in_(run_ids), ActivityEventConsumption.status == "claimed").with_for_update()):
        count = db.execute(update(ActivityEventConsumption).where(ActivityEventConsumption.id == row.id,
            ActivityEventConsumption.version == row.version, ActivityEventConsumption.status == "claimed",
            ActivityEventConsumption.claim_expires_at <= now).values(status="released", claim_run_id=None,
                claim_expires_at=None, target_activity_beat_id=None, version=row.version + 1)
            .execution_options(synchronize_session=False)).rowcount
        if count != 1:
            raise ValueError("legacy_event_claim_conflict")
        db.expire(row)
    for run in db.scalars(select(AgentRun).where(AgentRun.id.in_(run_ids)).with_for_update()):
        if run.status in {"running", "pending", "waiting", "interrupted"}:
            run.status, run.completed_at = "aborted", now
            run.gateway_result = {**(run.gateway_result or {}), "status": "aborted", "reason": reason}
    for slot in db.scalars(select(AgentSlot).where(AgentSlot.locked_by_run_id.in_(run_ids)).with_for_update()):
        if slot.lease_expires_at is None or aware(slot.lease_expires_at) > now:
            raise ValueError("legacy_execution_owner_active")
        from app.domains.routines.models import AgentActivitySetting
        setting = db.get(AgentActivitySetting, slot.assigned_character_id)
        if setting is None or not setting.auto_enabled:
            _clear_resident_slot(slot)
        else:
            slot.status = SLOT_STATUS_ASSIGNED_IDLE
            slot.locked_by_run_id = None
            slot.lease_expires_at = None
            slot.last_error = reason
    db.flush()
