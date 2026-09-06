"""Lazy profile and activity reads preserve the caller Session and read order."""
from dataclasses import dataclass
from typing import Callable, Protocol
from sqlalchemy.orm import Session

class CharacterProfile(Protocol):
    id: str
    name: str
    handle: str
    avatar_url: str | None

class UserProfile(Protocol):
    id: str
    display_name: str

class CharacterActivityRead(Protocol):
    def __call__(self, db: Session, *, character_id: str) -> str: ...

class ActionCountRead(Protocol):
    def __call__(self, db: Session, *, character_id: str, action: str) -> int: ...

@dataclass(frozen=True)
class ActivityPresentationReads:
    get_character: Callable[[Session, str], CharacterProfile | None]
    get_user: Callable[[Session, str], UserProfile | None]
    activity_timezone_name: CharacterActivityRead
    count_action_today: ActionCountRead

class ImportedWorldLockRead(Protocol):
    def __call__(self, db: Session, *, character_id: str) -> bool: ...
