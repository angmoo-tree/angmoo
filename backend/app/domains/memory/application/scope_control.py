"""Use cases for opt-in memory scope settings."""

from app.domains.memory.domain.errors import MemoryConflictError
from app.domains.memory.domain.lifecycle import normalize_memory_idempotency_key
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

    def set_enabled(
        self,
        scope: MemoryScope,
        *,
        expected_version: int,
        enabled: bool,
        idempotency_key: str,
    ) -> tuple[MemoryScopeSetting, bool]:
        """Apply the explicit owner ON/OFF target with replay-safe versioning.

        A side-effect-free GET represents a missing row as version ``0``.  The
        first explicit mutation may therefore create the canonical default-OFF
        row before applying ON.  A transport replay that observes the exact
        requested target is returned as a no-op; any other stale version fails
        closed.
        """

        normalize_memory_idempotency_key(idempotency_key)
        self._repository.validate_scope(scope)
        current = self._repository.get_scope_setting(scope)
        if current is None:
            if expected_version != 0:
                raise MemoryConflictError("memory_scope_version_conflict")
            current = self._repository.get_or_create_scope_setting(scope)
            if not enabled:
                return current, True
            expected_version = current.version

        if current.version != expected_version:
            replay_version = expected_version + 1
            if expected_version == 0 and enabled:
                # The first ON request creates the canonical default-OFF row
                # (v1) and then applies the explicit target (v2).
                replay_version = 2
            if current.enabled is enabled and current.version == replay_version:
                return current, False
            raise MemoryConflictError("memory_scope_version_conflict")
        if current.enabled is enabled:
            return current, False
        updated = self._repository.update_scope_setting(
            scope,
            expected_version=current.version,
            enabled=enabled,
            retention_days=current.retention_days,
            provider_mode=current.provider_mode,
        )
        return updated, True


__all__ = ["MemoryScopeService"]
