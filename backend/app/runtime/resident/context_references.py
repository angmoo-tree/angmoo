"""Resident context reads on the original caller-owned SQLAlchemy Session."""
from typing import cast

from sqlalchemy.orm import Session

from app.domains.routines.contracts.action_context import ActionPost

from app.domains.characters.models import Character
from app.domains.characters.service import profile as character_profile
from app.domains.identity.models import User
from app.domains.identity.service import profile as user_profile
from app.domains.social.models.posts import Post
from app.domains.social.repository import posts as post_repository
from app.domains.social.repository import resident_context as social_queries
from app.domains.social.service import visibility


class SqlAlchemyResidentActionReferences:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_post(self, post_id: str) -> Post | None:
        return post_repository.get_post(self._db, post_id)

    def is_post_public_context_visible(self, post: ActionPost) -> bool:
        # get_post returns the original Social row; cast only describes that binding.
        return visibility.is_post_public_context_visible(self._db, cast(Post, post))

    def get_character(self, character_id: str) -> Character | None:
        return character_profile.get_character(self._db, character_id)

    def get_user(self, user_id: str) -> User | None:
        return user_profile.get_user(self._db, user_id)

    def find_follow_id(self, *, follower_character_id: str, target_character_id: str) -> int | None:
        return social_queries.find_follow_id(self._db, follower_character_id=follower_character_id, target_character_id=target_character_id)

    def has_character_like(self, *, post_id: str, character_id: str) -> bool:
        return social_queries._has_character_like(self._db, post_id=post_id, character_id=character_id)

    def has_character_repost(self, *, post_id: str, character_id: str) -> bool:
        return social_queries._has_character_repost(self._db, post_id=post_id, character_id=character_id)

    def has_character_replied_to_thread(self, *, root_post_id: str, character_id: str) -> bool:
        return social_queries._has_character_replied_to_thread(self._db, root_post_id=root_post_id, character_id=character_id)

    def is_direct_reply_to_character_post(self, *, post_id: str, character_id: str) -> bool:
        return social_queries._is_direct_reply_to_character_post_for_action_gate(self._db, post_id=post_id, character_id=character_id)
