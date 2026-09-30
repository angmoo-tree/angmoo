import asyncio
import json

import pytest
from sqlalchemy import select, func

from app.config import Settings
from app.domains.chat.contracts import RetrievalRoute, ResponseRequestState, GenerationEventType
from app.domains.chat.exceptions import MessageValidationError
from app.domains.chat.models import MessageMessage, MessageAttachment, ChatResponseRequest
from app.domains.chat.schemas import WorldChatMessageCreate
from app.domains.media.models import InterpretationSetting
from app.domains.media.generation_contracts import ImagePreparationError
from image_integration.chat_support import synthetic_chat
from image_integration.test_interpretation import FakeInterpreter, pixels


def upload(chat, *, scope=None):
    with chat.sessions() as db:
        row = chat.media.assets.upload(db, owner_id=chat.owner.id, scope_kind="thread",
            scope_id=scope or chat.thread_id, content_type="image/png", content=pixels())
        identity = row.id
        db.commit()
        return identity


async def stream(chat, request):
    return [event async for event in chat.generation.stream_world_response(chat.db, chat.owner,
        chat.world_id, chat.thread_id, request, memory_recall_service=object(),
        runtime_settings=Settings(graph_projection_enabled=False))]


@pytest.mark.parametrize("body", ["", "이 사진을 설명해 줘."])
@pytest.mark.parametrize("route", [RetrievalRoute.CURRENT_CONTEXT, RetrievalRoute.CANONICAL])
def test_image_only_and_text_image_reach_real_workflow_after_analysis(tmp_path, body, route):
    fake = FakeInterpreter()
    chat = synthetic_chat(tmp_path, fake, route=route)
    try:
        asset = upload(chat)
        data = WorldChatMessageCreate(content=body, attachment_asset_id=asset, idempotency_key="synthetic-message-001")
        accepted = chat.generation.accept_world_message(chat.db, chat.owner, chat.world_id, chat.thread_id, data)
        assert fake.calls == 0
        replayed = chat.generation.accept_world_message(chat.db, chat.owner, chat.world_id, chat.thread_id, data)
        assert replayed.outcome == "replayed" and replayed.user_message.id == accepted.user_message.id
        result = asyncio.run(stream(chat, accepted.response_request.request_id))
        assert result[-1].event_type == GenerationEventType.COMPLETED, (result[-1].payload, chat.events)
        assert fake.calls == 1 and chat.events == ["workflow_build", "router", "crg"]
        assert "파란색 직사각형" in chat.commands[0].preflight.image_context
        assert chat.db.get(MessageMessage, accepted.user_message.id).content == body
        assert chat.db.get(ChatResponseRequest, accepted.response_request.request_id).state == "committed"
        attachment = chat.db.get(MessageAttachment, accepted.user_message.id)
        assert attachment.interpretation_id and json.loads(attachment.snapshot_json)["source"] == "actual_image_analysis"
        assert chat.generator.requests[0].evidence.items[0].kind.value == "current_image_analysis"
    finally:
        chat.source.close()


def test_off_without_cache_rejects_image_admission_and_preserves_draft(tmp_path):
    chat = synthetic_chat(tmp_path, FakeInterpreter())
    try:
        identity = upload(chat)
        chat.db.get(InterpretationSetting, chat.owner.id).enabled = False
        chat.db.commit()
        with pytest.raises(MessageValidationError, match="disabled"):
            chat.generation.accept_world_message(chat.db, chat.owner, chat.world_id, chat.thread_id,
                WorldChatMessageCreate(content="", attachment_asset_id=identity, idempotency_key="synthetic-message-001"))
        chat.db.rollback()
        assert chat.db.scalar(select(func.count()).select_from(MessageAttachment)) == 0
        assert chat.media.assets.owned(chat.db, owner_id=chat.owner.id, asset_id=identity).state == "draft"
    finally:
        chat.source.close()


def test_analysis_failure_never_starts_router_and_preserves_user_message(tmp_path):
    class Failed(FakeInterpreter):
        async def analyze(self, **kwargs):
            self.calls += 1
            raise ValueError("synthetic-invalid-output")
    fake = Failed()
    chat = synthetic_chat(tmp_path, fake)
    try:
        identity = upload(chat)
        accepted = chat.generation.accept_world_message(chat.db, chat.owner, chat.world_id, chat.thread_id,
            WorldChatMessageCreate(content="본문", attachment_asset_id=identity, idempotency_key="synthetic-message-001"))
        events = asyncio.run(stream(chat, accepted.response_request.request_id))
        assert events[-1].event_type == GenerationEventType.FAILED and events[-1].payload["retryable"]
        assert chat.events == [] and fake.calls == 1
        assert chat.db.get(MessageMessage, accepted.user_message.id).content == "본문"
        assert chat.db.get(ChatResponseRequest, accepted.response_request.request_id).state == "failed"
    finally:
        chat.source.close()


