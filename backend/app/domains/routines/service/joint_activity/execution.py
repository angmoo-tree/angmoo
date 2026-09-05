"""Joint claim fencing, opening publication and two-participant completion."""
from __future__ import annotations
from datetime import datetime
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.routines import models
from app.domains.routines.contracts.joint_activity import JointReferences
from app.domains.routines.exceptions import JointActivityRuntimeError
from app.domains.routines.service.scheduling import aware_utc as _aware_utc
from app.domains.routines.constants import (
    ACTIVE_JOINT_STATUSES,
    OPENING_LEASE,
    MAX_PARTICIPANT_OPENING_ATTEMPTS,
    MAX_JOINT_OPENING_ATTEMPTS,
)
from app.domains.routines.contracts.joint_activity import OpeningClaim
from app.domains.routines.service.joint_activity.eligibility import _eligible_world_character
from app.domains.routines.service.joint_activity.planning import _participant_rows


def claim_opening(
    db: Session,
    *,
    references: JointReferences,
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
        db, references=references,
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
    references: JointReferences,
    joint_activity_id: str,
    author_world_character_id: str,
    post: Any,
    post_event: Any,
    opening_claim: OpeningClaim | None,
    now: datetime,
) -> Any:
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
    references.set_joint_activity_id(post, joint_activity_id=joint.id)
    if joint.opening_post_id is not None:
        if opening_claim is not None:
            raise JointActivityRuntimeError("joint_activity_already_opened")
        if joint.status != "active":
            raise JointActivityRuntimeError("joint_activity_not_active")
        references.set_opening_post_id(post, opening_post_id=joint.opening_post_id)
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
    references.set_opening_post_id(post, opening_post_id=post.id)
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
    started = references.record_started_event(
        joint=joint, author_world_character_id=author_world_character_id,
        post=post, post_event=post_event, current=current,
    )
    other = next(
        row for row in participants if row.world_character_id != author_world_character_id
    )
    other_wc = references.get_world_character(other.world_character_id)
    actor_wc = references.get_world_character(author_world_character_id)
    if other_wc is None or actor_wc is None:
        raise JointActivityRuntimeError("joint_activity_participant_invalid")
    references.ensure_started_notification(
        joint_activity_id=joint.id,
        world_id=joint.world_id,
        recipient_world_character_id=other.world_character_id,
        actor_world_character_id=author_world_character_id,
        recipient_character_id=other_wc.character_id,
        actor_character_id=actor_wc.character_id,
        source_social_event_id=started.id,
        post_id=post.id,
    )
    db.flush()
    return started



def complete_due_joint_activities(
    db: Session, *, references: JointReferences, world_id: str, now: datetime
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
        post_count = references.visible_joint_post_count(joint_activity_id=joint.id)
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
            references.record_completed_event(
                joint=joint, actor=actor, target=target, current=current,
            )
        completed += 1
    if rows:
        db.commit()
    return completed, expired
