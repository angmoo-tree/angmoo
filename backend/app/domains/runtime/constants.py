from __future__ import annotations

from datetime import timedelta

from enum import StrEnum


class RuntimeDiagnosticCode(StrEnum):
    """Stable, content-free reason codes shared by status and doctor."""

    DOCKER_ENGINE_UNAVAILABLE = "docker_engine_unavailable"
    APPLICATION_STATUS_UNAVAILABLE = "application_status_unavailable"
    DOCKER_USAGE_UNAVAILABLE = "docker_usage_unavailable"
    COMPOSE_CONFIG_INVALID = "compose_config_invalid"
    HOST_PORT_CONFLICT = "host_port_conflict"
    RUNTIME_DISK_SPACE_LOW = "runtime_disk_space_low"
    RUNTIME_START_TIMEOUT = "runtime_start_timeout"
    MIGRATION_NOT_CURRENT = "migration_not_current"
    CREDENTIAL_RECOVERY_REQUIRED = "credential_recovery_required"
    SCHEDULER_LEASE_HELD = "scheduler_lease_held"
    SCHEDULER_LEASE_LOST = "scheduler_lease_lost"
    SCHEDULER_HEARTBEAT_STALE = "scheduler_heartbeat_stale"
    SCHEDULER_DUPLICATE_ACTIVE = "scheduler_duplicate_active"
    TEMPORARY_SLOT_UNAVAILABLE = "temporary_slot_unavailable"
    TEMPORARY_SLOT_RELEASE_FAILED = "temporary_slot_release_failed"
    PROJECTOR_STALLED = "projector_stalled"
    GRAPH_DEGRADED = "graph_degraded"
    DIAGNOSTIC_REDACTION_FAILED = "diagnostic_redaction_failed"

SCHEDULER_SINGLETON_KEY = "resident-tick-scheduler"

# Match the shipped SQLite manifest and Alembic graph. A real-database
# diagnostic regression checks this contract whenever the schema advances.
RUNTIME_MIGRATION_HEAD = "20260904_0089"
RECENT_PROVIDER_WINDOW = timedelta(hours=1)
