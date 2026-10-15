"""Explicit bounded multi-domain reads for Social, using the request's Session."""
from sqlalchemy import exists, select
from app.domains.characters.models import Character
from app.domains.identity.service.owner_context import is_claimed_local_owner
from app.domains.social.contracts.world_notifications import NotificationScope, WorldNotificationError
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.world_characters.service.owner_identity import OwnerControlledIdentityService
from app.domains.world_characters.contracts.owner_identity import OwnerControlledIdentityError, OwnerControlledIdentityNotFoundError, OwnerControlledIdentityConflictError
from app.domains.worlds.models import World, WorldMembership
from app.domains.worlds.models_deletion import WorldDeletionRequest
from app.runtime.social.post_authors import batch_world_post_authors


class RuntimeWorldNotificationReferences:
    def __init__(self, db):
        self.db = db

    def scopes(self, *, world_ids: list[str], user_id: str) -> dict[str, NotificationScope]:
        if not world_ids or not is_claimed_local_owner(self.db, user_id):
            return {}
        wc, member = WorldCharacter, WorldMembership
        rows = self.db.execute(select(wc.world_id, wc.id, wc.character_id)
            .join(World, World.id == wc.world_id)
            .join(member, (member.id == wc.membership_id) & (member.world_id == wc.world_id))
            .join(Character, Character.id == wc.character_id)
            .join(WorldCharacterConfiguration, WorldCharacterConfiguration.world_character_id == wc.id).where(
                wc.world_id.in_(world_ids), World.owner_user_id == user_id,
                ~exists(select(WorldDeletionRequest.id).where(WorldDeletionRequest.world_id == World.id)),
                member.user_id == user_id, member.role == "owner", member.status == "active",
                wc.owner_user_id == user_id, wc.control_mode == "owner_controlled", wc.status == "active",
                wc.autonomous_enabled.is_(False), Character.owner_id == user_id,
                Character.deleted_at.is_(None), Character.moderation_status == "active"))
        result = {}
        ambiguous = set()
        for world_id, role_id, character_id in rows:
            if world_id in result:
                ambiguous.add(world_id)
            result[world_id] = NotificationScope(world_id, role_id, character_id)
        return {key: value for key, value in result.items() if key not in ambiguous}

    def require_scope(self, *, world_id: str, user_id: str) -> NotificationScope:
        try:
            identity = OwnerControlledIdentityService(self.db).get(world_id=world_id, current_user_id=user_id)
        except (OwnerControlledIdentityNotFoundError, OwnerControlledIdentityConflictError) as exc:
            raise WorldNotificationError("notification_profile_unavailable", 409) from exc
        except OwnerControlledIdentityError as exc:
            raise WorldNotificationError("notification_scope_unavailable", 404) from exc
        scope = self.scopes(world_ids=[world_id], user_id=user_id).get(world_id)
        if scope is None or scope.recipient_world_character_id != identity.world_character_id:
            raise WorldNotificationError("notification_profile_unavailable", 409)
        return scope

    def author_profiles(self, *, world_id: str, author_ids: set[str]):
        return batch_world_post_authors(self.db, world_id=world_id, author_ids=author_ids)

    def profile_target_ids(self, scopes):
        if not scopes:
            return set()
        from app.domains.social.models.posts import Notification
        wc, member = WorldCharacter, WorldMembership
        return set(self.db.scalars(select(wc.id).join(Character, Character.id == wc.character_id)
            .join(member, (member.id == wc.membership_id) & (member.world_id == wc.world_id))
            .join(WorldCharacterConfiguration, WorldCharacterConfiguration.world_character_id == wc.id)
            .where(wc.world_id.in_([s.world_id for s in scopes]), wc.status.in_(("active", "left")),
                member.status == "active", Character.deleted_at.is_(None), Character.moderation_status == "active",
                wc.local_profile["deleted"].as_boolean().is_not(True),
                wc.id.in_(select(Notification.actor_world_character_id).where(
                    Notification.world_id.in_([s.world_id for s in scopes]),
                    Notification.recipient_world_character_id.in_([s.recipient_world_character_id for s in scopes]),
                    Notification.notification_type == "follow")))))
