"""Compose current World/owner reads with the Routines-owned schedule command."""
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.domains.characters.models import Character
from app.domains.characters.service.import_configuration import ImportSettings
from app.domains.identity.service.environment import snapshot
from app.domains.routines.contracts.scheduling import ResolvedSchedule
from app.domains.routines.service.schedule_updates import changed_schedule, refresh_idle_schedule
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.world_characters.contracts.configuration import configuration_from_request, WorldEffectiveConfiguration
from app.domains.world_characters.contracts.scheduling import SCHEDULE_FIELDS
from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
from app.domains.worlds.models import World, WorldMembership


def utc_now():
    return datetime.now(UTC)


def _current_settings(db, *, owner_id, world_id, world_character_id, character_id):
    # Column read deliberately bypasses stale identity-map objects. This is a
    # single bound actor, not a scan of all enabled Worlds or characters.
    value = db.scalar(select(WorldCharacterConfiguration.settings)
        .join(WorldCharacter, WorldCharacter.id == WorldCharacterConfiguration.world_character_id)
        .join(CharacterActiveWorld, CharacterActiveWorld.world_character_id == WorldCharacter.id)
        .join(Character, Character.id == WorldCharacter.character_id)
        .join(World, World.id == WorldCharacter.world_id)
        .join(WorldMembership, WorldMembership.id == WorldCharacter.membership_id)
        .where(WorldCharacter.id == world_character_id, WorldCharacter.world_id == world_id,
            WorldCharacter.character_id == character_id, WorldCharacter.status == "active",
            WorldCharacter.control_mode == "autonomous", WorldCharacter.autonomous_enabled.is_(True),
            CharacterActiveWorld.character_id == character_id, Character.owner_id == owner_id,
            Character.deleted_at.is_(None), World.owner_user_id == owner_id,
            WorldMembership.world_id == world_id, WorldMembership.user_id == owner_id,
            WorldMembership.status == "active"))
    return ImportSettings.model_validate(value) if value is not None else None


class WorldActivityScheduleUpdater:
    def refresh(self, db, *, owner_id, world_id, world_character_id, character_id):
        # World caller has already acquired admission and revision write locks.
        db.flush()
        setting = _current_settings(db, owner_id=owner_id, world_id=world_id,
            world_character_id=world_character_id, character_id=character_id)
        if setting is None:
            raise ValueError("activity_schedule_scope_invalid")
        return refresh_idle_schedule(db, owner_id=owner_id, character_id=character_id,
            setting=setting, environment=snapshot(db, owner_id), now=utc_now())


@dataclass(frozen=True)
class WorldCompletionSchedule:
    owner_id: str
    character_id: str
    admitted: WorldEffectiveConfiguration

    def resolve(self, db, slot, now):
        current = _current_settings(db, owner_id=self.owner_id, character_id=self.character_id,
            world_id=self.admitted.world_id, world_character_id=self.admitted.world_character_id)
        if current is None:
            # OFF/deleted/changed binding: allocator owns release, never schedule
            # a different World on behalf of this already accepted run.
            return None
        environment = snapshot(db, self.owner_id)
        if (all(getattr(current, key) == getattr(self.admitted.settings, key) for key in SCHEDULE_FIELDS)
            and slot.timezone_revision == environment.timezone_revision):
            return None
        return ResolvedSchedule(changed_schedule(current, character_id=self.character_id,
            now=now, last_run_at=now, timezone=ZoneInfo(environment.timezone)), environment.timezone_revision)


def automatic_completion_schedule(*, owner_id, character_id, input_snapshot, automatic):
    if not automatic or not input_snapshot or "_world_configuration" not in input_snapshot:
        return None
    admitted = configuration_from_request(input_snapshot["_world_configuration"])
    if admitted.character_id != character_id:
        raise ValueError("activity_schedule_scope_invalid")
    return WorldCompletionSchedule(owner_id, character_id, admitted)
