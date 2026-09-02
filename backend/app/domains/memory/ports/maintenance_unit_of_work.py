"""Commit owner used by the asynchronous Memory maintenance worker."""

from __future__ import annotations

from typing import Protocol


class MemoryMaintenanceUnitOfWorkPort(Protocol):
    def commit(self) -> None: ...

    def rollback(self) -> None: ...


__all__ = ["MemoryMaintenanceUnitOfWorkPort"]
