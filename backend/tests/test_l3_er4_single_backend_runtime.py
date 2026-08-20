from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from app.domains.runtime.public import (
    ActivityRuntimeStatus,
    ApplicationRuntimeStatus,
    InstallationState,
    MigrationRuntimeStatus,
    OwnerRuntimeStatus,
    ProjectorRuntimeStatus,
    ProviderUsageRuntimeStatus,
    RuntimeComponentState,
    RuntimeComponentStatus,
    RuntimeDiagnosticCode,
    SchedulerLeaseHeldError,
    SchedulerLeaseLostError,
    SchedulerRuntimeStatus,
    ComponentObservationRegistry,
    overlay_in_process_component_status,
    runtime_status_read,
)
from app.main import create_app, create_lifespan
from app.runtime.single_backend_components import (
    SingleBackendRuntimeComponents,
    SingleBackendRuntimeStartupError,
)


ROOT = Path(__file__).resolve().parents[2]


def _base_status() -> ApplicationRuntimeStatus:
    return ApplicationRuntimeStatus(
        installation_state=InstallationState.READY,
        version="er4-test",
        components=(
            RuntimeComponentStatus(
                name="backend",
                state=RuntimeComponentState.READY,
            ),
        ),
        migration=MigrationRuntimeStatus(state=RuntimeComponentState.READY),
        scheduler=SchedulerRuntimeStatus(state=RuntimeComponentState.RUNNING),
        projector=ProjectorRuntimeStatus(state=RuntimeComponentState.READY),
        provider_usage=ProviderUsageRuntimeStatus(),
        owner=OwnerRuntimeStatus(bootstrap_state="claimed", owner_user_id="owner"),
        activity=ActivityRuntimeStatus(),
    )


def test_single_backend_runtime_starts_and_stops_both_components() -> None:
    registry = ComponentObservationRegistry()
    calls: list[str] = []

    async def scheduler(stop, listener) -> None:
        calls.append("scheduler:start")
        listener("ready")
        await stop.wait()
        calls.append("scheduler:stop")

    def projector(stop, listener) -> None:
        calls.append("projector:start")
        listener("ready")
        assert stop.wait(timeout=2)
        calls.append("projector:stop")

    async def scenario() -> None:
        manager = SingleBackendRuntimeComponents(
            scheduler_runner=scheduler,
            projector_runner=projector,
            registry=registry,
            startup_timeout_seconds=1,
            shutdown_timeout_seconds=2,
        )
        await manager.start()
        assert {item.name: item.state for item in registry.snapshot()} == {
            "projector": RuntimeComponentState.READY,
            "scheduler": RuntimeComponentState.READY,
        }
        await manager.stop()

    asyncio.run(scenario())

    assert calls == [
        "scheduler:start",
        "projector:start",
        "scheduler:stop",
        "projector:stop",
    ]
    assert {item.name: item.state for item in registry.snapshot()} == {
        "projector": RuntimeComponentState.STOPPED,
        "scheduler": RuntimeComponentState.STOPPED,
    }


def test_duplicate_scheduler_rejects_second_single_backend_owner() -> None:
    registry = ComponentObservationRegistry()
    projector_stopped = False

    async def duplicate_scheduler(_stop, _listener) -> None:
        raise SchedulerLeaseHeldError("private-owner-detail")

    def projector(stop, listener) -> None:
        nonlocal projector_stopped
        listener("ready")
        projector_stopped = stop.wait(timeout=2)

    async def scenario() -> None:
        manager = SingleBackendRuntimeComponents(
            scheduler_runner=duplicate_scheduler,
            projector_runner=projector,
            registry=registry,
            startup_timeout_seconds=1,
            shutdown_timeout_seconds=2,
        )
        with pytest.raises(
            SingleBackendRuntimeStartupError,
            match="scheduler_component_start_failed",
        ):
            await manager.start()

    asyncio.run(scenario())

    assert projector_stopped is True
    scheduler = {item.name: item for item in registry.snapshot()}["scheduler"]
    assert scheduler.state is RuntimeComponentState.FAILED
    assert scheduler.reason_code is RuntimeDiagnosticCode.SCHEDULER_DUPLICATE_ACTIVE


def test_scheduler_reacquires_after_runtime_lease_loss() -> None:
    registry = ComponentObservationRegistry()
    attempts = 0
    recovered = asyncio.Event()

    async def scheduler(stop, listener) -> None:
        nonlocal attempts
        attempts += 1
        listener("ready")
        if attempts == 1:
            raise SchedulerLeaseLostError("simulated-sleep-gap")
        recovered.set()
        await stop.wait()

    def projector(stop, listener) -> None:
        listener("ready")
        assert stop.wait(timeout=2)

    async def scenario() -> None:
        manager = SingleBackendRuntimeComponents(
            scheduler_runner=scheduler,
            projector_runner=projector,
            registry=registry,
            startup_timeout_seconds=1,
            shutdown_timeout_seconds=2,
            scheduler_restart_delay_seconds=0.01,
        )
        await manager.start()
        await asyncio.wait_for(recovered.wait(), timeout=1)
        assert attempts == 2
        assert {item.name: item.state for item in registry.snapshot()}[
            "scheduler"
        ] is RuntimeComponentState.READY
        await manager.stop()

    asyncio.run(scenario())


