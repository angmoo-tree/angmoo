"""Owned manual inbox and mutual block queries at original transaction positions."""

from datetime import datetime
from sqlalchemy import or_, select
from sqlalchemy.engine import ScalarResult
from sqlalchemy.orm import Session
from app.domains.social.models.manual_writes import OwnerManualInboxCandidate
from app.domains.social.models.feed import WorldCharacterBlock


def _blocked(db: Session, *, row: OwnerManualInboxCandidate) -> bool:
    return (
        db.scalar(
            select(WorldCharacterBlock.id)
            .where(
                WorldCharacterBlock.world_id == row.world_id,
                or_(
                    (
                        WorldCharacterBlock.blocker_world_character_id
                        == row.actor_world_character_id
                    )
                    & (
                        WorldCharacterBlock.blocked_world_character_id
                        == row.target_world_character_id
                    ),
                    (
                        WorldCharacterBlock.blocker_world_character_id
                        == row.target_world_character_id
                    )
                    & (
                        WorldCharacterBlock.blocked_world_character_id
                        == row.actor_world_character_id
                    ),
                ),
            )
            .limit(1)
        )
        is not None
    )


def list_candidates(
    db: Session,
    *,
    world_id: str,
    consumer_world_character_id: str,
    after: datetime,
    before: datetime,
    current: datetime,
) -> list[OwnerManualInboxCandidate]:
    return list(
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
                    (OwnerManualInboxCandidate.status == "claimed")
                    & (
                        OwnerManualInboxCandidate.claim_expires_at.is_(None)
                        | (OwnerManualInboxCandidate.claim_expires_at <= current)
                    ),
                ),
            )
            .order_by(
                OwnerManualInboxCandidate.created_at, OwnerManualInboxCandidate.id
            )
        )
    )


def get_for_update(db: Session, row_id: str) -> OwnerManualInboxCandidate | None:
    return db.scalar(
        select(OwnerManualInboxCandidate)
        .where(OwnerManualInboxCandidate.id == row_id)
        .with_for_update()
    )


def get_candidate(db: Session, row_id: str) -> OwnerManualInboxCandidate | None:
    return db.get(OwnerManualInboxCandidate, row_id)


def claimed_for_run(
    db: Session, *, ids: list[str], claim_run_id: str
) -> ScalarResult[OwnerManualInboxCandidate]:
    return db.scalars(
        select(OwnerManualInboxCandidate)
        .where(
            OwnerManualInboxCandidate.id.in_(ids),
            OwnerManualInboxCandidate.status == "claimed",
            OwnerManualInboxCandidate.claim_run_id == claim_run_id,
        )
        .with_for_update()
    )


def list_for_update(db: Session, ids: list[str]) -> list[OwnerManualInboxCandidate]:
    return list(
        db.scalars(
            select(OwnerManualInboxCandidate)
            .where(OwnerManualInboxCandidate.id.in_(ids))
            .with_for_update()
        )
    )
