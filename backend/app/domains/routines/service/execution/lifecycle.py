"""Lifecycle used after caller admission; preserve the legacy scope contract."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.constants import TERMINAL_ITEM_STATUSES
from app.domains.routines.contracts.activity import ActivityReferences
from app.domains.routines.contracts.lifecycle import DaypartTransitionCounts, RecoveryCounts, WorldInterruptionCounts
from app.domains.routines.exceptions import ActivityRuntimeConflictError, ActivityRuntimeNotFoundError, ActivityRuntimeValidationError
from app.domains.routines.policies import activity_state as activity_state_contracts
from app.domains.routines.service.execution.claims import _close_open_beat_claims
from app.domains.routines.service.scheduling import aware_utc as _aware_utc


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
    references: ActivityReferences,
    world_character_id: str,
    now: datetime | None = None,
) -> WorldInterruptionCounts:
    """Stop current/future runtime after a World membership is deactivated."""

    current = _aware_utc(now or datetime.now(UTC))
    world_character = references.get_world_character(world_character_id, lock_for_update=True)
    if world_character is None:
        raise ActivityRuntimeNotFoundError(world_character_id)
    membership = references.get_membership(world_character.membership_id)
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
