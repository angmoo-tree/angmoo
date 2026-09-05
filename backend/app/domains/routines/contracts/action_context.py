"""Read collaborators used when deciding resident actions from existing context."""
from datetime import datetime
from typing import Protocol


class ActionPost(Protocol):
    id: str
    author_user_id: str | None
    author_character_id: str | None
    title: str
    body: str
    reply_to_post_id: str | None


class ActionCharacter(Protocol):
    name: str
    handle: str
    deleted_at: datetime | None


class ActionUser(Protocol):
    display_name: str


class ResidentActionReferences(Protocol):
    def get_post(self, post_id: str) -> ActionPost | None: ...
    def is_post_public_context_visible(self, post: ActionPost) -> bool: ...
    def get_character(self, character_id: str) -> ActionCharacter | None: ...
    def get_user(self, user_id: str) -> ActionUser | None: ...
    def find_follow_id(self, *, follower_character_id: str, target_character_id: str) -> int | None: ...
    def has_character_like(self, *, post_id: str, character_id: str) -> bool: ...
    def has_character_repost(self, *, post_id: str, character_id: str) -> bool: ...
    def has_character_replied_to_thread(self, *, root_post_id: str, character_id: str) -> bool: ...
    def is_direct_reply_to_character_post(self, *, post_id: str, character_id: str) -> bool: ...
