"""Use cases for opt-in memory scope settings."""

from app.domains.memory.domain.provenance import MemoryProviderMode
from app.domains.memory.domain.retention import validate_retention_days
from app.domains.memory.domain.scope import MemoryScope, MemoryScopeSetting
from app.domains.memory.ports.repository import MemoryRepositoryPort


class MemoryScopeService:
    def __init__(self, repository: MemoryRepositoryPort) -> None:
        self._repository = repository

    def get_or_create(self, scope: MemoryScope) -> MemoryScopeSetting:
        """Create the first setting as OFF; no implicit opt-in is permitted."""

        return self._repository.get_or_create_scope_setting(scope)

    def update(
        self,
        scope: MemoryScope,
        *,
        expected_version: int,
        enabled: bool,
        retention_days: int,
        provider_mode: MemoryProviderMode = MemoryProviderMode.NONE,
    ) -> MemoryScopeSetting:
        validate_retention_days(retention_days)
        return self._repository.update_scope_setting(
            scope,
            expected_version=expected_version,
            enabled=enabled,
            retention_days=retention_days,
            provider_mode=provider_mode,
        )


__all__ = ["MemoryScopeService"]
