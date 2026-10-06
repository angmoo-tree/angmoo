"""Explicit World target validated before the existing Routine manual admission."""
from app.domains.identity.service.environment import lock_environment_admission
from app.domains.world_characters.service.management import WorldManagementError


async def run_world_character_now(service, *, world_id, world_character_id, user, data, workflows):
    db = service.db
    lock_environment_admission(db, user.id)
    role, _ = service._owned_role(world_id=world_id, world_character_id=world_character_id, user=user)
    if role.version != data.expected_revision:
        db.rollback()
        raise WorldManagementError("world_character_revision_conflict")
    if role.control_mode != "autonomous":
        db.rollback()
        raise WorldManagementError("owner_controlled_activity_not_available", 403)
    service.references.ensure_ready(db, character_id=role.character_id, world_id=world_id, user=user)
    character_id, revision = role.character_id, role.version
    from app.domains.routines.service.manual_activity import run_agent_now
    from app.domains.routines import exceptions as run_errors
    from app.domains.characters import exceptions as character_errors
    try:
        run = await run_agent_now(db, user, character_id, workflows=workflows, scoped_world_id=world_id)
    except run_errors.RunNowCooldownError as exc:
        raise WorldManagementError("world_run_now_cooldown", 429) from exc
    except (run_errors.RunNowSlotUnavailableError, run_errors.RunNowSlotBusyError,
            run_errors.RunNowSchedulerBusyError, run_errors.RunNowSoonScheduledError,
            run_errors.AgentSlotUnavailableError, run_errors.AgentSessionBusyError,
            run_errors.ActivityProfileRequiredError, run_errors.TendencyAnalysisRequiredError,
            character_errors.CredentialRequiredError, character_errors.AgentExecutionModeError) as exc:
        reason = {run_errors.RunNowSlotBusyError: "world_run_now_busy",
            run_errors.RunNowSlotUnavailableError: "world_run_now_capacity_unavailable",
            run_errors.RunNowSchedulerBusyError: "world_run_now_scheduler_busy",
            run_errors.RunNowSoonScheduledError: "world_run_now_scheduled"}.get(type(exc), "world_activity_not_ready")
        raise WorldManagementError(reason, 409) from exc
    except run_errors.OpenClawNotConfiguredError as exc:
        raise WorldManagementError("world_activity_runtime_unavailable", 503) from exc
    return {"contract_version": "world-character-run-now-v1", "world_id": world_id,
        "world_character_id": world_character_id, "character_id": character_id, "revision": revision, "run": run}
