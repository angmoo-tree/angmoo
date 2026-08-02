from __future__ import annotations

import asyncio
import inspect

import httpx
import pytest

from app import models
from app.main import app as private_app
from app.public_main import app as public_app
from app.services import agent_runs as agent_run_service


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
