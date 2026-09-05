from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines.policies import activity_state
from app.domains.routines.exceptions import ActivityRuntimeConflictError, ActivityRuntimeNotFoundError, ActivityRuntimeValidationError
from app.domains.routines.contracts.lifecycle import DaypartTransitionCounts, RecoveryCounts, WorldInterruptionCounts
from app.domains.routines.service.scheduling import aware_utc
from app.domains.routines import models as models
from app.domains.world_characters.public import WorldCharacter
from app.domains.worlds.public import WorldMembership


TERMINAL_ITEM_STATUSES = frozenset(
    {"completed", "skipped", "interrupted", "cancelled"}
)


def _require_autonomous(db: Session, world_character_id: str) -> WorldCharacter:
    world_character = db.get(WorldCharacter, world_character_id)
    if world_character is None:
        raise ActivityRuntimeNotFoundError(world_character_id)
    if world_character.control_mode != "autonomous":
        raise ActivityRuntimeValidationError("owner_controlled_automation_disabled")
    return world_character


def recover_expired_claims(
    db: Session, *, now: datetime
) -> RecoveryCounts:
    current = aware_utc(now)
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
        _require_autonomous(db, beat.world_character_id)
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
        _require_autonomous(db, row.consumer_world_character_id)
        row.status = "released"
        row.claim_run_id = None
        row.claim_expires_at = None
        row.target_activity_beat_id = None
        row.version += 1
    db.commit()
    return RecoveryCounts(beats=len(beats), consumptions=len(consumptions))


def _close_open_beat_claims(
    db: Session, *, episode_id: str, reason_code: str, now: datetime
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
    db: Session, *, world_character_id: str, now: datetime
) -> DaypartTransitionCounts:
    """Close elapsed items without creating catch-up provider or SNS work."""

    _require_autonomous(db, world_character_id)
    current = aware_utc(now)
    items = list(
        db.scalars(
            select(models.DailyActivityPlanItem)
            .where(
                models.DailyActivityPlanItem.world_character_id == world_character_id,
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
            episode.current_state_snapshot = activity_state.apply_state_changes(
                episode.current_state_snapshot,
                [],
                daypart_ended=True,
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


def reconcile_all_elapsed_routines(
    db: Session, *, now: datetime
) -> DaypartTransitionCounts:
    """Reconcile eligible autonomous plans once; owner-controlled rows stay invisible."""

    current = aware_utc(now)
    world_character_ids = list(
        db.scalars(
            select(models.DailyActivityPlanItem.world_character_id)
            .join(
                WorldCharacter,
                WorldCharacter.id
                == models.DailyActivityPlanItem.world_character_id,
            )
            .where(
                models.DailyActivityPlanItem.scheduled_end_at <= current,
                models.DailyActivityPlanItem.status.in_({"planned", "active"}),
                WorldCharacter.control_mode == "autonomous",
            )
            .distinct()
        )
    )
    completed = 0
    skipped = 0
    for world_character_id in world_character_ids:
        transition = close_elapsed_dayparts(
            db,
            world_character_id=world_character_id,
            now=current,
        )
        completed += transition.completed
        skipped += transition.skipped
    return DaypartTransitionCounts(completed=completed, skipped=skipped)


def interrupt_inactive_world_character(
    db: Session, *, world_character_id: str, now: datetime
) -> WorldInterruptionCounts:
    current = aware_utc(now)
    world_character = _require_autonomous(db, world_character_id)
    membership = db.get(WorldMembership, world_character.membership_id)
    if membership is None or membership.world_id != world_character.world_id:
        raise ActivityRuntimeValidationError("cross_world_reference")
    if membership.status == "active" and world_character.status == "active":
        raise ActivityRuntimeConflictError("world_membership_still_active")

    items = list(
        db.scalars(
            select(models.DailyActivityPlanItem)
            .where(
                models.DailyActivityPlanItem.world_character_id == world_character_id,
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
    return WorldInterruptionCounts(interrupted=interrupted, cancelled=cancelled)


class SqlAlchemyLifecycleRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def reconcile_elapsed(self, *, now: datetime) -> DaypartTransitionCounts:
        return reconcile_all_elapsed_routines(self._db, now=now)

    def recover_expired_claims(self, *, now: datetime) -> RecoveryCounts:
        return recover_expired_claims(self._db, now=now)


__all__ = [
    "SqlAlchemyLifecycleRepository",
    "close_elapsed_dayparts",
    "interrupt_inactive_world_character",
    "reconcile_all_elapsed_routines",
    "recover_expired_claims",
]
