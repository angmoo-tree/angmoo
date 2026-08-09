from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.core.ids import uuid7_string


DAYPARTS = frozenset({"dawn", "morning", "afternoon", "evening"})
TERMINAL_ITEM_STATUSES = frozenset(
    {"active", "completed", "skipped", "interrupted", "cancelled"}
)


class JointActivitySchedulingError(Exception):
    reason_code = "joint_activity_schedule_error"


class JointActivityNotFoundError(JointActivitySchedulingError):
    reason_code = "joint_activity_not_found"


class JointActivityConflictError(JointActivitySchedulingError):
    reason_code = "joint_activity_schedule_conflict"

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class JointActivityValidationError(JointActivitySchedulingError):
    reason_code = "joint_activity_invalid"

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class JointScheduleResult:
    joint_activity: models.JointActivity
    linked_item_ids: tuple[str, ...]
    reused: bool
    scheduled: bool


@dataclass(frozen=True)
class RepresentationClaimResult:
    claim: models.JointActivityRepresentationClaim
    reused: bool


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _participants(
    db: Session,
    *,
    joint_activity: models.JointActivity,
    lock_for_update: bool,
) -> list[models.JointActivityParticipant]:
    statement = (
        select(models.JointActivityParticipant)
        .where(
            models.JointActivityParticipant.joint_activity_id == joint_activity.id
        )
        .order_by(models.JointActivityParticipant.world_character_id)
    )
    if lock_for_update:
        statement = statement.with_for_update()
    participants = list(db.scalars(statement))
    if len(participants) != 2:
        raise JointActivityValidationError("joint_activity_participant_invalid")
    if {participant.role for participant in participants} != {"proposer", "acceptor"}:
        raise JointActivityValidationError("joint_activity_participant_invalid")
    for participant in participants:
        if (
            participant.world_id != joint_activity.world_id
            or participant.participation_status
            not in {"accepted", "scheduled"}
        ):
            raise JointActivityValidationError("cross_world_reference")
        world_character = db.get(models.WorldCharacter, participant.world_character_id)
        if (
            world_character is None
            or world_character.world_id != joint_activity.world_id
            or world_character.status not in {"pending", "inactive", "active"}
        ):
            raise JointActivityValidationError("joint_activity_participant_invalid")
        membership = db.get(models.WorldMembership, world_character.membership_id)
        if (
            membership is None
            or membership.world_id != joint_activity.world_id
            or membership.status != "active"
        ):
            raise JointActivityValidationError("world_membership_inactive")
    return participants


def _window_for_mode(
    joint_activity: models.JointActivity,
    *,
    item_start: datetime,
    item_end: datetime,
) -> tuple[datetime, datetime] | None:
    start = _aware_utc(item_start)
    end = _aware_utc(item_end)
    not_before = (
        _aware_utc(joint_activity.not_before)
        if joint_activity.not_before is not None
        else None
    )
    schedule_by = (
        _aware_utc(joint_activity.schedule_by)
        if joint_activity.schedule_by is not None
        else None
    )
    if joint_activity.schedule_mode == "exact":
        if not_before is None or schedule_by is None:
            return None
        candidate = (not_before, schedule_by)
    else:
        candidate = (
            max(start, not_before) if not_before is not None else start,
            min(end, schedule_by) if schedule_by is not None else end,
        )
    if candidate[0] >= candidate[1] or candidate[0] < start or candidate[1] > end:
        return None
    return candidate


def _item_snapshot(item: models.DailyActivityPlanItem) -> dict[str, object]:
    return {
        "joint_activity_id": item.joint_activity_id,
        "activity_kind": item.activity_kind,
        "title": item.title,
        "activity_seed": item.activity_seed,
        "social_mode": item.social_mode,
        "place_key": item.place_key,
        "scheduled_start_at": _aware_utc(item.scheduled_start_at).isoformat(),
        "scheduled_end_at": _aware_utc(item.scheduled_end_at).isoformat(),
    }


