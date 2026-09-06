"""Bind owner facts and the existing mixed active-profile join to one Session."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.characters.models import Character
from app.domains.characters.service.profile import get_character
from app.domains.social.contracts.actors import SocialCharacter
from app.domains.social.contracts.manual_feed import ManualFeedWorldCharacter
from app.domains.social.contracts.source_writes import SourceMembership
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.repository.source_writes import get_source_actor
from app.domains.world_characters.service.owner_identity import OwnerControlledIdentityService
from app.domains.world_characters.contracts.owner_identity import OwnerControlledIdentitySnapshot
from app.domains.worlds.models import WorldMembership
from app.domains.worlds.service.character_entry import get_character_entry_membership


class RuntimeManualFeedReferences:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_owner_identity(self, *, world_id: str, current_user_id: str) -> OwnerControlledIdentitySnapshot:
        return OwnerControlledIdentityService(self.db).get(world_id=world_id, current_user_id=current_user_id)

    def get_world_character(self, world_character_id: str) -> ManualFeedWorldCharacter | None:
        return get_source_actor(self.db, world_character_id)

    def get_character(self, character_id: str) -> SocialCharacter | None:
        return get_character(self.db, character_id)

    def get_membership(self, membership_id: str) -> SourceMembership | None:
        return get_character_entry_membership(self.db, membership_id)

    def active_author_id(self, *, world_id: str, author_world_character_id: str) -> str | None:
        db = self.db
        return db.scalar(
            select(WorldCharacter.id)
            .join(
                Character,
                Character.id == WorldCharacter.character_id,
            )
            .join(
                WorldMembership,
                (WorldMembership.id == WorldCharacter.membership_id)
                & (WorldMembership.world_id == WorldCharacter.world_id),
            )
            .where(
                WorldCharacter.id == author_world_character_id,
                WorldCharacter.world_id == world_id,
                WorldCharacter.status == "active",
                WorldMembership.status == "active",
                Character.deleted_at.is_(None),
                Character.moderation_status == "active",
            )
        )
