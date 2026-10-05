"""Separate owned settings reads from published World execution admission."""
from sqlalchemy import inspect, select

from app.domains.routines.exceptions import ActivityRuntimeValidationError
from app.runtime.world_configuration.effective_values import configured_setting
from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
from app.domains.world_characters.service.configuration import configuration_for_actor
from app.domains.identity.models import LlmCredential
from app.domains.characters.models import Character
from app.domains.worlds.models import World, WorldMembership


def _configuration_for_settings_read(db, *, character_id):
    """Read saved policy for an active owned role, including an unpublished World."""
    # Legacy pre-World schemas remain supported by the existing non-World path.
    if not inspect(db.connection()).has_table(WorldCharacter.__tablename__):
        return None
    roles = list(db.scalars(select(WorldCharacter).where(WorldCharacter.character_id == character_id).limit(2)))
    if not roles:
        return None
    if len(roles) != 1:
        raise ActivityRuntimeValidationError("world_character_binding_ambiguous")
    role = roles[0]
    if role.status != "active":
        raise ActivityRuntimeValidationError("world_character_inactive")
    binding = db.get(CharacterActiveWorld, character_id)
    if binding is None or binding.world_character_id != role.id:
        raise ActivityRuntimeValidationError("world_character_binding_invalid")
    character = db.get(Character, character_id)
    membership = db.get(WorldMembership, role.membership_id)
    world = db.get(World, role.world_id)
    if (
        character is None
        or membership is None
        or membership.world_id != role.world_id
        or membership.user_id != character.owner_id
        or membership.status != "active"
        or world is None
    ):
        raise ActivityRuntimeValidationError("world_scope_not_ready")
    configuration = configuration_for_actor(db, character_id=character_id, world_id=role.world_id)
    if configuration is None:
        raise ActivityRuntimeValidationError("world_configuration_missing")
    return configuration


def _configuration_for_admission(db, *, character_id):
    """New execution also requires the owned World to be published and ready."""
    configuration = _configuration_for_settings_read(db, character_id=character_id)
    if configuration is None:
        return None
    world = db.get(World, configuration.world_id)
    if world is None or world.status != "published" or world.readiness_status != "publish_ready":
        raise ActivityRuntimeValidationError("world_scope_not_ready")
    return configuration


def capture_activity_input(db, *, character_id):
    """Freeze input only after strict execution admission; accepted input stays saved."""
    configuration = _configuration_for_admission(db, character_id=character_id)
    if configuration is None:
        return None
    credential = db.execute(select(LlmCredential.model, LlmCredential.thinking_level).where(
        LlmCredential.character_id == character_id, LlmCredential.purpose == "agent")).first()
    metadata = {"_world_configuration": configuration.request_snapshot()}
    model = configuration.settings.generation_model or (credential.model if credential else None)
    if model:
        metadata["_generation_model"] = model
        metadata["_generation_thinking_level"] = (credential.thinking_level if credential else None) or "high"
    return metadata


def read_effective_setting(db, *, character_id, setting):
    configuration = _configuration_for_settings_read(db, character_id=character_id)
    return configured_setting(setting, configuration)


def read_autonomy_enabled(db, *, character_id, setting):
    try:
        configuration = _configuration_for_admission(db, character_id=character_id)
        effective = configured_setting(setting, configuration)
    except ActivityRuntimeValidationError:
        return False
    return bool(effective and effective.auto_enabled)
