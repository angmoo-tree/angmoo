from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine

from app import models as _models  # noqa: F401 - register canonical metadata
from app.domains.chat.api.schemas import WorldChatThreadModelUpdate
from app.domains.chat.domain.model_binding import MessageModelBindingMode
from app.providers.gemini import build_generate_content_config
from app.runtime.chat import world_generation
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.migrations.sqlite_versions.v6_to_v7_chat_model_binding import (
    capture_v6_to_v7_delta,
    upgrade_v6_to_v7,
    verify_v6_to_v7_delta,
)
from app.runtime.persistence.sqlite_schema import (
    build_sqlite_v6_metadata,
    create_schema_version_table,
    sqlite_schema_contract_digest,
)


def _thinking_payload(model: str, level: str | None = "low") -> dict[str, object]:
    config = build_generate_content_config(
        model=model,
        system_prompt="hotfix contract",
        max_output_tokens=64,
        response_mime_type=None,
        response_schema=None,
        thinking_level=level,
    )
    return config.model_dump(exclude_none=True).get("thinking_config", {})


def test_gemini_thinking_config_is_serialized_by_model_family() -> None:
    assert _thinking_payload("gemini-3.1-flash-lite") == {
        "thinking_level": "LOW"
    }
    assert _thinking_payload("gemini-2.5-flash-lite") == {
        "thinking_budget": 0
    }
    assert _thinking_payload("gemini-2.5-flash") == {"thinking_budget": 0}
    assert _thinking_payload("gemma-4-26b-a4b-it") == {}


def test_unknown_thinking_family_fails_before_provider_io() -> None:
    with pytest.raises(ValueError, match="unsupported_gemini_thinking_model_family"):
        _thinking_payload("future-model-without-a-policy")


def test_structured_json_and_family_thinking_config_serialize_together() -> None:
    config = build_generate_content_config(
        model="gemini-2.5-flash-lite",
        system_prompt="hotfix contract",
        max_output_tokens=64,
        response_mime_type="application/json",
        response_schema={
            "type": "object",
            "properties": {"route": {"type": "string"}},
            "required": ["route"],
        },
        thinking_level="low",
    ).model_dump(exclude_none=True)
    assert config["thinking_config"] == {"thinking_budget": 0}
    assert config["response_json_schema"]["required"] == ["route"]


def test_world_thread_model_update_contract_is_closed() -> None:
    default = WorldChatThreadModelUpdate(mode="default")
    override = WorldChatThreadModelUpdate(
        mode="thread_override",
        selected_model="gemini-3.1-flash-lite",
    )
    assert default.mode is MessageModelBindingMode.DEFAULT
    assert default.selected_model is None
    assert override.mode is MessageModelBindingMode.THREAD_OVERRIDE
    assert override.selected_model == "gemini-3.1-flash-lite"

    with pytest.raises(ValidationError, match="default binding cannot include"):
        WorldChatThreadModelUpdate(
            mode="default",
            selected_model="gemini-2.5-flash-lite",
        )
    with pytest.raises(ValidationError, match="thread_override requires"):
        WorldChatThreadModelUpdate(mode="thread_override")


def test_generation_acceptance_locks_thread_before_model_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = object()
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        world_generation.sqlalchemy_service,
        "_require_world_chat_owner_scope",
        lambda *_args, **_kwargs: None,
    )

    def get_owned_thread(
        _db: object,
        _user: object,
        _world_id: str,
        _thread_id: str,
        *,
        lock_thread: bool = False,
    ) -> object:
        observed["lock_thread"] = lock_thread
        return thread

    monkeypatch.setattr(
        world_generation.sqlalchemy_service,
        "_get_owned_world_thread",
        get_owned_thread,
    )
    monkeypatch.setattr(
        world_generation.sqlalchemy_service,
        "_world_thread_read",
        lambda *_args, **_kwargs: None,
    )

    assert world_generation._mutation_thread(
        object(),
        SimpleNamespace(id="owner"),
        "world-a",
        "thread-a",
    ) is thread
    assert observed == {"lock_thread": True}


