"""Inputs and runtime reader factory used by the owner diagnostics endpoint."""
from __future__ import annotations
from typing import Protocol
from sqlalchemy.orm import Session
from app.config import Settings
from app.domains.runtime.contracts.status_reader import ApplicationRuntimeProbe

class RuntimeOwner(Protocol):
    id: str

class RuntimeStatusReaderFactory(Protocol):
    def __call__(self, db: Session, *, config: Settings = ...) -> ApplicationRuntimeProbe: ...
