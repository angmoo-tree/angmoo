from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.core.ids import uuid7_string
from app.domains.routines.policies import activity_state as activity_state_contracts
from app.domains.routines.exceptions import ActivityRuntimeConflictError, ActivityRuntimeError, ActivityRuntimeNotFoundError, ActivityRuntimeValidationError
from app.domains.routines.contracts.lifecycle import DaypartTransitionCounts, DueTick, RecoveryCounts, WorldInterruptionCounts


EVENT_CONSUMPTION_NAMESPACE = "next_activity_beat"
BEAT_TRIGGER_KINDS = frozenset({"scheduled", "comment_influenced", "joint_activity"})
TERMINAL_ITEM_STATUSES = frozenset(
    {"completed", "skipped", "interrupted", "cancelled"}
)


@dataclass(frozen=True)
class RuntimeClaimResult:
    row: models.ActivityBeat | models.ActivityEventConsumption
    reused: bool


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_future_expiry(expiry: datetime, *, now: datetime) -> datetime:
    normalized = _aware_utc(expiry)
    if normalized <= now:
        raise ActivityRuntimeValidationError("claim_expiry_invalid")
    return normalized


def latest_due_tick(
    *,
    window_start: datetime,
    window_end: datetime,
    now: datetime,
    activity_interval_minutes: int,
    last_scheduled_for: datetime | None = None,
) -> DueTick | None:
    """Return only the newest due tick in the current daypart window.

    Older due ticks are counted, not replayed.  This is the P3 restart burst
    boundary; the scheduler can persist the returned count on ActivityBeat.
    """

    if not 30 <= activity_interval_minutes <= 1440:
        raise ActivityRuntimeValidationError("activity_interval_out_of_range")
    start = _aware_utc(window_start)
    end = _aware_utc(window_end)
    current = _aware_utc(now)
    if start >= end:
        raise ActivityRuntimeValidationError("plan_item_window_invalid")
    if current < start or current >= end:
        return None

    interval = timedelta(minutes=activity_interval_minutes)
    latest_index = int((current - start) // interval)
    first_unhandled_index = 0
    if last_scheduled_for is not None:
        previous = _aware_utc(last_scheduled_for)
        if previous >= start:
            first_unhandled_index = int((previous - start) // interval) + 1
    if latest_index < first_unhandled_index:
        return None
    return DueTick(
        scheduled_for=start + (latest_index * interval),
        skipped_tick_count=latest_index - first_unhandled_index,
    )


def _episode_scope(
    db: Session,
    *,
    episode_id: str,
    lock_for_update: bool,
) -> tuple[models.ActivityEpisode, models.DailyActivityPlanItem, models.DailyActivityPlan]:
    statement = select(models.ActivityEpisode).where(
        models.ActivityEpisode.id == episode_id
    )
    if lock_for_update:
        statement = statement.with_for_update()
    episode = db.scalar(statement)
    if episode is None:
        raise ActivityRuntimeNotFoundError(episode_id)
    item = db.get(models.DailyActivityPlanItem, episode.plan_item_id)
    if item is None:
        raise ActivityRuntimeNotFoundError(episode.plan_item_id)
    plan = db.get(models.DailyActivityPlan, item.plan_id)
    if plan is None:
        raise ActivityRuntimeNotFoundError(item.plan_id)
    if (
        episode.world_id != item.world_id
        or episode.world_character_id != item.world_character_id
        or item.world_id != plan.world_id
        or item.world_character_id != plan.world_character_id
    ):
        raise ActivityRuntimeValidationError("cross_world_reference")
    return episode, item, plan


def _lock_beat_with_episode_scope(
    db: Session,
    *,
    beat_id: str,
) -> tuple[
    models.ActivityBeat,
    models.ActivityEpisode,
    models.DailyActivityPlanItem,
    models.DailyActivityPlan,
]:
    """Lock an episode before its beat to keep one global lock order.

    Claiming a beat already locks ``episode -> beat``. Completion and terminal
    failure must use the same order or a duplicate scheduler can deadlock with
    the winning publisher while both are inspecting the same tick.
    """

    episode_id = db.scalar(
        select(models.ActivityBeat.episode_id).where(
            models.ActivityBeat.id == beat_id
        )
    )
    if episode_id is None:
        raise ActivityRuntimeNotFoundError(beat_id)
    episode, item, plan = _episode_scope(
        db,
        episode_id=episode_id,
        lock_for_update=True,
    )
    beat = db.scalar(
        select(models.ActivityBeat)
        .where(
            models.ActivityBeat.id == beat_id,
            models.ActivityBeat.episode_id == episode.id,
        )
        .with_for_update()
    )
    if beat is None:
        raise ActivityRuntimeNotFoundError(beat_id)
    return beat, episode, item, plan


def claim_activity_beat(
    db: Session,
    *,
    episode_id: str,
    scheduled_for: datetime,
    trigger_kind: str,
    idempotency_key: str,
    claim_run_id: str,
    claim_expires_at: datetime,
    source_event_ids: list[str] | None = None,
    skipped_tick_count: int = 0,
    now: datetime | None = None,
) -> RuntimeClaimResult:
    current = _aware_utc(now or datetime.now(UTC))
    scheduled = _aware_utc(scheduled_for)
    expiry = _require_future_expiry(claim_expires_at, now=current)
    if trigger_kind not in BEAT_TRIGGER_KINDS:
        raise ActivityRuntimeValidationError("beat_trigger_invalid")
    if skipped_tick_count < 0:
        raise ActivityRuntimeValidationError("skipped_tick_count_invalid")

    episode, item, _plan = _episode_scope(
        db, episode_id=episode_id, lock_for_update=True
    )
    if episode.status not in {"planned", "active"}:
        raise ActivityRuntimeConflictError("plan_item_already_terminal")
    if item.status in TERMINAL_ITEM_STATUSES:
        raise ActivityRuntimeConflictError("plan_item_already_terminal")
    if not (
        _aware_utc(item.scheduled_start_at)
        <= scheduled
        < _aware_utc(item.scheduled_end_at)
    ):
        raise ActivityRuntimeValidationError("beat_outside_plan_item_window")
    state_before = activity_state_contracts.validate_state_snapshot(
        episode.current_state_snapshot
    )

    existing = db.scalar(
        select(models.ActivityBeat)
        .where(
            models.ActivityBeat.world_character_id == episode.world_character_id,
            models.ActivityBeat.scheduled_for == scheduled,
            models.ActivityBeat.idempotency_key == idempotency_key,
        )
        .with_for_update()
    )
    if existing is not None:
        if existing.episode_id != episode.id or existing.world_id != episode.world_id:
            raise ActivityRuntimeValidationError("cross_world_reference")
        if existing.status == "claimed":
            existing_expiry = (
                _aware_utc(existing.claim_expires_at)
                if existing.claim_expires_at is not None
                else current
            )
            if existing.claim_run_id == claim_run_id and existing_expiry > current:
                return RuntimeClaimResult(existing, True)
            if existing_expiry > current:
                raise ActivityRuntimeConflictError("beat_already_claimed")
            existing.status = "pending"
            existing.claim_run_id = None
            existing.claim_expires_at = None
        if existing.status != "pending":
            raise ActivityRuntimeConflictError("beat_already_terminal")
        if existing.attempt_count >= 2:
            raise ActivityRuntimeConflictError("beat_retry_limit_reached")
        existing.status = "claimed"
        existing.claim_run_id = claim_run_id
        existing.claim_expires_at = expiry
        existing.attempt_count += 1
        existing.started_at = current
        db.commit()
        return RuntimeClaimResult(existing, False)

    beat = models.ActivityBeat(
        id=uuid7_string(),
        world_id=episode.world_id,
        world_character_id=episode.world_character_id,
        episode_id=episode.id,
        sequence_no=episode.next_sequence_no,
        scheduled_for=scheduled,
        trigger_kind=trigger_kind,
        status="claimed",
        previous_successful_beat_id=episode.last_successful_beat_id,
        source_event_ids=list(dict.fromkeys(source_event_ids or [])),
        state_before_snapshot=state_before,
        idempotency_key=idempotency_key,
        claim_run_id=claim_run_id,
        claim_expires_at=expiry,
        attempt_count=1,
        skipped_tick_count=skipped_tick_count,
        started_at=current,
    )
    db.add(beat)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = db.scalar(
            select(models.ActivityBeat).where(
                models.ActivityBeat.world_character_id
                == episode.world_character_id,
                models.ActivityBeat.scheduled_for == scheduled,
                models.ActivityBeat.idempotency_key == idempotency_key,
            )
        )
        if replay is None:
            raise ActivityRuntimeConflictError("beat_already_claimed") from exc
        if replay.claim_run_id == claim_run_id and replay.status == "claimed":
            return RuntimeClaimResult(replay, True)
        raise ActivityRuntimeConflictError("beat_already_claimed") from exc
    return RuntimeClaimResult(beat, False)


def claim_event_consumption(
    db: Session,
    *,
    world_id: str,
    consumer_world_character_id: str,
    source_social_event_id: str,
    target_activity_beat_id: str,
    idempotency_key: str,
    claim_run_id: str,
    claim_expires_at: datetime,
    now: datetime | None = None,
) -> RuntimeClaimResult:
    current = _aware_utc(now or datetime.now(UTC))
    expiry = _require_future_expiry(claim_expires_at, now=current)
    world_character = db.get(models.WorldCharacter, consumer_world_character_id)
    beat = db.get(models.ActivityBeat, target_activity_beat_id)
    if world_character is None or beat is None:
        raise ActivityRuntimeNotFoundError(source_social_event_id)
    if (
        world_character.world_id != world_id
        or beat.world_id != world_id
        or beat.world_character_id != consumer_world_character_id
    ):
        raise ActivityRuntimeValidationError("cross_world_reference")
    existing = db.scalar(
        select(models.ActivityEventConsumption)
        .where(
            models.ActivityEventConsumption.consumer_world_character_id
            == consumer_world_character_id,
            models.ActivityEventConsumption.source_social_event_id
            == source_social_event_id,
            models.ActivityEventConsumption.namespace == EVENT_CONSUMPTION_NAMESPACE,
        )
        .with_for_update()
    )
    if existing is not None:
        if existing.world_id != world_id:
            raise ActivityRuntimeValidationError("cross_world_reference")
        if existing.status == "applied":
            raise ActivityRuntimeConflictError("source_event_already_consumed")
        if existing.status == "rejected":
            raise ActivityRuntimeConflictError("source_event_rejected")
    if beat.status != "claimed" or beat.claim_run_id != claim_run_id:
        raise ActivityRuntimeConflictError("beat_already_claimed")
    if existing is not None:
        if existing.status == "claimed":
            existing_expiry = (
                _aware_utc(existing.claim_expires_at)
                if existing.claim_expires_at is not None
                else current
            )
            if (
                existing.claim_run_id == claim_run_id
                and existing.target_activity_beat_id == target_activity_beat_id
                and existing_expiry > current
            ):
                return RuntimeClaimResult(existing, True)
            if existing_expiry > current:
                raise ActivityRuntimeConflictError("source_event_already_claimed")
        existing.status = "claimed"
        existing.target_activity_beat_id = target_activity_beat_id
        existing.idempotency_key = idempotency_key
        existing.claim_run_id = claim_run_id
        existing.claim_expires_at = expiry
        existing.applied_at = None
        existing.rejected_reason_code = None
        existing.version += 1
        db.commit()
        return RuntimeClaimResult(existing, False)

    consumption = models.ActivityEventConsumption(
        id=uuid7_string(),
        world_id=world_id,
        consumer_world_character_id=consumer_world_character_id,
        source_social_event_id=source_social_event_id,
        namespace=EVENT_CONSUMPTION_NAMESPACE,
        target_activity_beat_id=target_activity_beat_id,
        status="claimed",
        idempotency_key=idempotency_key,
        claim_run_id=claim_run_id,
        claim_expires_at=expiry,
        version=1,
    )
    db.add(consumption)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ActivityRuntimeConflictError("source_event_already_claimed") from exc
    return RuntimeClaimResult(consumption, False)


def release_event_consumption(
    db: Session,
    *,
    consumption_id: str,
    claim_run_id: str,
) -> models.ActivityEventConsumption:
    row = db.scalar(
        select(models.ActivityEventConsumption)
        .where(models.ActivityEventConsumption.id == consumption_id)
        .with_for_update()
    )
    if row is None:
        raise ActivityRuntimeNotFoundError(consumption_id)
    if row.status != "claimed" or row.claim_run_id != claim_run_id:
        raise ActivityRuntimeConflictError("source_event_already_claimed")
    row.status = "released"
    row.claim_run_id = None
    row.claim_expires_at = None
    row.target_activity_beat_id = None
    row.version += 1
    db.commit()
    return row


def reject_event_consumption(
    db: Session,
    *,
    consumption_id: str,
    claim_run_id: str,
    reason_code: str,
) -> models.ActivityEventConsumption:
    row = db.scalar(
        select(models.ActivityEventConsumption)
        .where(models.ActivityEventConsumption.id == consumption_id)
        .with_for_update()
    )
    if row is None:
        raise ActivityRuntimeNotFoundError(consumption_id)
    if row.status != "claimed" or row.claim_run_id != claim_run_id:
        raise ActivityRuntimeConflictError("source_event_already_claimed")
    row.status = "rejected"
    row.rejected_reason_code = reason_code
    row.claim_run_id = None
    row.claim_expires_at = None
    row.target_activity_beat_id = None
    row.version += 1
    db.commit()
    return row


def complete_activity_beat(
    db: Session,
    *,
    beat_id: str,
    claim_run_id: str,
    source_post_id: str,
    state_after_snapshot: dict[str, object],
    result_snapshot: dict[str, object],
    external_claimed_source_event_ids: set[str] | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> models.ActivityBeat:
    current = _aware_utc(now or datetime.now(UTC))
    beat, episode, item, plan = _lock_beat_with_episode_scope(
        db,
        beat_id=beat_id,
    )
    if beat.status != "claimed" or beat.claim_run_id != claim_run_id:
        raise ActivityRuntimeConflictError("beat_already_claimed")
    if beat.claim_expires_at is None or _aware_utc(beat.claim_expires_at) <= current:
        raise ActivityRuntimeConflictError("beat_claim_expired")
    if beat.world_id != episode.world_id or beat.world_character_id != episode.world_character_id:
        raise ActivityRuntimeValidationError("cross_world_reference")
    if beat.previous_successful_beat_id != episode.last_successful_beat_id:
        raise ActivityRuntimeConflictError("previous_successful_beat_stale")
    if activity_state_contracts.validate_state_snapshot(
        episode.current_state_snapshot
    ) != activity_state_contracts.validate_state_snapshot(beat.state_before_snapshot):
        raise ActivityRuntimeConflictError("activity_state_stale")
    next_state = activity_state_contracts.validate_state_snapshot(
        state_after_snapshot
    )
    post = db.get(models.Post, source_post_id)
    world_character = db.get(models.WorldCharacter, beat.world_character_id)
    if post is None or world_character is None:
        raise ActivityRuntimeValidationError("publish_evidence_missing")
    if post.author_character_id != world_character.character_id:
        raise ActivityRuntimeValidationError("publish_evidence_invalid")
    if world_character.activity_runtime_mode == "routine_resident_v1" and (
        post.world_id != beat.world_id
        or post.author_world_character_id != beat.world_character_id
    ):
        raise ActivityRuntimeValidationError("publish_evidence_world_invalid")

    consumptions = list(
        db.scalars(
            select(models.ActivityEventConsumption)
            .where(
                models.ActivityEventConsumption.target_activity_beat_id == beat.id
            )
            .with_for_update()
        )
    )
    claimed_event_ids = {
        row.source_social_event_id
        for row in consumptions
        if row.status == "claimed" and row.claim_run_id == claim_run_id
    }
    claimed_event_ids.update(external_claimed_source_event_ids or set())
    if set(beat.source_event_ids) != claimed_event_ids:
        raise ActivityRuntimeValidationError("source_event_claim_mismatch")

    beat.status = "succeeded"
    beat.source_post_id = source_post_id
    beat.state_after_snapshot = next_state
    beat.result_snapshot = result_snapshot
    beat.claim_run_id = None
    beat.claim_expires_at = None
    beat.completed_at = current
    episode.status = "active"
    episode.current_state_snapshot = next_state
    episode.last_successful_beat_id = beat.id
    episode.next_sequence_no = beat.sequence_no + 1
    episode.started_at = episode.started_at or current
    episode.version += 1
    item.status = "active"
    item.version += 1
    plan.status = "active"
    plan.version += 1
    for row in consumptions:
        row.status = "applied"
        row.claim_run_id = None
        row.claim_expires_at = None
        row.applied_at = current
        row.version += 1
    if commit:
        db.commit()
    else:
        db.flush()
    return beat


def release_activity_beat_for_retry(
    db: Session,
    *,
    beat_id: str,
    claim_run_id: str,
    reason_code: str,
) -> models.ActivityBeat:
    beat = db.scalar(
        select(models.ActivityBeat)
        .where(models.ActivityBeat.id == beat_id)
        .with_for_update()
    )
    if beat is None:
        raise ActivityRuntimeNotFoundError(beat_id)
    if beat.status != "claimed" or beat.claim_run_id != claim_run_id:
        raise ActivityRuntimeConflictError("beat_already_claimed")
    if beat.attempt_count >= 2:
        raise ActivityRuntimeConflictError("beat_retry_limit_reached")
    beat.status = "pending"
    beat.failure_reason_code = reason_code
    beat.state_after_snapshot = None
    beat.source_post_id = None
    beat.result_snapshot = None
    beat.claim_run_id = None
    beat.claim_expires_at = None
    beat.started_at = None
    for row in db.scalars(
        select(models.ActivityEventConsumption)
        .where(
            models.ActivityEventConsumption.target_activity_beat_id == beat.id,
            models.ActivityEventConsumption.status == "claimed",
            models.ActivityEventConsumption.claim_run_id == claim_run_id,
        )
        .with_for_update()
    ):
        row.status = "released"
        row.claim_run_id = None
        row.claim_expires_at = None
        row.target_activity_beat_id = None
        row.version += 1
    db.commit()
    return beat


def fail_activity_beat(
    db: Session,
    *,
    beat_id: str,
    claim_run_id: str,
    reason_code: str,
    now: datetime | None = None,
) -> models.ActivityBeat:
    current = _aware_utc(now or datetime.now(UTC))
    beat, episode, _item, _plan = _lock_beat_with_episode_scope(
        db,
        beat_id=beat_id,
    )
    if beat.status != "claimed" or beat.claim_run_id != claim_run_id:
        raise ActivityRuntimeConflictError("beat_already_claimed")
    beat.status = "failed"
    beat.failure_reason_code = reason_code
    beat.state_after_snapshot = None
    beat.source_post_id = None
    beat.result_snapshot = None
    beat.claim_run_id = None
    beat.claim_expires_at = None
    beat.completed_at = current
    # A failed publication does not advance the narrative state, but the
    # execution-ledger ordinal must advance so the next due tick can be
    # recorded without colliding with this retained failure evidence.
    episode.next_sequence_no = max(episode.next_sequence_no, beat.sequence_no + 1)
    episode.version += 1
    for row in db.scalars(
        select(models.ActivityEventConsumption)
        .where(
            models.ActivityEventConsumption.target_activity_beat_id == beat.id,
            models.ActivityEventConsumption.status == "claimed",
            models.ActivityEventConsumption.claim_run_id == claim_run_id,
        )
        .with_for_update()
    ):
        row.status = "released"
        row.claim_run_id = None
        row.claim_expires_at = None
        row.target_activity_beat_id = None
        row.version += 1
    db.commit()
    return beat


def recover_expired_claims(
    db: Session,
    *,
    now: datetime | None = None,
) -> RecoveryCounts:
    current = _aware_utc(now or datetime.now(UTC))
    beats = list(
        db.scalars(
            select(models.ActivityBeat)
            .where(
                models.ActivityBeat.status == "claimed",
                models.ActivityBeat.claim_expires_at <= current,
            )
            .with_for_update(skip_locked=True)
        )
    )
    for beat in beats:
        beat.status = "pending"
        beat.claim_run_id = None
        beat.claim_expires_at = None
        beat.started_at = None
    consumptions = list(
        db.scalars(
            select(models.ActivityEventConsumption)
            .where(
                models.ActivityEventConsumption.status == "claimed",
                models.ActivityEventConsumption.claim_expires_at <= current,
            )
            .with_for_update(skip_locked=True)
        )
    )
    for row in consumptions:
        row.status = "released"
        row.claim_run_id = None
        row.claim_expires_at = None
        row.target_activity_beat_id = None
        row.version += 1
    db.commit()
    return RecoveryCounts(beats=len(beats), consumptions=len(consumptions))


def _close_open_beat_claims(
    db: Session,
    *,
    episode_id: str,
    reason_code: str,
    now: datetime,
) -> None:
    beats = list(
        db.scalars(
            select(models.ActivityBeat)
            .where(
                models.ActivityBeat.episode_id == episode_id,
                models.ActivityBeat.status.in_({"pending", "claimed"}),
            )
            .with_for_update()
        )
    )
    beat_ids = [beat.id for beat in beats]
    if beat_ids:
        for row in db.scalars(
            select(models.ActivityEventConsumption)
            .where(
                models.ActivityEventConsumption.target_activity_beat_id.in_(beat_ids),
                models.ActivityEventConsumption.status == "claimed",
            )
            .with_for_update()
        ):
            row.status = "released"
            row.claim_run_id = None
            row.claim_expires_at = None
            row.target_activity_beat_id = None
            row.version += 1
    for beat in beats:
        beat.status = "cancelled"
        beat.failure_reason_code = reason_code
        beat.claim_run_id = None
        beat.claim_expires_at = None
        beat.completed_at = now


def close_elapsed_dayparts(
    db: Session,
    *,
    world_character_id: str,
    now: datetime | None = None,
) -> DaypartTransitionCounts:
    """Close elapsed items without generating catch-up SNS activity."""

    current = _aware_utc(now or datetime.now(UTC))
    items = list(
        db.scalars(
            select(models.DailyActivityPlanItem)
            .where(
                models.DailyActivityPlanItem.world_character_id
                == world_character_id,
                models.DailyActivityPlanItem.scheduled_end_at <= current,
                models.DailyActivityPlanItem.status.in_({"planned", "active"}),
            )
            .order_by(models.DailyActivityPlanItem.scheduled_start_at)
            .with_for_update(skip_locked=True)
        )
    )
    completed = 0
    skipped = 0
    affected_plan_ids: set[str] = set()
    for item in items:
        episode = db.scalar(
            select(models.ActivityEpisode)
            .where(models.ActivityEpisode.plan_item_id == item.id)
            .with_for_update()
        )
        if episode is None:
            raise ActivityRuntimeValidationError("activity_episode_missing")
        affected_plan_ids.add(item.plan_id)
        if item.status == "active":
            successful_beats = list(
                db.scalars(
                    select(models.ActivityBeat)
                    .where(
                        models.ActivityBeat.episode_id == episode.id,
                        models.ActivityBeat.status == "succeeded",
                    )
                    .order_by(models.ActivityBeat.sequence_no)
                )
            )
            episode.current_state_snapshot = (
                activity_state_contracts.apply_state_changes(
                    episode.current_state_snapshot,
                    [],
                    daypart_ended=True,
                )
            )
            episode.status = "completed"
            episode.completed_at = current
            episode.completion_summary = {
                "successful_beat_count": len(successful_beats),
                "successful_post_ids": [
                    beat.source_post_id
                    for beat in successful_beats
                    if beat.source_post_id is not None
                ],
            }
            episode.terminal_reason_code = "daypart_completed"
            item.status = "completed"
            item.terminal_reason_code = "daypart_completed"
            completed += 1
        else:
            episode.status = "cancelled"
            episode.completed_at = current
            episode.terminal_reason_code = "daypart_window_elapsed"
            item.status = "skipped"
            item.terminal_reason_code = "daypart_window_elapsed"
            skipped += 1
        episode.version += 1
        item.version += 1
        _close_open_beat_claims(
            db,
            episode_id=episode.id,
            reason_code=item.terminal_reason_code or "daypart_window_elapsed",
            now=current,
        )

    db.flush()
    for plan_id in affected_plan_ids:
        plan = db.scalar(
            select(models.DailyActivityPlan)
            .where(models.DailyActivityPlan.id == plan_id)
            .with_for_update()
        )
        if plan is None:
            raise ActivityRuntimeValidationError("activity_plan_missing")
        statuses = set(
            db.scalars(
                select(models.DailyActivityPlanItem.status).where(
                    models.DailyActivityPlanItem.plan_id == plan_id
                )
            )
        )
        if statuses and statuses.issubset(TERMINAL_ITEM_STATUSES):
            plan.status = "completed"
        elif "active" in statuses:
            plan.status = "active"
        plan.version += 1
    db.commit()
    return DaypartTransitionCounts(completed=completed, skipped=skipped)


def interrupt_inactive_world_character(
    db: Session,
    *,
    world_character_id: str,
    now: datetime | None = None,
) -> WorldInterruptionCounts:
    """Stop current/future runtime after a World membership is deactivated."""

    current = _aware_utc(now or datetime.now(UTC))
    world_character = db.scalar(
        select(models.WorldCharacter)
        .where(models.WorldCharacter.id == world_character_id)
        .with_for_update()
    )
    if world_character is None:
        raise ActivityRuntimeNotFoundError(world_character_id)
    membership = db.get(models.WorldMembership, world_character.membership_id)
    if membership is None or membership.world_id != world_character.world_id:
        raise ActivityRuntimeValidationError("cross_world_reference")
    if membership.status == "active" and world_character.status == "active":
        raise ActivityRuntimeConflictError("world_membership_still_active")

    items = list(
        db.scalars(
            select(models.DailyActivityPlanItem)
            .where(
                models.DailyActivityPlanItem.world_character_id
                == world_character_id,
                models.DailyActivityPlanItem.status.in_({"planned", "active"}),
                models.DailyActivityPlanItem.scheduled_end_at > current,
            )
            .order_by(models.DailyActivityPlanItem.scheduled_start_at)
            .with_for_update()
        )
    )
    interrupted = 0
    cancelled = 0
    affected_plan_ids: set[str] = set()
    for item in items:
        episode = db.scalar(
            select(models.ActivityEpisode)
            .where(models.ActivityEpisode.plan_item_id == item.id)
            .with_for_update()
        )
        if episode is None:
            raise ActivityRuntimeValidationError("activity_episode_missing")
        affected_plan_ids.add(item.plan_id)
        if item.status == "active":
            item.status = "interrupted"
            episode.status = "interrupted"
            interrupted += 1
        else:
            item.status = "cancelled"
            episode.status = "cancelled"
            cancelled += 1
        item.terminal_reason_code = "world_membership_inactive"
        episode.terminal_reason_code = "world_membership_inactive"
        episode.completed_at = current
        item.version += 1
        episode.version += 1
        _close_open_beat_claims(
            db,
            episode_id=episode.id,
            reason_code="world_membership_inactive",
            now=current,
        )
    for plan_id in affected_plan_ids:
        plan = db.scalar(
            select(models.DailyActivityPlan)
            .where(models.DailyActivityPlan.id == plan_id)
            .with_for_update()
        )
        if plan is None:
            raise ActivityRuntimeValidationError("activity_plan_missing")
        plan.status = "interrupted"
        plan.version += 1
    db.commit()
    return WorldInterruptionCounts(
        interrupted=interrupted,
        cancelled=cancelled,
    )
