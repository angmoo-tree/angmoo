"""Same-session ownership and IO needed by autonomy activation/deactivation."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Generic, Protocol, TypeVar
from sqlalchemy.orm import Session
from app.domains.routines import models, schemas
from app.domains.routines.contracts.activity_management import ActivityOwner, ActivityCharacter

DetailT = TypeVar("DetailT")

class AutonomyCredential(Protocol):
    id: str
    enabled: bool

class SelectedWorldCharacter(Protocol):
    world_id: str
    autonomous_enabled: bool

class ActivityReadiness(Protocol):
    ready: bool
    source: str
    world_id: str | None

class ReadinessEvaluator(Protocol):
    def __call__(self, db: Session, *, character: ActivityCharacter, setting: models.AgentActivitySetting) -> ActivityReadiness: ...

class WorldCharacterSelector(Protocol):
    def __call__(self, db: Session, *, character_id: str) -> SelectedWorldCharacter | None: ...

class WorldCapacityLock(Protocol):
    def __call__(self, db: Session, *, world_id: str) -> None: ...

class WorldAutonomyCount(Protocol):
    def __call__(self, db: Session, *, world_id: str, exclude_character_ids: set[str] | None = None) -> int: ...

class EffectiveAutonomyCount(Protocol):
    def __call__(self, db: Session, *, exclude_character_ids: set[str] | None = None) -> int: ...

class WorldAutonomyWrite(Protocol):
    def __call__(self, db: Session, *, character_id: str, enabled: bool) -> bool: ...

class CharacterStatusWrite(Protocol):
    def __call__(self, character: ActivityCharacter, *, status: str) -> None: ...

class ResidentAssignment(Protocol):
    def __call__(self, db: Session, *, user_id: str, character_id: str, credential_id: str, heartbeat_interval_seconds: int, commit: bool) -> schemas.AgentSlotRead: ...

class ProfileBind(Protocol):
    def __call__(self, slot: models.AgentSlot | schemas.AgentSlotRead, *, user_id: str, character: ActivityCharacter, credential: AutonomyCredential) -> None: ...

class ProfileRelease(Protocol):
    def __call__(self, slot: models.AgentSlot | schemas.AgentSlotRead, *, user_id: str, character_id: str, credential: AutonomyCredential) -> None: ...

@dataclass(frozen=True)
class AutonomyWorkflows(Generic[DetailT]):
    get_user: Callable[[Session, str], ActivityOwner | None]
    get_character: Callable[[Session, str], ActivityCharacter | None]
    get_owned_character: Callable[[Session, ActivityOwner, str], ActivityCharacter]
    ensure_not_suspended: Callable[[ActivityCharacter], None]
    ensure_llm_mode: Callable[[ActivityCharacter], None]
    ensure_auto_ticks_available: Callable[[Session], None]
    evaluate_readiness: ReadinessEvaluator
    get_credential: Callable[[Session, str], AutonomyCredential | None]
    select_world_character: WorldCharacterSelector
    lock_world_capacity: WorldCapacityLock
    count_world_autonomy: WorldAutonomyCount
    count_effective_agents: EffectiveAutonomyCount
    set_world_autonomy: WorldAutonomyWrite
    set_character_status: CharacterStatusWrite
    assign_slot: ResidentAssignment
    sync_enabled: Callable[[], bool]
    bind_profile: ProfileBind
    release_profile: ProfileRelease
    reload_secrets: Callable[[], None]
    build_detail: Callable[[Session, ActivityCharacter], DetailT]
    character_not_found_error: type[Exception]
    credential_required_error: type[Exception]
    credential_sync_error: type[Exception]
    slot_busy_error: type[Exception]
    social_character_not_found_error: type[Exception]
