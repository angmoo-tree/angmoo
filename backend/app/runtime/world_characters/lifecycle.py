"""Runtime composition of scheduler state and the WC leave guard contract."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import models
from app.domains.world_characters import models as wc_models
from app.domains.world_characters import exceptions as world_character_setup


class WorldCharacterLeaveRuntimeGuard:
    """Read scheduler/setup busy state in the leave caller transaction."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def require_idle(
        self,
        *,
        owner_user_id: str,
        character_id: str,
        world_character_id: str,
        selected_active_world: bool,
    ) -> None:
        setup_running = self.db.scalar(
            select(wc_models.WorldCharacterSetupAttempt.id)
            .where(
                wc_models.WorldCharacterSetupAttempt.world_character_id
                == world_character_id,
                wc_models.WorldCharacterSetupAttempt.status == "running",
            )
            .limit(1)
        )
        if setup_running is not None:
            raise world_character_setup.StudioWorldCharacterBusyError(
                "world_character_setup_in_progress"
            )
        if not selected_active_world:
            return

        active_run = self.db.scalar(
            select(models.AgentRun.id)
            .where(
                models.AgentRun.user_id == owner_user_id,
                models.AgentRun.character_id == character_id,
                models.AgentRun.status == "running",
            )
            .limit(1)
        )
        if active_run is not None:
            raise world_character_setup.StudioWorldCharacterBusyError(
                "world_character_run_in_progress"
            )
        assigned_slot = self.db.scalar(
            select(models.AgentSlot.agent_id)
            .where(
                models.AgentSlot.assigned_user_id == owner_user_id,
                models.AgentSlot.assigned_character_id == character_id,
            )
            .limit(1)
        )
        if assigned_slot is not None:
            raise world_character_setup.StudioWorldCharacterBusyError(
                "scheduler_assignment_active"
            )
        setting = self.db.get(models.AgentActivitySetting, character_id)
        if setting is not None and setting.auto_enabled:
            raise world_character_setup.StudioWorldCharacterConflictError(
                "world_character_autonomy_enabled"
            )
