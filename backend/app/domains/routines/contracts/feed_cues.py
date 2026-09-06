"""Identity-only inputs; callers keep their original attached objects."""
from typing import Protocol


class FeedCueIdentity(Protocol):
    @property
    def id(self) -> str: ...


from dataclasses import dataclass
from typing import Callable
from sqlalchemy.orm import Session
from app.domains.routines.contracts.activity_management import ActivityOwner, ActivityCharacter
from app.domains.routines.contracts.activity_policy import ActivityPolicy
from app.domains.routines.contracts.manual_activity import ImportedWorldGuard

class FeedCuePolicy(Protocol):
    def __call__(self, db: Session, *, character_id: str, ignore_active_hours: bool) -> ActivityPolicy: ...

@dataclass(frozen=True)
class FeedCueWorkflows:
    get_owned_character: Callable[[Session, ActivityOwner, str], ActivityCharacter]
    ensure_not_suspended: Callable[[ActivityCharacter], None]
    ensure_llm_mode: Callable[[ActivityCharacter], None]
    ensure_imported_world_runtime_enabled: ImportedWorldGuard
    ensure_feed_cues_available: Callable[[Session], None]
    build_activity_policy: FeedCuePolicy
    prompt_injection_error: type[Exception]
