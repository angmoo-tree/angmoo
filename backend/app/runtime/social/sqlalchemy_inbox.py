"""Runtime SQLAlchemy inbox adapter for owner social observations."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models
from app.domains.social.domain.inbox import (
    ManualInboxInteractionCandidate,
)
from app.domains.social.infrastructure.sqlalchemy_models import (
    OwnerManualInboxCandidate,
)


SOURCE_PREFIX = "manual-inbox:"


class ManualInboxRuntimeError(Exception):
    pass


def source_id(candidate_id: str) -> str:
    return f"{SOURCE_PREFIX}{candidate_id}"


def candidate_id(value: str) -> str | None:
    if not value.startswith(SOURCE_PREFIX):
        return None
    result = value[len(SOURCE_PREFIX) :].strip()
    return result or None


def is_manual_inbox_source(value: str) -> bool:
    return candidate_id(value) is not None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _blocked(db: Session, *, row: OwnerManualInboxCandidate) -> bool:
    return (
        db.scalar(
            select(models.WorldCharacterBlock.id)
            .where(
                models.WorldCharacterBlock.world_id == row.world_id,
                or_(
                    (
                        models.WorldCharacterBlock.blocker_world_character_id
                        == row.actor_world_character_id
                    )
                    & (
                        models.WorldCharacterBlock.blocked_world_character_id
                        == row.target_world_character_id
                    ),
                    (
                        models.WorldCharacterBlock.blocker_world_character_id
                        == row.target_world_character_id
                    )
                    & (
                        models.WorldCharacterBlock.blocked_world_character_id
                        == row.actor_world_character_id
                    ),
                ),
            )
            .limit(1)
        )
        is not None
    )


def _valid_candidate(
    db: Session,
    *,
    row: OwnerManualInboxCandidate,
) -> tuple[models.Post, models.Post] | None:
    reply = db.get(models.Post, row.source_reply_post_id)
    target_post = db.get(models.Post, row.target_post_id)
    actor = db.get(models.WorldCharacter, row.actor_world_character_id)
    target = db.get(models.WorldCharacter, row.target_world_character_id)
    if (
        reply is None
        or target_post is None
        or actor is None
        or target is None
        or reply.world_id != row.world_id
        or target_post.world_id != row.world_id
        or reply.author_world_character_id != actor.id
        or target_post.author_world_character_id != target.id
        or reply.reply_to_post_id != target_post.id
        or reply.deleted_at is not None
        or target_post.deleted_at is not None
        or reply.report_hidden_at is not None
        or target_post.report_hidden_at is not None
        or reply.visibility != "public"
        or target_post.visibility != "public"
        or actor.status != "active"
        or actor.control_mode != "owner_controlled"
        or target.status != "active"
        or target.control_mode != "autonomous"
        or target.activity_runtime_mode != "routine_resident_v1"
        or _blocked(db, row=row)
    ):
        return None
    actor_membership = db.get(models.WorldMembership, actor.membership_id)
    target_membership = db.get(models.WorldMembership, target.membership_id)
    if (
        actor_membership is None
        or target_membership is None
        or actor_membership.world_id != row.world_id
        or target_membership.world_id != row.world_id
        or actor_membership.status != "active"
        or target_membership.status != "active"
    ):
        return None
    return reply, target_post


def candidates(
    db: Session,
    *,
    world_id: str,
    consumer_world_character_id: str,
    episode_id: str,
    after: datetime,
    before: datetime,
) -> list[ManualInboxInteractionCandidate]:
    current = _aware_utc(before)
    rows = list(
        db.scalars(
            select(OwnerManualInboxCandidate)
            .where(
                OwnerManualInboxCandidate.world_id == world_id,
                OwnerManualInboxCandidate.target_world_character_id
                == consumer_world_character_id,
                OwnerManualInboxCandidate.created_at > after,
                OwnerManualInboxCandidate.created_at <= before,
                or_(
                    OwnerManualInboxCandidate.status.in_({"pending", "released"}),
                    (
                        OwnerManualInboxCandidate.status == "claimed"
                    )
                    & (
                        OwnerManualInboxCandidate.claim_expires_at.is_(None)
                        | (OwnerManualInboxCandidate.claim_expires_at <= current)
                    ),
                ),
            )
            .order_by(
                OwnerManualInboxCandidate.created_at,
                OwnerManualInboxCandidate.id,
            )
        )
    )
    result: list[ManualInboxInteractionCandidate] = []
    rejected = False
    for row in rows:
        valid = _valid_candidate(db, row=row)
        if valid is None:
            row.status = "rejected"
            row.rejected_reason_code = "source_context_invalid"
            row.claim_run_id = None
            row.claim_expires_at = None
            row.target_activity_beat_id = None
            row.version += 1
            rejected = True
            continue
        reply, target_post = valid
        result.append(
            ManualInboxInteractionCandidate(
                source_event_id=source_id(row.id),
                world_id=row.world_id,
                consumer_world_character_id=row.target_world_character_id,
                actor_world_character_id=row.actor_world_character_id,
                excerpt=reply.body,
                occurred_at=row.created_at,
                directness=100,
                episode_relevance=(
                    100 if target_post.activity_episode_id == episode_id else 60
                ),
                relationship_band="new",
            )
        )
    if rejected:
        db.commit()
    return result


def claim(
    db: Session,
    *,
    source_event_id: str,
    world_id: str,
    consumer_world_character_id: str,
    target_activity_beat_id: str,
    claim_run_id: str,
    claim_expires_at: datetime,
    now: datetime,
) -> OwnerManualInboxCandidate:
    row_id = candidate_id(source_event_id)
    if row_id is None:
        raise ManualInboxRuntimeError("manual_inbox_source_invalid")
    current = _aware_utc(now)
    expiry = _aware_utc(claim_expires_at)
    row = db.scalar(
        select(OwnerManualInboxCandidate)
        .where(OwnerManualInboxCandidate.id == row_id)
        .with_for_update()
    )
    if row is None:
        raise ManualInboxRuntimeError("manual_inbox_missing")
    if (
        row.world_id != world_id
        or row.target_world_character_id != consumer_world_character_id
        or _valid_candidate(db, row=row) is None
    ):
        raise ManualInboxRuntimeError("manual_inbox_scope_invalid")
    if row.status == "consumed":
        raise ManualInboxRuntimeError("manual_inbox_already_consumed")
    if row.status == "rejected":
        raise ManualInboxRuntimeError("manual_inbox_rejected")
    if (
        row.status == "claimed"
        and row.claim_run_id != claim_run_id
        and row.claim_expires_at is not None
        and _aware_utc(row.claim_expires_at) > current
    ):
        raise ManualInboxRuntimeError("manual_inbox_already_claimed")
    row.status = "claimed"
    row.target_activity_beat_id = target_activity_beat_id
    row.claim_run_id = claim_run_id
    row.claim_expires_at = expiry
    row.rejected_reason_code = None
    row.version += 1
    db.commit()
    return row


def claimed_observation_post_id(
    db: Session,
    *,
    source_event_id: str,
    world_id: str,
    consumer_world_character_id: str,
    target_activity_beat_id: str,
    claim_run_id: str,
) -> str:
    """Resolve the canonical reply post behind one fenced manual claim."""

    row_id = candidate_id(source_event_id)
    if row_id is None:
        raise ManualInboxRuntimeError("manual_inbox_source_invalid")
    row = db.get(OwnerManualInboxCandidate, row_id)
    if (
        row is None
        or row.world_id != world_id
        or row.target_world_character_id != consumer_world_character_id
        or row.target_activity_beat_id != target_activity_beat_id
        or row.claim_run_id != claim_run_id
        or row.status != "claimed"
    ):
        raise ManualInboxRuntimeError("manual_inbox_claim_mismatch")
    valid = _valid_candidate(db, row=row)
    if valid is None:
        raise ManualInboxRuntimeError("manual_inbox_source_context_invalid")
    reply, _target_post = valid
    return reply.id


def release_claims(
    db: Session,
    *,
    source_event_ids: list[str],
    claim_run_id: str,
) -> None:
    ids = [value for value in (candidate_id(item) for item in source_event_ids) if value]
    if not ids:
        return
    for row in db.scalars(
        select(OwnerManualInboxCandidate)
        .where(
            OwnerManualInboxCandidate.id.in_(ids),
            OwnerManualInboxCandidate.status == "claimed",
            OwnerManualInboxCandidate.claim_run_id == claim_run_id,
        )
        .with_for_update()
    ):
        row.status = "released"
        row.target_activity_beat_id = None
        row.claim_run_id = None
        row.claim_expires_at = None
        row.version += 1
    db.commit()


def consume_claims(
    db: Session,
    *,
    source_event_ids: list[str],
    target_activity_beat_id: str,
    claim_run_id: str,
    now: datetime,
) -> None:
    ids = [value for value in (candidate_id(item) for item in source_event_ids) if value]
    if not ids:
        return
    rows = list(
        db.scalars(
            select(OwnerManualInboxCandidate)
            .where(OwnerManualInboxCandidate.id.in_(ids))
            .with_for_update()
        )
    )
    if len(rows) != len(ids) or any(
        row.status != "claimed"
        or row.claim_run_id != claim_run_id
        or row.target_activity_beat_id != target_activity_beat_id
        for row in rows
    ):
        raise ManualInboxRuntimeError("manual_inbox_claim_mismatch")
    current = _aware_utc(now)
    for row in rows:
        row.status = "consumed"
        row.claim_run_id = None
        row.claim_expires_at = None
        row.consumed_at = current
        row.version += 1
    db.flush()


__all__ = [
    "ManualInboxRuntimeError",
    "candidate_id",
    "candidates",
    "claimed_observation_post_id",
    "claim",
    "consume_claims",
    "is_manual_inbox_source",
    "release_claims",
    "source_id",
]