def schedule_joint_activity(
    db: Session,
    *,
    joint_activity_id: str,
    local_date: date,
    daypart: str,
    idempotency_key: str,
    now: datetime | None = None,
) -> JointScheduleResult:
    current = _aware_utc(now or datetime.now(UTC))
    if daypart not in DAYPARTS:
        raise JointActivityValidationError("daypart_invalid")
    joint_activity = db.scalar(
        select(models.JointActivity)
        .where(models.JointActivity.id == joint_activity_id)
        .with_for_update()
    )
    if joint_activity is None:
        raise JointActivityNotFoundError(joint_activity_id)
    participants = _participants(
        db, joint_activity=joint_activity, lock_for_update=True
    )
    linked = tuple(
        participant.linked_daily_activity_plan_item_id
        for participant in participants
        if participant.linked_daily_activity_plan_item_id is not None
    )
    if joint_activity.status in {"scheduled", "ready"}:
        if len(linked) != 2:
            raise JointActivityValidationError(
                "joint_activity_partial_schedule_forbidden"
            )
        return JointScheduleResult(
            joint_activity,
            (linked[0], linked[1]),
            True,
            True,
        )
    if joint_activity.status != "accepted_unscheduled":
        raise JointActivityConflictError("joint_activity_schedule_conflict")
    if linked:
        raise JointActivityValidationError("joint_activity_partial_schedule_forbidden")
    if joint_activity.eligible_dayparts and daypart not in joint_activity.eligible_dayparts:
        return JointScheduleResult(joint_activity, (), False, False)

    plans: list[models.DailyActivityPlan] = []
    items: list[models.DailyActivityPlanItem] = []
    for participant in participants:
        plan = db.scalar(
            select(models.DailyActivityPlan)
            .where(
                models.DailyActivityPlan.world_id == joint_activity.world_id,
                models.DailyActivityPlan.world_character_id
                == participant.world_character_id,
                models.DailyActivityPlan.local_date == local_date,
            )
            .with_for_update()
        )
        if plan is None:
            return JointScheduleResult(joint_activity, (), False, False)
        item = db.scalar(
            select(models.DailyActivityPlanItem)
            .where(
                models.DailyActivityPlanItem.plan_id == plan.id,
                models.DailyActivityPlanItem.daypart == daypart,
            )
            .with_for_update()
        )
        if item is None:
            return JointScheduleResult(joint_activity, (), False, False)
        plans.append(plan)
        items.append(item)

    if any(
        item.status in TERMINAL_ITEM_STATUSES
        or item.revision_count >= 1
        or item.joint_activity_id is not None
        or _aware_utc(item.scheduled_start_at) <= current
        for item in items
    ) or any(plan.revision_count >= 2 for plan in plans):
        raise JointActivityConflictError("joint_activity_schedule_conflict")
    starts = {_aware_utc(item.scheduled_start_at) for item in items}
    ends = {_aware_utc(item.scheduled_end_at) for item in items}
    if len(starts) != 1 or len(ends) != 1:
        raise JointActivityValidationError("joint_activity_schedule_conflict")
    scheduled_window = _window_for_mode(
        joint_activity,
        item_start=items[0].scheduled_start_at,
        item_end=items[0].scheduled_end_at,
    )
    if scheduled_window is None:
        return JointScheduleResult(joint_activity, (), False, False)

    for participant, plan, item in zip(participants, plans, items):
        before = _item_snapshot(item)
        item.joint_activity_id = joint_activity.id
        item.revision_count += 1
        item.version += 1
        plan.revision_count += 1
        plan.version += 1
        participant.linked_daily_activity_plan_item_id = item.id
        participant.participation_status = "scheduled"
        after = {
            **_item_snapshot(item),
            "joint_activity_seed": joint_activity.activity_seed,
            "joint_activity_place_key": joint_activity.place_key,
        }
        db.add(
            models.ActivityPlanRevision(
                id=uuid7_string(),
                plan_id=plan.id,
                plan_item_id=item.id,
                joint_activity_id=joint_activity.id,
                revision_ordinal=plan.revision_count,
                before_snapshot=before,
                after_snapshot=after,
                source_acceptance_event_id=joint_activity.source_acceptance_event_id,
                reason_code="accepted_joint_activity",
                idempotency_key=sha256(
                    f"{idempotency_key}|{participant.world_character_id}".encode(
                        "utf-8"
                    )
                ).hexdigest(),
                applied_at=current,
            )
        )
    joint_activity.scheduled_start_at = scheduled_window[0]
    joint_activity.scheduled_end_at = scheduled_window[1]
    joint_activity.status = "scheduled"
    joint_activity.version += 1
    if db.get(models.JointActivityRepresentationClaim, joint_activity.id) is None:
        db.add(
            models.JointActivityRepresentationClaim(
                joint_activity_id=joint_activity.id,
                world_id=joint_activity.world_id,
                representation_status="pending",
                claim_version=1,
            )
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise JointActivityConflictError("joint_activity_schedule_conflict") from exc
    return JointScheduleResult(
        joint_activity,
        (items[0].id, items[1].id),
        False,
        True,
    )


def claim_representation(
    db: Session,
    *,
    joint_activity_id: str,
    claimant_world_character_id: str,
    claim_expires_at: datetime,
    now: datetime | None = None,
) -> RepresentationClaimResult:
    current = _aware_utc(now or datetime.now(UTC))
    expiry = _aware_utc(claim_expires_at)
    if expiry <= current:
        raise JointActivityValidationError("claim_expiry_invalid")
    joint_activity = db.scalar(
        select(models.JointActivity)
        .where(models.JointActivity.id == joint_activity_id)
        .with_for_update()
    )
    if joint_activity is None:
        raise JointActivityNotFoundError(joint_activity_id)
    if joint_activity.status == "represented":
        raise JointActivityConflictError("representation_already_completed")
    if joint_activity.status not in {"scheduled", "ready"}:
        raise JointActivityConflictError("joint_activity_accepted_unscheduled")
    participants = _participants(
        db, joint_activity=joint_activity, lock_for_update=True
    )
    if claimant_world_character_id not in {
        participant.world_character_id for participant in participants
    }:
        raise JointActivityValidationError("joint_activity_participant_invalid")
    if any(
        participant.linked_daily_activity_plan_item_id is None
        for participant in participants
    ):
        raise JointActivityValidationError("joint_activity_partial_schedule_forbidden")

    claim = db.scalar(
        select(models.JointActivityRepresentationClaim)
        .where(
            models.JointActivityRepresentationClaim.joint_activity_id
            == joint_activity.id
        )
        .with_for_update()
    )
    if claim is None:
        claim = models.JointActivityRepresentationClaim(
            joint_activity_id=joint_activity.id,
            world_id=joint_activity.world_id,
            representation_status="pending",
            claim_version=1,
        )
        db.add(claim)
        db.flush()
    if claim.world_id != joint_activity.world_id:
        raise JointActivityValidationError("cross_world_reference")
    if claim.representation_status == "represented":
        raise JointActivityConflictError("representation_already_completed")
    if claim.representation_status == "claimed":
        existing_expiry = (
            _aware_utc(claim.claim_expires_at)
            if claim.claim_expires_at is not None
            else current
        )
        if (
            claim.claimed_by_world_character_id == claimant_world_character_id
            and existing_expiry > current
        ):
            return RepresentationClaimResult(claim, True)
        if existing_expiry > current:
            raise JointActivityConflictError("representation_already_claimed")
    claim.representation_status = "claimed"
    claim.claimed_by_world_character_id = claimant_world_character_id
    claim.claim_expires_at = expiry
    claim.claim_version += 1
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise JointActivityConflictError("representation_already_claimed") from exc
    return RepresentationClaimResult(claim, False)


def release_representation(
    db: Session,
    *,
    joint_activity_id: str,
    claimant_world_character_id: str,
) -> models.JointActivityRepresentationClaim:
    claim = db.scalar(
        select(models.JointActivityRepresentationClaim)
        .where(
            models.JointActivityRepresentationClaim.joint_activity_id
            == joint_activity_id
        )
        .with_for_update()
    )
    if claim is None:
        raise JointActivityNotFoundError(joint_activity_id)
    if (
        claim.representation_status != "claimed"
        or claim.claimed_by_world_character_id != claimant_world_character_id
    ):
        raise JointActivityConflictError("representation_already_claimed")
    claim.representation_status = "pending"
    claim.claimed_by_world_character_id = None
    claim.claim_expires_at = None
    claim.claim_version += 1
    db.commit()
    return claim


def recover_expired_representation_claims(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    current = _aware_utc(now or datetime.now(UTC))
    claims = list(
        db.scalars(
            select(models.JointActivityRepresentationClaim)
            .where(
                models.JointActivityRepresentationClaim.representation_status
                == "claimed",
                models.JointActivityRepresentationClaim.claim_expires_at <= current,
            )
            .with_for_update(skip_locked=True)
        )
    )
    for claim in claims:
        claim.representation_status = "pending"
        claim.claimed_by_world_character_id = None
        claim.claim_expires_at = None
        claim.claim_version += 1
    db.commit()
    return len(claims)
