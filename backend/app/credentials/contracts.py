from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class CredentialPurpose(StrEnum):
    RESIDENT_LLM = "resident_llm"
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
