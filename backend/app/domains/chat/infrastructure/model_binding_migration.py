"""Lossless MessageThread response-model binding migration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import MetaData, text
from sqlalchemy.schema import CreateIndex, CreateTable

from app.core.db import Base
from app.domains.chat.domain.model_binding import MessageModelBindingMode
from app.domains.chat.domain.policies import MESSAGE_MODELS
from app.domains.chat.infrastructure.world_scope_migration import (
    add_world_scoped_message_threads_v4_table,
)


MESSAGE_THREAD_V6_COLUMNS = (
    "id",
    "requester_id",
    "character_id",
    "world_id",
    "requester_world_character_id",
    "responding_world_character_id",
    "world_scope_status",
    "selected_model",
    "response_lease_token",
    "response_lease_expires_at",
    "last_message_at",
    "deleted_at",
    "created_at",
    "updated_at",
)


@dataclass(frozen=True)
class ModelBindingBackfillStats:
    total: int
    default_bound: int
    override_bound: int


def rebuild_and_backfill_message_threads_v7(connection) -> ModelBindingBackfillStats:
    """Rebuild embedded v6 threads and bind resolved World chats to defaults."""

    _require_sqlite_rebuild_precondition(connection)
    validate_resolved_default_models(connection)
    total = int(
        connection.exec_driver_sql("SELECT count(*) FROM message_threads").scalar_one()
    )
    default_bound = int(
        connection.exec_driver_sql(
            "SELECT count(*) FROM message_threads "
            "WHERE world_scope_status = 'resolved'"
        ).scalar_one()
    )
    connection.exec_driver_sql("PRAGMA defer_foreign_keys = ON")
    connection.exec_driver_sql("PRAGMA legacy_alter_table = ON")
    try:
        connection.exec_driver_sql(
            "ALTER TABLE message_threads RENAME TO message_threads_v6"
        )
        metadata = MetaData()
        for table_name in ("characters", "users", "worlds", "world_characters"):
            Base.metadata.tables[table_name].to_metadata(metadata)
        target = Base.metadata.tables["message_threads"].to_metadata(metadata)
        connection.execute(CreateTable(target))
        target_column_names: list[str] = []
        selected_expressions: list[str] = []
        for column in MESSAGE_THREAD_V6_COLUMNS:
            target_column_names.append(column)
            if column == "selected_model":
                selected_expressions.append(
                    "CASE WHEN thread.world_scope_status = 'resolved' THEN "
                    "COALESCE(preference.default_model, thread.selected_model) "
                    "ELSE thread.selected_model END"
                )
                target_column_names.append("model_binding_mode")
                selected_expressions.append(
                    "CASE WHEN thread.world_scope_status = 'resolved' THEN "
                    "'default' ELSE 'thread_override' END"
                )
            else:
                # Every legacy column must be qualified because the preference
                # join also exposes created_at/updated_at.
                selected_expressions.append(f"thread.{column}")
        target_columns = ", ".join(target_column_names)
        selected_columns = ", ".join(selected_expressions)
        connection.execute(
            text(
                "INSERT INTO message_threads ("
                f"{target_columns}) SELECT {selected_columns} "
                "FROM message_threads_v6 AS thread "
                "LEFT JOIN user_message_preferences AS preference "
                "ON preference.user_id = thread.requester_id"
            )
        )
        connection.exec_driver_sql("DROP TABLE message_threads_v6")
        for index in sorted(target.indexes, key=lambda item: item.name or ""):
            connection.execute(CreateIndex(index))
    finally:
        connection.exec_driver_sql("PRAGMA legacy_alter_table = OFF")
    return ModelBindingBackfillStats(
        total=total,
        default_bound=default_bound,
        override_bound=total - default_bound,
    )


def rebuild_message_threads_v6(connection) -> None:
    """Restore the immutable pre-model-binding MessageThread shape."""

    _require_sqlite_rebuild_precondition(connection)
    metadata = MetaData()
    for table_name in sorted(Base.metadata.tables):
        if table_name == "message_threads":
            continue
        Base.metadata.tables[table_name].to_metadata(metadata)
    target = add_world_scoped_message_threads_v4_table(metadata)
    connection.exec_driver_sql("PRAGMA defer_foreign_keys = ON")
    connection.exec_driver_sql("PRAGMA legacy_alter_table = ON")
    try:
        connection.exec_driver_sql(
            "ALTER TABLE message_threads RENAME TO message_threads_v7"
        )
        connection.execute(CreateTable(target))
        columns = ", ".join(MESSAGE_THREAD_V6_COLUMNS)
        connection.exec_driver_sql(
            f"INSERT INTO message_threads ({columns}) "
            f"SELECT {columns} FROM message_threads_v7"
        )
        connection.exec_driver_sql("DROP TABLE message_threads_v7")
        for index in sorted(target.indexes, key=lambda item: item.name or ""):
            connection.execute(CreateIndex(index))
    finally:
        connection.exec_driver_sql("PRAGMA legacy_alter_table = OFF")


def expected_model_bindings(
    connection,
    rows: list[dict[str, Any]],
) -> dict[str, tuple[str, str]]:
    preferences = {
        str(row["user_id"]): str(row["default_model"])
        for row in connection.exec_driver_sql(
            "SELECT user_id, default_model FROM user_message_preferences"
        ).mappings()
    }
    return {
        str(row["id"]): (
            (
                preferences.get(str(row["requester_id"]), str(row["selected_model"]))
                if row["world_scope_status"] == "resolved"
                else str(row["selected_model"])
            ),
            (
                MessageModelBindingMode.DEFAULT.value
                if row["world_scope_status"] == "resolved"
                else MessageModelBindingMode.THREAD_OVERRIDE.value
            ),
        )
        for row in rows
    }


def validate_resolved_default_models(connection) -> None:
    allowed = tuple(MESSAGE_MODELS)
    placeholders = ", ".join(f":model_{index}" for index in range(len(allowed)))
    parameters = {
        **{f"model_{index}": model for index, model in enumerate(allowed)},
    }
    invalid = connection.execute(
        text(
            "SELECT thread.id FROM message_threads AS thread "
            "LEFT JOIN user_message_preferences AS preference "
            "ON preference.user_id = thread.requester_id "
            "WHERE thread.world_scope_status = 'resolved' "
            "AND COALESCE(preference.default_model, thread.selected_model) "
            f"NOT IN ({placeholders}) LIMIT 1"
        ),
        parameters,
    ).first()
    if invalid is not None:
        raise RuntimeError("world_chat_default_model_backfill_unsupported")


def _require_sqlite_rebuild_precondition(connection) -> None:
    enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
    if int(enabled) != 0:
        raise RuntimeError(
            "sqlite_model_binding_rebuild_requires_foreign_keys_off_before_transaction"
        )


__all__ = [
    "MESSAGE_THREAD_V6_COLUMNS",
    "ModelBindingBackfillStats",
    "expected_model_bindings",
    "rebuild_and_backfill_message_threads_v7",
    "rebuild_message_threads_v6",
    "validate_resolved_default_models",
]
