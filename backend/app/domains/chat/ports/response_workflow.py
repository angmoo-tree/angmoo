"""Unit-of-work checkpoint used by the streaming response workflow."""

from __future__ import annotations

from typing import Protocol


class ResponseWorkflowUnitOfWorkPort(Protocol):
    def checkpoint(self) -> None: ...

    def rollback(self) -> None: ...


__all__ = ["ResponseWorkflowUnitOfWorkPort"]