def test_bounded_shutdown_marks_only_non_cooperative_component_failed() -> None:
    registry = ComponentObservationRegistry()
    projector_stopped = False

    async def stuck_scheduler(_stop, listener) -> None:
        listener("ready")
        await asyncio.Event().wait()

    def projector(stop, listener) -> None:
        nonlocal projector_stopped
        listener("ready")
        projector_stopped = stop.wait(timeout=2)

    async def scenario() -> None:
        manager = SingleBackendRuntimeComponents(
            scheduler_runner=stuck_scheduler,
            projector_runner=projector,
            registry=registry,
            startup_timeout_seconds=1,
            shutdown_timeout_seconds=0.1,
        )
        await manager.start()
        await manager.stop()

    asyncio.run(scenario())

    assert projector_stopped is True
    observations = {item.name: item for item in registry.snapshot()}
    assert observations["scheduler"].state is RuntimeComponentState.FAILED
    assert (
        observations["scheduler"].reason_code
        is RuntimeDiagnosticCode.SCHEDULER_LEASE_LOST
    )
    assert observations["projector"].state is RuntimeComponentState.STOPPED


def test_component_failure_degrades_aggregate_status_without_private_text() -> None:
    registry = ComponentObservationRegistry()
    registry.update("scheduler", RuntimeComponentState.READY)
    registry.update(
        "projector",
        RuntimeComponentState.DEGRADED,
        reason_code=RuntimeDiagnosticCode.GRAPH_DEGRADED,
    )

    status = overlay_in_process_component_status(
        _base_status(),
        config=SimpleNamespace(LOCAL_RUNTIME_COMPONENT_MODE="in_process"),
        registry=registry,
    )
    payload = runtime_status_read(status).model_dump_json()

    assert status.installation_state is InstallationState.DEGRADED
    assert status.projector.state is RuntimeComponentState.DEGRADED
    assert status.projector.reason_code is RuntimeDiagnosticCode.GRAPH_DEGRADED
    assert {item.name for item in status.components} == {
        "backend",
        "projector",
        "scheduler",
    }
    for forbidden in (
        "private-owner-detail",
        "api_key",
        "app_secret",
        "prompt",
        "provider_response",
    ):
        assert forbidden not in payload.lower()


def test_external_mode_does_not_overlay_process_local_state() -> None:
    registry = ComponentObservationRegistry()
    registry.update(
        "projector",
        RuntimeComponentState.FAILED,
        reason_code=RuntimeDiagnosticCode.PROJECTOR_STALLED,
    )
    baseline = _base_status()

    result = overlay_in_process_component_status(
        baseline,
        config=SimpleNamespace(LOCAL_RUNTIME_COMPONENT_MODE="external"),
        registry=registry,
    )

    assert result is baseline


def test_fastapi_lifespan_owns_component_start_and_stop(monkeypatch) -> None:
    calls: list[str] = []
    from app.core.config import settings

    monkeypatch.setattr(settings, "SEED_DEMO_DATA", False)

    class FakeComponents:
        async def start(self) -> None:
            calls.append("start")

        async def stop(self) -> None:
            calls.append("stop")

    lifespan = create_lifespan(
        security_validator=lambda: None,
        session_factory=lambda: pytest.fail("seed must remain disabled"),
        component_manager_factory=lambda: FakeComponents(),  # type: ignore[arg-type]
    )
    app = create_app(lifespan_handler=lifespan)

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            assert calls == ["start"]

    asyncio.run(scenario())

    assert calls == ["start", "stop"]


def test_in_process_compose_override_parks_external_workers() -> None:
    payload = yaml.safe_load((ROOT / "compose.in-process.yml").read_text("utf-8"))

    assert payload["services"]["backend"]["environment"] == {
        "LOCAL_RUNTIME_COMPONENT_MODE": "in_process"
    }
    assert payload["services"]["scheduler"]["profiles"] == ["external-workers"]
    assert payload["services"]["projector"]["profiles"] == ["external-workers"]

    development = yaml.safe_load((ROOT / "compose.dev.yml").read_text("utf-8"))
    frontend_command = development["services"]["frontend"]["command"]
    assert "rm -rf .next/dev" in frontend_command[-1]
    assert "exec pnpm dev --hostname 0.0.0.0" in frontend_command[-1]

    contract = (
        ROOT / "docs/architecture/l3-er4-single-backend-runtime.md"
    ).read_text("utf-8")
    assert "compose.dev.yml down" in contract
    assert "compose.dev.yml down -v" not in contract


def test_observation_timestamps_are_bounded_runtime_metadata() -> None:
    registry = ComponentObservationRegistry()
    registry.update("scheduler", RuntimeComponentState.READY)
    observation = registry.snapshot()[0]

    assert observation.started_at is not None
    assert observation.last_heartbeat_at is not None
    assert observation.started_at.tzinfo == UTC
    assert observation.last_heartbeat_at >= datetime(2026, 1, 1, tzinfo=UTC)
