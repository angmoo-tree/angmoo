"""Joint reservations, two-participant plan materialization and revision policy."""
from __future__ import annotations
from datetime import date, datetime
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.routines import models
from app.domains.routines.contracts.joint_activity import JointReferences
from app.domains.routines.exceptions import JointActivityRuntimeError
from app.domains.routines.service.scheduling import aware_utc as _aware_utc
from dataclasses import dataclass
from hashlib import sha256
from sqlalchemy import func
from app.core.ids import uuid7_string
from app.domains.routines.constants import DAYPARTS, ACTIVE_JOINT_STATUSES
from app.domains.routines.service.joint_activity.eligibility import _eligible_world_character, validate_pair


@dataclass(frozen=True)
class ScheduledJoint:
    joint_activity: models.JointActivity
    linked_item_ids: tuple[str, ...]



def _participant_rows(
    db: Session, *, joint_activity_id: str, lock: bool = False
) -> list[models.JointActivityParticipant]:
    statement = (
        select(models.JointActivityParticipant)
        .where(
            models.JointActivityParticipant.joint_activity_id == joint_activity_id
        )
        .order_by(models.JointActivityParticipant.world_character_id)
    )
    if lock:
        statement = statement.with_for_update()
    rows = list(db.scalars(statement))
    if len(rows) != 2 or {row.role for row in rows} != {"proposer", "acceptor"}:
        raise JointActivityRuntimeError("joint_activity_participant_invalid")
    return rows



def active_commitment_count(db: Session, *, world_character_id: str) -> int:
    return int(
        db.scalar(
            select(func.count(models.JointActivityParticipant.joint_activity_id))
            .join(
                models.JointActivity,
                models.JointActivity.id
                == models.JointActivityParticipant.joint_activity_id,
            )
            .where(
                models.JointActivityParticipant.world_character_id
                == world_character_id,
                models.JointActivity.status.in_(ACTIVE_JOINT_STATUSES),
            )
        )
        or 0
    )



def reservation_for(
    db: Session,
    *,
    world_character_id: str,
    local_date: date,
    daypart: str,
) -> models.JointActivity | None:
    return db.scalar(
        select(models.JointActivity)
        .join(
            models.JointActivityParticipant,
            models.JointActivityParticipant.joint_activity_id
            == models.JointActivity.id,
        )
        .where(
            models.JointActivityParticipant.world_character_id
            == world_character_id,
            models.JointActivity.scheduled_local_date == local_date,
            models.JointActivity.target_daypart == daypart,
            models.JointActivity.status.in_(ACTIVE_JOINT_STATUSES),
        )
        .order_by(models.JointActivity.created_at, models.JointActivity.id)
        .limit(1)
    )



def slot_available(
    db: Session,
    *,
    references: JointReferences,
    world_id: str,
    world_character_id: str,
    local_date: date,
    daypart: str,
    now: datetime,
) -> bool:
    try:
        _eligible_world_character(
            db, references=references, world_id=world_id, world_character_id=world_character_id
        )
    except JointActivityRuntimeError:
        return False
    if reservation_for(
        db,
        world_character_id=world_character_id,
        local_date=local_date,
        daypart=daypart,
    ) is not None:
        return False
    plan = db.scalar(
        select(models.DailyActivityPlan).where(
            models.DailyActivityPlan.world_id == world_id,
            models.DailyActivityPlan.world_character_id == world_character_id,
            models.DailyActivityPlan.local_date == local_date,
        )
    )
    if plan is None:
        return True
    item = db.scalar(
        select(models.DailyActivityPlanItem).where(
            models.DailyActivityPlanItem.plan_id == plan.id,
            models.DailyActivityPlanItem.daypart == daypart,
            models.DailyActivityPlanItem.status != "superseded",
        )
    )
    if (
        item is None
        or item.origin_type != "repertoire"
        or item.joint_activity_id is not None
        or item.is_user_pinned
        or item.status != "planned"
        or _aware_utc(item.scheduled_start_at) <= _aware_utc(now)
    ):
        return False
    episode = db.scalar(
        select(models.ActivityEpisode).where(
            models.ActivityEpisode.plan_item_id == item.id
        )
    )
    return episode is not None and episode.status == "planned" and episode.started_at is None



