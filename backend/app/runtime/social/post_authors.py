"""Bind Social authors to owning World values in the caller's transaction."""
from sqlalchemy import select

from app.domains.characters.models import Character
from app.domains.social.contracts.post_authors import WorldPostAuthor
from app.domains.worlds.models import WorldMembership
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service.configuration import batch_effective_profiles, configuration_for_actor
from app.domains.world_characters.service.social_scope import resolve_social_target_scope
from app.runtime.world_configuration.effective_values import configuration_for_input


def batch_world_post_authors(db, *, world_id, author_ids):
    if not author_ids:
        return {}
    roles = db.execute(select(WorldCharacter.id, WorldCharacter.character_id).join(
        Character, Character.id == WorldCharacter.character_id).join(
        WorldMembership, WorldMembership.id == WorldCharacter.membership_id).where(
        WorldCharacter.world_id == world_id, WorldCharacter.id.in_(author_ids),
        WorldCharacter.status == "active", WorldMembership.world_id == world_id,
        WorldMembership.status == "active", Character.deleted_at.is_(None),
        Character.moderation_status == "active")).all()
    profiles = batch_effective_profiles(db, world_id=world_id, world_character_ids=[role_id for role_id, _ in roles])
    return {role_id: WorldPostAuthor(world_id, role_id, character_id,
        profile.display_name, profile.handle, profile.avatar_url)
        for role_id, character_id in roles if (profile := profiles.get(role_id)) is not None}


def world_post_author_for_write(db, *, character_id, world_id=None, world_character_id=None, input_snapshot=None):
    configuration = configuration_for_input(input_snapshot, character_id=character_id)
    if configuration is not None:
        if ((world_id is not None and configuration.world_id != world_id) or
            (world_character_id is not None and configuration.world_character_id != world_character_id)):
            raise ValueError("world_configuration_snapshot_scope_invalid")
    elif world_id is not None:
        configuration = configuration_for_actor(db, character_id=character_id, world_id=world_id)
        if configuration is not None and world_character_id is not None and configuration.world_character_id != world_character_id:
            raise ValueError("world_configuration_snapshot_scope_invalid")
    if configuration is None:
        return None
    profile = configuration.profile
    return WorldPostAuthor(configuration.world_id, configuration.world_character_id,
        configuration.character_id, profile.display_name, profile.handle, profile.avatar_url)


def historical_tool_post_author(db, *, character_id, world_id=None, world_character_id=None):
    """Pre-transition runs retain their original common Character name source."""
    if world_id is None:
        return None
    character = db.get(Character, character_id)
    if character is None:
        return None  # The timeline still owns canonical actor rejection.
    role_id = world_character_id or resolve_social_target_scope(db, target_world_id=world_id, character=character)
    return WorldPostAuthor(world_id, role_id, character_id, character.name, character.handle, character.avatar_url)
