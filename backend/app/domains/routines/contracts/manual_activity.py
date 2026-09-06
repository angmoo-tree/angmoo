"""Same-session owner lookups and IO used by an explicit manual activity request."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol
from sqlalchemy.orm import Session
from app.domains.routines import models, schemas
from app.domains.routines.contracts.activity_management import ActivityOwner, ActivityCharacter
from app.domains.routines.contracts.autonomy_management import AutonomyCredential, ProfileBind, ProfileRelease, ActivityReadiness

class ImportedWorldGuard(Protocol):
    def __call__(self, db: Session, *, character: ActivityCharacter) -> None: ...

class ManualReadiness(Protocol):
    def __call__(self, db: Session, *, character: ActivityCharacter, setting: models.AgentActivitySetting) -> ActivityReadiness: ...

class AssignedRun(Protocol):
    def __call__(self, db: Session, *, user_id: str, character_id: str, message: str, require_public_action: bool, enforce_activity_policy: bool) -> Awaitable[schemas.OpenClawAgentRunRead]: ...

class TemporaryClaim(Protocol):
    def __call__(self, db: Session, *, user_id: str, character_id: str, credential_id: str, heartbeat_interval_seconds: int, timeout_seconds: int) -> models.AgentSlot: ...

class TemporaryRun(Protocol):
    def __call__(self, db: Session, *, agent_id: str, user_id: str, character_id: str, credential_id: str, timeout_seconds: int, message: str, require_public_action: bool, enforce_activity_policy: bool) -> Awaitable[schemas.OpenClawAgentRunRead]: ...

class TemporaryRelease(Protocol):
    def __call__(self, db: Session, *, agent_id: str, user_id: str, character_id: str, credential_id: str) -> None: ...

@dataclass(frozen=True)
class ManualActivityWorkflows:
    get_owned_character: Callable[[Session, ActivityOwner, str], ActivityCharacter]
    ensure_not_suspended: Callable[[ActivityCharacter], None]
    is_owner_controlled_character: Callable[[Session, str], bool]
    ensure_llm_mode: Callable[[ActivityCharacter], None]
    ensure_imported_world_runtime_enabled: ImportedWorldGuard
    ensure_run_now_available: Callable[[Session], None]
    _ensure_activity_profile_ready: ManualReadiness
    get_credential: Callable[[Session, str], AutonomyCredential | None]
    run_assigned_slot: AssignedRun
    claim_temporary_slot: TemporaryClaim
    sync_enabled: Callable[[], bool]
    bind_profile: ProfileBind
    reload_secrets: Callable[[], None]
    run_temporary_slot: TemporaryRun
    release_profile: ProfileRelease
    release_temporary_slot: TemporaryRelease
    execution_mode_error: type[Exception]
    credential_required_error: type[Exception]
