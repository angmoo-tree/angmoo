"""Canonical owner diagnostic queries without commit or provider calls."""
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.routines import models


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
