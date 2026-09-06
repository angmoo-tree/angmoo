from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from types import SimpleNamespace as _RuntimeTestNamespace
from app.domains.runtime.contracts.status import ActivityRuntimeStatus as _runtime_ActivityRuntimeStatus
from app.domains.runtime.contracts.status import ApplicationRuntimeStatus as _runtime_ApplicationRuntimeStatus
from app.domains.runtime.contracts.status import InstallationState as _runtime_InstallationState
from app.domains.runtime.schemas import LocalRuntimeStatusRead as _runtime_LocalRuntimeStatusRead
from app.domains.runtime.contracts.status import MigrationRuntimeStatus as _runtime_MigrationRuntimeStatus
from app.domains.runtime.contracts.status import OwnerRuntimeStatus as _runtime_OwnerRuntimeStatus
from app.domains.runtime.contracts.status import ProjectorRuntimeStatus as _runtime_ProjectorRuntimeStatus
from app.domains.runtime.contracts.status import ProviderFailureClass as _runtime_ProviderFailureClass
from app.domains.runtime.contracts.status import ProviderUsageRuntimeStatus as _runtime_ProviderUsageRuntimeStatus
from app.domains.runtime.service.status import ReadApplicationRuntimeStatus as _runtime_ReadApplicationRuntimeStatus
from app.domains.runtime.contracts.status import RuntimeCapabilityStatus as _runtime_RuntimeCapabilityStatus
from app.domains.runtime.contracts.status import RuntimeComponentState as _runtime_RuntimeComponentState
from app.domains.runtime.contracts.status import RuntimeComponentStatus as _runtime_RuntimeComponentStatus
from app.domains.runtime.contracts.status import RuntimeDependencyStatus as _runtime_RuntimeDependencyStatus
from app.domains.runtime.constants import RuntimeDiagnosticCode as _runtime_RuntimeDiagnosticCode
from app.domains.runtime.contracts.status import SchedulerRuntimeStatus as _runtime_SchedulerRuntimeStatus
from app.domains.runtime.schemas import runtime_status_read as _runtime_runtime_status_read

# Preserve the original test namespace with the same actual role objects.
runtime = _RuntimeTestNamespace(
    ActivityRuntimeStatus=_runtime_ActivityRuntimeStatus,
    ApplicationRuntimeStatus=_runtime_ApplicationRuntimeStatus,
    InstallationState=_runtime_InstallationState,
    LocalRuntimeStatusRead=_runtime_LocalRuntimeStatusRead,
    MigrationRuntimeStatus=_runtime_MigrationRuntimeStatus,
    OwnerRuntimeStatus=_runtime_OwnerRuntimeStatus,
    ProjectorRuntimeStatus=_runtime_ProjectorRuntimeStatus,
    ProviderFailureClass=_runtime_ProviderFailureClass,
    ProviderUsageRuntimeStatus=_runtime_ProviderUsageRuntimeStatus,
    ReadApplicationRuntimeStatus=_runtime_ReadApplicationRuntimeStatus,
    RuntimeCapabilityStatus=_runtime_RuntimeCapabilityStatus,
    RuntimeComponentState=_runtime_RuntimeComponentState,
    RuntimeComponentStatus=_runtime_RuntimeComponentStatus,
    RuntimeDependencyStatus=_runtime_RuntimeDependencyStatus,
    RuntimeDiagnosticCode=_runtime_RuntimeDiagnosticCode,
    SchedulerRuntimeStatus=_runtime_SchedulerRuntimeStatus,
    runtime_status_read=_runtime_runtime_status_read,
)


class FakeApplicationRuntimeProbe:
    def __init__(self, status: runtime.ApplicationRuntimeStatus) -> None:
        self.status = status
        self.read_count = 0

    def read_status(self) -> runtime.ApplicationRuntimeStatus:
        self.read_count += 1
        return self.status


