from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.domains.runtime import public as runtime


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
