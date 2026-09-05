from zoneinfo import ZoneInfo

from app.domains.routines.contracts.activity_scope import ActivityScopeReads, WorldCharacterRead
from app.domains.routines.service.tick_schedule import APP_TIMEZONE


def activity_timezone(reads: ActivityScopeReads, *, character_id: str) -> ZoneInfo:
    """Resolve the selected World's IANA timezone, falling back to KST."""

    if not reads.has_active_world_table():
        return APP_TIMEZONE
    active_world = reads.get_active_world(character_id)
    if active_world is None:
        return APP_TIMEZONE
    if not reads.has_world_character_table():
        return APP_TIMEZONE
    world_character = reads.get_world_character(active_world.world_character_id)
    if world_character is None or world_character.character_id != character_id:
        return APP_TIMEZONE
    if not reads.has_world_table():
        return APP_TIMEZONE
    world = reads.get_world(world_character.world_id)
    if world is None:
        return APP_TIMEZONE
    try:
        return ZoneInfo(world.timezone)
    except (KeyError, ValueError):
        return APP_TIMEZONE


def activity_timezone_name(reads: ActivityScopeReads, *, character_id: str) -> str:
    return activity_timezone(reads, character_id=character_id).key


def is_imported_world_runtime_locked(
    reads: ActivityScopeReads,
    world_character: WorldCharacterRead,
) -> bool:
    """Return whether package lineage still requires explicit autonomy enable.

    Direct-created characters retain the user-initiated manual-run contract.
    Imported Worlds are stricter: P4-P7 must remain inert while their active
    WorldCharacter is autonomy-disabled, even in a resident-manual session.
    """

    if world_character.autonomous_enabled:
        return False
    if not reads.has_import_table():
        # Focused service fixtures may intentionally omit the v1 package
        # registry. Migrated production runtimes always have this table.
        return False
    return (
        reads.get_import_id(world_character.world_id)
        is not None
    )


def is_imported_world_runtime_locked_for_character(
    reads: ActivityScopeReads,
    *,
    character_id: str,
) -> bool:
    """Apply the import activation gate before an active World exists, too."""

    if not reads.has_import_table():
        return False
    active_world = reads.get_active_world(character_id)
    if active_world is not None:
        world_character = reads.get_world_character(active_world.world_character_id)
    else:
        world_character = reads.get_latest_imported_world_character(character_id)
    return bool(
        world_character is not None
        and not world_character.autonomous_enabled
        and reads.get_import_id(world_character.world_id)
        is not None
    )
