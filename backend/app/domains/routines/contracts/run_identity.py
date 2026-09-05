"""Attached values needed to authorize an existing Resident run."""
from datetime import datetime
from typing import Protocol


class RunCharacter(Protocol):
    id: str
    owner_id: str
    deleted_at: datetime | None


class RunCredential(Protocol):
    id: str
    owner_id: str
    character_id: str | None
    enabled: bool


class RunIdentityReferences(Protocol):
    def get_character(self, character_id: str) -> RunCharacter | None: ...
    def get_credential(self, credential_id: str) -> RunCredential | None: ...
    def character_not_found(self, character_id: str) -> Exception: ...
