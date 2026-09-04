import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.routes import memory as memory_routes
from app.domains.identity.public import CredentialMaterial, CredentialPurpose
from app.domains.memory.domain.batch_policy import (
    MEMORY_CONSENT_VERSION,
    MAX_SELECTION_INPUT_TOKEN_BOUND,
    memory_token_upper_bound,
)
from app.domains.memory.domain.errors import MemoryValidationError
from app.domains.memory.domain.selection import MemorySelectionSource
from app.domains.memory.infrastructure.batch_models import (
    MemoryBatchSetting,
    MemoryBatchProfile,
)
from app.domains.memory.infrastructure.sqlalchemy_models import MemoryMaintenanceJob
from app.integrations.llm import memory_selection
from app.providers.contracts import ProviderResponse, ProviderUsage
from app.runtime.memory.shutdown import MemoryShutdownAdmissionMiddleware
from test_p8_l_q_memory_read_inspector import _fixture, _seed, FRONTEND_HEADERS


def test_batch_settings_require_explicit_consent_exact_scope_csrf_and_saved_version(
    monkeypatch,
):
    client, engine, principal = _fixture()
    _seed(engine, principal)
    calls = []
    monkeypatch.setattr(
        memory_routes,
        "memory_provider",
        lambda factory, owner, model: calls.append((owner, model)),
    )
    path = "/api/v1/worlds/q-world/world-characters/q-responding/memory/batch-settings"
    value = client.get(path, headers=FRONTEND_HEADERS)
    assert value.status_code == 200
    assert value.json()["ai_enabled"] is False
    assert value.json()["version"] == 0
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(MemoryBatchSetting)) == 0
        assert db.scalar(select(func.count()).select_from(MemoryBatchProfile)) == 0
    body = {
        "expected_version": 0,
        "expected_profile_version": 0,
        "ai_enabled": True,
        "shutdown_enabled": True,
        "schedule_enabled": True,
        "local_time": "22:30",
        "model_id": "gemini-3.1-flash-lite",
        "consent_version": MEMORY_CONSENT_VERSION,
        "idempotency_key": "explicit-memory-consent",
    }
    assert client.put(path, json=body).status_code == 403
    assert (
        client.put(
            path, headers=FRONTEND_HEADERS, json={**body, "consent_version": None}
        ).status_code
        == 422
    )
    saved = client.put(path, headers=FRONTEND_HEADERS, json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1
    assert saved.json()["timezone"] == "Asia/Seoul"
    assert client.put(path, headers=FRONTEND_HEADERS, json=body).json()["version"] == 1
    assert (
        client.put(
            path,
            headers=FRONTEND_HEADERS,
            json={
                **body,
                "idempotency_key": "stale-memory-version",
                "local_time": "23:00",
            },
        ).status_code
        == 409
    )
    assert (
        client.put(
            path, headers=FRONTEND_HEADERS, json={**body, "owner_id": "intruder"}
        ).status_code
        == 422
    )
    assert client.get(
        path.replace("q-world/", "not-my-world/"), headers=FRONTEND_HEADERS
    ).status_code in {403, 404}
    with Session(engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(MemoryMaintenanceJob)
                .where(MemoryMaintenanceJob.reason == "memory_selection_v2")
            )
            == 0
        )
    assert calls  # credential readiness only, the fake has no generate method


@pytest.mark.parametrize(
    "failure", [None, "MAX_TOKENS", "invalid_ref", "missing_decision", "provider"]
)
def test_memory_adapter_one_call_strict_output_and_redacted_failure(
    monkeypatch, failure
):
    requests = []

    class Adapter:
        async def generate_json(self, request):
            requests.append(request)
            if failure == "provider":
                raise RuntimeError("raw secret fixture-secret and source body")
            decisions = [
                {
                    "candidate_ref": "candidate-99"
                    if failure == "invalid_ref"
                    else "candidate-1",
                    "decision": "retain",
                    "reason_code": "meaningful_experience",
                    "memory": {
                        "summary": "팀 연습을 마쳤다.",
                        "evidence_refs": ["source-1"],
                        "subjective_context_refs": [],
                    },
                }
            ]
            return ProviderResponse(
                "",
                {
                    "version": "memory-selection.v2",
                    "batch_ref": "batch-1",
                    "decisions": [] if failure == "missing_decision" else decisions,
                },
                ProviderUsage(input_tokens=100, output_tokens=80, thought_tokens=40),
                finish_reason="MAX_TOKENS" if failure == "MAX_TOKENS" else "STOP",
            )

    monkeypatch.setattr(
        memory_selection, "get_provider_adapter", lambda *args: Adapter()
    )
    provider = memory_selection.DirectLlmMemorySelectionProvider(
        CredentialMaterial(
            credential_id="fixture",
            provider="google",
            model="gemini-3.1-flash-lite",
            fingerprint="fixture",
            purpose=CredentialPurpose.MESSAGE_LLM,
            _secret="fixture-secret",
        )
    )
    sources = (
        MemorySelectionSource(
            "candidate-1", "source-1", "AUTOBIOGRAPHICAL_EVENT", "팀 연습을 마쳤다."
        ),
    )
    if failure:
        with pytest.raises(MemoryValidationError) as error:
            asyncio.run(provider.select(sources, timeout=1))
        assert str(error.value).startswith("memory_selection_")
        assert "fixture-secret" not in str(error.value)
    else:
        decisions = asyncio.run(provider.select(sources, timeout=1))
        assert decisions[0].decision == "retain"
        assert provider.usage.thought_tokens == 40
    assert len(requests) == 1
    assert requests[0].max_output_tokens == 2048
    assert requests[0].thinking_level == "high"
    assert "owner_id" not in requests[0].user_prompt
    assert "fixture-secret" not in repr(requests[0])


def test_input_budget_is_complete_normalized_byte_token_bound():
    assert memory_token_upper_bound("㍍") >= len("メートル".encode("utf-8"))
    assert memory_token_upper_bound("가" * 12000) > MAX_SELECTION_INPUT_TOKEN_BOUND


def test_shutdown_rejects_new_mutations_but_keeps_status_readable():
    class Coordinator:
        closing = False
        requests = set()

    state = Coordinator()
    app = FastAPI()
    app.add_middleware(MemoryShutdownAdmissionMiddleware, coordinator=state)

    @app.post("/submit")
    async def submit():
        return {"ok": True}

    @app.get("/status")
    async def status():
        return {"ok": True}

    client = TestClient(app)
    assert client.post("/submit").status_code == 200
    assert not state.requests
    state.closing = True
    assert client.post("/submit").status_code == 503
    assert client.get("/status").status_code == 200