def _status() -> runtime.ApplicationRuntimeStatus:
    now = datetime(2026, 8, 16, 2, 0, tzinfo=UTC)
    return runtime.ApplicationRuntimeStatus(
        installation_state=runtime.InstallationState.DEGRADED,
        version="0.2.0",
        components=(
            runtime.RuntimeComponentStatus(
                name="backend",
                state=runtime.RuntimeComponentState.READY,
                version="0.2.0",
                started_at=now - timedelta(minutes=10),
                last_heartbeat_at=now,
                dependencies=(
                    runtime.RuntimeDependencyStatus(
                        name="postgresql",
                        state=runtime.RuntimeComponentState.READY,
                    ),
                ),
            ),
            runtime.RuntimeComponentStatus(
                name="neo4j",
                state=runtime.RuntimeComponentState.DEGRADED,
                reason_code=runtime.RuntimeDiagnosticCode.GRAPH_DEGRADED,
            ),
        ),
        migration=runtime.MigrationRuntimeStatus(
            state=runtime.RuntimeComponentState.READY,
            current_revision="0080",
            head_revision="0080",
        ),
        scheduler=runtime.SchedulerRuntimeStatus(
            state=runtime.RuntimeComponentState.RUNNING,
            active_owner_id="opaque-scheduler-owner",
            fencing_epoch=4,
            last_heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=30),
            next_tick_at=now + timedelta(minutes=1),
        ),
        projector=runtime.ProjectorRuntimeStatus(
            state=runtime.RuntimeComponentState.DEGRADED,
            last_heartbeat_at=now,
            lag_seconds=4.5,
            pending_count=2,
            retry_count=1,
            reason_code=runtime.RuntimeDiagnosticCode.GRAPH_DEGRADED,
        ),
        provider_usage=runtime.ProviderUsageRuntimeStatus(
            recent_call_count=0,
            recent_failure_class=runtime.ProviderFailureClass.TIMEOUT,
            kill_switch_enabled=False,
        ),
        owner=runtime.OwnerRuntimeStatus(
            bootstrap_state="claimed",
            owner_user_id="opaque-owner",
            registered_world_count=2,
            active_world_count=1,
            active_world_character_count=3,
        ),
        activity=runtime.ActivityRuntimeStatus(
            last_successful_run_id="opaque-run",
            last_successful_post_id="opaque-post",
            last_successful_beat_id="opaque-beat",
            last_successful_episode_id="opaque-episode",
            last_successful_at=now,
            inbox_result_code="no_action",
            feed_result_code="comment_created",
        ),
        capabilities=(
            runtime.RuntimeCapabilityStatus(
                name="world_package_import",
                state=runtime.RuntimeComponentState.NOT_AVAILABLE,
            ),
        ),
    )


def test_read_status_uses_one_probe_read_and_versioned_schema() -> None:
    probe = FakeApplicationRuntimeProbe(_status())

    status = runtime.ReadApplicationRuntimeStatus(probe).execute()
    result = runtime.runtime_status_read(status)

    assert probe.read_count == 1
    assert result.schema_version == "local-runtime-status-v1"
    assert result.installation_state == "degraded"
    assert [item.name for item in result.components] == ["backend", "neo4j"]
    assert result.components[1].reason_code == "graph_degraded"
    assert result.scheduler.fencing_epoch == 4
    assert result.provider_usage.recent_call_count == 0
    assert result.provider_usage.recent_failure_class == "timeout"
    assert result.owner.registered_world_count == 2
    assert result.activity.inbox_result_code == "no_action"
    assert result.capabilities["world_package_import"].state == "not_available"


def test_status_schema_rejects_unknown_fields() -> None:
    payload = runtime.runtime_status_read(_status()).model_dump(mode="json")
    payload["container_id"] = "must-not-be-exposed"

    with pytest.raises(ValidationError):
        runtime.LocalRuntimeStatusRead.model_validate(payload)


def test_status_schema_rejects_negative_operational_counts() -> None:
    payload = runtime.runtime_status_read(_status()).model_dump(mode="json")
    payload["projector"]["pending_count"] = -1

    with pytest.raises(ValidationError):
        runtime.LocalRuntimeStatusRead.model_validate(payload)


def test_runtime_diagnostic_codes_are_unique_and_content_free() -> None:
    values = [item.value for item in runtime.RuntimeDiagnosticCode]

    assert len(values) == len(set(values))
    assert "diagnostic_redaction_failed" in values
    assert all(" " not in value for value in values)


def test_existing_public_health_contract_is_unchanged() -> None:
    from app.main import health

    assert health() == {"status": "ok"}
