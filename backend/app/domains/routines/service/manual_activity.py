"""Manual run admission, scheduler headroom and original cleanup precedence."""
from __future__ import annotations
from datetime import UTC, datetime
from sqlalchemy.orm import Session
from app.config import settings
from app.domains.routines import models, schemas
from app.domains.routines import constants as routine_constants
from app.domains.routines.constants import RUN_NOW_COOLDOWN, RUN_NOW_SCHEDULER_GUARD_WINDOW, RUN_NOW_SCHEDULER_HEADROOM
from app.domains.routines.contracts.activity_management import ActivityOwner
from app.domains.routines.contracts.manual_activity import ManualActivityWorkflows
from app.domains.routines.contracts.execution_errors import AgentSlotUnavailableError
from app.domains.routines.exceptions import RunNowCooldownError, RunNowSlotBusyError, RunNowSlotUnavailableError, RunNowSchedulerBusyError, RunNowSoonScheduledError
from app.domains.routines.repository import slots as slot_queries, runs as routine_run_queries
from app.domains.routines.service import activity_settings
from app.domains.routines.service.tick_schedule import aware_utc as _aware_utc, tick_interval_seconds

def _slot_has_live_lease(slot: models.AgentSlot, now: datetime) -> bool:
    lease_expires_at = slot.lease_expires_at
    if lease_expires_at is None:
        return False
    return _aware_utc(lease_expires_at) > now


def _slot_is_live_running(slot: models.AgentSlot, now: datetime) -> bool:
    return (
        slot.status == routine_constants.SLOT_STATUS_RUNNING
        and _slot_has_live_lease(slot, now)
    )


def _slot_is_assigned_resident(slot: models.AgentSlot) -> bool:
    return (
        slot.assigned_user_id is not None
        and slot.assigned_character_id is not None
        and slot.assigned_credential_id is not None
    )


def _allowed_existing_running_resident_slots() -> int:
    if settings.resident_tick_single_flight_enabled:
        return 0
    return max(0, settings.resident_tick_max_runs - RUN_NOW_SCHEDULER_HEADROOM - 1)


def _slot_is_due(slot: models.AgentSlot, now: datetime) -> bool:
    if slot.next_tick_at is None:
        return False
    return _aware_utc(slot.next_tick_at) <= now


def _slot_is_imminent(slot: models.AgentSlot, now: datetime) -> bool:
    if slot.next_tick_at is None:
        return False
    return _aware_utc(slot.next_tick_at) <= now + RUN_NOW_SCHEDULER_GUARD_WINDOW


def _ensure_run_now_scheduler_safe(
    db: Session,
    *,
    target_slot: models.AgentSlot,
    setting: models.AgentActivitySetting,
    now: datetime,
) -> None:
    if _slot_is_live_running(target_slot, now):
        raise RunNowSlotBusyError()
    if setting.auto_enabled and _slot_is_imminent(target_slot, now) and not _slot_is_due(
        target_slot, now
    ):
        raise RunNowSoonScheduledError()

    live_running_count = sum(
        1
        for slot in slot_queries.list_agent_slots(db)
        if _slot_is_assigned_resident(slot) and _slot_is_live_running(slot, now)
    )
    if live_running_count > _allowed_existing_running_resident_slots():
        raise RunNowSchedulerBusyError()


def _ensure_claimed_temporary_run_now_scheduler_safe(
    db: Session,
    *,
    target_slot: models.AgentSlot,
    now: datetime,
) -> None:
    live_other_running_count = sum(
        1
        for slot in slot_queries.list_agent_slots(db)
        if slot.agent_id != target_slot.agent_id
        and _slot_is_assigned_resident(slot)
        and _slot_is_live_running(slot, now)
    )
    if live_other_running_count > _allowed_existing_running_resident_slots():
        raise RunNowSchedulerBusyError()


def _manual_run_available_at(db: Session, user_id: str) -> datetime | None:
    latest_manual_run = routine_run_queries.get_latest_manual_run_for_user(db, user_id)
    if latest_manual_run is None:
        return None
    created_at = latest_manual_run.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at + RUN_NOW_COOLDOWN


