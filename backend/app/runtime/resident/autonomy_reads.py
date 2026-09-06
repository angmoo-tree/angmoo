"""Original aggregate across Character identity and Routines assignment state."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.characters.models import Character
from app.domains.routines import models

def count_effective_active_server_llm_autonomy_agents(
    db: Session, *, exclude_character_ids: set[str] | None = None
) -> int:
    excluded = exclude_character_ids or set()
    auto_enabled_ids = set(
        db.scalars(
            select(Character.id)
            .join(models.AgentActivitySetting)
            .where(
                Character.execution_mode == "llm",
                Character.deleted_at.is_(None),
                Character.moderation_status != "suspended",
                models.AgentActivitySetting.auto_enabled.is_(True),
            )
        )
    )
    assigned_slot_ids = set(
        db.scalars(
            select(models.AgentSlot.assigned_character_id)
            .join(
                Character,
                Character.id == models.AgentSlot.assigned_character_id,
            )
            .where(
                models.AgentSlot.assigned_character_id.is_not(None),
                Character.execution_mode == "llm",
                Character.deleted_at.is_(None),
                Character.moderation_status != "suspended",
            )
        )
    )
    return len((auto_enabled_ids | assigned_slot_ids) - excluded)