def test_attachment_evidence_is_rejected_after_file_replacement(tmp_path):
    chat = synthetic_chat(tmp_path, FakeInterpreter())
    try:
        identity = upload(chat)
        accepted = chat.generation.accept_world_message(chat.db, chat.owner, chat.world_id, chat.thread_id,
            WorldChatMessageCreate(content="", attachment_asset_id=identity, idempotency_key="synthetic-message-001"))
        observation = asyncio.run(chat.generation.images.observation(chat.db, chat.owner.id, chat.thread_id, accepted.user_message.id))
        evidence = chat.generation.images.evidence(chat.owner.id, chat.thread_id, observation)
        asset = chat.media.assets.owned(chat.db, owner_id=chat.owner.id, asset_id=identity)
        chat.media.assets.path(asset).write_bytes(b"replacement")
        from app.domains.media.contracts import InvalidProfileMediaError
        with pytest.raises(InvalidProfileMediaError, match="changed"):
            chat.generation.images.assert_current(chat.db, chat.owner.id, chat.thread_id, accepted.user_message.id, evidence)
    finally:
        chat.source.close()


@pytest.mark.parametrize("analysis_fails", [False, True])
def test_cancellation_during_analysis_preserves_terminal_state_and_never_routes(tmp_path, analysis_fails):
    from datetime import datetime, timezone
    from app.domains.chat.repository.response_lifecycle import SqlAlchemyResponseLifecycleRepository
    class Cancelling(FakeInterpreter):
        async def analyze(self, **kwargs):
            with chat.sessions() as session:
                repository = SqlAlchemyResponseLifecycleRepository(session)
                row = repository.get_request(request_id)
                repository.request_cancel(request_id=request_id, request_scope_hash=row.request_scope_hash,
                    now=datetime.now(timezone.utc))
                session.commit()
            if analysis_fails:
                self.calls += 1
                raise ValueError("synthetic-analysis-failure-after-cancel")
            return await super().analyze(**kwargs)
    fake = Cancelling()
    chat = synthetic_chat(tmp_path, fake)
    try:
        asset = upload(chat)
        accepted = chat.generation.accept_world_message(chat.db, chat.owner, chat.world_id, chat.thread_id,
            WorldChatMessageCreate(content="keep this message", attachment_asset_id=asset, idempotency_key="synthetic-cancel-001"))
        request_id = accepted.response_request.request_id
        events = asyncio.run(stream(chat, request_id))
        assert events[-1].event_type == GenerationEventType.FAILED
        assert events[-1].payload["failure_class"] == "user_cancelled"
        assert chat.events == [] and fake.calls == 1
        assert chat.db.get(ChatResponseRequest, request_id).state == "cancelled"
        assert chat.db.get(MessageMessage, accepted.user_message.id).content == "keep this message"
    finally:
        chat.source.close()


def test_scope_revocation_during_analysis_never_routes(tmp_path):
    from datetime import datetime, timezone
    from app.domains.chat.models import MessageThread
    class Revoking(FakeInterpreter):
        async def analyze(self, **kwargs):
            with chat.sessions() as session:
                session.get(MessageThread, chat.thread_id).deleted_at = datetime.now(timezone.utc)
                session.commit()
            return await super().analyze(**kwargs)
    fake = Revoking()
    chat = synthetic_chat(tmp_path, fake)
    try:
        asset = upload(chat)
        accepted = chat.generation.accept_world_message(chat.db, chat.owner, chat.world_id, chat.thread_id,
            WorldChatMessageCreate(content="keep", attachment_asset_id=asset, idempotency_key="synthetic-revoke-001"))
        events = asyncio.run(stream(chat, accepted.response_request.request_id))
        assert events[-1].event_type == GenerationEventType.FAILED
        assert chat.events == [] and fake.calls == 1
        assert chat.db.get(MessageMessage, accepted.user_message.id).content == "keep"
    finally:
        chat.source.close()


def test_valid_cache_allows_off_admission_and_actual_workflow_without_second_analysis(tmp_path):
    fake = FakeInterpreter()
    chat = synthetic_chat(tmp_path, fake)
    try:
        asset = upload(chat)
        asyncio.run(chat.media.interpretation.interpret(chat.db, chat.owner.id, asset))
        chat.db.get(InterpretationSetting, chat.owner.id).enabled = False
        chat.db.commit()
        assert chat.media.interpretation.preflight(chat.db, chat.owner.id, asset)["reason"] == "cached"
        accepted = chat.generation.accept_world_message(chat.db, chat.owner, chat.world_id, chat.thread_id,
            WorldChatMessageCreate(content="", attachment_asset_id=asset, idempotency_key="synthetic-cache-001"))
        events = asyncio.run(stream(chat, accepted.response_request.request_id))
        assert events[-1].event_type == GenerationEventType.COMPLETED
        assert fake.calls == 1 and chat.events == ["workflow_build", "router", "crg"]
    finally:
        chat.source.close()
