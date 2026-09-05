"""Activity setting validation, mutations and schedule update ordering."""
from __future__ import annotations
from datetime import UTC, datetime
from sqlalchemy.orm import Session
from app.core import active_hours
from app.domains.routines import models, schemas
from app.domains.routines import constants as routine_constants
from app.domains.routines.contracts.activity_management import ActivityOwner, InitialActivitySettings, ActivityManagementReferences
from app.domains.routines.exceptions import AgentAutonomyCapacityError
from app.domains.routines.repository import slots as slot_queries
from app.domains.routines.service import activity_settings as agent_crud
from app.domains.routines.service.activity_policy import build_activity_policy
from app.domains.routines.service.tick_schedule import tick_interval_seconds


def _validate_initial_activity_settings(data: InitialActivitySettings, *, invalid_active_hours: type[Exception]) -> None:
    if data.active_hours_start is None and data.active_hours_end is None:
        return
    if data.active_hours_start is None or data.active_hours_end is None:
        raise invalid_active_hours(
            "active_hours_start and active_hours_end must be provided together."
        )
    try:
        active_hours.validate_active_hours(data.active_hours_start, data.active_hours_end)
    except ValueError as exc:
        raise invalid_active_hours(str(exc)) from exc


def _apply_initial_activity_settings(
    db: Session,
    setting: models.AgentActivitySetting,
    data: InitialActivitySettings,
) -> None:
    changed = False
    if data.activity_interval_minutes is not None:
        setting.activity_interval_minutes = data.activity_interval_minutes
        changed = True
    if data.active_hours_start is not None and data.active_hours_end is not None:
        setting.active_hours_start = data.active_hours_start
        setting.active_hours_end = data.active_hours_end
        changed = True
    if changed:
        db.commit()
        db.refresh(setting)


def get_settings(
    db: Session, user: ActivityOwner, character_id: str,
    *, references: ActivityManagementReferences,
) -> schemas.AgentActivitySettingRead:
    character = references.get_owned_character(db, user, character_id)
    return schemas.AgentActivitySettingRead.model_validate(
        agent_crud.ensure_setting(db, character.id)
    )


def update_settings(
    db: Session,
    user: ActivityOwner,
    character_id: str,
    data: schemas.AgentActivitySettingUpdate,
    *, references: ActivityManagementReferences,
) -> schemas.AgentActivitySettingRead:
    character = references.get_owned_character(db, user, character_id)
    references.ensure_mutable(user)
    if references.is_local_mode(character) and data.auto_enabled is True:
        raise references.execution_mode_error(references.local_mode_message)
    if not references.is_local_mode(character) and data.auto_enabled is not None:
        raise AgentAutonomyCapacityError(
            "자율활동 상태는 활성화/비활성화 버튼을 사용해주세요."
        )
    setting = agent_crud.ensure_setting(db, character.id)
    start = (
        data.active_hours_start
        if data.active_hours_start is not None
        else setting.active_hours_start
    )
    end = (
        data.active_hours_end
        if data.active_hours_end is not None
        else setting.active_hours_end
    )
    try:
        active_hours.validate_active_hours(start, end)
    except ValueError as exc:
        raise references.active_hours_error(str(exc)) from exc
    if data.allow_observe is not None:
        data = data.model_copy(update={"allow_observe": True})
    schedule_fields = {
        "activity_interval_minutes",
        "active_hours_start",
        "active_hours_end",
    }
    schedule_changed = bool(data.model_fields_set & schedule_fields)
    setting = agent_crud.update_setting(db, setting, data, commit=False)
    slot = slot_queries.get_assigned_slot(db, character.id)
    if slot is not None:
        slot.heartbeat_interval_seconds = tick_interval_seconds(
            setting
        )
        if (
            setting.auto_enabled
            and schedule_changed
            and slot.status == routine_constants.SLOT_STATUS_ASSIGNED_IDLE
        ):
            policy = build_activity_policy(
                db,
                character_id=character.id,
                now=datetime.now(UTC),
                timezone_reader=references.timezone_reader,
            )
            slot.next_tick_at = policy.next_tick_at
    db.commit()
    db.refresh(setting)
    return schemas.AgentActivitySettingRead.model_validate(setting)
