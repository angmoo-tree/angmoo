"""The opt-in real-provider probe must never exceed its physical request cap."""

import asyncio
from dataclasses import replace

import pytest

from app.integrations.direct_llm import DirectLlmMaxCallsExceeded
from app.providers.contracts import ProviderCapabilities, ProviderRequest
from scripts.evaluate_description_centric import CASES, EDGE_CASES, CAP, DurableBudget, OneSdkAttempt


def test_evaluation_budget_is_durable_across_process_restarts(tmp_path):
    path = tmp_path / "budget.json"
    first = DurableBudget(path)
    for _ in range(CAP - 1):
        first.reserve()
    second = DurableBudget(path)
    assert second.used == CAP - 1
    second.reserve()
    with pytest.raises(DirectLlmMaxCallsExceeded):
        DurableBudget(path).reserve()
    assert DurableBudget(path).used == CAP


def test_eval_adapter_disables_sdk_auto_retries():
    class Adapter:
        capabilities = ProviderCapabilities(text=True, structured_json=True)
        async def generate_json(self, request):
            return request.sdk_attempts
        async def generate_text(self, request):
            return request.sdk_attempts

    adapter = OneSdkAttempt(Adapter())
    request = ProviderRequest(api_key="fixture", model="fixture", system_prompt="", user_prompt="",
        max_output_tokens=10, timeout_seconds=1)
    assert asyncio.run(adapter.generate_json(request)) == 1
    assert asyncio.run(adapter.generate_text(replace(request, sdk_attempts=5))) == 1


def test_synthetic_comparison_contains_same_information_once():
    description = CASES[0][2]
    separated = CASES[1][2]
    assert description is not None and separated is not None
    assert description["worldview"].split("\n") == [
        separated["worldview"], separated["speech_style"],
        separated["character_background"], separated["topic_preferences"],
        separated["safety_rules"],
    ]
    assert all(len(edits["worldview"]) <= 8000 and len(edits.get("character_background", "")) <= 8000
               for _, edits, _ in EDGE_CASES)
