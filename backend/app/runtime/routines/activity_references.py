"""Original Post/WorldCharacter/membership reads using the caller's Session."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.social.models.posts import Post
from app.domains.world_characters.models import WorldCharacter
from app.domains.worlds.models import WorldMembership


class SqlAlchemyActivityReferences:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_world_character(self, world_character_id: str, *, lock_for_update: bool = False) -> WorldCharacter | None:
        if lock_for_update:
            return self._db.scalar(
                select(WorldCharacter)
                .where(WorldCharacter.id == world_character_id)
                .with_for_update()
            )
        return self._db.get(WorldCharacter, world_character_id)

    def get_membership(self, membership_id: str) -> WorldMembership | None:
        return self._db.get(WorldMembership, membership_id)

    def get_post(self, post_id: str) -> Post | None:
        return self._db.get(Post, post_id)
