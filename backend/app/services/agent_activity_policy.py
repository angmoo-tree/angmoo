from app.domains.routines.constants import (PUBLIC_ACTION_TYPES, POLICY_ACTION_NAMES, TENDENCY_PUBLIC_ACTION_NAMES, POLICY_SESSION_MARKER, MANUAL_POLICY_SESSION_MARKER)
from app.domains.routines.exceptions import ActivityPolicyDeniedError
from app.domains.routines.contracts.activity_policy import ActivityPolicy, _format_tendency_prompt
from app.domains.routines.service.activity_sessions import is_policy_enforced_session, is_manual_policy_session

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app import models
from app.domains.routines.service import tick_schedule as agent_activity_schedule


APP_TIMEZONE = agent_activity_schedule.APP_TIMEZONE
TickSchedule = agent_activity_schedule.TickSchedule
tick_interval_seconds = agent_activity_schedule.tick_interval_seconds
next_tick_schedule = agent_activity_schedule.next_tick_schedule
initial_tick_schedule = agent_activity_schedule.initial_tick_schedule
retry_tick_schedule = agent_activity_schedule.retry_tick_schedule
recovery_tick_schedule = agent_activity_schedule.recovery_tick_schedule
_is_within_active_hours = agent_activity_schedule.is_within_active_hours
_aware_utc = agent_activity_schedule.aware_utc






def activity_timezone(db: Session, *, character_id: str) -> ZoneInfo:
    """Resolve the selected World's IANA timezone, falling back to KST."""

    inspector = inspect(db.get_bind())
    if not inspector.has_table(models.CharacterActiveWorld.__tablename__):
        return APP_TIMEZONE
    active_world = db.get(models.CharacterActiveWorld, character_id)
    if active_world is None:
        return APP_TIMEZONE
    if not inspector.has_table(models.WorldCharacter.__tablename__):
        return APP_TIMEZONE
    world_character = db.get(models.WorldCharacter, active_world.world_character_id)
    if world_character is None or world_character.character_id != character_id:
        return APP_TIMEZONE
    if not inspector.has_table(models.World.__tablename__):
        return APP_TIMEZONE
    world = db.get(models.World, world_character.world_id)
    if world is None:
        return APP_TIMEZONE
    try:
        return ZoneInfo(world.timezone)
    except (KeyError, ValueError):
        return APP_TIMEZONE


def activity_timezone_name(db: Session, *, character_id: str) -> str:
    return activity_timezone(db, character_id=character_id).key






def is_imported_world_runtime_locked(
    db: Session,
    world_character: models.WorldCharacter,
) -> bool:
    """Return whether package lineage still requires explicit autonomy enable.

    Direct-created characters retain the user-initiated manual-run contract.
    Imported Worlds are stricter: P4-P7 must remain inert while their active
    WorldCharacter is autonomy-disabled, even in a resident-manual session.
    """

    if world_character.autonomous_enabled:
        return False
    bind = db.get_bind()
    if not inspect(bind).has_table(models.WorldPackageImport.__tablename__):
        # Focused service fixtures may intentionally omit the v1 package
        # registry. Migrated production runtimes always have this table.
        return False
    return (
        db.scalar(
            select(models.WorldPackageImport.import_id)
            .where(
                models.WorldPackageImport.imported_world_id
                == world_character.world_id
            )
            .limit(1)
        )
        is not None
    )


def is_imported_world_runtime_locked_for_character(
    db: Session,
    *,
    character_id: str,
) -> bool:
    """Apply the import activation gate before an active World exists, too."""

    bind = db.get_bind()
    if not inspect(bind).has_table(models.WorldPackageImport.__tablename__):
        return False
    active_world = db.get(models.CharacterActiveWorld, character_id)
    if active_world is not None:
        world_character = db.get(
            models.WorldCharacter, active_world.world_character_id
        )
    else:
        world_character = db.scalar(
            select(models.WorldCharacter)
            .join(
                models.WorldPackageImport,
                models.WorldPackageImport.imported_world_id
                == models.WorldCharacter.world_id,
            )
            .where(models.WorldCharacter.character_id == character_id)
            .order_by(models.WorldCharacter.created_at.desc())
            .limit(1)
        )
    return bool(
        world_character is not None
        and not world_character.autonomous_enabled
        and db.scalar(
            select(models.WorldPackageImport.import_id)
            .where(
                models.WorldPackageImport.imported_world_id
                == world_character.world_id
            )
            .limit(1)
        )
        is not None
    )
























from app.domains.routines.service import activity_policy as canonical_activity_policy
from app.domains.routines.repository.activity_counts import count_public_actions_since, _count_action_today, _latest_action_at
from app.domains.routines.utils.activity_actions import _normalize_action_types, _public_action_log_types
from app.domains.routines.service.activity_policy import _evaluate_counted_actions, _block_actions


def build_activity_policy(
    db: Session,
    *,
    character_id: str,
    now: datetime | None = None,
    ignore_active_hours: bool = False,
) -> ActivityPolicy:
    return canonical_activity_policy.build_activity_policy(
        db, character_id=character_id, now=now,
        ignore_active_hours=ignore_active_hours, timezone_reader=activity_timezone,
    )


def assert_action_allowed(db: Session, *, run: models.AgentRun, action: str) -> None:
    return canonical_activity_policy.assert_action_allowed(
        db, run=run, action=action, timezone_reader=activity_timezone,
    )


def count_action_today(
    db: Session, *, character_id: str, action: str, now: datetime | None = None,
) -> int:
    return canonical_activity_policy.count_action_today(
        db, character_id=character_id, action=action, now=now,
        timezone_reader=activity_timezone,
    )
