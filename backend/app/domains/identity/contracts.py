from __future__ import annotations

from dataclasses import dataclass

from dataclasses import field

from datetime import datetime

from enum import StrEnum

from typing import Literal

from typing import Protocol

from typing import TYPE_CHECKING

from typing import Callable

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.domains.identity.models import User, LlmCredential

class CredentialPurpose(StrEnum):
    RESIDENT_LLM = "resident_llm"
    WORLD_CHARACTER_SETUP_LLM = "world_character_setup_llm"
    CREATION_DRAFT_LLM = "creation_draft_llm"
    MESSAGE_LLM = "message_llm"
    LORE_EMBEDDING = "lore_embedding"
    USER_IMAGE = "user_image"
    SERVICE_IMAGE = "service_image"
    PRIVATE_OPENCLAW = "private_openclaw"

@dataclass(frozen=True, repr=False)
class CredentialMaterial:
    credential_id: str
    provider: str
    model: str
    fingerprint: str | None
    purpose: CredentialPurpose
    _secret: str = field(repr=False)

    def reveal(self) -> str:
        return self._secret

    def __repr__(self) -> str:
        return (
            "CredentialMaterial("
            f"credential_id={self.credential_id!r}, "
            f"provider={self.provider!r}, "
            f"model={self.model!r}, "
            f"fingerprint={self.fingerprint!r}, "
            f"purpose={self.purpose!r}, secret=[REDACTED])"
        )

    __str__ = __repr__

BootstrapState = Literal["unclaimed", "claimed", "recovery_required"]

@dataclass(frozen=True)
class LocalOwnerCandidate:
    user_id: str
    display_name: str
    character_count: int
    world_count: int
    credential_count: int

    @property
    def activity_count(self) -> int:
        return self.character_count + self.world_count + self.credential_count

@dataclass(frozen=True)
class LocalUserSnapshot:
    user_id: str
    email: str | None
    display_name: str
    profile_setup_completed: bool
    feed_content_filter: str
    is_admin: bool

@dataclass(frozen=True)
class LocalBootstrapStatus:
    state: BootstrapState
    installation_id: str | None
    local_label: str | None
    owner: LocalUserSnapshot | None
    candidates: tuple[LocalOwnerCandidate, ...]

@dataclass(frozen=True)
class IssuedBootstrapChallenge:
    token: str
    expires_at: datetime

@dataclass(frozen=True)
class IssuedLocalSession:
    token: str
    expires_at: datetime
    user: LocalUserSnapshot

class AccountDeletionWorkflow(Protocol):
    """An application-provided multi-domain transaction using the caller session."""

    def __call__(self, db: Session, user: User) -> None: ...

class CredentialCharacter(Protocol):
    """Character identity required to label and scope its stored credential."""

    id: str
    name: str

class CredentialSlot(Protocol):
    status: str

class CharacterCredentialUpsert(Protocol):
    def __call__(self, db: Session, *, user: User, character: CredentialCharacter, provider: str, model: str, api_key: str, auth_profile_id: str | None, label: str | None, commit: bool) -> LlmCredential: ...

class CredentialProfileBind(Protocol):
    def __call__(self, slot: CredentialSlot, *, user_id: str, character: CredentialCharacter, credential: LlmCredential) -> None: ...

class CredentialProfileRelease(Protocol):
    def __call__(self, slot: CredentialSlot, *, user_id: str, character_id: str, credential: LlmCredential) -> None: ...

class CredentialSlotRelease(Protocol):
    def __call__(self, db: Session, *, user_id: str, character_id: str, commit: bool) -> object: ...

class CredentialWorldAutonomyWrite(Protocol):
    def __call__(self, db: Session, *, character_id: str, enabled: bool) -> bool: ...

class CredentialCharacterStatusWrite(Protocol):
    def __call__(self, character: CredentialCharacter, *, status: str) -> None: ...

class CredentialActivityLog(Protocol):
    def __call__(self, db: Session, *, user_id: str, character_id: str, action_type: str, target_post_id: str | None, reason: str, result: str) -> object: ...

@dataclass(frozen=True)
class CharacterCredentialWorkflows:
    get_owned_character: Callable[[Session, User, str], CredentialCharacter]
    ensure_mutable: Callable[[User], None]
    ensure_llm_mode: Callable[[CredentialCharacter], None]
    get_membership_id: Callable[[Session, str, str], str | None]
    get_world_character_id: Callable[[Session, str, str, str], str | None]
    get_assigned_slot: Callable[[Session, str], CredentialSlot | None]
    running_slot_status: str
    upsert_credential: CharacterCredentialUpsert
    get_credential: Callable[[Session, str], LlmCredential | None]
    sync_enabled: Callable[[], bool]
    slot_read: Callable[[CredentialSlot], CredentialSlot]
    bind_profile: CredentialProfileBind
    release_profile: CredentialProfileRelease
    reload_secrets: Callable[[], None]
    release_slot: CredentialSlotRelease
    disable_auto: Callable[[Session, str], None]
    set_world_autonomy: CredentialWorldAutonomyWrite
    set_character_status: CredentialCharacterStatusWrite
    log_activity: CredentialActivityLog
    character_not_found_error: type[Exception]
    slot_busy_error: type[Exception]
    credential_required_error: type[Exception]
