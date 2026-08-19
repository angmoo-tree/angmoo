"""Transaction boundary shared by current and future canonical stores."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class UnitOfWorkPort(Protocol):
    def flush(self) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def refresh(self, entity: object) -> None: ...


__all__ = ["UnitOfWorkPort"]
