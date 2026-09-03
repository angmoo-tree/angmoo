from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.domains.chat.domain.evidence_bundle import (
    EvidenceBundle,
    compute_evidence_hash,
)
from app.domains.chat.domain.policies import (
    MESSAGE_MODELS,
    WORLD_CHAT_FOREGROUND_MAX_OUTPUT_TOKENS,
    resolve_world_chat_model_execution_policy,
)
from app.domains.chat.domain.response_request import RetrievalOutcome
from app.domains.chat.domain.retrieval_intent import RetrievalRoute
from app.domains.chat.ports.character_response_generator import (
    CharacterResponseGeneratorRequest,
    CharacterResponseProfile,
)
from app.domains.identity.public import CredentialMaterial, CredentialPurpose
from app.integrations import direct_llm
from app.integrations.llm.canonical_retrieval_planner import (
    CANONICAL_PLANNER_MAX_OUTPUT_TOKENS,
)
from app.integrations.llm.character_response_generator import (
    CHARACTER_RESPONSE_MAX_OUTPUT_TOKENS,
    DirectLlmCharacterResponseGenerator,
)
from app.integrations.llm.graph_retrieval_planner import (
    GRAPH_PLANNER_MAX_OUTPUT_TOKENS,
)
from app.integrations.llm.memory_consolidation import (
    MEMORY_CONSOLIDATION_MAX_OUTPUT_TOKENS,
)
from app.integrations.llm.retrieval_router import ROUTER_MAX_OUTPUT_TOKENS
from app.providers.gemini import build_generate_content_config
from app.providers.registry import (
    AGENT_GOOGLE_MODELS,
    EMBEDDING_GOOGLE_MODELS,
    MESSAGE_GOOGLE_MODELS,
    get_model_spec,
    get_provider_adapter,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HIGH_REASONING_MODELS = (
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
)


@pytest.mark.parametrize("model", HIGH_REASONING_MODELS)
def test_world_chat_high_reasoning_policy_is_model_bounded(model: str) -> None:
    policy = resolve_world_chat_model_execution_policy(model)

    assert policy.model == model
    assert policy.thinking_level == "high"
    assert policy.max_output_tokens == 3_072


@pytest.mark.parametrize(
    ("model", "thinking_level"),
    (
        ("gemini-2.5-flash-lite", "low"),
        ("gemini-2.5-flash", "low"),
        ("gemma-4-26b-a4b-it", None),
        ("gemma-4-31b-it", None),
    ),
)
def test_world_chat_legacy_model_policy_remains_compatible(
    model: str,
    thinking_level: str | None,
) -> None:
    policy = resolve_world_chat_model_execution_policy(model)

    assert policy.thinking_level == thinking_level
    assert policy.max_output_tokens == 3_072


def test_world_chat_execution_policy_rejects_an_unknown_future_model() -> None:
    with pytest.raises(ValueError, match="world_chat_message_model_unsupported"):
        resolve_world_chat_model_execution_policy("gemini-future-unreviewed")


def test_foreground_caps_are_shared_while_background_consolidation_is_unchanged() -> None:
    assert WORLD_CHAT_FOREGROUND_MAX_OUTPUT_TOKENS == 3_072
    assert {
        ROUTER_MAX_OUTPUT_TOKENS,
        CANONICAL_PLANNER_MAX_OUTPUT_TOKENS,
        GRAPH_PLANNER_MAX_OUTPUT_TOKENS,
        CHARACTER_RESPONSE_MAX_OUTPUT_TOKENS,
    } == {3_072}
    assert MEMORY_CONSOLIDATION_MAX_OUTPUT_TOKENS == 2_048


def test_gemini_35_is_message_only_and_reuses_the_reviewed_adapter() -> None:
    model = "gemini-3.5-flash-lite"

    assert MESSAGE_GOOGLE_MODELS.count(model) == 1
    assert model in MESSAGE_MODELS
    assert model not in AGENT_GOOGLE_MODELS
    assert model not in EMBEDDING_GOOGLE_MODELS
    spec = get_model_spec("google", model)
    assert spec.capabilities.text is True
    assert spec.capabilities.structured_json is True
    assert spec.capabilities.embedding is False
    assert get_provider_adapter("google", model) is get_provider_adapter("google", "gemini-3.1-flash-lite")


@pytest.mark.parametrize("model", HIGH_REASONING_MODELS)
def test_high_reasoning_serialization_has_no_numeric_thinking_budget(
    model: str,
) -> None:
    policy = resolve_world_chat_model_execution_policy(model)
    payload = build_generate_content_config(
        model=model,
        system_prompt="bounded World Chat test",
        max_output_tokens=policy.max_output_tokens,
        response_mime_type="application/json",
        response_schema={
            "type": "object",
            "properties": {"route": {"type": "string"}},
            "required": ["route"],
        },
        thinking_level=policy.thinking_level,
    ).model_dump(exclude_none=True)

    assert payload["max_output_tokens"] == 3_072
    assert payload["thinking_config"] == {"thinking_level": "HIGH"}
    assert "thinking_budget" not in payload["thinking_config"]


def test_frontend_message_catalog_exposes_35_without_expanding_agent_models() -> None:
    chat_contract = (REPOSITORY_ROOT / "frontend/src/features/chat/model/chat-contract.ts").read_text(encoding="utf-8")
    agent_contract = (REPOSITORY_ROOT / "frontend/src/lib/agents.ts").read_text(encoding="utf-8")

    assert chat_contract.count('value: "gemini-3.5-flash-lite"') == 1
    assert 'label: "Gemini 3.5 Flash-Lite"' in chat_contract
    assert "gemini-3.5-flash-lite" not in agent_contract


@pytest.mark.parametrize("model", HIGH_REASONING_MODELS)
def test_character_response_generator_propagates_high_cap_and_safe_metrics(
    monkeypatch: pytest.MonkeyPatch,
    model: str,
) -> None:
    captured: dict[str, object] = {}

    async def fake_generate_text(**kwargs: object) -> direct_llm.DirectLlmResponse:
        captured.update(kwargs)
        tracker = kwargs["tracker"]
        assert isinstance(tracker, direct_llm.RunLlmTracker)
        context = kwargs["context"]
        assert isinstance(context, direct_llm.DirectLlmCallContext)
        usage = {
            "prompt_token_count": 11,
            "candidates_token_count": 13,
            "thoughts_token_count": 17,
            "total_token_count": 41,
        }
        tracker.record_call(
            context=context,
            call_order=tracker.next_call_order(),
            provider_call_order=tracker.next_provider_call_order(),
            status="ok",
            duration_ms=23,
            usage=usage,
            thinking_level=str(kwargs["thinking_level"]),
            max_output_tokens=int(kwargs["max_output_tokens"]),
            finish_reason="STOP",
        )
        return direct_llm.DirectLlmResponse(
            text="응, 지금은 괜찮아!",
            parsed=None,
            usage=usage,
            finish_reason="STOP",
        )

    monkeypatch.setattr(
        "app.integrations.llm.character_response_generator.direct_llm.generate_text",
        fake_generate_text,
    )
    material = CredentialMaterial(
        credential_id="credential-1",
        provider="google",
        model=model,
        fingerprint="safe-fingerprint",
        purpose=CredentialPurpose.MESSAGE_LLM,
        _secret="not-a-real-key",
    )
    result = asyncio.run(
        DirectLlmCharacterResponseGenerator(material).generate(
            CharacterResponseGeneratorRequest(
                user_message="안녕 지금 기분이 어때?",
                profile=CharacterResponseProfile(
                    name="미도리야 이즈쿠",
                    handle="midoriya_izuku",
                    one_liner="히어로 지망생입니다!",
                    personality="성실하고 다정함",
                    speech_style="정중한 한국어",
                    worldview="친구를 돕는다",
                    topic_preferences="훈련과 친구",
                    safety_rules="안전하게 대화한다",
                ),
                recent_context=(),
                evidence=_current_context_evidence(),
            )
        )
    )

    assert captured["thinking_level"] == "high"
    assert captured["max_output_tokens"] == 3_072
    assert result.model == model
    assert result.thinking_level == "high"
    assert result.max_output_tokens == 3_072
    assert result.prompt_token_count == 11
    assert result.output_token_count == 13
    assert result.thought_token_count == 17
    assert result.total_token_count == 41
    assert result.latency_ms == 23
    assert result.finish_reason == "STOP"
    assert "not-a-real-key" not in repr(result)


def _current_context_evidence() -> EvidenceBundle:
    request_id = "high-reasoning-request"
    request_scope_hash = "a" * 64
    items = ()
    partial_axes = ()
    evidence_hash = compute_evidence_hash(
        request_id=request_id,
        request_scope_hash=request_scope_hash,
        route=RetrievalRoute.CURRENT_CONTEXT,
        retrieval_outcome=RetrievalOutcome.CURRENT_CONTEXT,
        items=items,
        partial_axes=partial_axes,
        degraded_reason=None,
        clarification_slot=None,
    )
    return EvidenceBundle(
        request_id=request_id,
        request_scope_hash=request_scope_hash,
        route=RetrievalRoute.CURRENT_CONTEXT,
        retrieval_outcome=RetrievalOutcome.CURRENT_CONTEXT,
        items=items,
        partial_axes=partial_axes,
        evidence_hash=evidence_hash,
    )
