"""Capture supported providers, strict parsers and SDK HTTP without external AI.

These checks prove supplied policy and exact original data, not model quality.
"""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.contracts.environment import EnvironmentSnapshot
from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.domains.memory.contracts.episode import EpisodeBundle
from app.domains.memory.policies.selection_output import MemorySelectionSource
from app.integrations.llm import memory_selection, episode_selection, relationship_review
from app.integrations.llm.image_interpretation import GeminiImageInterpreter
from app.providers.contracts import ProviderResponse, ProviderUsage
from memory.test_episode_contracts import unit

pytestmark = pytest.mark.usefixtures("deny_external_network")
ORIGINAL = "앵무 原文 A-17: وعد لم يحدث / 約束は取り消された / not accepted."


def material():
    return CredentialMaterial(credential_id="synthetic", provider="google", model="gemini-3.1-flash-lite",
        purpose=CredentialPurpose.MESSAGE_LLM, fingerprint="synthetic", _secret="synthetic", thinking_level="high")


def capture(monkeypatch, module, payload):
    requests = []
    async def generate(request):
        requests.append(deepcopy(request))
        return ProviderResponse(json.dumps(payload, ensure_ascii=False), payload,
            ProviderUsage(input_tokens=10, output_tokens=10), finish_reason="STOP")
    adapter = SimpleNamespace(generate_json=generate)
    monkeypatch.setattr(module, "get_provider_adapter", lambda *_: adapter)
    return requests


@pytest.mark.parametrize("locale", ["ko-KR", "en-US", "ja-JP", "ar-AE"])
def test_selection_provider_receives_frozen_locale_and_preserves_source(monkeypatch, locale):
    source = MemorySelectionSource("candidate-1", "source-1", "experience", ORIGINAL)
    payload = {"version": "memory-selection.v2", "batch_ref": "batch-1", "decisions": [{
        "candidate_ref": "candidate-1", "decision": "retain", "reason_code": "meaningful_experience",
        "memory": {"summary": ORIGINAL, "evidence_refs": ["source-1"], "subjective_context_refs": []}}]}
    requests = capture(monkeypatch, memory_selection, payload)
    environment = EnvironmentSnapshot(locale, "America/New_York", 7, 3)
    provider = memory_selection.DirectLlmMemorySelectionProvider(material())
    result = asyncio.run(provider.select((source,), timeout=5, environment=environment))
    assert result[0].summary == ORIGINAL and source.text == ORIGINAL
    prompt = json.loads(requests[0].user_prompt)
    assert prompt["environment"] == environment.to_dict()
    assert prompt["sources"][0]["text"] == ORIGINAL
    assert "admitted memory/search language" in requests[0].system_prompt
    assert len(requests) == provider.physical_calls == 1
    assert requests[0].sdk_attempts == 1 and requests[0].thinking_level == "high"


@pytest.mark.parametrize("locale", ["ko-KR", "en-US", "ja-JP", "ar-AE"])
def test_episode_request_and_result_keep_language_and_refs(monkeypatch, locale):
    first = unit(1, ORIGINAL)
    bundle = EpisodeBundle("B1", first.scope, (first,), environment=EnvironmentSnapshot(locale, "UTC", 3, 2))
    payload = {"bundle_ref": "B1", "episodes": [{"summary": ORIGINAL, "source_refs": ["S1"], "follows_episode_refs": []}],
        "skipped_new_refs": [], "needs_split": False}
    requests = capture(monkeypatch, episode_selection, payload)
    provider = episode_selection.DirectLlmEpisodeSelectionProvider(material())
    result = asyncio.run(provider.select(bundle, timeout=5))
    assert result.episodes[0].summary == ORIGINAL
    assert json.loads(requests[0].user_prompt)["environment"] == bundle.environment.to_dict()
    assert ORIGINAL in requests[0].user_prompt
    assert "memory_search_locale" in requests[0].system_prompt
    assert len(requests) == provider.physical_calls == 1 and requests[0].max_output_tokens == 8192


@pytest.mark.parametrize("visible", ["앵무 A-17", "原文 A-17", "وعد A-17", "Original A-17"])
def test_image_analysis_english_policy_original_text_and_auxiliary_hint(visible):
    requests = []
    async def generate(request):
        requests.append(request)
        return ProviderResponse("", {"description": "A sign with A-17.", "visible_text": [visible],
            "uncertainties": ["The smaller text is not legible."], "recall_hint": "x"*121}, ProviderUsage(), finish_reason="STOP")
    result, _ = asyncio.run(GeminiImageInterpreter(SimpleNamespace(generate_json=generate)).analyze(
        key="synthetic", model="gemini-3.1-flash-lite", thinking_level="medium", content=b"synthetic", content_type="image/png"))
    assert result.visible_text == [visible] and result.recall_hint is None
    assert result.description == "A sign with A-17."
    assert "description and uncertainties concisely in English" in requests[0].system_prompt
    assert "visible_text exactly in its original language" in requests[0].system_prompt
    assert len(requests) == 1 and requests[0].sdk_attempts == 1 and requests[0].max_output_tokens == 1800


