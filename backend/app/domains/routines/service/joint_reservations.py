from __future__ import annotations

from datetime import UTC, date, datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.routines import models as routine_models


DAYPARTS = ("dawn", "morning", "afternoon", "evening")
ACTIVE_JOINT_STATUSES = {"scheduled", "ready", "active"}


class JointActivityReservationError(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _participant_rows(
    db: Session, *, joint_activity_id: str, lock: bool = False
) -> list[routine_models.JointActivityParticipant]:
    statement = (
        select(routine_models.JointActivityParticipant)
        .where(
            routine_models.JointActivityParticipant.joint_activity_id
            == joint_activity_id
        )
        .order_by(routine_models.JointActivityParticipant.world_character_id)
    )
    if lock:
        statement = statement.with_for_update()
    rows = list(db.scalars(statement))
    if len(rows) != 2 or {row.role for row in rows} != {"proposer", "acceptor"}:
        raise JointActivityReservationError("joint_activity_participant_invalid")
    return rows


def reservation_for(
    db: Session,
    *,
    world_character_id: str,
    local_date: date,
    daypart: str,
) -> routine_models.JointActivity | None:
    return db.scalar(
        select(routine_models.JointActivity)
        .join(
            routine_models.JointActivityParticipant,
            routine_models.JointActivityParticipant.joint_activity_id
            == routine_models.JointActivity.id,
        )
        .where(
            routine_models.JointActivityParticipant.world_character_id
            == world_character_id,
            routine_models.JointActivity.scheduled_local_date == local_date,
            routine_models.JointActivity.target_daypart == daypart,
            routine_models.JointActivity.status.in_(ACTIVE_JOINT_STATUSES),
        )
        .order_by(
            routine_models.JointActivity.created_at,
            routine_models.JointActivity.id,
        )
        .limit(1)
    )


def _item_snapshot(
    item: routine_models.DailyActivityPlanItem,
) -> dict[str, object]:
    return {
        "id": item.id,
        "origin_type": item.origin_type,
        "joint_activity_id": item.joint_activity_id,
        "activity_kind": item.activity_kind,
        "title": item.title,
        "activity_seed": item.activity_seed,
        "social_mode": item.social_mode,
        "place_key": item.place_key,
        "status": item.status,
        "scheduled_start_at": _aware_utc(item.scheduled_start_at).isoformat(),
        "scheduled_end_at": _aware_utc(item.scheduled_end_at).isoformat(),
    }


def _joint_snapshot(joint: routine_models.JointActivity) -> dict[str, object]:
    return {
        "joint_activity_id": joint.id,
        "origin_type": "joint_activity",
        "activity_kind": "joint_activity",
        "title": joint.activity_seed[:120],
        "activity_seed": joint.activity_seed,
        "social_mode": "joint",
        "place_key": joint.place_key,
        "scheduled_local_date": (
            joint.scheduled_local_date.isoformat()
            if joint.scheduled_local_date is not None
            else None
        ),
        "target_daypart": joint.target_daypart,
    }


def _materialize_existing_plan(
    db: Session,
    *,
    joint: routine_models.JointActivity,
    participant: routine_models.JointActivityParticipant,
    acceptance_event_id: str,
    now: datetime,
) -> str | None:
    plan = db.scalar(
        select(routine_models.DailyActivityPlan)
        .where(
            routine_models.DailyActivityPlan.world_id == joint.world_id,
            routine_models.DailyActivityPlan.world_character_id
            == participant.world_character_id,
            routine_models.DailyActivityPlan.local_date == joint.scheduled_local_date,
        )
        .with_for_update()
    )
    if plan is None:
        return None
    base_item = db.scalar(
        select(routine_models.DailyActivityPlanItem)
        .where(
            routine_models.DailyActivityPlanItem.plan_id == plan.id,
            routine_models.DailyActivityPlanItem.daypart == joint.target_daypart,
            routine_models.DailyActivityPlanItem.status != "superseded",
        )
        .with_for_update()
    )
    if base_item is None:
        raise JointActivityReservationError("joint_activity_schedule_conflict")
    episode = db.scalar(
        select(routine_models.ActivityEpisode)
        .where(routine_models.ActivityEpisode.plan_item_id == base_item.id)
        .with_for_update()
    )
    if (
        base_item.origin_type != "repertoire"
        or base_item.joint_activity_id is not None
        or base_item.is_user_pinned
        or base_item.status != "planned"
        or _aware_utc(base_item.scheduled_start_at) <= _aware_utc(now)
        or episode is None
        or episode.status != "planned"
        or episode.started_at is not None
    ):
        raise JointActivityReservationError("joint_activity_schedule_conflict")
    if plan.revision_count >= 2 or base_item.revision_count >= 1:
        raise JointActivityReservationError("joint_activity_revision_limit")

    before = _item_snapshot(base_item)
    base_item.status = "superseded"
    base_item.terminal_reason_code = "accepted_joint_activity"
    base_item.revision_count += 1
    base_item.version += 1
    episode.status = "cancelled"
    episode.terminal_reason_code = "plan_item_superseded"
    episode.completed_at = _aware_utc(now)
    episode.version += 1

    joint_item = routine_models.DailyActivityPlanItem(
        id=uuid7_string(),
        plan_id=plan.id,
        world_id=joint.world_id,
        world_character_id=participant.world_character_id,
        daypart=str(joint.target_daypart),
        selected_candidate_id=None,
        candidate_signature=None,
        candidate_ordinal=None,
        origin_type="joint_activity",
        supersedes_plan_item_id=base_item.id,
        is_user_pinned=False,
        activity_kind="joint_activity",
        title=joint.activity_seed[:120],
        activity_seed=joint.activity_seed,
        social_mode="joint",
        place_key=joint.place_key,
        joint_activity_id=joint.id,
        scheduled_start_at=base_item.scheduled_start_at,
        scheduled_end_at=base_item.scheduled_end_at,
        status="planned",
        revision_count=1,
        version=1,
    )
    db.add(joint_item)
    db.flush()
    joint_episode = routine_models.ActivityEpisode(
        id=uuid7_string(),
        world_id=joint.world_id,
        world_character_id=participant.world_character_id,
        plan_item_id=joint_item.id,
        effective_activity_snapshot=_joint_snapshot(joint),
        status="planned",
        current_state_schema_version=1,
        current_state_snapshot={
            "mood": "neutral",
            "mood_intensity": 0,
            "energy": 50,
            "social_energy": 50,
            "action_note": "",
        },
        next_sequence_no=1,
        version=1,
    )
    db.add(joint_episode)
    plan.revision_count += 1
    plan.version += 1
    participant.linked_daily_activity_plan_item_id = joint_item.id
    participant.linked_activity_episode_id = joint_episode.id
    participant.participation_status = "scheduled"
    db.add(
        routine_models.ActivityPlanRevision(
            id=uuid7_string(),
            plan_id=plan.id,
            plan_item_id=joint_item.id,
            joint_activity_id=joint.id,
            revision_ordinal=plan.revision_count,
            before_snapshot=before,
            after_snapshot=_item_snapshot(joint_item),
            source_acceptance_event_id=acceptance_event_id,
            reason_code="accepted_joint_activity",
            idempotency_key=sha256(
                f"joint-plan|{joint.id}|{participant.world_character_id}".encode(
                    "utf-8"
                )
            ).hexdigest(),
            applied_at=_aware_utc(now),
        )
    )
    return joint_item.id


def materialize_reservation_for_new_plan(
    db: Session,
    *,
    plan: routine_models.DailyActivityPlan,
    joint: routine_models.JointActivity,
    scheduled_start_at: datetime,
    scheduled_end_at: datetime,
    now: datetime,
) -> tuple[routine_models.DailyActivityPlanItem, routine_models.ActivityEpisode]:
    if (
        joint.scheduled_local_date != plan.local_date
        or joint.target_daypart not in DAYPARTS
        or joint.world_id != plan.world_id
    ):
        raise JointActivityReservationError("joint_activity_schedule_conflict")
    participant = db.scalar(
        select(routine_models.JointActivityParticipant)
        .where(
            routine_models.JointActivityParticipant.joint_activity_id == joint.id,
            routine_models.JointActivityParticipant.world_character_id
            == plan.world_character_id,
        )
        .with_for_update()
    )
    if participant is None:
        raise JointActivityReservationError("joint_activity_participant_invalid")
    if participant.linked_daily_activity_plan_item_id is not None:
        existing_item = db.get(
            routine_models.DailyActivityPlanItem,
            participant.linked_daily_activity_plan_item_id,
        )
        existing_episode = db.get(
            routine_models.ActivityEpisode,
            participant.linked_activity_episode_id,
        )
        if existing_item is None or existing_episode is None:
            raise JointActivityReservationError(
                "joint_activity_partial_schedule_forbidden"
            )
        return existing_item, existing_episode

    item = routine_models.DailyActivityPlanItem(
        id=uuid7_string(),
        plan_id=plan.id,
        world_id=plan.world_id,
        world_character_id=plan.world_character_id,
        daypart=str(joint.target_daypart),
        selected_candidate_id=None,
        candidate_signature=None,
        candidate_ordinal=None,
        origin_type="joint_activity",
        is_user_pinned=False,
        activity_kind="joint_activity",
        title=joint.activity_seed[:120],
        activity_seed=joint.activity_seed,
        social_mode="joint",
        place_key=joint.place_key,
        joint_activity_id=joint.id,
        scheduled_start_at=scheduled_start_at,
        scheduled_end_at=scheduled_end_at,
        status="planned",
        revision_count=0,
        version=1,
    )
    db.add(item)
    db.flush()
    episode = routine_models.ActivityEpisode(
        id=uuid7_string(),
        world_id=plan.world_id,
        world_character_id=plan.world_character_id,
        plan_item_id=item.id,
        effective_activity_snapshot=_joint_snapshot(joint),
        status="planned",
        current_state_schema_version=1,
        current_state_snapshot={
            "mood": "neutral",
            "mood_intensity": 0,
            "energy": 50,
            "social_energy": 50,
            "action_note": "",
        },
        next_sequence_no=1,
        version=1,
    )
    db.add(episode)
    participant.linked_daily_activity_plan_item_id = item.id
    participant.linked_activity_episode_id = episode.id
    participant.participation_status = "scheduled"
    db.flush()

    if joint.source_acceptance_event_id is None:
        raise JointActivityReservationError(
            "joint_activity_acceptance_evidence_missing"
        )
    other_participants = [
        row
        for row in _participant_rows(db, joint_activity_id=joint.id, lock=True)
        if row.world_character_id != plan.world_character_id
        and row.linked_daily_activity_plan_item_id is None
    ]
    for other in other_participants:
        other_plan_id = db.scalar(
            select(routine_models.DailyActivityPlan.id).where(
                routine_models.DailyActivityPlan.world_id == joint.world_id,
                routine_models.DailyActivityPlan.world_character_id
                == other.world_character_id,
                routine_models.DailyActivityPlan.local_date
                == joint.scheduled_local_date,
            )
        )
        if other_plan_id is None:
            continue
        linked_id = _materialize_existing_plan(
            db,
            joint=joint,
            participant=other,
            acceptance_event_id=joint.source_acceptance_event_id,
            now=now,
        )
        if linked_id is None:
            raise JointActivityReservationError(
                "joint_activity_partial_schedule_forbidden"
            )
    participants = _participant_rows(db, joint_activity_id=joint.id)
    if all(row.linked_daily_activity_plan_item_id is not None for row in participants):
        joint.status = "ready"
        joint.version += 1
    return item, episode


__all__ = [
    "JointActivityReservationError",
    "materialize_reservation_for_new_plan",
    "reservation_for",
]
