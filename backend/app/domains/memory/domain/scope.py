"""Owner + World + remembering-subject scope values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domains.memory.domain.errors import MemoryValidationError
from app.domains.memory.domain.provenance import MemoryProviderMode
from app.domains.memory.domain.retention import validate_retention_days


def _required_identifier(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 64:
        raise MemoryValidationError(f"memory_{field}_invalid")
    return normalized


@dataclass(frozen=True, slots=True)
class MemoryScope:
    owner_id: str
    world_id: str
    subject_world_character_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "owner_id", _required_identifier(self.owner_id, "owner"))
        object.__setattr__(self, "world_id", _required_identifier(self.world_id, "world"))
        object.__setattr__(
            self,
            "subject_world_character_id",
            _required_identifier(
                self.subject_world_character_id,
                "subject_world_character",
            ),
        )


@dataclass(frozen=True, slots=True)
class MemoryScopeSetting:
    id: str
    scope: MemoryScope
    enabled: bool
    retention_days: int
    provider_mode: MemoryProviderMode
    version: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _required_identifier(self.id, "scope_setting")
        validate_retention_days(self.retention_days)
        if self.version < 1:
            raise MemoryValidationError("memory_scope_version_invalid")


__all__ = ["MemoryScope", "MemoryScopeSetting"]
