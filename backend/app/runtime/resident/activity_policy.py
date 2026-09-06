"""Construct activity decisions with the caller Session and lazy World reads."""

from app.domains.routines.constants import (PUBLIC_ACTION_TYPES, POLICY_ACTION_NAMES, TENDENCY_PUBLIC_ACTION_NAMES, POLICY_SESSION_MARKER, MANUAL_POLICY_SESSION_MARKER)
from app.domains.routines.exceptions import ActivityPolicyDeniedError
from app.domains.routines.contracts.activity_policy import ActivityPolicy, _format_tendency_prompt
from app.domains.routines.service.activity_sessions import is_policy_enforced_session, is_manual_policy_session
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from app.domains.routines import models
from app.domains.routines.service import tick_schedule as agent_activity_schedule
from app.domains.routines.service import activity_scope
from app.domains.routines.contracts.activity_scope import WorldCharacterRead
from app.runtime.resident.activity_scope import SqlAlchemyActivityScopeReads
from app.domains.routines.service import activity_policy as canonical_activity_policy
from app.domains.routines.repository.activity_counts import count_public_actions_since, _count_action_today, _latest_action_at
from app.domains.routines.utils.activity_actions import _normalize_action_types, _public_action_log_types
from app.domains.routines.service.activity_policy import _evaluate_counted_actions, _block_actions

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
    return activity_scope.activity_timezone(
        SqlAlchemyActivityScopeReads(db), character_id=character_id,
    )


def activity_timezone_name(db: Session, *, character_id: str) -> str:
    return activity_timezone(db, character_id=character_id).key


def is_imported_world_runtime_locked(db: Session, world_character: WorldCharacterRead) -> bool:
    return activity_scope.is_imported_world_runtime_locked(
        SqlAlchemyActivityScopeReads(db), world_character,
    )


def is_imported_world_runtime_locked_for_character(db: Session, *, character_id: str) -> bool:
    return activity_scope.is_imported_world_runtime_locked_for_character(
        SqlAlchemyActivityScopeReads(db), character_id=character_id,
    )


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
