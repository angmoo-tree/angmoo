"""Canonical repository boundary for scope control and later lifecycle work."""

from __future__ import annotations

from typing import Protocol

from app.domains.memory.domain.provenance import MemoryProviderMode
from app.domains.memory.domain.scope import MemoryScope, MemoryScopeSetting


class MemoryRepositoryPort(Protocol):
    def get_scope_setting(self, scope: MemoryScope) -> MemoryScopeSetting | None: ...

    def get_or_create_scope_setting(
        self,
        scope: MemoryScope,
    ) -> MemoryScopeSetting: ...

    def update_scope_setting(
        self,
        scope: MemoryScope,
        *,
        expected_version: int,
        enabled: bool,
        retention_days: int,
        provider_mode: MemoryProviderMode,
    ) -> MemoryScopeSetting: ...


__all__ = ["MemoryRepositoryPort"]
