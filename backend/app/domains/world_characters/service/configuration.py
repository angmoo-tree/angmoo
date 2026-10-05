"""Canonical World value resolution. No writes, commits or live Character fallback."""
from sqlalchemy import select
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.world_characters.contracts.configuration import WorldEffectiveConfiguration
from app.domains.characters.service.import_configuration import ImportProfile, ImportSettings


def effective_configuration(db, *, world_character_id):
    row = db.get(WorldCharacter, world_character_id)
    stored = db.get(WorldCharacterConfiguration, world_character_id)
    if row is None or stored is None:
        raise ValueError("world_configuration_missing")
    return configuration_value(row, stored)


def configuration_value(row, stored):
    return WorldEffectiveConfiguration(world_id=row.world_id, world_character_id=row.id, character_id=row.character_id,
        revision=row.version, autonomous_enabled=row.autonomous_enabled,
        profile=ImportProfile.model_validate(stored.profile), settings=ImportSettings.model_validate(stored.settings))


def configuration_for_actor(db, *, character_id, world_id=None):
    query = select(WorldCharacter.id).where(WorldCharacter.character_id == character_id, WorldCharacter.status == "active")
    if world_id is not None:
        query = query.where(WorldCharacter.world_id == world_id)
    ids = list(db.scalars(query.limit(2)))
    if len(ids) != 1:
        return None
    # An unconfigured pre-transition role is not fabricated during a read.
    if db.get(WorldCharacterConfiguration, ids[0]) is None:
        return None
    return effective_configuration(db, world_character_id=ids[0])


def initialize_configuration(db, *, world_character, snapshot_id, configuration):
    existing = db.get(WorldCharacterConfiguration, world_character.id)
    if existing is not None:
        return existing
    from app.domains.characters.service.import_snapshots import get_import_snapshot
    origin, _ = get_import_snapshot(db, world_character.character_id)
    if origin.id != snapshot_id:
        raise ValueError("world_configuration_origin_mismatch")
    row = WorldCharacterConfiguration(world_character_id=world_character.id, snapshot_id=snapshot_id,
        profile=configuration.profile.model_dump(mode="json"), settings=configuration.settings.model_dump(mode="json"))
    db.add(row)
    db.flush()
    return row


def batch_effective_profiles(db, *, world_id, world_character_ids):
    """Minimal public values for already-authorized, canonical graph candidates."""
    rows = db.execute(select(WorldCharacter.id, WorldCharacterConfiguration.profile).join(
        WorldCharacterConfiguration, WorldCharacterConfiguration.world_character_id == WorldCharacter.id).where(
        WorldCharacter.world_id == world_id, WorldCharacter.id.in_(world_character_ids))).all()
    return {role_id: ImportProfile.model_validate(profile) for role_id, profile in rows}
