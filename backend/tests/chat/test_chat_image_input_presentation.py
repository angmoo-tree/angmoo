"""Capture real adapter requests without paid I/O or changing source payloads."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from chat.test_chat_identity_delivery import identity, request
from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterRequest
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.integrations import direct_llm
from app.integrations.llm.character_response_generator import DirectLlmCharacterResponseGenerator, _user_prompt
from app.integrations.llm.supervisor_selection import DirectLlmSupervisorSelectionProvider, selection_prompt


DESCRIPTION = "describes an image attached by the user to"
OBSERVATION = '{"description":"A beach","visible_text":[],"uncertainties":["Unknown place"]}'


class CapturedRequest(Exception):
    pass


def capture(monkeypatch):
    calls = []
    async def stop(**kwargs):
        calls.append(kwargs)
        raise CapturedRequest()
    monkeypatch.setattr(direct_llm, "generate_text", stop)
    return calls


def material():
    return CredentialMaterial("fixture", "google", "gemini-3.1-flash-lite", "fixture", CredentialPurpose.MESSAGE_LLM, "fake")


@pytest.mark.parametrize("current", [False, True])
@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("repair", [None, "router_schema_rejected"])
def test_supervisor_submits_conditional_current_attachment_once(monkeypatch, current, native, repair):
    item = RetrievalRouterRequest("Look at this", image_context=OBSERVATION if current else None,
        chat_identity=identity(), repair_diagnostic=repair)
    expected_payload = selection_prompt(item)
    calls = capture(monkeypatch)
    with pytest.raises(CapturedRequest):
        asyncio.run(DirectLlmSupervisorSelectionProvider(material(), native_controls=native).route(item))
    assert len(calls) == 1
    call = calls[0]
    assert call["system_prompt"].count(DESCRIPTION) == int(current)
    assert call["user_prompt"] == expected_payload
    assert item.image_context == (OBSERVATION if current else None)
    if current:
        assert "does not establish that the user took the photo" in call["system_prompt"]
        assert "do not reassign them to the current message" in call["system_prompt"]


@pytest.mark.parametrize("current", [False, True])
@pytest.mark.parametrize("raw", ["What do you think?", "The image shows a beach."])
def test_crg_uses_frozen_current_image_kind_and_preserves_submitted_payload(monkeypatch, current, raw):
    item = request(raw=raw, participants=identity())
    if current:
        image = SimpleNamespace(asset_hash="a" * 64, asset_revision=1, asset_id="image", context=OBSERVATION)
        item = replace(item, evidence=EvidenceBundleAssembler().with_image(item.evidence, image))
    before = item.evidence.evidence_hash
    expected_payload = _user_prompt(item)
    calls = capture(monkeypatch)
    with pytest.raises(CapturedRequest):
        asyncio.run(DirectLlmCharacterResponseGenerator(material()).generate(item))
    assert len(calls) == 1
    assert calls[0]["system_prompt"].count(DESCRIPTION) == int(current)
    assert calls[0]["user_prompt"] == expected_payload
    assert item.evidence.evidence_hash == before
    assert item.user_message == raw
    assert "First-person expressions refer to the speaker" in calls[0]["system_prompt"]
    assert "Honor a clear language request" in calls[0]["system_prompt"]


def test_previous_observation_is_not_a_current_attachment(monkeypatch):
    from app.domains.chat.contracts.character_response_generator import CharacterResponseContextMessage
    item = request(participants=identity(), context=(CharacterResponseContextMessage(
        "assistant", "Earlier photo: <untrusted_image_observation>A forest</untrusted_image_observation>", "p-responding"),))
    calls = capture(monkeypatch)
    with pytest.raises(CapturedRequest):
        asyncio.run(DirectLlmCharacterResponseGenerator(material()).generate(item))
    assert DESCRIPTION not in calls[0]["system_prompt"]
    assert "Earlier photo" in calls[0]["user_prompt"]
