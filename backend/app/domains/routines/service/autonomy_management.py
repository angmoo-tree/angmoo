"""Activation/deactivation policy, fixed lock order and original commit semantics."""
from __future__ import annotations
from sqlalchemy.orm import Session
from app.config import settings
from app.core import unit_of_work
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.exceptions import SqliteBusyRetryExhausted
from app.domains.routines import models
from app.domains.routines import constants as routine_constants
from app.domains.routines.constants import SERVER_LLM_AUTONOMY_CAPACITY_ERROR_MESSAGE, WORLD_AUTONOMY_CAPACITY_ERROR_MESSAGE
from app.domains.routines.contracts.activity_management import ActivityOwner, ActivityCharacter
from app.domains.routines.contracts.autonomy_management import AutonomyWorkflows, DetailT, ActivityReadiness
from app.domains.routines.exceptions import AgentAutonomyCapacityError, AgentAutonomyRetryableError, ActivityProfileRequiredError, TendencyAnalysisRequiredError
from app.domains.routines.repository import slots as slot_queries
from app.domains.routines.repository.autonomy import _lock_server_llm_autonomy_capacity
from app.domains.routines.service import activity_settings, activity_logs, slot_assignments
from app.domains.routines.service.tick_schedule import tick_interval_seconds

def activate_agent(
    db: Session, user: ActivityOwner, character_id: str,
    *, workflows: AutonomyWorkflows[DetailT],
) -> DetailT:
    user_id = user.id
    try:
        if db.get_bind().dialect.name == "sqlite":
            with unit_of_work.deferred_commits():
                activated_character_id = run_sqlite_session_immediate(
                    db,
                    lambda: _activate_agent_uow(
                        db,
                        user_id=user_id,
                        character_id=character_id,
                        commit=False,
                        workflows=workflows,
                    ),
                )
        else:
            activated_character_id = _activate_agent_uow(
                db,
                user_id=user_id,
                character_id=character_id,
                commit=True,
                workflows=workflows,
            )
        activated_character = workflows.get_character(db, activated_character_id)
        if activated_character is None:
            raise workflows.character_not_found_error(activated_character_id)
        return workflows.build_detail(db, activated_character)
    except AgentAutonomyCapacityError as exc:
        db.rollback()
        _log_autonomy_activation_rejection(
            db,
            user_id=user_id,
            character_id=character_id,
            error=exc,
        )
        raise
    except SqliteBusyRetryExhausted as exc:
        raise AgentAutonomyRetryableError(
            "autonomy_activation_retryable: 자율활동 상태를 동시에 변경하고 있어요. "
            "잠시 후 다시 시도해주세요."
        ) from exc


def _activate_agent_uow(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    commit: bool,
    workflows: AutonomyWorkflows[DetailT],
) -> str:
    user = workflows.get_user(db, user_id)
    if user is None:
        raise workflows.character_not_found_error(character_id)
    character = workflows.get_owned_character(db, user, character_id)
    workflows.ensure_not_suspended(character)
    workflows.ensure_llm_mode(character)
    workflows.ensure_auto_ticks_available(db)
    current_setting = activity_settings.ensure_setting(db, character.id, commit=commit)
    readiness = _ensure_activity_profile_ready(
        db,
        character=character,
        setting=current_setting,
        workflows=workflows,
    )
    credential = workflows.get_credential(db, character.id)
    if credential is None or not credential.enabled:
        raise workflows.credential_required_error("Agent credential is required before activation")

    current_assigned_slot = slot_queries.get_assigned_slot(db, character.id)
    selected_world_character = workflows.select_world_character(
        db, character_id=character.id
    )
    if (
        current_setting.auto_enabled
        and current_assigned_slot is not None
        and (
            selected_world_character is None
            or selected_world_character.autonomous_enabled
        )
    ):
        return character.id

    # Fixed lock order: global first, then exact World. SQLite callers already
    # hold the single writer through BEGIN IMMEDIATE.
    _lock_server_llm_autonomy_capacity(db)
    if selected_world_character is not None:
        workflows.lock_world_capacity(
            db, world_id=selected_world_character.world_id
        )
        max_world_active = settings.world_autonomy_max_active_characters
        world_active_count = workflows.count_world_autonomy(
            db,
            world_id=selected_world_character.world_id,
            exclude_character_ids={character.id},
        )
        if world_active_count >= max_world_active:
            _reject_world_autonomy_capacity(
                active_count=world_active_count,
                max_active=max_world_active,
            )
    else:
        world_active_count = 0
        max_world_active = settings.world_autonomy_max_active_characters

    max_active = settings.server_llm_autonomy_max_active_agents
    active_count_without_target = workflows.count_effective_agents(
        db, exclude_character_ids={character.id}
    )
    if active_count_without_target >= max_active:
        _reject_server_llm_autonomy_capacity(
            active_count=active_count_without_target,
            max_active=max_active,
        )

    heartbeat_interval_seconds = tick_interval_seconds(current_setting)
    slot = workflows.assign_slot(
        db,
        user_id=user.id,
        character_id=character.id,
        credential_id=credential.id,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        commit=False,
    )
    if workflows.sync_enabled():
        try:
            workflows.bind_profile(
                slot, user_id=user.id, character=character, credential=credential
            )
            workflows.reload_secrets()
        except workflows.credential_sync_error:
            try:
                workflows.release_profile(
                    slot,
                    user_id=user.id,
                    character_id=character.id,
                    credential=credential,
                )
                workflows.reload_secrets()
            except workflows.credential_sync_error:
                pass
            slot_assignments.release_resident_slot_assignment(
                db,
                user_id=user.id,
                character_id=character.id,
                commit=False,
            )
            current_setting.auto_enabled = False
            workflows.set_world_autonomy(
                db,
                character_id=character.id,
                enabled=False,
            )
            workflows.set_character_status(character, status="inactive")
            if commit:
                db.commit()
            else:
                db.flush()
            raise
    current_setting.auto_enabled = True
    workflows.set_world_autonomy(
        db,
        character_id=character.id,
        enabled=True,
    )
    workflows.set_character_status(character, status="active")
    active_count = workflows.count_effective_agents(db)
    world_active_count = (
        workflows.count_world_autonomy(
            db,
            world_id=selected_world_character.world_id,
        )
        if selected_world_character is not None
        else 0
    )
    if commit:
        db.commit()
    else:
        db.flush()
    activity_logs.log_activity(
        db,
        user_id=user.id,
        character_id=character.id,
        action_type="activated",
        target_post_id=None,
        reason="user_enabled_autonomy",
        result=(
            f"Assigned resident slot {slot.agent_id} with credential {credential.id}. "
            f"active_count={active_count}; max_active={max_active}; "
            f"world_id={readiness.world_id}; world_active_count={world_active_count}; "
            f"max_world_active={max_world_active}"
        ),
    )
    db.refresh(character)
    return character.id


