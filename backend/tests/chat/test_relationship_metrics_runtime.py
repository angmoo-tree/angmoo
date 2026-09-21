from dataclasses import replace
from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from chat.test_p8_l_j_response_generation_lifecycle import response_session, _ready_to_commit, _fence, _commit_payload
from app.domains.chat.repository import SqlAlchemyResponseLifecycleRepository
from app.domains.relationships.models.personalization import RelationshipMetricApplication
from app.domains.relationships.models.social import RelationshipState
from app.domains.relationships.service.policy_activation import activate_policy
from app.runtime.relationships.experience_metrics import RelationshipChatLifecycle, apply_pending_metrics, stage_chat_metrics


def test_committed_chat_metadata_is_applied_once_to_fixed_persona(response_session):
    db = response_session
    now = datetime.now(UTC)
    activate_policy(db, world_id='response-world', now=now-timedelta(days=1))
    delegate = SqlAlchemyResponseLifecycleRepository(db)
    record = _ready_to_commit(delegate, now)
    raw = [dict(target_ref='counterpart_1', affinity='keep', trust='increase', tension='decrease', new_evidence_refs=['current_message'])]
    lifecycle = RelationshipChatLifecycle(db, delegate)
    lifecycle.finalize(_fence(record), replace(_commit_payload(record), relationship_metrics=raw), now=now)
    db.commit()
    application = db.scalar(select(RelationshipMetricApplication))
    assert application.status == 'pending'
    apply_pending_metrics(db, world_id='response-world')
    state = db.scalar(select(RelationshipState))
    assert state.actor_world_character_id == 'response-responding'
    assert state.target_world_character_id == 'response-requester'
    assert (state.familiarity, state.trust) == (1, 1)
    version = state.version
    stage_chat_metrics(db, request_id=record.request_id, raw=raw, now=now)
    apply_pending_metrics(db, world_id='response-world')
    db.refresh(state)
    assert state.version == version
    assert len(list(db.scalars(select(RelationshipMetricApplication)))) == 1


def test_retained_owner_persona_is_still_a_valid_memory_counterpart(response_session):
    from app.domains.world_characters.models import WorldCharacter
    from app.runtime.memory.source_queries import active_participant_ids
    db = response_session
    old = db.get(WorldCharacter, "response-requester")
    old.status = "inactive"
    db.flush()
    assert list(active_participant_ids(db, [old.id], "response-world")) == [old.id]
    old.control_mode = "autonomous"
    old.owner_user_id = None
    db.flush()
    assert list(active_participant_ids(db, [old.id], "response-world")) == []


import pytest

@pytest.mark.parametrize("thought_enabled", [True, False])
@pytest.mark.parametrize("metadata", [None, {"invalid": True}])
def test_crg_relation_metadata_does_not_regenerate_valid_text(monkeypatch, thought_enabled, metadata):
    import asyncio
    from app.integrations import direct_llm
    from app.integrations.llm.character_response_generator import DirectLlmCharacterResponseGenerator
    from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
    from app.domains.chat.contracts.character_response_generator import CharacterResponseGeneratorRequest, CharacterResponseProfile
    from chat.test_p8_l_p_high_reasoning_hotfix import _current_context_evidence
    calls=[]
    async def generate(**kwargs):
        calls.append(kwargs)
        return direct_llm.DirectLlmResponse(text="",parsed={"text":"함께 해보자.","relationship_metrics":metadata},usage={},finish_reason="STOP")
    monkeypatch.setattr(direct_llm,"generate_text",generate)
    credential=CredentialMaterial(credential_id="test",provider="google",model="gemini-3.1-flash-lite",fingerprint="test",purpose=CredentialPurpose.MESSAGE_LLM,_secret="fake")
    request=CharacterResponseGeneratorRequest(user_message="함께할래?",profile=CharacterResponseProfile(*(["캐릭터"]*8)),recent_context=(),evidence=_current_context_evidence())
    result=asyncio.run(DirectLlmCharacterResponseGenerator(credential,thought_enabled=thought_enabled,relationship_enabled=True).generate(request))
    assert result.text == "함께 해보자."
    assert len(calls) == 1
    assert "recent_context" in calls[0]["user_prompt"]
    if not thought_enabled:
        assert result.activity_thought is None
        assert "thought" not in calls[0]["response_schema"]["required"]
