"""User profile lookup for owner-aware collaboration in the caller Session."""
from sqlalchemy.orm import Session
from app.domains.identity import models


def get_user(db: Session, user_id: str) -> models.User | None:
    return db.get(models.User, user_id)
