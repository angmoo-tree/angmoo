from dataclasses import dataclass
from typing import Protocol
from sqlalchemy.orm import Session


class LocalKeyOwner(Protocol):
    id: str


class LocalKeyCharacter(Protocol):
    id: str
    execution_mode: str


class LocalKeyActivityLog(Protocol):
    def __call__(self, db: Session, *, user_id: str, character_id: str,
                 action_type: str, target_post_id: str | None, reason: str,
                 result: str) -> object: ...


@dataclass(frozen=True)
class LocalKeyWorkflows:
    """Activity logging after the original LocalBot key commit."""

    log_activity: LocalKeyActivityLog
