from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domains.runtime.domain.diagnostic_codes import RuntimeDiagnosticCode


RUNTIME_STATUS_SCHEMA_VERSION = "local-runtime-status-v1"


class InstallationState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    RECOVERY_REQUIRED = "recovery_required"
    FAILED = "failed"


class RuntimeComponentState(StrEnum):
    RUNNING = "running"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    FAILED = "failed"
    NOT_AVAILABLE = "not_available"


class ProviderFailureClass(StrEnum):
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"
    SAFETY = "safety"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RuntimeDependencyStatus:
    name: str
    state: RuntimeComponentState
    required: bool = True
    reason_code: RuntimeDiagnosticCode | None = None


@dataclass(frozen=True)
class RuntimeComponentStatus:
    name: str
    state: RuntimeComponentState
    version: str | None = None
    started_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    reason_code: RuntimeDiagnosticCode | None = None
    dependencies: tuple[RuntimeDependencyStatus, ...] = ()


@dataclass(frozen=True)
class MigrationRuntimeStatus:
    state: RuntimeComponentState
    current_revision: str | None = None
    head_revision: str | None = None
    reason_code: RuntimeDiagnosticCode | None = None


@dataclass(frozen=True)
class SchedulerRuntimeStatus:
    state: RuntimeComponentState
    active_owner_id: str | None = None
    fencing_epoch: int | None = None
    last_heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    next_tick_at: datetime | None = None
    reason_code: RuntimeDiagnosticCode | None = None


@dataclass(frozen=True)
class ProjectorRuntimeStatus:
    state: RuntimeComponentState
    last_heartbeat_at: datetime | None = None
    lag_seconds: float | None = None
    pending_count: int = 0
    retry_count: int = 0
    failed_count: int = 0
    dead_letter_count: int = 0
    reason_code: RuntimeDiagnosticCode | None = None


@dataclass(frozen=True)
class ProviderUsageRuntimeStatus:
    recent_call_count: int = 0
    recent_failure_class: ProviderFailureClass | None = None
    kill_switch_enabled: bool = False


@dataclass(frozen=True)
class RuntimeCapabilityStatus:
    name: str
    state: RuntimeComponentState
    reason_code: RuntimeDiagnosticCode | None = None


@dataclass(frozen=True)
class ApplicationRuntimeStatus:
    installation_state: InstallationState
    version: str
    components: tuple[RuntimeComponentStatus, ...]
    migration: MigrationRuntimeStatus
    scheduler: SchedulerRuntimeStatus
    projector: ProjectorRuntimeStatus
    provider_usage: ProviderUsageRuntimeStatus
    capabilities: tuple[RuntimeCapabilityStatus, ...] = ()
