"""Stable World identifiers used to rebuild their canonical graph projection."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.worlds import models


def list_projection_world_ids(db: Session) -> tuple[str, ...]:
    return tuple(
        str(value)
        for value in db.scalars(
            select(models.World.id).order_by(models.World.id)
        )
    )
