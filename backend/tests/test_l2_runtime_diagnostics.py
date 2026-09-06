from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.domains.identity.dependencies import get_current_user
from app.domains.runtime import router as runtime_routes
from app.database import get_db
from types import SimpleNamespace as _RuntimeTestNamespace
from app.domains.runtime.contracts.status import ActivityRuntimeStatus as _runtime_ActivityRuntimeStatus
from app.domains.runtime.contracts.status import ApplicationRuntimeStatus as _runtime_ApplicationRuntimeStatus
from app.domains.runtime.contracts.status import InstallationState as _runtime_InstallationState
from app.domains.runtime.contracts.status import MigrationRuntimeStatus as _runtime_MigrationRuntimeStatus
from app.domains.runtime.contracts.status import OwnerRuntimeStatus as _runtime_OwnerRuntimeStatus
from app.domains.runtime.contracts.status import ProjectorRuntimeStatus as _runtime_ProjectorRuntimeStatus
from app.domains.runtime.contracts.status import ProviderFailureClass as _runtime_ProviderFailureClass
from app.domains.runtime.contracts.status import ProviderUsageRuntimeStatus as _runtime_ProviderUsageRuntimeStatus
from app.domains.runtime.contracts.status import RuntimeComponentState as _runtime_RuntimeComponentState
from app.domains.runtime.contracts.status import RuntimeComponentStatus as _runtime_RuntimeComponentStatus
from app.domains.runtime.constants import RuntimeDiagnosticCode as _runtime_RuntimeDiagnosticCode
from app.domains.runtime.contracts.status import SchedulerRuntimeStatus as _runtime_SchedulerRuntimeStatus

# Preserve the original test namespace with the same actual role objects.
runtime = _RuntimeTestNamespace(
    ActivityRuntimeStatus=_runtime_ActivityRuntimeStatus,
    ApplicationRuntimeStatus=_runtime_ApplicationRuntimeStatus,
    InstallationState=_runtime_InstallationState,
    MigrationRuntimeStatus=_runtime_MigrationRuntimeStatus,
    OwnerRuntimeStatus=_runtime_OwnerRuntimeStatus,
    ProjectorRuntimeStatus=_runtime_ProjectorRuntimeStatus,
    ProviderFailureClass=_runtime_ProviderFailureClass,
    ProviderUsageRuntimeStatus=_runtime_ProviderUsageRuntimeStatus,
    RuntimeComponentState=_runtime_RuntimeComponentState,
    RuntimeComponentStatus=_runtime_RuntimeComponentStatus,
    RuntimeDiagnosticCode=_runtime_RuntimeDiagnosticCode,
    SchedulerRuntimeStatus=_runtime_SchedulerRuntimeStatus,
)
from app.domains.runtime.service.status import RUNTIME_MIGRATION_HEAD
from app.runtime.diagnostics.status_composition import create_runtime_status_reader as SqlAlchemyApplicationRuntimeProbe
from app.domains.runtime.service.status import _find_opaque_id
from app.domains.runtime.service.status import _graph_backend_available
from app.domains.runtime.service.status import _lane_result_code
from app.domains.runtime.service.status import _provider_call_count
from app.domains.runtime.service.status import _provider_failure_class
from app.domains.runtime.service import status as runtime_probe_module


def _status() -> runtime.ApplicationRuntimeStatus:
    now = datetime(2026, 8, 17, 0, 0, tzinfo=UTC)
    return runtime.ApplicationRuntimeStatus(
        installation_state=runtime.InstallationState.READY,
        version="0.2.0",
        components=(
            runtime.RuntimeComponentStatus(
                name="backend",
                state=runtime.RuntimeComponentState.READY,
            ),
        ),
        migration=runtime.MigrationRuntimeStatus(
            state=runtime.RuntimeComponentState.READY,
            current_revision="20260816_0080",
            head_revision="20260816_0080",
        ),
        scheduler=runtime.SchedulerRuntimeStatus(
            state=runtime.RuntimeComponentState.RUNNING,
            active_owner_id="opaque-scheduler",
            fencing_epoch=7,
            last_heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=30),
        ),
        projector=runtime.ProjectorRuntimeStatus(
            state=runtime.RuntimeComponentState.READY,
        ),
        provider_usage=runtime.ProviderUsageRuntimeStatus(recent_call_count=2),
        owner=runtime.OwnerRuntimeStatus(
            bootstrap_state="claimed",
            owner_user_id="owner-a",
            registered_world_count=2,
            active_world_count=1,
            active_world_character_count=2,
        ),
        activity=runtime.ActivityRuntimeStatus(
            last_successful_run_id="run-a",
            last_successful_post_id="post-a",
            last_successful_at=now,
            inbox_result_code="reply_created",
            feed_result_code="no_action",
        ),
    )


