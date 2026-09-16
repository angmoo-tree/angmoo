import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib

import pytest
from sqlalchemy import func, select

from app.contracts.activity_output import parse_activity_output
from app.contracts.activity_thought import parse_activity_thought
from app.domains.chat.models import ChatMessageThought
from app.domains.chat.contracts import GenerationContractError
from app.domains.chat.contracts.character_response_generator import (
    CharacterResponseGeneratorRequest, CharacterResponseProfile,
)
from app.domains.chat.repository.response_lifecycle import SqlAlchemyResponseLifecycleRepository
from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.integrations import direct_llm
from app.integrations.llm.character_response_generator import DirectLlmCharacterResponseGenerator
from chat.test_p8_l_j_response_generation_lifecycle import (
    _commit_payload, _fence, _ready_to_commit, response_session,
)
from chat.test_p8_l_p_high_reasoning_hotfix import _current_context_evidence


@pytest.mark.parametrize("thought,status", [(None, "missing"), (3, "invalid"), ("", "missing"), ("마음" * 200, "recorded")])
def test_body_survives_optional_thought_error_without_repair(monkeypatch, thought, status):
    calls = []
    async def generate(**kwargs):
        calls.append(kwargs)
        return direct_llm.DirectLlmResponse(text="", parsed={"text": "응, 함께하자.", "thought": thought}, usage={}, finish_reason="STOP")
    monkeypatch.setattr(direct_llm, "generate_text", generate)
    material = CredentialMaterial(credential_id="test", provider="google", model="gemini-3.1-flash-lite", fingerprint="test", purpose=CredentialPurpose.MESSAGE_LLM, _secret="fake")
    request = CharacterResponseGeneratorRequest(
        user_message="도와줄래?", profile=CharacterResponseProfile(*(["캐릭터"] * 8)),
        recent_context=(), evidence=_current_context_evidence(),
    )
    result = asyncio.run(DirectLlmCharacterResponseGenerator(material, thought_enabled=True).generate(request))
    assert result.text == "응, 함께하자."
    assert result.activity_thought.status == status
    assert len(calls) == 1
    assert calls[0]["response_mime_type"] == "application/json"
    assert "no JSON or metadata" not in calls[0]["user_prompt"]
    if status == "recorded":
        assert len(result.activity_thought.text) == 280
        assert result.activity_thought.truncated


@pytest.mark.parametrize("raw", ['{"thought":"생각"}', 'not json', '[]', '{"text":3}'])
def test_invalid_body_never_leaks_envelope(raw):
    with pytest.raises(ValueError):
        parse_activity_output(raw)


def test_committed_thought_is_atomic_and_replay_does_not_overwrite(response_session):
    ChatMessageThought.__table__.create(response_session.get_bind(), checkfirst=True)
    now = datetime.now(UTC)
    repo = SqlAlchemyResponseLifecycleRepository(response_session)
    record = _ready_to_commit(repo, now)
    payload = replace(_commit_payload(record), activity_thought=parse_activity_thought("친구를 돕고 싶다."))
    fence = _fence(record)
    with pytest.raises(GenerationContractError):
        repo.finalize_response(replace(fence, lease_generation=fence.lease_generation + 1), payload, now=now + timedelta(seconds=1))
    assert response_session.scalar(select(func.count(ChatMessageThought.message_id))) == 0
    committed = repo.finalize_response(fence, payload, now=now + timedelta(seconds=2))
    response_session.commit()
    repo.finalize_response(fence, replace(payload, activity_thought=parse_activity_thought("버린 초안")), now=now + timedelta(seconds=3))
    thought = response_session.get(ChatMessageThought, committed.committed_assistant_message_id)
    assert thought.thought_text == "친구를 돕고 싶다."
    assert thought.request_id == record.request_id
    assert thought.source_digest == hashlib.sha256(payload.content.encode()).hexdigest()
    assert response_session.scalar(select(func.count(ChatMessageThought.message_id))) == 1

    from app.domains.chat.models import MessageThread, MessageMessage
    from app.domains.chat.repository.memory_turns import SqlAlchemyChatMemoryTurns
    thread = response_session.get(MessageThread, record.thread_id)
    reader = SqlAlchemyChatMemoryTurns(response_session)
    scope = dict(owner_id=thread.requester_id, world_id=thread.world_id,
                 subject_id=thread.responding_world_character_id, thread_id=thread.id)
    cutoff = reader.cutoff(**scope)
    assert cutoff == committed.committed_assistant_message_id
    turns = reader.read_page(**scope, cutoff=cutoff)
    assert len(turns) == 1
    assert turns[0].request_id == record.request_id
    assert turns[0].user_message_id == record.user_message_id
    assert turns[0].thought.text == "친구를 돕고 싶다."
    assert reader.read_page(**(scope | {"owner_id": "other-owner"}), cutoff=cutoff) == ()
    assert reader.read_page(**scope, cutoff=cutoff - 1) == ()
    from app.domains.memory.contracts.scope import MemoryScope
    from app.runtime.memory.episode_chat_sources import read_episode_chat_page
    from app.domains.social.models.feed import WorldCharacterBlock
    WorldCharacterBlock.__table__.create(response_session.get_bind(), checkfirst=True)
    episode_scope = MemoryScope(thread.requester_id, thread.world_id, thread.responding_world_character_id)
    page = read_episode_chat_page(response_session, scope=episode_scope, thread_id=thread.id, cutoff=cutoff)
    assert page.rejected_request_ids == ()
    assert len(page.new_units) == 1
    assert page.new_units[0].thought_reference == f"chat:{cutoff}"
    assert page.new_units[0].members[0].source_id == str(record.user_message_id)
    assert page.new_units[0].members[1].text == payload.content
    continuation = read_episode_chat_page(response_session, scope=episode_scope, thread_id=thread.id, cutoff=cutoff, after=cutoff)
    assert continuation.new_units == ()
    assert continuation.context_units == page.new_units
    from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
    details = RuntimeEpisodeDetailReader(response_session)
    original = details.read_sources(scope=episode_scope, identities=(("CHAT_MESSAGE", str(cutoff)),))
    assert original[("CHAT_MESSAGE", str(cutoff))].text == payload.content
    assert original[("CHAT_MESSAGE", str(cutoff))].evidence.source_digest == page.new_units[0].members[1].source_digest
    assert details.read_thoughts(scope=episode_scope, references=(f"chat:{cutoff}",))[f"chat:{cutoff}"].text == "친구를 돕고 싶다."
    answer = response_session.get(MessageMessage, cutoff)
    answer.content = "수정된 원문"
    response_session.flush()
    assert reader.read_page(**scope, cutoff=cutoff)[0].thought.status == "invalid"
    assert details.read_thoughts(scope=episode_scope, references=(f"chat:{cutoff}",))[f"chat:{cutoff}"].status == "invalid"
