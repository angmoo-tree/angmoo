"""Proposal counts and successful published-evidence lookup in the caller Session."""
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.domains.relationships import models


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
