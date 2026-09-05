"""Original elapsed-plan join and owner records on the caller's Session."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines.models import DailyActivityPlanItem
from app.domains.world_characters.models import WorldCharacter
from app.domains.worlds.models import WorldMembership


class SqlAlchemyLifecycleReferences:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_world_character(self, world_character_id: str) -> WorldCharacter | None:
        return self._db.get(WorldCharacter, world_character_id)

    def get_membership(self, membership_id: str) -> WorldMembership | None:
        return self._db.get(WorldMembership, membership_id)

    def elapsed_autonomous_world_character_ids(self, *, now: datetime) -> list[str]:
        return list(self._db.scalars(
            select(DailyActivityPlanItem.world_character_id)
            .join(
                WorldCharacter,
                WorldCharacter.id == DailyActivityPlanItem.world_character_id,
            )
            .where(
                DailyActivityPlanItem.scheduled_end_at <= now,
                DailyActivityPlanItem.status.in_({"planned", "active"}),
                WorldCharacter.control_mode == "autonomous",
            )
            .distinct()
        ))
