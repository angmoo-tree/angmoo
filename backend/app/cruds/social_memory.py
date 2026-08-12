from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import models


def list_recent_events(
    db: Session,
    *,
    world_id: str,
    world_character_id: str,
    limit: int = 30,
) -> list[models.SocialEvent]:
    return list(
        db.scalars(
            select(models.SocialEvent)
            .where(
                models.SocialEvent.world_id == world_id,
                or_(
                    models.SocialEvent.actor_world_character_id
                    == world_character_id,
                    models.SocialEvent.target_world_character_id
                    == world_character_id,
                ),
            )
            .order_by(
                models.SocialEvent.occurred_at.desc(),
                models.SocialEvent.id.desc(),
            )
            .limit(max(1, min(limit, 100)))
        )
    )


def list_event_evidence(
    db: Session, event_ids: list[str]
) -> dict[str, list[models.SocialEventEvidence]]:
    grouped: dict[str, list[models.SocialEventEvidence]] = {
        event_id: [] for event_id in event_ids
    }
    if not event_ids:
        return grouped
    for row in db.scalars(
        select(models.SocialEventEvidence)
        .where(models.SocialEventEvidence.social_event_id.in_(event_ids))
        .order_by(models.SocialEventEvidence.created_at.asc())
    ):
        grouped.setdefault(row.social_event_id, []).append(row)
    return grouped


def list_relationships(
    db: Session,
    *,
    world_id: str,
    world_character_id: str,
    outgoing: bool,
) -> list[models.RelationshipState]:
    direction = (
        models.RelationshipState.actor_world_character_id
        if outgoing
        else models.RelationshipState.target_world_character_id
    )
    return list(
        db.scalars(
            select(models.RelationshipState)
            .where(
                models.RelationshipState.world_id == world_id,
                direction == world_character_id,
            )
            .order_by(
                models.RelationshipState.last_event_at.desc().nullslast(),
                models.RelationshipState.id.asc(),
            )
        )
    )


def list_open_proposals(
    db: Session, *, world_id: str, world_character_id: str
) -> list[models.ActivityProposal]:
    return list(
        db.scalars(
            select(models.ActivityProposal)
            .where(
                models.ActivityProposal.world_id == world_id,
                models.ActivityProposal.status == "proposed",
                or_(
                    models.ActivityProposal.proposer_world_character_id
                    == world_character_id,
                    models.ActivityProposal.target_world_character_id
                    == world_character_id,
                ),
            )
            .order_by(models.ActivityProposal.created_at.desc())
        )
    )


def list_active_joint_activities(
    db: Session, *, world_id: str, world_character_id: str
) -> list[tuple[models.JointActivity, list[models.JointActivityParticipant]]]:
    activities = list(
        db.scalars(
            select(models.JointActivity)
            .join(
                models.JointActivityParticipant,
                models.JointActivityParticipant.joint_activity_id
                == models.JointActivity.id,
            )
            .where(
                models.JointActivity.world_id == world_id,
                models.JointActivityParticipant.world_character_id
                == world_character_id,
                models.JointActivity.status.in_(
                    ("scheduled", "ready", "active")
                ),
            )
            .order_by(models.JointActivity.scheduled_start_at.asc())
        )
    )
    result = []
    for activity in activities:
        participants = list(
            db.scalars(
                select(models.JointActivityParticipant)
                .where(
                    models.JointActivityParticipant.joint_activity_id
                    == activity.id
                )
                .order_by(models.JointActivityParticipant.role.asc())
            )
        )
        result.append((activity, participants))
    return result


def pending_outbox_count(db: Session, *, world_id: str) -> int:
    return int(
        db.scalar(
            select(func.count(models.GraphProjectionOutbox.id)).where(
                models.GraphProjectionOutbox.world_id == world_id,
                models.GraphProjectionOutbox.status == "pending",
            )
        )
        or 0
    )
