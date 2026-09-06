"""Direct durable response commands retain scope, fencing and replay semantics."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.compatibility.chat_generation_lifecycle import GenerationLifecycleService
from app.domains.chat import models, schemas
from app.domains.chat.contracts import GenerationContractError, ResponseRequestState
from app.domains.chat.repository.response_lifecycle import (
    SqlAlchemyResponseLifecycleRepository,
)
from app.runtime.chat import world_generation
from app.runtime.chat.message_composition import thread_service
from chat.test_p8_l_d_world_chat_identity import (
    _character,
    _create_tables,
    _installation,
    _seed_world,
    _user,
)
from chat.test_p8_l_j_response_generation_lifecycle import (
    _commit_payload,
    _fence,
    _ready_to_commit,
    response_session,
)


def test_http_generation_accept_and_replay_use_the_durable_owner(monkeypatch) -> None:
    def old_wrapper_must_not_run(*args, **kwargs):
        raise AssertionError("Production generation used its retired forwarding layer")

    monkeypatch.setattr(
        GenerationLifecycleService, "__init__", old_wrapper_must_not_run
    )
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    try:
        with Session(engine) as db:
            owner = _user("direct-owner")
            other = _user("direct-other")
            requester = _character("direct-requester", owner.id)
            responder = _character("direct-responder", other.id)
            db.add_all([owner, other, _installation(owner.id), requester, responder])
            db.flush()
            _, responding = _seed_world(
                db,
                owner=owner,
                responder_owner=other,
                world_id="direct-world",
                requester_character=requester,
                responding_character=responder,
                suffix="direct",
            )
            db.commit()
            result = thread_service.create_or_get_world_thread(
                db,
                owner,
                "direct-world",
                schemas.WorldChatThreadCreate(
                    responding_world_character_id=responding.id
                ),
            )
            data = schemas.WorldChatMessageCreate(
                content="Keep this accepted message exactly once.",
                idempotency_key="direct-request-idempotency",
            )
            first = world_generation.accept_world_message(
                db, owner, "direct-world", result.thread.id, data
            )
            replay = world_generation.accept_world_message(
                db, owner, "direct-world", result.thread.id, data
            )
            assert first.outcome == "accepted"
            assert replay.outcome == "replayed"
            assert first.user_message.id == replay.user_message.id
            assert (
                first.response_request.request_id == replay.response_request.request_id
            )
            assert db.scalar(select(func.count(models.MessageMessage.id))) == 1
            assert (
                db.scalar(select(func.count(models.ChatResponseRequest.request_id)))
                == 1
            )
    finally:
        engine.dispose()


def test_direct_finalize_keeps_fence_rejection_and_exactly_one_committed_reply(
    response_session: Session,
) -> None:
    now = datetime.now(UTC)
    repository = SqlAlchemyResponseLifecycleRepository(response_session)
    record = _ready_to_commit(repository, now)
    fence = _fence(record)
    payload = _commit_payload(record)
    bad_fence = replace(fence, lease_generation=fence.lease_generation + 1)
    before = response_session.scalar(select(func.count(models.MessageMessage.id)))

    with pytest.raises(GenerationContractError, match="finalize_fence_conflict"):
        repository.finalize(bad_fence, payload, now=now + timedelta(seconds=1))
    assert (
        response_session.scalar(select(func.count(models.MessageMessage.id))) == before
    )

    committed = repository.finalize(fence, payload, now=now + timedelta(seconds=2))
    response_session.commit()
    replay = repository.finalize(fence, payload, now=now + timedelta(seconds=3))
    assert committed.state is ResponseRequestState.COMMITTED
    assert committed.committed_assistant_message_id is not None
    assert (
        replay.committed_assistant_message_id
        == committed.committed_assistant_message_id
    )
    assert (
        response_session.scalar(select(func.count(models.MessageMessage.id)))
        == before + 1
    )
