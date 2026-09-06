"""Concrete source-write collaboration bound to the one transaction Session."""
from collections.abc import Callable
from sqlalchemy.orm import Session
from app.domains.characters.service.profile import get_character
from app.domains.identity.service.profile import get_user
from app.domains.social.contracts.actors import SocialCharacter, SocialUser
from app.domains.social.contracts.source_writes import SourceWorldCharacter, SourceMembership
from app.domains.social.models.posts import Post
from app.domains.relationships.service.source_posts import record_source_post_event
from app.domains.world_characters.contracts.owner_identity import OwnerControlledIdentitySnapshot
from app.domains.world_characters.service.owner_identity import OwnerControlledIdentityService
from app.domains.world_characters.repository.source_writes import get_source_actor
from app.domains.worlds.service.character_entry import get_character_entry_membership


class RuntimeSourceWriteReferences:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_owner_identity(self, *, world_id: str, current_user_id: str) -> OwnerControlledIdentitySnapshot:
        return OwnerControlledIdentityService(self.db).get(world_id=world_id, current_user_id=current_user_id)

    def get_world_character(self, world_character_id: str) -> SourceWorldCharacter | None:
        return get_source_actor(self.db, world_character_id)

    def get_character(self, character_id: str) -> SocialCharacter | None:
        return get_character(self.db, character_id)

    def get_user(self, user_id: str) -> SocialUser | None:
        return get_user(self.db, user_id)

    def get_membership(self, membership_id: str) -> SourceMembership | None:
        return get_character_entry_membership(self.db, membership_id)

    def record_source_event(self, *, world_id: str, actor_world_character_id: str, target_world_character_id: str | None, operation: str, post: Post, root_post: Post, request_key: str, failure_injector: Callable[[str], None] | None) -> None:
        record_source_post_event(self.db, world_id=world_id, actor_world_character_id=actor_world_character_id, target_world_character_id=target_world_character_id, operation=operation, post=post, root_post=root_post, request_key=request_key, failure_injector=failure_injector)
