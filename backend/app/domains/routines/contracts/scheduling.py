"""Next-schedule resolution at the owned slot completion boundary."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from sqlalchemy.orm import Session
from app.domains.routines.models import AgentSlot
from app.domains.routines.service.tick_schedule import TickSchedule


@dataclass(frozen=True)
class ResolvedSchedule:
    tick: TickSchedule
    timezone_revision: int


class CompletionScheduleResolver(Protocol):
    owner_id: str
    character_id: str

    def resolve(self, db: Session, slot: AgentSlot, now: datetime) -> ResolvedSchedule | None: ...
