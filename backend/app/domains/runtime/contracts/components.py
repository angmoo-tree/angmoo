from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from app.domains.runtime.constants import RuntimeDiagnosticCode
from app.domains.runtime.contracts.status import RuntimeComponentState


class ComponentMode(Protocol):
    LOCAL_RUNTIME_COMPONENT_MODE: str


@dataclass(frozen=True)
class ComponentObservation:
    name: str
    state: RuntimeComponentState
    started_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    reason_code: RuntimeDiagnosticCode | None = None
