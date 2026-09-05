from __future__ import annotations

from app.runtime.routines.joint_references import SqlAlchemyJointReferences

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.ids import uuid7_string
from app.services import daily_activity_plans
from app.domains.routines.service import joint_activity as joint_activity_runtime


OPEN_PROPOSAL_LIMIT_PER_PAIR = 1
OPEN_PROPOSAL_LIMIT_PER_CHARACTER = 3
ACTIVE_COMMITMENT_LIMIT = 2
COUNTER_LIMIT = 2
PAIR_COOLDOWN = timedelta(hours=24)
SEARCH_DAYS = 7
PROPOSAL_TTL = timedelta(days=7)


class ActivityProposalRuntimeError(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class ProposalEligibility:
    eligible: bool
    reason_code: str | None
    target_world_character_id: str | None


@dataclass(frozen=True)
class ResolvedSchedule:
    local_date: date
    daypart: str
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    timezone_name: str


@dataclass(frozen=True)
class ProposalResponseResult:
    proposal: models.ActivityProposal
    child_proposal: models.ActivityProposal | None
    joint_activity: models.JointActivity | None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _open_pair_count(
    db: Session, *, actor_id: str, target_id: str
) -> int:
    return int(
        db.scalar(
            select(func.count(models.ActivityProposal.id)).where(
                models.ActivityProposal.proposer_world_character_id == actor_id,
                models.ActivityProposal.target_world_character_id == target_id,
                models.ActivityProposal.status == "proposed",
            )
        )
        or 0
    )


def _open_character_count(db: Session, *, world_character_id: str) -> int:
    return int(
        db.scalar(
            select(func.count(models.ActivityProposal.id)).where(
                models.ActivityProposal.status == "proposed",
                or_(
                    models.ActivityProposal.proposer_world_character_id
                    == world_character_id,
                    models.ActivityProposal.target_world_character_id
                    == world_character_id,
                ),
            )
        )
        or 0
    )


def _cooldown_active(
    db: Session, *, actor_id: str, target_id: str, now: datetime
) -> bool:
    cutoff = _aware_utc(now) - PAIR_COOLDOWN
    return (
        db.scalar(
            select(models.ActivityProposal.id)
            .where(
                models.ActivityProposal.proposer_world_character_id == actor_id,
                models.ActivityProposal.target_world_character_id == target_id,
                models.ActivityProposal.status.in_(
                    {"rejected", "cancelled", "expired"}
                ),
                models.ActivityProposal.updated_at >= cutoff,
            )
            .limit(1)
        )
        is not None
    )


def proposal_eligibility(
    db: Session,
    *,
    actor_world_character_id: str,
    target_post_id: str,
    now: datetime,
) -> ProposalEligibility:
    post = db.get(models.Post, target_post_id)
    if (
        post is None
        or post.world_id is None
        or post.author_world_character_id is None
        or post.deleted_at is not None
        or post.report_hidden_at is not None
        or post.visibility != "public"
    ):
        return ProposalEligibility(False, "proposal_target_invalid", None)
    target_id = post.author_world_character_id
    try:
        joint_activity_runtime.validate_pair(
            db, references=SqlAlchemyJointReferences(db),
            world_id=post.world_id,
            first_world_character_id=actor_world_character_id,
            second_world_character_id=target_id,
        )
    except joint_activity_runtime.JointActivityRuntimeError as exc:
        return ProposalEligibility(False, exc.reason_code, target_id)
    if _open_pair_count(db, actor_id=actor_world_character_id, target_id=target_id):
        return ProposalEligibility(False, "proposal_pair_limit", target_id)
    if any(
        _open_character_count(db, world_character_id=world_character_id)
        >= OPEN_PROPOSAL_LIMIT_PER_CHARACTER
        for world_character_id in (actor_world_character_id, target_id)
    ):
        return ProposalEligibility(False, "proposal_character_limit", target_id)
    if any(
        joint_activity_runtime.active_commitment_count(
            db, world_character_id=world_character_id
        )
        >= ACTIVE_COMMITMENT_LIMIT
        for world_character_id in (actor_world_character_id, target_id)
    ):
        return ProposalEligibility(False, "proposal_commitment_limit", target_id)
    if _cooldown_active(
        db,
        actor_id=actor_world_character_id,
        target_id=target_id,
        now=now,
    ):
        return ProposalEligibility(False, "proposal_pair_cooldown", target_id)
    return ProposalEligibility(True, None, target_id)


_DAYPART_MARKERS = {
    "dawn": ("새벽", "dawn"),
    "morning": ("아침", "오전", "morning"),
    "afternoon": ("낮", "오후", "afternoon"),
    "evening": ("저녁", "밤", "evening", "tonight"),
}


def _text_daypart_consistent(text: str, target_daypart: str) -> bool:
    normalized = text.casefold()
    explicit = {
        daypart
        for daypart, markers in _DAYPART_MARKERS.items()
        if any(marker in normalized for marker in markers)
    }
    return not explicit or explicit == {target_daypart}


def validate_preview(
    db: Session,
    *,
    preview: schemas.JointActivityProposalPreview,
    world_id: str,
    proposer_world_character_id: str,
    target_post_id: str,
    now: datetime,
) -> tuple[models.WorldCharacter, models.WorldCharacter]:
    if preview.source_post_id != target_post_id:
        raise ActivityProposalRuntimeError("proposal_source_mismatch")
    post = db.get(models.Post, target_post_id)
    if (
        post is None
        or post.world_id != world_id
        or post.author_world_character_id != preview.target_world_character_id
    ):
        raise ActivityProposalRuntimeError("proposal_target_mismatch")
    eligibility = proposal_eligibility(
        db,
        actor_world_character_id=proposer_world_character_id,
        target_post_id=target_post_id,
        now=now,
    )
    if not eligibility.eligible:
        raise ActivityProposalRuntimeError(
            eligibility.reason_code or "proposal_ineligible"
        )
    proposer, target = joint_activity_runtime.validate_pair(
        db, references=SqlAlchemyJointReferences(db),
        world_id=world_id,
        first_world_character_id=proposer_world_character_id,
        second_world_character_id=preview.target_world_character_id,
    )
    joint_activity_runtime.validate_place(
        db, references=SqlAlchemyJointReferences(db),
        world_id=world_id,
        place_key=preview.place_key,
        target_daypart=preview.target_daypart,
        participant_role_keys=(proposer.role_key, target.role_key),
    )
    if preview.date_policy == "exact" and preview.target_date is None:
        raise ActivityProposalRuntimeError("proposal_exact_date_required")
    world = db.get(models.World, world_id)
    if world is None:
        raise ActivityProposalRuntimeError("world_not_found")
    local_today = daily_activity_plans.local_activity_date(now, world.timezone)
    if preview.target_date is not None and not (
        local_today <= preview.target_date < local_today + timedelta(days=SEARCH_DAYS)
    ):
        raise ActivityProposalRuntimeError("proposal_date_out_of_range")
    if not _text_daypart_consistent(preview.text, preview.target_daypart):
        raise ActivityProposalRuntimeError("proposal_text_daypart_mismatch")
    return proposer, target


def create_published_proposal(
    db: Session,
    *,
    preview: schemas.JointActivityProposalPreview,
    proposal_comment: models.Post,
    proposal_event: models.SocialEvent,
    proposer_world_character_id: str,
    now: datetime,
) -> models.ActivityProposal:
    if proposal_event.event_type != "joint_proposed":
        raise ActivityProposalRuntimeError("proposal_event_invalid")
    validate_preview(
        db,
        preview=preview,
        world_id=proposal_event.world_id,
        proposer_world_character_id=proposer_world_character_id,
        target_post_id=preview.source_post_id,
        now=now,
    )
    if (
        proposal_comment.id
        != db.scalar(
            select(models.SocialEventEvidence.source_post_id).where(
                models.SocialEventEvidence.social_event_id == proposal_event.id
            )
        )
        or proposal_comment.reply_to_post_id != preview.source_post_id
    ):
        raise ActivityProposalRuntimeError("proposal_evidence_invalid")
    existing = db.scalar(
        select(models.ActivityProposal).where(
            models.ActivityProposal.source_proposal_event_id == proposal_event.id
        )
    )
    if existing is not None:
        return existing
    proposal_id = uuid7_string()
    proposal = models.ActivityProposal(
        id=proposal_id,
        world_id=proposal_event.world_id,
        root_proposal_id=proposal_id,
        parent_proposal_id=None,
        proposal_version=1,
        proposer_world_character_id=proposer_world_character_id,
        target_world_character_id=preview.target_world_character_id,
        activity_seed=preview.activity_seed,
        place_key=preview.place_key,
        target_daypart=preview.target_daypart,
        date_policy=preview.date_policy,
        target_date=preview.target_date,
        proposed_local_snapshot={
            "timezone": db.get(models.World, proposal_event.world_id).timezone,
            "target_daypart": preview.target_daypart,
            "target_date": (
                preview.target_date.isoformat()
                if preview.target_date is not None
                else None
            ),
        },
        status="proposed",
        source_proposal_event_id=proposal_event.id,
        idempotency_key=sha256(
            f"proposal|{proposal_event.id}".encode("utf-8")
        ).hexdigest(),
        expires_at=_aware_utc(now) + PROPOSAL_TTL,
        version=1,
    )
    db.add(proposal)
    db.flush()
    return proposal


def find_open_proposal_for_source_post(
    db: Session,
    *,
    world_id: str,
    target_world_character_id: str,
    source_post_id: str,
) -> models.ActivityProposal | None:
    """Resolve a proposal only through its successful published reply evidence."""

    return db.scalar(
        select(models.ActivityProposal)
        .join(
            models.SocialEvent,
            models.SocialEvent.id
            == models.ActivityProposal.source_proposal_event_id,
        )
        .join(
            models.SocialEventEvidence,
            models.SocialEventEvidence.social_event_id == models.SocialEvent.id,
        )
        .where(
            models.ActivityProposal.world_id == world_id,
            models.ActivityProposal.target_world_character_id
            == target_world_character_id,
            models.ActivityProposal.status == "proposed",
            models.SocialEvent.event_type == "joint_proposed",
            models.SocialEventEvidence.source_post_id == source_post_id,
        )
        .order_by(models.ActivityProposal.created_at.desc())
        .limit(1)
    )


def resolve_acceptance_schedule(
    db: Session,
    *,
    proposal_id: str,
    now: datetime,
) -> ResolvedSchedule:
    proposal = db.get(models.ActivityProposal, proposal_id)
    if proposal is None or proposal.status != "proposed":
        raise ActivityProposalRuntimeError("proposal_not_open")
    world = db.get(models.World, proposal.world_id)
    if world is None:
        raise ActivityProposalRuntimeError("world_not_found")
    joint_activity_runtime.validate_pair(
        db, references=SqlAlchemyJointReferences(db),
        world_id=proposal.world_id,
        first_world_character_id=proposal.proposer_world_character_id,
        second_world_character_id=proposal.target_world_character_id,
    )
    local_today = daily_activity_plans.local_activity_date(now, world.timezone)
    if proposal.date_policy == "exact":
        if proposal.target_date is None:
            raise ActivityProposalRuntimeError("proposal_exact_date_required")
        candidates = (proposal.target_date,)
    else:
        candidates = tuple(local_today + timedelta(days=offset) for offset in range(SEARCH_DAYS))
    for candidate_date in candidates:
        if not (local_today <= candidate_date < local_today + timedelta(days=SEARCH_DAYS)):
            continue
        start_at, end_at = daily_activity_plans.daypart_windows(
            candidate_date, world.timezone
        )[proposal.target_daypart]
        if _aware_utc(start_at) <= _aware_utc(now):
            continue
        if all(
            joint_activity_runtime.slot_available(
                db, references=SqlAlchemyJointReferences(db),
                world_id=proposal.world_id,
                world_character_id=world_character_id,
                local_date=candidate_date,
                daypart=proposal.target_daypart,
                now=now,
            )
            for world_character_id in (
                proposal.proposer_world_character_id,
                proposal.target_world_character_id,
            )
        ):
            return ResolvedSchedule(
                candidate_date,
                proposal.target_daypart,
                start_at,
                end_at,
                world.timezone,
            )
    raise ActivityProposalRuntimeError("joint_activity_no_shared_schedule")


def apply_response(
    db: Session,
    *,
    proposal_id: str,
    response_event: models.SocialEvent,
    decision: str,
    now: datetime,
    resolved_schedule: ResolvedSchedule | None = None,
    counter_activity_seed: str | None = None,
    counter_place_key: str | None = None,
    counter_target_daypart: str | None = None,
    counter_date_policy: str | None = None,
    counter_target_date: date | None = None,
) -> ProposalResponseResult:
    proposal = db.scalar(
        select(models.ActivityProposal)
        .where(models.ActivityProposal.id == proposal_id)
        .with_for_update()
    )
    if proposal is None or proposal.status != "proposed":
        raise ActivityProposalRuntimeError("proposal_not_open")
    if response_event.world_id != proposal.world_id:
        raise ActivityProposalRuntimeError("proposal_response_world_mismatch")
    if (
        response_event.actor_world_character_id
        != proposal.target_world_character_id
        or response_event.target_world_character_id
        != proposal.proposer_world_character_id
    ):
        raise ActivityProposalRuntimeError("proposal_response_actor_mismatch")
    if proposal.source_response_event_id is not None:
        if proposal.source_response_event_id != response_event.id:
            raise ActivityProposalRuntimeError("proposal_already_answered")
        joint = db.scalar(
            select(models.JointActivity).where(
                models.JointActivity.proposal_id == proposal.id
            )
        )
        return ProposalResponseResult(proposal, None, joint)

    current = _aware_utc(now)
    proposal.source_response_event_id = response_event.id
    proposal.version += 1
    if decision == "accept":
        if response_event.event_type != "joint_accepted":
            raise ActivityProposalRuntimeError("proposal_response_event_invalid")
        schedule = resolved_schedule or resolve_acceptance_schedule(
            db, proposal_id=proposal.id, now=current
        )
        proposal.status = "accepted"
        proposal.accepted_at = current
        scheduled = joint_activity_runtime.create_scheduled_joint(
            db, references=SqlAlchemyJointReferences(db),
            proposal=proposal,
            acceptance_event_id=response_event.id,
            scheduled_local_date=schedule.local_date,
            scheduled_start_at=schedule.scheduled_start_at,
            scheduled_end_at=schedule.scheduled_end_at,
            timezone_name=schedule.timezone_name,
            now=current,
        )
        db.flush()
        return ProposalResponseResult(proposal, None, scheduled.joint_activity)
    if decision == "reject":
        if response_event.event_type != "joint_declined":
            raise ActivityProposalRuntimeError("proposal_response_event_invalid")
        proposal.status = "rejected"
        proposal.rejected_at = current
        db.flush()
        return ProposalResponseResult(proposal, None, None)
    if decision != "counter":
        raise ActivityProposalRuntimeError("proposal_decision_invalid")
    if response_event.event_type != "joint_proposed":
        raise ActivityProposalRuntimeError("proposal_response_event_invalid")
    if proposal.proposal_version > COUNTER_LIMIT:
        raise ActivityProposalRuntimeError("proposal_counter_limit")
    if not counter_activity_seed or counter_target_daypart not in joint_activity_runtime.DAYPARTS:
        raise ActivityProposalRuntimeError("proposal_counter_invalid")
    if counter_date_policy not in {"exact", "earliest_available"}:
        raise ActivityProposalRuntimeError("proposal_counter_invalid")
    if counter_date_policy == "exact" and counter_target_date is None:
        raise ActivityProposalRuntimeError("proposal_exact_date_required")
    proposer, target = joint_activity_runtime.validate_pair(
        db, references=SqlAlchemyJointReferences(db),
        world_id=proposal.world_id,
        first_world_character_id=proposal.target_world_character_id,
        second_world_character_id=proposal.proposer_world_character_id,
    )
    joint_activity_runtime.validate_place(
        db, references=SqlAlchemyJointReferences(db),
        world_id=proposal.world_id,
        place_key=counter_place_key,
        target_daypart=str(counter_target_daypart),
        participant_role_keys=(proposer.role_key, target.role_key),
    )
    proposal.status = "countered"
    proposal.countered_at = current
    child = models.ActivityProposal(
        id=uuid7_string(),
        world_id=proposal.world_id,
        root_proposal_id=proposal.root_proposal_id,
        parent_proposal_id=proposal.id,
        proposal_version=proposal.proposal_version + 1,
        proposer_world_character_id=proposal.target_world_character_id,
        target_world_character_id=proposal.proposer_world_character_id,
        activity_seed=counter_activity_seed,
        place_key=counter_place_key,
        target_daypart=str(counter_target_daypart),
        date_policy=str(counter_date_policy),
        target_date=counter_target_date,
        proposed_local_snapshot={
            "timezone": db.get(models.World, proposal.world_id).timezone,
            "target_daypart": counter_target_daypart,
            "target_date": (
                counter_target_date.isoformat()
                if counter_target_date is not None
                else None
            ),
        },
        status="proposed",
        source_proposal_event_id=response_event.id,
        idempotency_key=sha256(
            f"proposal-counter|{proposal.id}|{response_event.id}".encode("utf-8")
        ).hexdigest(),
        expires_at=current + PROPOSAL_TTL,
        version=1,
    )
    db.add(child)
    db.flush()
    return ProposalResponseResult(proposal, child, None)