def _item_snapshot(item: models.DailyActivityPlanItem) -> dict[str, object]:
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



def _joint_snapshot(joint: models.JointActivity) -> dict[str, object]:
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
    joint: models.JointActivity,
    participant: models.JointActivityParticipant,
    acceptance_event_id: str,
    now: datetime,
) -> str | None:
    plan = db.scalar(
        select(models.DailyActivityPlan)
        .where(
            models.DailyActivityPlan.world_id == joint.world_id,
            models.DailyActivityPlan.world_character_id
            == participant.world_character_id,
            models.DailyActivityPlan.local_date == joint.scheduled_local_date,
        )
        .with_for_update()
    )
    if plan is None:
        return None
    base_item = db.scalar(
        select(models.DailyActivityPlanItem)
        .where(
            models.DailyActivityPlanItem.plan_id == plan.id,
            models.DailyActivityPlanItem.daypart == joint.target_daypart,
            models.DailyActivityPlanItem.status != "superseded",
        )
        .with_for_update()
    )
    if base_item is None:
        raise JointActivityRuntimeError("joint_activity_schedule_conflict")
    episode = db.scalar(
        select(models.ActivityEpisode)
        .where(models.ActivityEpisode.plan_item_id == base_item.id)
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
        raise JointActivityRuntimeError("joint_activity_schedule_conflict")
    if plan.revision_count >= 2 or base_item.revision_count >= 1:
        raise JointActivityRuntimeError("joint_activity_revision_limit")

    before = _item_snapshot(base_item)
    base_item.status = "superseded"
    base_item.terminal_reason_code = "accepted_joint_activity"
    base_item.revision_count += 1
    base_item.version += 1
    episode.status = "cancelled"
    episode.terminal_reason_code = "plan_item_superseded"
    episode.completed_at = _aware_utc(now)
    episode.version += 1

    item_id = uuid7_string()
    joint_item = models.DailyActivityPlanItem(
        id=item_id,
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
    joint_episode = models.ActivityEpisode(
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
        models.ActivityPlanRevision(
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



def create_scheduled_joint(
    db: Session,
    *,
    references: JointReferences,
    proposal: Any,
    acceptance_event_id: str,
    scheduled_local_date: date,
    scheduled_start_at: datetime,
    scheduled_end_at: datetime,
    timezone_name: str,
    now: datetime,
) -> ScheduledJoint:
    validate_pair(
        db, references=references,
        world_id=proposal.world_id,
        first_world_character_id=proposal.proposer_world_character_id,
        second_world_character_id=proposal.target_world_character_id,
    )
    existing = db.scalar(
        select(models.JointActivity).where(
            models.JointActivity.proposal_id == proposal.id
        )
    )
    if existing is not None:
        participants = _participant_rows(db, joint_activity_id=existing.id)
        return ScheduledJoint(
            existing,
            tuple(
                row.linked_daily_activity_plan_item_id
                for row in participants
                if row.linked_daily_activity_plan_item_id is not None
            ),
        )
    joint = models.JointActivity(
        id=uuid7_string(),
        world_id=proposal.world_id,
        activity_seed=proposal.activity_seed,
        place_key=proposal.place_key,
        schedule_mode="exact",
        eligible_dayparts=[proposal.target_daypart],
        not_before=_aware_utc(scheduled_start_at),
        schedule_by=_aware_utc(scheduled_end_at),
        scheduled_start_at=_aware_utc(scheduled_start_at),
        scheduled_end_at=_aware_utc(scheduled_end_at),
        status="scheduled",
        proposal_id=proposal.id,
        scheduled_local_date=scheduled_local_date,
        target_daypart=proposal.target_daypart,
        timezone_snapshot=timezone_name,
        source_proposal_event_id=proposal.source_proposal_event_id,
        source_acceptance_event_id=acceptance_event_id,
        version=1,
    )
    db.add(joint)
    db.flush()
    participants = [
        models.JointActivityParticipant(
            joint_activity_id=joint.id,
            world_character_id=proposal.proposer_world_character_id,
            world_id=proposal.world_id,
            role="proposer",
            participation_status="accepted",
        ),
        models.JointActivityParticipant(
            joint_activity_id=joint.id,
            world_character_id=proposal.target_world_character_id,
            world_id=proposal.world_id,
            role="acceptor",
            participation_status="accepted",
        ),
    ]
    db.add_all(participants)
    db.flush()
    existing_plan_ids = tuple(
        db.scalar(
            select(models.DailyActivityPlan.id).where(
                models.DailyActivityPlan.world_id == joint.world_id,
                models.DailyActivityPlan.world_character_id
                == participant.world_character_id,
                models.DailyActivityPlan.local_date == joint.scheduled_local_date,
            )
        )
        for participant in participants
    )
    linked: tuple[str, ...] = ()
    if all(plan_id is not None for plan_id in existing_plan_ids):
        linked = tuple(
            item_id
            for participant in participants
            if (
                item_id := _materialize_existing_plan(
                    db,
                    joint=joint,
                    participant=participant,
                    acceptance_event_id=acceptance_event_id,
                    now=now,
                )
            )
            is not None
        )
        if len(linked) != 2:
            raise JointActivityRuntimeError(
                "joint_activity_partial_schedule_forbidden"
            )
        joint.status = "ready"
        joint.version += 1
    db.add(
        models.JointActivityRepresentationClaim(
            joint_activity_id=joint.id,
            world_id=joint.world_id,
            representation_status="pending",
            claim_version=1,
        )
    )
    db.flush()
    return ScheduledJoint(joint, linked)



def materialize_reservation_for_new_plan(
    db: Session,
    *,
    plan: models.DailyActivityPlan,
    joint: models.JointActivity,
    scheduled_start_at: datetime,
    scheduled_end_at: datetime,
    now: datetime,
) -> tuple[models.DailyActivityPlanItem, models.ActivityEpisode]:
    if (
        joint.scheduled_local_date != plan.local_date
        or joint.target_daypart not in DAYPARTS
        or joint.world_id != plan.world_id
    ):
        raise JointActivityRuntimeError("joint_activity_schedule_conflict")
    participant = db.scalar(
        select(models.JointActivityParticipant)
        .where(
            models.JointActivityParticipant.joint_activity_id == joint.id,
            models.JointActivityParticipant.world_character_id
            == plan.world_character_id,
        )
        .with_for_update()
    )
    if participant is None:
        raise JointActivityRuntimeError("joint_activity_participant_invalid")
    if participant.linked_daily_activity_plan_item_id is not None:
        existing_item = db.get(
            models.DailyActivityPlanItem,
            participant.linked_daily_activity_plan_item_id,
        )
        existing_episode = db.get(
            models.ActivityEpisode,
            participant.linked_activity_episode_id,
        )
        if existing_item is None or existing_episode is None:
            raise JointActivityRuntimeError("joint_activity_partial_schedule_forbidden")
        return existing_item, existing_episode
    item = models.DailyActivityPlanItem(
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
    episode = models.ActivityEpisode(
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
        raise JointActivityRuntimeError("joint_activity_acceptance_evidence_missing")
    other_participants = [
        row
        for row in _participant_rows(db, joint_activity_id=joint.id, lock=True)
        if row.world_character_id != plan.world_character_id
        and row.linked_daily_activity_plan_item_id is None
    ]
    for other in other_participants:
        other_plan_id = db.scalar(
            select(models.DailyActivityPlan.id).where(
                models.DailyActivityPlan.world_id == joint.world_id,
                models.DailyActivityPlan.world_character_id
                == other.world_character_id,
                models.DailyActivityPlan.local_date == joint.scheduled_local_date,
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
            raise JointActivityRuntimeError(
                "joint_activity_partial_schedule_forbidden"
            )
    participants = _participant_rows(db, joint_activity_id=joint.id)
    if all(row.linked_daily_activity_plan_item_id is not None for row in participants):
        joint.status = "ready"
        joint.version += 1
    return item, episode