@pytest.mark.parametrize("speech", ["한국어로 말한다", "Speak English.", "日本語を使う", "تحدث بالعربية"])
def test_relationship_request_keeps_direction_subject_evidence_and_keep(monkeypatch, speech):
    payload = {"subject": {"name": "Original A-17", "speech_style": speech}, "memories": [ORIGINAL],
        "existing_relationship": {"relationship_label": "約束", "perception": ORIGINAL},
        "actor_ref": "character-a", "target_ref": "character-b", "world_ref": "world-1"}
    requests = capture(monkeypatch, relationship_review, {"decision": "keep", "relationship_label": "約束", "perception": ORIGINAL, "memory_refs": []})
    provider = relationship_review.DirectRelationshipReviewProvider(material(), validate_credential=lambda: None)
    result = asyncio.run(provider.review(payload, partial=False, timeout=5))
    assert result["decision"] == "keep" and result["perception"] == ORIGINAL
    sent = json.loads(requests[0].user_prompt)
    assert sent["subject"] == payload["subject"] and sent["existing_relationship"] == payload["existing_relationship"]
    assert (sent["actor_ref"], sent["target_ref"], sent["world_ref"]) == ("character-a", "character-b", "world-1")
    assert "subject's explicitly directed language" in requests[0].system_prompt
    assert "unchanged" in requests[0].system_prompt and len(requests) == 1


@pytest.mark.parametrize("lane_name,capable", [("feed",False),("feed",True),("inbox",False),("inbox",True)])
def test_final_combined_language_policy_and_schema_reach_real_sdk_http(monkeypatch, lane_name, capable):
    import httpx
    from google import genai
    from google.genai import types
    from sqlalchemy.orm import Session
    from app.domains.world_characters.contracts.social_io import LANE_IO
    from app.integrations import direct_llm
    from app.runtime.autonomous_activity import provider as transport
    from runtime.test_activity_combined_delivery import fixture
    from runtime.test_gemini_schema_missing_contract import candidate
    from social.test_feed_reaction_intent import _engine

    original_client = genai.Client
    requests = []
    output = {"decision": {"state_update": None, "decisions": [{"target_id": "post", "action": "no_action"}]}, "draft": {"replies": []}}
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(output)}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 10}})
    def client(**kwargs):
        supplied = kwargs["http_options"]
        kwargs["http_options"] = types.HttpOptions(timeout=supplied.timeout,
            retry_options=supplied.retry_options, client_args={"transport": httpx.MockTransport(respond)})
        return original_client(**kwargs)
    monkeypatch.setattr(genai, "Client", client)
    monkeypatch.setattr(transport, "_api_key", lambda _: "synthetic")
    monkeypatch.setattr(transport, "_llm_context", lambda ctx, **kw: direct_llm.DirectLlmCallContext(
        "synthetic", "actor", "run", kw["node"], kw["lane"], "google", "gemini-3.1-flash-lite"))
    async def execute():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, _, _, _ = fixture(db)
            lane.provider.social_io_policy = LANE_IO
            item = candidate()
            if capable: item["proposal_eligible" if lane_name == "feed" else "activity_proposal"] = True
            environment = EnvironmentSnapshot("ja-JP", "Asia/Tokyo", 7, 3).to_dict()
            result = await lane.provider.plan(lane=lane_name, context={"environment":environment,
                "persona": {"description": ORIGINAL, "speech_style": "Speak English."}}, candidates=[item])
            assert result["decisions"][0]["action"] == "no_action"
            assert len(requests) == 1
            body = requests[0]
            system = body["systemInstruction"]["parts"][0]["text"]
            assert "English" in system and "language" in system
            assert not any('\uac00' <= ch <= '\ud7a3' for ch in system)
            prompt = body["contents"][0]["parts"][0]["text"]
            assert ORIGINAL in prompt and json.dumps(environment,ensure_ascii=False) in prompt
            schema = body["generationConfig"]["responseJsonSchema"]
            intent = schema["properties"]["decision"]["properties"]["decisions"]["items"]["properties"]["interaction_intent"]
            values = intent["anyOf"][0]["enum"]
            assert "ordinary_comment" in values and intent["anyOf"][1] == {"type":"null"}
            assert ("joint_activity_proposal" in values) == (capable and lane_name == "feed")
            assert ("proposal_response" in values) == (capable and lane_name == "inbox")
            assert body["generationConfig"]["maxOutputTokens"] == 8192
    asyncio.run(execute())
