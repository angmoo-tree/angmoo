from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import models
from app.core.ids import uuid7_string
from app.runtime.relationships import (
    sqlalchemy_social_event as social_event_runtime,
)


DAYPARTS = ("dawn", "morning", "afternoon", "evening")
OPENING_LEASE = timedelta(seconds=120)
MAX_PARTICIPANT_OPENING_ATTEMPTS = 2
MAX_JOINT_OPENING_ATTEMPTS = 4
ACTIVE_JOINT_STATUSES = {"scheduled", "ready", "active"}


class JointActivityRuntimeError(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class OpeningClaim:
    joint_activity_id: str
    claimant_world_character_id: str
    claim_version: int
    expires_at: datetime
    reused: bool


@dataclass(frozen=True)
class ScheduledJoint:
    joint_activity: models.JointActivity
    linked_item_ids: tuple[str, ...]


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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


def _eligible_world_character(
    db: Session, *, world_id: str, world_character_id: str
) -> models.WorldCharacter:
    world_character = db.get(models.WorldCharacter, world_character_id)
    if (
        world_character is None
        or world_character.world_id != world_id
        or world_character.status != "active"
    ):
        raise JointActivityRuntimeError("world_character_ineligible")
    membership = db.get(models.WorldMembership, world_character.membership_id)
    if (
        membership is None
        or membership.world_id != world_id
        or membership.status != "active"
    ):
        raise JointActivityRuntimeError("world_membership_inactive")
    return world_character


def _mutually_blocked(
    db: Session, *, world_id: str, first_id: str, second_id: str
) -> bool:
    return (
        db.scalar(
            select(models.WorldCharacterBlock.id)
            .where(
                models.WorldCharacterBlock.world_id == world_id,
                or_(
                    (
                        models.WorldCharacterBlock.blocker_world_character_id
                        == first_id
                    )
                    & (
                        models.WorldCharacterBlock.blocked_world_character_id
                        == second_id
                    ),
                    (
                        models.WorldCharacterBlock.blocker_world_character_id
                        == second_id
                    )
                    & (
                        models.WorldCharacterBlock.blocked_world_character_id
                        == first_id
                    ),
                ),
            )
            .limit(1)
        )
        is not None
    )


def validate_pair(
    db: Session,
    *,
    world_id: str,
    first_world_character_id: str,
    second_world_character_id: str,
) -> tuple[models.WorldCharacter, models.WorldCharacter]:
    if first_world_character_id == second_world_character_id:
        raise JointActivityRuntimeError("self_target_forbidden")
    first = _eligible_world_character(
        db, world_id=world_id, world_character_id=first_world_character_id
    )
    second = _eligible_world_character(
        db, world_id=world_id, world_character_id=second_world_character_id
    )
    if _mutually_blocked(
        db,
        world_id=world_id,
        first_id=first_world_character_id,
        second_id=second_world_character_id,
    ):
        raise JointActivityRuntimeError("world_character_blocked")
    return first, second


def validate_place(
    db: Session,
    *,
    world_id: str,
    place_key: str | None,
    target_daypart: str,
    participant_role_keys: tuple[str | None, str | None],
) -> None:
    if target_daypart not in DAYPARTS:
        raise JointActivityRuntimeError("daypart_invalid")
    if place_key is None:
        return
    place = db.scalar(
        select(models.WorldPlace).where(
            models.WorldPlace.world_id == world_id,
            models.WorldPlace.place_key == place_key,
            models.WorldPlace.status == "enabled",
        )
    )
    if place is None:
        raise JointActivityRuntimeError("world_place_invalid")
    if place.available_dayparts and target_daypart not in place.available_dayparts:
        raise JointActivityRuntimeError("world_place_daypart_invalid")
    if place.access_role_keys and any(
        role_key not in place.access_role_keys for role_key in participant_role_keys
    ):
        raise JointActivityRuntimeError("world_place_role_forbidden")


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
    world_id: str,
    world_character_id: str,
    local_date: date,
    daypart: str,
    now: datetime,
) -> bool:
    try:
        _eligible_world_character(
            db, world_id=world_id, world_character_id=world_character_id
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
    proposal: models.ActivityProposal,
    acceptance_event_id: str,
    scheduled_local_date: date,
    scheduled_start_at: datetime,
    scheduled_end_at: datetime,
    timezone_name: str,
    now: datetime,
) -> ScheduledJoint:
    validate_pair(
        db,
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


def claim_opening(
    db: Session,
    *,
    joint_activity_id: str,
    claimant_world_character_id: str,
    now: datetime,
) -> OpeningClaim:
    current = _aware_utc(now)
    joint = db.scalar(
        select(models.JointActivity)
        .where(models.JointActivity.id == joint_activity_id)
        .with_for_update()
    )
    if joint is None:
        raise JointActivityRuntimeError("joint_activity_not_found")
    if joint.opening_post_id is not None or joint.status == "active":
        raise JointActivityRuntimeError("joint_activity_already_opened")
    if joint.status not in {"scheduled", "ready"}:
        raise JointActivityRuntimeError("joint_activity_not_ready")
    participants = _participant_rows(db, joint_activity_id=joint.id, lock=True)
    participant = next(
        (
            row
            for row in participants
            if row.world_character_id == claimant_world_character_id
        ),
        None,
    )
    if participant is None:
        raise JointActivityRuntimeError("joint_activity_participant_invalid")
    if any(
        row.linked_daily_activity_plan_item_id is None
        or row.linked_activity_episode_id is None
        for row in participants
    ):
        raise JointActivityRuntimeError("joint_activity_not_ready")
    _eligible_world_character(
        db,
        world_id=joint.world_id,
        world_character_id=claimant_world_character_id,
    )
    claim = db.scalar(
        select(models.JointActivityRepresentationClaim)
        .where(
            models.JointActivityRepresentationClaim.joint_activity_id == joint.id
        )
        .with_for_update()
    )
    if claim is None:
        raise JointActivityRuntimeError("joint_activity_claim_missing")
    if claim.representation_status == "represented":
        raise JointActivityRuntimeError("joint_activity_already_opened")
    if claim.representation_status == "claimed":
        existing_expiry = (
            _aware_utc(claim.claim_expires_at)
            if claim.claim_expires_at is not None
            else current
        )
        if existing_expiry > current:
            if claim.claimed_by_world_character_id == claimant_world_character_id:
                return OpeningClaim(
                    joint.id,
                    claimant_world_character_id,
                    claim.claim_version,
                    existing_expiry,
                    True,
                )
            raise JointActivityRuntimeError("joint_activity_opening_claimed")
    participant_attempts = participant.opening_attempt_count
    joint_attempts = joint.opening_attempt_count
    if participant_attempts >= MAX_PARTICIPANT_OPENING_ATTEMPTS:
        raise JointActivityRuntimeError("joint_activity_participant_attempt_limit")
    if joint_attempts >= MAX_JOINT_OPENING_ATTEMPTS:
        raise JointActivityRuntimeError("joint_activity_attempt_limit")
    participant.opening_attempt_count = participant_attempts + 1
    joint.opening_attempt_count = joint_attempts + 1
    claim.representation_status = "claimed"
    claim.claimed_by_world_character_id = claimant_world_character_id
    claim.claim_expires_at = current + OPENING_LEASE
    claim.claim_version += 1
    db.commit()
    return OpeningClaim(
        joint.id,
        claimant_world_character_id,
        claim.claim_version,
        current + OPENING_LEASE,
        False,
    )


def release_opening(
    db: Session,
    *,
    claim: OpeningClaim,
) -> None:
    row = db.scalar(
        select(models.JointActivityRepresentationClaim)
        .where(
            models.JointActivityRepresentationClaim.joint_activity_id
            == claim.joint_activity_id
        )
        .with_for_update()
    )
    if (
        row is None
        or row.representation_status != "claimed"
        or row.claimed_by_world_character_id != claim.claimant_world_character_id
        or row.claim_version != claim.claim_version
    ):
        db.rollback()
        return
    row.representation_status = "pending"
    row.claimed_by_world_character_id = None
    row.claim_expires_at = None
    row.claim_version += 1
    db.commit()


def apply_joint_post(
    db: Session,
    *,
    joint_activity_id: str,
    author_world_character_id: str,
    post: models.Post,
    post_event: models.SocialEvent,
    opening_claim: OpeningClaim | None,
    now: datetime,
) -> models.SocialEvent | None:
    current = _aware_utc(now)
    joint = db.scalar(
        select(models.JointActivity)
        .where(models.JointActivity.id == joint_activity_id)
        .with_for_update()
    )
    if joint is None or post.world_id != joint.world_id:
        raise JointActivityRuntimeError("joint_activity_not_found")
    participants = _participant_rows(db, joint_activity_id=joint.id, lock=True)
    participant = next(
        (row for row in participants if row.world_character_id == author_world_character_id),
        None,
    )
    if participant is None:
        raise JointActivityRuntimeError("joint_activity_participant_invalid")
    post.joint_activity_id = joint.id
    if joint.opening_post_id is not None:
        if opening_claim is not None:
            raise JointActivityRuntimeError("joint_activity_already_opened")
        if joint.status != "active":
            raise JointActivityRuntimeError("joint_activity_not_active")
        post.opening_post_id = joint.opening_post_id
        participant.last_joint_post_id = post.id
        participant.represented_at = participant.represented_at or current
        db.flush()
        return None
    if opening_claim is None:
        raise JointActivityRuntimeError("joint_activity_opening_claim_required")
    claim = db.scalar(
        select(models.JointActivityRepresentationClaim)
        .where(
            models.JointActivityRepresentationClaim.joint_activity_id == joint.id
        )
        .with_for_update()
    )
    if (
        claim is None
        or claim.representation_status != "claimed"
        or claim.claimed_by_world_character_id != author_world_character_id
        or claim.claim_version != opening_claim.claim_version
        or claim.claim_expires_at is None
        or _aware_utc(claim.claim_expires_at) <= current
    ):
        raise JointActivityRuntimeError("joint_activity_opening_claim_stale")
    joint.opening_post_id = post.id
    joint.representation_post_id = post.id
    joint.opened_by_world_character_id = author_world_character_id
    joint.represented_by_world_character_id = author_world_character_id
    joint.started_at = current
    joint.represented_at = current
    joint.status = "active"
    joint.version += 1
    post.opening_post_id = post.id
    claim.representation_status = "represented"
    claim.representation_post_id = post.id
    claim.claim_expires_at = None
    for row in participants:
        row.participation_status = "active"
        item = (
            db.get(models.DailyActivityPlanItem, row.linked_daily_activity_plan_item_id)
            if row.linked_daily_activity_plan_item_id is not None
            else None
        )
        episode = (
            db.get(models.ActivityEpisode, row.linked_activity_episode_id)
            if row.linked_activity_episode_id is not None
            else None
        )
        if item is None or episode is None:
            raise JointActivityRuntimeError("joint_activity_partial_schedule_forbidden")
        item.status = "active"
        item.version += 1
        episode.status = "active"
        episode.started_at = episode.started_at or current
        episode.version += 1
    participant.last_joint_post_id = post.id
    participant.represented_at = current
    started = social_event_runtime.record_successful_social_event(
        db,
        world_id=joint.world_id,
        actor_world_character_id=author_world_character_id,
        target_world_character_id=None,
        event_type="joint_started",
        occurred_at=current,
        idempotency_key=sha256(f"joint-started|{joint.id}".encode("utf-8")).hexdigest(),
        evidence=social_event_runtime.EvidenceInput(
            evidence_kind="joint_activity",
            source_object_type="joint_activity",
            source_object_id=joint.id,
            root_post_id=post.id,
            source_post_id=post.id,
            agent_run_id=next(
                (
                    evidence.agent_run_id
                    for evidence in db.scalars(
                        select(models.SocialEventEvidence).where(
                            models.SocialEventEvidence.social_event_id == post_event.id
                        )
                    )
                    if evidence.agent_run_id is not None
                ),
                None,
            ),
            source_visibility_at_event=post.visibility,
            source_author_id_at_event=author_world_character_id,
        ),
    ).event
    other = next(
        row for row in participants if row.world_character_id != author_world_character_id
    )
    other_wc = db.get(models.WorldCharacter, other.world_character_id)
    actor_wc = db.get(models.WorldCharacter, author_world_character_id)
    if other_wc is None or actor_wc is None:
        raise JointActivityRuntimeError("joint_activity_participant_invalid")
    existing_notification = db.scalar(
        select(models.Notification).where(
            models.Notification.notification_type == "joint_activity_started",
            models.Notification.source_joint_activity_id == joint.id,
            models.Notification.recipient_world_character_id == other.world_character_id,
        )
    )
    if existing_notification is None:
        db.add(
            models.Notification(
                recipient_character_id=other_wc.character_id,
                actor_character_id=actor_wc.character_id,
                world_id=joint.world_id,
                recipient_world_character_id=other.world_character_id,
                actor_world_character_id=author_world_character_id,
                source_social_event_id=started.id,
                source_joint_activity_id=joint.id,
                notification_type="joint_activity_started",
                post_id=post.id,
                source_post_id=post.id,
                data=json.dumps(
                    {"joint_activity_id": joint.id, "opening_post_id": post.id},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )
    db.flush()
    return started


def complete_due_joint_activities(
    db: Session, *, world_id: str, now: datetime
) -> tuple[int, int]:
    current = _aware_utc(now)
    rows = list(
        db.scalars(
            select(models.JointActivity)
            .where(
                models.JointActivity.world_id == world_id,
                models.JointActivity.status.in_(ACTIVE_JOINT_STATUSES),
                models.JointActivity.scheduled_end_at <= current,
            )
            .with_for_update(skip_locked=True)
        )
    )
    completed = 0
    expired = 0
    for joint in rows:
        participants = _participant_rows(db, joint_activity_id=joint.id, lock=True)
        post_count = int(
            db.scalar(
                select(func.count(models.Post.id)).where(
                    models.Post.joint_activity_id == joint.id,
                    models.Post.deleted_at.is_(None),
                    models.Post.report_hidden_at.is_(None),
                )
            )
            or 0
        )
        success = post_count > 0
        joint.status = "completed" if success else "expired_unrepresented"
        joint.completed_at = current
        joint.version += 1
        for participant in participants:
            participant.participation_status = "completed" if success else "interrupted"
            item = (
                db.get(models.DailyActivityPlanItem, participant.linked_daily_activity_plan_item_id)
                if participant.linked_daily_activity_plan_item_id is not None
                else None
            )
            episode = (
                db.get(models.ActivityEpisode, participant.linked_activity_episode_id)
                if participant.linked_activity_episode_id is not None
                else None
            )
            if item is not None:
                item.status = "completed" if success else "skipped"
                item.terminal_reason_code = None if success else "joint_unrepresented"
                item.version += 1
            if episode is not None:
                episode.status = "completed" if success else "interrupted"
                episode.completed_at = current
                episode.terminal_reason_code = None if success else "joint_unrepresented"
                episode.version += 1
        if not success:
            expired += 1
            continue
        for actor in participants:
            target = next(
                row
                for row in participants
                if row.world_character_id != actor.world_character_id
            )
            social_event_runtime.record_successful_social_event(
                db,
                world_id=joint.world_id,
                actor_world_character_id=actor.world_character_id,
                target_world_character_id=target.world_character_id,
                event_type="joint_completed",
                occurred_at=current,
                idempotency_key=sha256(
                    f"joint-completed|{joint.id}|{actor.world_character_id}".encode(
                        "utf-8"
                    )
                ).hexdigest(),
                evidence=social_event_runtime.EvidenceInput(
                    evidence_kind="joint_activity",
                    source_object_type="joint_activity",
                    source_object_id=joint.id,
                    root_post_id=joint.opening_post_id,
                    source_post_id=actor.last_joint_post_id or joint.opening_post_id,
                    target_post_id=joint.opening_post_id,
                    source_author_id_at_event=actor.world_character_id,
                    source_visibility_at_event="public",
                ),
            )
        completed += 1
    if rows:
        db.commit()
    return completed, expired
