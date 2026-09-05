"""Creator HTTP retains error semantics while consuming neutral contracts."""
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes import agents as mixed
from app.domains.characters import dependencies, exceptions, router, schemas
from app.domains.characters.service import drafts
from app.domains.media import contracts as media_contracts
from app.domains.runtime import contracts as runtime_contracts
from app.runtime.characters import management
from app.services import agent_runs, profile_media, runtime_boundary


@pytest.mark.parametrize("operation,error,status,detail", [
    ("create", exceptions.CredentialSyncError("credential sync failed"), 502, "credential sync failed"),
    ("create", runtime_contracts.AgentSlotUnavailableError("slot unavailable"), 409, "slot unavailable"),
    ("create", runtime_contracts.OpenClawGatewayAuthError("hidden provider auth"), 502, "OpenClaw Gateway authentication failed"),
    ("create", runtime_contracts.OpenClawGatewayError("API key invalid"), 400, "저장된 LLM API key가 만료되었거나 유효하지 않습니다. 새 API key를 저장한 뒤 커뮤니티 성향 분석을 다시 실행해주세요."),
    ("enhance", exceptions.AgentCreationDraftCooldownError(datetime(2026, 9, 5, tzinfo=UTC)), 429, "페르소나 보강은 2026-09-05T00:00:00+00:00 이후 다시 시도할 수 있습니다."),
    ("enhance", exceptions.CredentialRequiredError("credential required"), 409, "credential required"),
    ("complete", media_contracts.InvalidProfileMediaError("invalid media"), 422, "invalid media"),
    ("complete", exceptions.AgentHandleConflictError("handle conflict"), 409, "handle conflict"),
])
def test_creator_http_keeps_existing_error_status_and_detail(monkeypatch, operation, error, status, detail):
    async def fail_async(*args, **kwargs):
        raise error
    def fail_sync(*args, **kwargs):
        raise error
    function, path, payload = {
        "create": ("create_draft", "/api/v1/agents/drafts", {"api_key": "test-credential"}),
        "enhance": ("enhance_persona", "/api/v1/agents/drafts/example/enhance-persona", None),
        "complete": ("complete_draft", "/api/v1/agents/drafts/example/complete", {}),
    }[operation]
    monkeypatch.setattr(drafts, function, fail_sync if operation == "complete" else fail_async)
    app = FastAPI()
    app.include_router(mixed.router, prefix="/api/v1")
    app.dependency_overrides[dependencies.get_current_user] = lambda: SimpleNamespace(id="owner")
    app.dependency_overrides[dependencies.get_db] = lambda: object()
    app.state.creator_workflows = lambda: object()
    with TestClient(app) as client:
        response = client.post(path, json=payload)
    assert response.status_code == status
    assert response.json() == {"detail": detail}


def test_error_exports_are_same_objects_and_keep_runtime_diagnostics():
    assert management.CredentialRequiredError is exceptions.CredentialRequiredError
    assert management.CredentialSyncError is exceptions.CredentialSyncError
    assert agent_runs.AgentRunServiceError is runtime_contracts.AgentRunServiceError
    assert agent_runs.AgentSlotUnavailableError is runtime_contracts.AgentSlotUnavailableError
    assert issubclass(agent_runs.AgentSlotUnavailableError, agent_runs.AgentRunServiceError)
    assert profile_media.InvalidProfileMediaError is media_contracts.InvalidProfileMediaError
    assert runtime_boundary.OpenClawGatewayError is runtime_contracts.ResidentRuntimeError
    assert runtime_boundary.OpenClawGatewayAuthError is runtime_contracts.ResidentRuntimeAuthError
    diagnostics = {"engine": "fixture", "status": "unavailable"}
    error = runtime_contracts.ResidentRuntimeError("not ready", diagnostics=diagnostics)
    assert str(error) == "not ready"
    assert error.diagnostics is diagnostics
    expected = [route.name for route in mixed.router.routes]
    assert expected.index("create_agent_draft") < expected.index("get_agent")
    assert expected.index("complete_agent_draft") < expected.index("get_agent")