def test_v6_to_v7_backfills_only_resolved_threads_to_default_binding() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        create_schema_version_table(connection)
        metadata = build_sqlite_v6_metadata()
        metadata.create_all(connection)
        now = datetime.now(UTC)
        connection.execute(
            metadata.tables["users"].insert(),
            [
                {"id": "owner-with-preference", "display_name": "Owner A"},
                {"id": "owner-without-preference", "display_name": "Owner B"},
            ],
        )
        connection.execute(
            metadata.tables["user_message_preferences"].insert().values(
                user_id="owner-with-preference",
                default_model="gemini-3.1-flash-lite",
            )
        )
        connection.execute(
            metadata.tables["message_threads"].insert(),
            [
                {
                    "id": "resolved-preference",
                    "requester_id": "owner-with-preference",
                    "character_id": "character-a",
                    "world_id": "world-a",
                    "requester_world_character_id": "requester-a",
                    "responding_world_character_id": "responding-a",
                    "world_scope_status": "resolved",
                    "selected_model": "gemini-2.5-flash-lite",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": "resolved-no-preference",
                    "requester_id": "owner-without-preference",
                    "character_id": "character-b",
                    "world_id": "world-b",
                    "requester_world_character_id": "requester-b",
                    "responding_world_character_id": "responding-b",
                    "world_scope_status": "resolved",
                    "selected_model": "gemini-2.5-flash",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": "ambiguous-preserved",
                    "requester_id": "owner-with-preference",
                    "character_id": "character-c",
                    "world_id": None,
                    "requester_world_character_id": None,
                    "responding_world_character_id": None,
                    "world_scope_status": "ambiguous",
                    "selected_model": "gemini-2.5-flash-lite",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        connection.execute(
            metadata.tables["message_messages"].insert().values(
                id=1,
                thread_id="resolved-preference",
                role="user",
                content="실패 attempt의 원문",
                status="ok",
                created_at=now,
            )
        )
        connection.execute(
            metadata.tables["chat_response_requests"].insert().values(
                request_id="historical-failed-attempt",
                thread_id="resolved-preference",
                user_message_id=1,
                response_slot_id="historical-response-slot",
                request_scope_hash="b" * 64,
                idempotency_key="historical-idempotency",
                generation_id="historical-generation",
                attempt_number=1,
                selected_model="gemini-2.5-flash-lite",
                state="failed",
                terminal_reason="provider_failure",
                terminal_at=now,
                retryable=True,
                deadline_at=now,
                created_at=now,
                updated_at=now,
            )
        )

        snapshot = capture_v6_to_v7_delta(connection)
        upgrade_v6_to_v7(connection)
        verify_v6_to_v7_delta(connection, snapshot)

        rows = {
            row[0]: (row[1], row[2])
            for row in connection.exec_driver_sql(
                "SELECT id, selected_model, model_binding_mode "
                "FROM message_threads ORDER BY id"
            )
        }
        assert rows == {
            "ambiguous-preserved": (
                "gemini-2.5-flash-lite",
                "thread_override",
            ),
            "resolved-no-preference": ("gemini-2.5-flash", "default"),
            "resolved-preference": ("gemini-3.1-flash-lite", "default"),
        }
        assert connection.exec_driver_sql(
            "SELECT selected_model FROM chat_response_requests "
            "WHERE request_id = 'historical-failed-attempt'"
        ).scalar_one() == "gemini-2.5-flash-lite"
        assert (
            sqlite_schema_contract_digest(connection)
            == load_sqlite_manifest(7).schema_digest
        )
    engine.dispose()


def test_v6_to_v7_rejects_unknown_resolved_model_without_guessing() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        metadata = build_sqlite_v6_metadata()
        metadata.create_all(connection)
        connection.execute(
            metadata.tables["users"].insert().values(
                id="owner",
                display_name="Owner",
            )
        )
        connection.execute(
            metadata.tables["message_threads"].insert().values(
                id="unsupported-model-thread",
                requester_id="owner",
                character_id="character",
                world_id="world",
                requester_world_character_id="requester",
                responding_world_character_id="responding",
                world_scope_status="resolved",
                selected_model="unsupported-future-model",
            )
        )

        with pytest.raises(
            RuntimeError,
            match="world_chat_default_model_backfill_unsupported",
        ):
            upgrade_v6_to_v7(connection)
        assert "model_binding_mode" not in {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(message_threads)"
            )
        }
    engine.dispose()