async def run_agent_now(
    db: Session, user: ActivityOwner, character_id: str,
    *, workflows: ManualActivityWorkflows,
) -> schemas.OpenClawAgentRunRead:
    character = workflows.get_owned_character(db, user, character_id)
    workflows.ensure_not_suspended(character)
    if workflows.is_owner_controlled_character(db, character.id):
        raise workflows.execution_mode_error("owner_controlled_manual_write_not_available")
    workflows.ensure_llm_mode(character)
    workflows.ensure_imported_world_runtime_enabled(db, character=character)
    workflows.ensure_run_now_available(db)
    setting = activity_settings.ensure_setting(db, character.id)
    workflows._ensure_activity_profile_ready(
        db,
        character=character,
        setting=setting,
    )
    available_at = _manual_run_available_at(db, user.id)
    if available_at is not None and available_at > datetime.now(UTC):
        raise RunNowCooldownError(available_at)
    credential = workflows.get_credential(db, character.id)
    if credential is None:
        raise workflows.credential_required_error("Agent credential is required before running")
    run_message = (
        "This is a user-clicked run-once test. Read the community, "
        "then perform one visible public action as this character: "
        "reply to an existing post, create a new post, repost a post, "
        "follow a profile, unfollow a profile, or like a relevant post. "
        "Do not only save mood/state. Save character state after the public action, "
        "then summarize what you did and why in Korean."
    )
    assigned_slot = slot_queries.get_assigned_slot(db, character.id)
    if assigned_slot is not None:
        _ensure_run_now_scheduler_safe(
            db,
            target_slot=assigned_slot,
            setting=setting,
            now=datetime.now(UTC),
        )
        return await workflows.run_assigned_slot(
            db,
            user_id=user.id,
            character_id=character.id,
            message=run_message,
            require_public_action=True,
            enforce_activity_policy=True,
        )

    timeout_seconds = settings.openclaw_timeout_seconds
    heartbeat_interval_seconds = tick_interval_seconds(setting)
    try:
        temporary_slot = workflows.claim_temporary_slot(
            db,
            user_id=user.id,
            character_id=character.id,
            credential_id=credential.id,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            timeout_seconds=timeout_seconds,
        )
    except AgentSlotUnavailableError as exc:
        raced_slot = slot_queries.get_assigned_slot(db, character.id)
        if raced_slot is not None and _slot_is_live_running(
            raced_slot, datetime.now(UTC)
        ):
            raise RunNowSlotBusyError() from exc
        raise RunNowSlotUnavailableError() from exc

    auth_profile_attempted = False
    primary_error: BaseException | None = None
    try:
        _ensure_claimed_temporary_run_now_scheduler_safe(
            db,
            target_slot=temporary_slot,
            now=datetime.now(UTC),
        )
        if workflows.sync_enabled():
            auth_profile_attempted = True
            workflows.bind_profile(
                schemas.AgentSlotRead.model_validate(temporary_slot),
                user_id=user.id,
                character=character,
                credential=credential,
            )
            workflows.reload_secrets()
        return await workflows.run_temporary_slot(
            db,
            agent_id=temporary_slot.agent_id,
            user_id=user.id,
            character_id=character.id,
            credential_id=credential.id,
            timeout_seconds=timeout_seconds,
            message=run_message,
            require_public_action=True,
            enforce_activity_policy=True,
        )
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        cleanup_error: Exception | None = None
        if auth_profile_attempted:
            try:
                workflows.release_profile(
                    temporary_slot,
                    user_id=user.id,
                    character_id=character.id,
                    credential=credential,
                )
                workflows.reload_secrets()
            except Exception as exc:
                cleanup_error = exc
        try:
            workflows.release_temporary_slot(
                db,
                agent_id=temporary_slot.agent_id,
                user_id=user.id,
                character_id=character.id,
                credential_id=credential.id,
            )
        except Exception as exc:
            if cleanup_error is None:
                cleanup_error = exc
        if cleanup_error is not None and primary_error is None:
            raise cleanup_error

