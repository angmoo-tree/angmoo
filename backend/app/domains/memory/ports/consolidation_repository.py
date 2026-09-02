"""Canonical persistence boundary for consolidation and hot briefs."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domains.memory.domain.consolidation import (
    MemoryHotBriefRecord,
    MemoryMaintenanceSnapshot,
)
from app.domains.memory.domain.lifecycle import MemoryItemRecord
from app.domains.memory.domain.scope import MemoryScopeSetting


class MemoryConsolidationRepositoryPort(Protocol):
    def get_scope_setting_by_id(
        self,
        scope_setting_id: str,
    ) -> MemoryScopeSetting | None: ...

    def maintenance_snapshot(
        self,
        *,
        scope_setting_id: str,
        now: datetime,
        candidate_limit: int,
    ) -> MemoryMaintenanceSnapshot: ...

    def hot_brief_source_items(
        self,
        *,
        setting: MemoryScopeSetting,
        now: datetime,
        limit: int,
    ) -> tuple[MemoryItemRecord, ...]: ...

    def replace_hot_brief(
        self,
        *,
        setting: MemoryScopeSetting,
        expected_source_items: tuple[MemoryItemRecord, ...],
        summary: str,
        contract_version: str,
        now: datetime,
    ) -> MemoryHotBriefRecord: ...


__all__ = ["MemoryConsolidationRepositoryPort"]
