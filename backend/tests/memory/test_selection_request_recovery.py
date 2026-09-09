"""Request rejection, SDK retry ownership and durable recovery regression."""

import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors, types
from sqlalchemy import func, select

from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.domains.memory.exceptions import MemoryValidationError
from app.domains.memory.models.batch import MemoryBatchRun
from app.domains.memory.models.items import MemoryItem, MemoryMaintenanceJob
from app.domains.memory.policies.selection_output import MemorySelectionSource, selection_response_schema
from app.integrations.llm.memory_selection import DirectLlmMemorySelectionProvider, _prompt_payload
from app.providers import gemini
from app.providers.contracts import ProviderRequest
from memory.test_p8_l_o_memory_consolidation import memory_session
from memory.test_p8_l_r_memory_batch_runtime import batch_stack


def test_transport_changes_only_decisions_bound():
    canonical = selection_response_schema()
    expected = deepcopy(canonical)
    del expected["properties"]["decisions"]["maxItems"]
    for count in (10, 32):
        sources = tuple(MemorySelectionSource(f"candidate-{i}", f"source-{i}", "social", "경험") for i in range(count))
        assert _prompt_payload(sources)[1] == expected
    assert selection_response_schema() == canonical
    assert canonical["properties"]["decisions"]["maxItems"] == 32


def test_subjective_reference_is_explicit_without_weakening_parser():
    import json
    from app.domains.memory.policies.selection_output import parse_selection
    source = MemorySelectionSource("candidate-1", "source-1", "social", "약속", "안도했다")
    prompt, _ = _prompt_payload((source,))
    assert json.loads(prompt)["sources"][0]["subjective_context_ref"] == "source-1.subjective"
    payload = {"version": "memory-selection.v2", "batch_ref": "batch-1", "decisions": [
        {"candidate_ref": "candidate-1", "decision": "retain", "reason_code": "commitment",
         "memory": {"summary": "협력을 약속하고 안도했다", "evidence_refs": ["source-1"],
                    "subjective_context_refs": ["안도했다"]}}]}
    with pytest.raises(MemoryValidationError):
        parse_selection(payload, sources=(source,))
    payload["decisions"][0]["memory"]["subjective_context_refs"] = ["source-1.subjective"]
    assert len(parse_selection(payload, sources=(source,))) == 1


@pytest.mark.parametrize("status,code,retryable", [
    (400, "request_invalid", False), (401, "auth_failed", False),
    (403, "auth_failed", False), (404, "model_unavailable", False),
    (429, "rate_limited", True), (500, "provider_unavailable", True),
    (502, "provider_unavailable", True), (503, "provider_unavailable", True),
    (504, "provider_unavailable", True), (418, "failed", False),
])
def test_sdk_failure_reaches_durable_job_once_per_attempt(monkeypatch, memory_session, status, code, retryable):
    calls, options = [], []

    def generate(**kwargs):
        calls.append(kwargs)
        raise errors.APIError(status, {"error": {"code": status, "message": "private-key-and-source"}})

    def client(**kwargs):
        options.append(kwargs["http_options"])
        return SimpleNamespace(models=SimpleNamespace(generate_content=generate))

    monkeypatch.setattr(gemini.genai, "Client", client)
    material = CredentialMaterial("fixture", "google", "gemini-3.1-flash-lite", None, CredentialPurpose.MESSAGE_LLM, "fixture-key", "high")
    provider = DirectLlmMemorySelectionProvider(material)
    _, _, job_id, _, service = batch_stack(memory_session, provider=provider)
    now = datetime.now(UTC)
    for attempt in range(1, 4 if retryable else 2):
        service.clock = lambda: now
        assert asyncio.run(service.run_next(lease_token=f"lease-{attempt}")) == f"memory_selection_{code}"
        memory_session.expire_all()
        job = memory_session.get(MemoryMaintenanceJob, job_id)
        assert job.attempt_count == attempt
        assert job.status == ("pending" if retryable and attempt < 3 else "failed")
        now += timedelta(minutes=10)
    assert len(calls) == (3 if retryable else 1)
    assert all(option.retry_options.attempts == 1 for option in options)
    assert memory_session.get(MemoryBatchRun, job_id).physical_calls == len(calls)
    assert memory_session.scalar(select(func.count()).select_from(MemoryItem)) == 0
    assert provider.provider_code == status
    assert provider.retryable == retryable
    assert "private" not in str(gemini.classify_generation_failure(errors.APIError(status, {})))


@pytest.mark.parametrize("error,code", [
    (httpx.ReadTimeout("secret"), "timeout"),
    (httpx.ConnectError("secret"), "transport_failed"),
    (TimeoutError("secret"), "timeout"),
    (RuntimeError("secret"), "failed"),
])
def test_transport_and_unknown_failures_are_safe(error, code):
    result = gemini.classify_generation_failure(error)
    assert result.failure_class == code
    assert result.retryable == (code != "failed")
    assert "secret" not in str(result)


def test_default_callers_keep_sdk_retry_and_output_policy(monkeypatch):
    options, configs = [], []
    def generate(**kwargs):
        configs.append(kwargs["config"])
        return types.GenerateContentResponse()
    def client(**kwargs):
        options.append(kwargs["http_options"])
        return SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    monkeypatch.setattr(gemini.genai, "Client", client)
    request = ProviderRequest("fixture", "gemini-3.1-flash-lite", "system", "user", 2048, 10)
    gemini._generate_content_sync(request)
    gemini._generate_content_sync(replace(request, sdk_attempts=1, max_output_tokens=65536))
    assert options[0].retry_options is None
    assert options[1].retry_options.attempts == 1
    assert [config.max_output_tokens for config in configs] == [2048, 65536]
