import asyncio
from dataclasses import replace
from sqlalchemy import select
import pytest

from app.contracts.name_binding import read_name_binding
from app.domains.world_characters.service.name_binding import validate_name_binding
from app.domains.chat.schemas import WorldChatMessageCreate
from app.runtime.chat.message_composition import generation_service
from app.domains.chat.repository.response_lifecycle import SqlAlchemyResponseLifecycleRepository
from app.domains.chat.contracts.generation_lifecycle import GenerationEventType, ResponseRequestState
from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
from model_fixture_support import models
from tests.characters.name_binding_fixture import rename_profile
from tests.chat.test_p8_l_p_evidence_response_streaming import response_session, _Generator, _MemoryProducer, _workflow, _command, _collect


@pytest.mark.parametrize("invalid", [False, True])
def test_chat_resolves_before_first_delta_and_stream_storage_memory_match(response_session, invalid):
    db = response_session
    owner = db.get(models.User, "p-owner")
    rename_profile(db, "p-world", owner.id, "민식")
    accepted = generation_service.accept_world_message(db, owner, "p-world", "p-thread",
        WorldChatMessageCreate(content="오늘은 어땠어?", idempotency_key="bound-chat-request"))
    repository = SqlAlchemyResponseLifecycleRepository(db)
    record = repository.get_request(accepted.response_request.request_id)
    binding = read_name_binding(record.node_state)
    rename_profile(db, "p-world", owner.id, "민수")
    class Generator(_Generator):
        async def generate(self, request):
            assert "민식" in request.profile.worldview and "민수" not in request.profile.worldview
            assert request.profile.speech_style == "대화 상대: 반가워"
            response = await super().generate(request)
            return replace(response, text="{{getvar::secret}}" if invalid else "{{user}}, 반가워. `{{user}}`는 코드 예시야.")
    memory = _MemoryProducer()
    command = _command(record)
    command = replace(command, profile=replace(command.profile, worldview="{{char}}는 {{user}}의 동료", speech_style="대화 상대: 반가워"),
        name_binding_validator=lambda: validate_name_binding(db, binding, actor=db.get(models.WorldCharacter, "p-responding"), owner_id=owner.id))
    events = asyncio.run(_collect(_workflow(db, RetrievalRoute.CURRENT_CONTEXT, Generator(), memory_producer=memory).run(command)))
    deltas = "".join(event.payload["text"] for event in events if event.event_type is GenerationEventType.DELTA)
    final = repository.get_request(record.request_id)
    assert read_name_binding(final.node_state) == binding
    if invalid:
        assert not deltas and final.state is ResponseRequestState.FAILED and not memory.sources
        return
    assert final.state is ResponseRequestState.COMMITTED
    message = db.get(models.MessageMessage, final.committed_assistant_message_id)
    assert message.content == deltas == "민식, 반가워. `{{user}}`는 코드 예시야."
    assert len(memory.sources) == 1
    assert memory.sources[0].assistant_message_id == message.id


@pytest.mark.parametrize("tail_invalid", [False, True])
def test_raw_thought_port_checks_entire_tail_before_first_delta(response_session, tail_invalid):
    db=response_session
    owner=db.get(models.User,"p-owner")
    rename_profile(db,"p-world",owner.id,"민식")
    accepted=generation_service.accept_world_message(db,owner,"p-world","p-thread",
        WorldChatMessageCreate(content="합성 테스트",idempotency_key="synthetic-thought-port"))
    repository=SqlAlchemyResponseLifecycleRepository(db)
    record=repository.get_request(accepted.response_request.request_id)
    class Generator(_Generator):
        async def generate(self,request):
            response=await super().generate(request)
            assert request.thought_finalizer is not None
            raw="{{user}} " + "한"*350 + ("{{getvar::secret}}" if tail_invalid else "")
            return replace(response,text="Synthetic visible body",activity_thought=request.thought_finalizer(raw))
    generator=Generator(); memory=_MemoryProducer()
    events=asyncio.run(_collect(_workflow(db,RetrievalRoute.CURRENT_CONTEXT,generator,memory_producer=memory).run(_command(record))))
    final=repository.get_request(record.request_id)
    deltas="".join(event.payload["text"] for event in events if event.event_type is GenerationEventType.DELTA)
    assert len(generator.requests)==1
    if tail_invalid:
        assert final.state is ResponseRequestState.FAILED and not deltas and not memory.sources
    else:
        assert final.state is ResponseRequestState.COMMITTED
        message=db.get(models.MessageMessage,final.committed_assistant_message_id)
        assert message.content==deltas=="Synthetic visible body" and len(memory.sources)==1
        from app.domains.chat.models import ChatMessageThought
        thought = db.get(ChatMessageThought, message.id)
        assert thought.thought_text == ("민식 " + "한" * 350)[:280]
        assert thought.status == "recorded" and thought.truncated is True
        assert memory.sources[0].assistant_message_id == message.id
