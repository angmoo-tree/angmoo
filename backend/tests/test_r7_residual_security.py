from __future__ import annotations

import asyncio
import inspect

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.main import app as private_app
from app.public_main import app as public_app
from app.services import agent_runs as agent_run_service
from app.services import messages as message_service


@pytest.mark.parametrize("app", [private_app, public_app])
def test_resident_slot_assignment_is_not_exposed_over_http(
    app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def _unexpected_assignment(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("resident slot assignment must remain internal")

    monkeypatch.setattr(
        agent_run_service,
        "assign_resident_slot",
        _unexpected_assignment,
    )

    async def _post() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/agent-runs/resident-slots/assign",
                json={
                    "user_id": "user-attacker",
                    "character_id": "char-attacker",
                    "credential_id": "cred-attacker",
                    "agent_id": "attacker-controlled-slot",
                },
            )

    response = asyncio.run(_post())

    assert response.status_code in {404, 405}
    assert called is False


def test_internal_assignment_does_not_accept_caller_selected_agent_id() -> None:
    parameters = inspect.signature(agent_run_service.assign_resident_slot).parameters

    assert "data" not in parameters
    assert "agent_id" not in parameters
    assert "agent_ids" not in parameters


def test_agent_slot_has_one_non_null_assignment_per_character() -> None:
    indexes = {index.name: index for index in models.AgentSlot.__table__.indexes}
    index = indexes["uq_agent_slots_assigned_character_not_null"]

    assert index.unique is True
    assert [column.name for column in index.columns] == ["assigned_character_id"]
    assert "assigned_character_id IS NOT NULL" in str(
        index.dialect_options["postgresql"]["where"]
    )


def test_message_thread_response_lease_contract() -> None:
    columns = models.MessageThread.__table__.columns
    constraints = {
        constraint.name for constraint in models.MessageThread.__table__.constraints
    }

    assert "response_lease_token" in columns
    assert "response_lease_expires_at" in columns
    assert "ck_message_threads_response_lease_pair" in constraints


def test_message_response_lease_rejects_second_session_and_is_token_scoped(
    tmp_path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'message-lease.db'}")
    models.User.__table__.create(engine)
    models.Character.__table__.create(engine)
    models.MessageThread.__table__.create(engine)

    with Session(engine) as db:
        user = models.User(
            id="user-lease",
            email="lease@example.test",
            display_name="lease",
            profile_setup_completed=True,
        )
        character = models.Character(
            id="char-lease",
            owner_id=user.id,
            name="lease",
            handle="lease",
            one_liner="",
            personality="curious",
            speech_style="friendly",
            worldview="angmoo",
            topic_preferences="daily",
            safety_rules="be kind",
            execution_mode="llm",
            persona_summary="message lease fixture",
        )
        thread = models.MessageThread(
            id="thread-lease",
            requester_id=user.id,
            character_id=character.id,
            selected_model=message_service.DEFAULT_MESSAGE_MODEL,
        )
        db.add_all([user, character, thread])
        db.commit()

    with Session(engine) as first, Session(engine) as second:
        first_user = first.get(models.User, "user-lease")
        second_user = second.get(models.User, "user-lease")
        assert first_user is not None and second_user is not None

        token = message_service._acquire_response_lease(
            first,
            first_user,
            "thread-lease",
        )
        with pytest.raises(message_service.MessageInFlightError):
            message_service._acquire_response_lease(
                second,
                second_user,
                "thread-lease",
            )

        message_service._release_response_lease(
            first,
            "thread-lease",
            "stale-token",
        )
        with pytest.raises(message_service.MessageInFlightError):
            message_service._acquire_response_lease(
                second,
                second_user,
                "thread-lease",
            )

        message_service._release_response_lease(first, "thread-lease", token)
        replacement = message_service._acquire_response_lease(
            second,
            second_user,
            "thread-lease",
        )
        assert replacement != token
