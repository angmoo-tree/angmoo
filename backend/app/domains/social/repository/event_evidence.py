"""Unfiltered Social source reads for the event owner's evidence policy."""
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models


def get_post(db: Session, post_id: str) -> models.Post | None:
    return db.get(models.Post, post_id)


def get_numeric_source(db: Session, *, source_object_type: str, source_id: int) -> object | None:
    source_model = {
        "post_like": models.PostLike,
        "post_repost": models.PostRepost,
        "profile_follow": models.ProfileFollow,
        "notification": models.Notification,
    }[source_object_type]
    return db.get(source_model, source_id)
