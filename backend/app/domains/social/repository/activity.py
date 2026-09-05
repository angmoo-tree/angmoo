"""Social-owned comments displayed in the existing public activity projection."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models


def recent_character_comments(db: Session, *, character_id: str) -> list[models.Comment]:
    return list(
            db.scalars(
                select(models.Comment)
                .where(models.Comment.author_character_id == character_id)
                .order_by(models.Comment.created_at.desc(), models.Comment.id.desc())
                .limit(20)
            )
        )
