"""Explicit same-transaction collaboration for a saved World schedule change."""
from typing import Protocol
from sqlalchemy.orm import Session


SCHEDULE_FIELDS = ("active_hours_start", "active_hours_end", "activity_interval_minutes")


class ActivityScheduleUpdater(Protocol):
    def refresh(self, db: Session, *, owner_id: str, world_id: str,
                world_character_id: str, character_id: str) -> str: ...
