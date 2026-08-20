from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import threading
from typing import Protocol

from app.domains.runtime.domain.diagnostic_codes import RuntimeDiagnosticCode
from app.domains.runtime.domain.installation_state import (
    ApplicationRuntimeStatus,
    InstallationState,
    RuntimeComponentState,
    RuntimeComponentStatus,
    RuntimeDependencyStatus,
)


class ComponentMode(Protocol):
    LOCAL_RUNTIME_COMPONENT_MODE: str


@dataclass(frozen=True)
class ComponentObservation:
    name: str
    state: RuntimeComponentState
    started_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    reason_code: RuntimeDiagnosticCode | None = None


class ComponentObservationRegistry:
    """Process-local, privacy-safe scheduler/projector observations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._observations: dict[str, ComponentObservation] = {}

    def update(
        self,
        name: str,
        state: RuntimeComponentState,
        *,
        reason_code: RuntimeDiagnosticCode | None = None,
    ) -> None:
        now = datetime.now(UTC)
        with self._lock:
            previous = self._observations.get(name)
            started_at = previous.started_at if previous is not None else None
            if state in {
                RuntimeComponentState.RUNNING,
                RuntimeComponentState.READY,
                RuntimeComponentState.DEGRADED,
            } and started_at is None:
                started_at = now
            self._observations[name] = ComponentObservation(
                name=name,
                state=state,
                started_at=started_at,
                last_heartbeat_at=now,
                reason_code=reason_code,
            )

    def snapshot(self) -> tuple[ComponentObservation, ...]:
        with self._lock:
            return tuple(
                self._observations[name]
                for name in sorted(self._observations)
            )

    def reset(self) -> None:
        with self._lock:
            self._observations.clear()


component_observations = ComponentObservationRegistry()


def overlay_in_process_component_status(
    status: ApplicationRuntimeStatus,
    *,
    config: ComponentMode,
    registry: ComponentObservationRegistry = component_observations,
) -> ApplicationRuntimeStatus:
    """Overlay bounded process observations on the canonical status read."""

    if config.LOCAL_RUNTIME_COMPONENT_MODE != "in_process":
        return status
    observations = {item.name: item for item in registry.snapshot()}
    component_statuses = list(status.components)
    for name in ("scheduler", "projector"):
        observation = observations.get(name)
        if observation is None:
            continue
        dependencies = (
            RuntimeDependencyStatus(
                name="canonical_database",
                state=RuntimeComponentState.READY,
            ),
        )
        if name == "projector":
            dependencies += (
                RuntimeDependencyStatus(
                    name="graph_projection",
                    state=(
                        RuntimeComponentState.DEGRADED
                        if observation.state
                        in {
                            RuntimeComponentState.DEGRADED,
                            RuntimeComponentState.FAILED,
                        }
                        else RuntimeComponentState.READY
                    ),
                    required=False,
                    reason_code=observation.reason_code,
                ),
            )
        component_statuses.append(
            RuntimeComponentStatus(
                name=name,
                state=observation.state,
                started_at=observation.started_at,
                last_heartbeat_at=observation.last_heartbeat_at,
                reason_code=observation.reason_code,
                dependencies=dependencies,
            )
        )

    scheduler = status.scheduler
    scheduler_observation = observations.get("scheduler")
    if scheduler_observation is not None and scheduler_observation.state in {
        RuntimeComponentState.DEGRADED,
        RuntimeComponentState.FAILED,
    }:
        scheduler = replace(
            scheduler,
            state=scheduler_observation.state,
            reason_code=scheduler_observation.reason_code,
        )
    projector = status.projector
    projector_observation = observations.get("projector")
    if projector_observation is not None and projector_observation.state in {
        RuntimeComponentState.DEGRADED,
        RuntimeComponentState.FAILED,
    }:
        projector = replace(
            projector,
            state=projector_observation.state,
            reason_code=projector_observation.reason_code,
        )
    installation_state = status.installation_state
    if any(
        item.state in {
            RuntimeComponentState.DEGRADED,
            RuntimeComponentState.FAILED,
        }
        for item in observations.values()
    ):
        installation_state = InstallationState.DEGRADED
    return replace(
        status,
        installation_state=installation_state,
        components=tuple(component_statuses),
        scheduler=scheduler,
        projector=projector,
    )


__all__ = [
    "ComponentObservation",
    "ComponentObservationRegistry",
    "component_observations",
    "overlay_in_process_component_status",
]
