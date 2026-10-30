"""Owned runtime resources; cleanup callbacks are supplied by composition roots."""
from __future__ import annotations
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, Protocol
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from app.config import Settings
from app.domains.memory.service.recall import CanonicalRecallService
from app.runtime.configuration_contracts import RuntimeConfig

class StoppableProjection(Protocol):
    def stop(self) -> None: ...

# Implementations differ between SQLite compatibility and PostgreSQL; this
# resource holder does not import or instantiate either adapter.
EmbeddedSocialSearchProjection = StoppableProjection
EmbeddedMemoryRecallProjection = StoppableProjection
MemoryHybridRuntime = Any

@dataclass(frozen=True)
class RuntimeComposition:
    config: RuntimeConfig
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    social_search_projection: EmbeddedSocialSearchProjection
    memory_recall_projection: EmbeddedMemoryRecallProjection
    memory_recall_service: CanonicalRecallService
    memory_hybrid_runtime: MemoryHybridRuntime
    generation_use_pin: object | None = None
    checkpoint_store: object | None = None
    checkpoint_dispose: Callable[[], None] | None = field(default=None, repr=False, compare=False)

    def dispose(self, *, release_pin: bool = True) -> None:
        stop_error = None
        try:
            for projection in (self.memory_recall_projection, self.social_search_projection):
                try:
                    projection.stop()
                except BaseException as exc:
                    stop_error = stop_error or exc
        finally:
            if self.checkpoint_dispose is not None:
                self.checkpoint_dispose()
            self.engine.dispose()
            if release_pin and stop_error is None and self.generation_use_pin is not None:
                self.generation_use_pin.close()
        if stop_error is not None:
            raise stop_error
