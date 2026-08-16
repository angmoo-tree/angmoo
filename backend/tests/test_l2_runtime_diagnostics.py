from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.deps import get_current_user
from app.api.v1.routes import runtime_status as runtime_routes
from app.core.db import get_db
from app.domains.runtime import public as runtime
from app.domains.runtime.infrastructure.sqlalchemy_application_runtime_probe import (
    _find_opaque_id,
    _lane_result_code,
    _provider_call_count,
    _provider_failure_class,
)


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
    monkeypatch.setattr(runtime_routes, "SqlAlchemyApplicationRuntimeProbe", _FakeProbe)
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
