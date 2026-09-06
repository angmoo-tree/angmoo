"""Exact active membership lookup used by credential authorization."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.worlds import models


def get_active_membership_id(db: Session, world_id: str, user_id: str) -> str | None:
    return db.scalar(
        select(models.WorldMembership.id).where(
            models.WorldMembership.world_id == world_id,
            models.WorldMembership.user_id == user_id,
            models.WorldMembership.status == "active",
        )
    )
