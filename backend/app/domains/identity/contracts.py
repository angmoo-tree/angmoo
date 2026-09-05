from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.domains.identity.models import User


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