def deactivate_agent(
    db: Session, user: ActivityOwner, character_id: str,
    *, workflows: AutonomyWorkflows[DetailT],
) -> DetailT:
    character = workflows.get_owned_character(db, user, character_id)
    current_setting = activity_settings.ensure_setting(db, character.id)
    assigned_slot = slot_queries.get_assigned_slot(db, character.id)
    if assigned_slot is None and not current_setting.auto_enabled:
        changed = workflows.set_world_autonomy(
            db,
            character_id=character.id,
            enabled=False,
        )
        if changed:
            db.commit()
        return workflows.build_detail(db, character)
    if (
        assigned_slot is not None
        and assigned_slot.status == routine_constants.SLOT_STATUS_RUNNING
    ):
        raise workflows.slot_busy_error(
            f"agent {character.id}가 지금 실행 중이라 끌 수 없습니다. 잠시 뒤 다시 시도해주세요."
        )
    credential = workflows.get_credential(db, character.id)
    if (
        assigned_slot is not None
        and credential is not None
        and workflows.sync_enabled()
    ):
        workflows.release_profile(
            assigned_slot,
            user_id=user.id,
            character_id=character.id,
            credential=credential,
        )
        workflows.reload_secrets()
    slot_assignments.release_resident_slot_assignment(
        db,
        user_id=user.id,
        character_id=character.id,
        commit=False,
    )
    current_setting.auto_enabled = False
    workflows.set_world_autonomy(
        db,
        character_id=character.id,
        enabled=False,
    )
    workflows.set_character_status(character, status="inactive")
    db.commit()
    activity_logs.log_activity(
        db,
        user_id=user.id,
        character_id=character.id,
        action_type="deactivated",
        target_post_id=None,
        reason="user_disabled_autonomy",
        result="OpenClaw slot assignment was released.",
    )
    db.refresh(character)
    return workflows.build_detail(db, character)


def _reject_server_llm_autonomy_capacity(
    *,
    active_count: int,
    max_active: int,
) -> None:
    raise AgentAutonomyCapacityError(
        SERVER_LLM_AUTONOMY_CAPACITY_ERROR_MESSAGE,
        reason_code="global_autonomy_capacity_full",
        active_count=active_count,
        max_active=max_active,
    )


def _reject_world_autonomy_capacity(
    *,
    active_count: int,
    max_active: int,
) -> None:
    raise AgentAutonomyCapacityError(
        WORLD_AUTONOMY_CAPACITY_ERROR_MESSAGE,
        reason_code="world_autonomy_capacity_full",
        active_count=active_count,
        max_active=max_active,
    )


def _log_autonomy_activation_rejection(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    error: AgentAutonomyCapacityError,
) -> None:
    activity_logs.log_activity(
        db,
        user_id=user_id,
        character_id=character_id,
        action_type="autonomy_activation_rejected",
        target_post_id=None,
        reason=error.reason_code,
        result=(
            f"active_count={error.active_count}; max_active={error.max_active}"
        ),
    )


def _ensure_activity_profile_ready(
    db: Session,
    *,
    character: ActivityCharacter,
    setting: models.AgentActivitySetting,
    workflows: AutonomyWorkflows[DetailT],
) -> ActivityReadiness:
    readiness = workflows.evaluate_readiness(
        db,
        character=character,
        setting=setting,
    )
    if readiness.ready:
        return readiness
    if readiness.source == "world_community_profile":
        raise ActivityProfileRequiredError(
            "이 World의 활동 준비를 완료해주세요."
        )
    raise TendencyAnalysisRequiredError(
        "커뮤니티 성향 분석을 먼저 실행해주세요."
    )
