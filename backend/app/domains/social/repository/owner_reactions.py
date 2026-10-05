from sqlalchemy import select
from app.domains.social.models.posts import PostLike


def owner_like(db, *, post_id, character_id):
    return db.scalar(select(PostLike).where(PostLike.post_id == post_id, PostLike.character_id == character_id).with_for_update())