class _FakeProbe:
    def __init__(self, _db: object) -> None:
        pass

    def read_status(self) -> runtime.ApplicationRuntimeStatus:
        return _status()


class _FakeDb:
    def __init__(self, owner_user_id: str) -> None:
        self.owner_user_id = owner_user_id

    def get(self, _model: object, _key: str) -> object:
        return SimpleNamespace(
            bootstrap_state="claimed",
            owner_user_id=self.owner_user_id,
        )


def _client(monkeypatch, *, authenticated_user_id: str, owner_user_id: str) -> TestClient:
    app = FastAPI()
    app.include_router(runtime_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: _FakeDb(owner_user_id)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=authenticated_user_id
    )
    app.state.runtime_status_reader_factory = _FakeProbe
    return TestClient(app, base_url="http://127.0.0.1:3000")


def test_owner_runtime_status_endpoint_is_versioned_and_content_free(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        authenticated_user_id="owner-a",
        owner_user_id="owner-a",
    )

    response = client.get("/api/v1/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "local-runtime-status-v1"
    assert payload["owner"]["registered_world_count"] == 2
    assert payload["activity"]["last_successful_post_id"] == "post-a"
    serialized = response.text.lower()
    for forbidden in (
        "api_key",
        "app_secret",
        "authorization",
        "private_chat",
        "full_prompt",
        "provider_response",
        "container_id",
        "host_path",
    ):
        assert forbidden not in serialized


def test_runtime_status_endpoint_rejects_non_owner(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        authenticated_user_id="other-user",
        owner_user_id="owner-a",
    )

    response = client.get("/api/v1/runtime/status")

    assert response.status_code == 403
    assert response.json() == {"detail": "local_owner_required"}


def test_runtime_status_openapi_contains_versioned_owner_endpoint(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        authenticated_user_id="owner-a",
        owner_user_id="owner-a",
    )

    schema = client.get("/openapi.json").json()

    assert "/api/v1/runtime/status" in schema["paths"]
    response_schema = schema["components"]["schemas"]["LocalRuntimeStatusRead"]
    assert "owner" in response_schema["properties"]
    assert "activity" in response_schema["properties"]


def test_application_probe_extracts_only_bounded_metadata() -> None:
    gateway_result = {
        "llm_usage_summary": {"provider_call_count": 3},
        "inbox_result": {"status": "reply_created", "summary": "private text"},
        "feed_result": {"reason": "NO_ACTION", "content": "private text"},
        "routine": {
            "activity_beat_id": "beat-opaque",
            "activity_episode_id": "episode-opaque",
        },
    }

    assert _provider_call_count(gateway_result) == 3
    assert _lane_result_code(gateway_result, "inbox") == "reply_created"
    assert _lane_result_code(gateway_result, "feed") == "no_action"
    assert _find_opaque_id(gateway_result, ("activity_beat_id",)) == "beat-opaque"
    assert _find_opaque_id(gateway_result, ("activity_episode_id",)) == "episode-opaque"


def test_provider_failure_classifier_returns_normalized_class_only() -> None:
    failure = _provider_failure_class(
        "failed",
        {"error_code": "provider_timeout", "provider_response": "private text"},
    )

    assert failure is runtime.ProviderFailureClass.TIMEOUT


def test_application_probe_degrades_when_alembic_metadata_is_missing() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    with Session(engine) as session:
        migration = SqlAlchemyApplicationRuntimeProbe(session)._migration_status()

        assert migration.state is runtime.RuntimeComponentState.DEGRADED
        assert migration.current_revision is None
        assert migration.head_revision == RUNTIME_MIGRATION_HEAD
        assert (
            migration.reason_code
            is runtime.RuntimeDiagnosticCode.MIGRATION_NOT_CURRENT
        )
        # The failed metadata query must not poison the request-scoped session.
        assert session.execute(text("SELECT 1")).scalar_one() == 1


def test_application_probe_reads_embedded_sqlite_schema_lineage(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    monkeypatch.setattr(
        runtime_probe_module.settings,
        "DATABASE_URL",
        "sqlite+pysqlite:///:memory:",
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE angmoo_schema_version (
                    singleton_key INTEGER PRIMARY KEY,
                    source_revision TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO angmoo_schema_version (
                    singleton_key, source_revision
                ) VALUES (1, :revision)
                """
            ),
            {"revision": RUNTIME_MIGRATION_HEAD},
        )

    with Session(engine) as session:
        migration = SqlAlchemyApplicationRuntimeProbe(session)._migration_status()

    assert migration.state is runtime.RuntimeComponentState.READY
    assert migration.current_revision == RUNTIME_MIGRATION_HEAD
    assert migration.reason_code is None


def test_embedded_ladybug_uses_in_process_health_signal() -> None:
    assert _graph_backend_available() is True
