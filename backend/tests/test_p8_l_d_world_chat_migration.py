from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path

import pytest
from sqlalchemy import URL, create_engine, inspect

from app import models as _models  # noqa: F401 - register canonical metadata
from app.domains.chat.infrastructure.world_scope_migration import (
    rebuild_message_threads_v3,
)
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.migrations.sqlite_versions import registry as sqlite_registry
from app.runtime.migrations.embedded_sqlite import (
    SqliteCanonicalUpgradeCoordinator,
    SqliteCanonicalUpgradeError,
)
from app.runtime.migrations.sqlite_versions.v3_to_v4_world_scoped_chat import (
    capture_v3_to_v4_delta,
    upgrade_v3_to_v4,
    verify_v3_to_v4_delta,
)
from app.runtime.migrations.sqlite_versions.contracts import (
    SqliteMigrationDeltaError,
)
from app.runtime.persistence.sqlite_schema import (
    SCHEMA_VERSION_TABLE,
    build_sqlite_v3_metadata,
    create_schema_version_table,
    sqlite_schema_contract_digest,
    sqlite_schema_digest,
)
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_codecs import encode_utc_timestamp


def _seed_predecessor(connection, *, duplicate_thread: bool = False) -> None:
    metadata = build_sqlite_v3_metadata()
    create_schema_version_table(connection)
    metadata.create_all(connection)
    now = datetime.now(UTC)
    connection.execute(
        metadata.tables["users"].insert(),
        [
            {
                "id": "owner",
                "email": "owner@example.test",
                "display_name": "Owner",
                "profile_setup_completed": True,
            },
            {
                "id": "responder-owner",
                "email": "responder@example.test",
                "display_name": "Responder owner",
                "profile_setup_completed": True,
            },
        ],
    )
    connection.execute(
        metadata.tables["installation_identities"].insert().values(
            singleton_key="local-installation",
            installation_id="p8-l-d-migration-fixture",
            owner_user_id="owner",
            bootstrap_state="claimed",
            local_label="P8-L-D migration fixture",
            claimed_at=now,
        )
    )
    connection.execute(
        metadata.tables["characters"].insert(),
        [
            {
                "id": "requester-character",
                "owner_id": "owner",
                "name": "Requester",
                "handle": "requester",
                "persona_summary": "requester",
            },
            {
                "id": "responding-character",
                "owner_id": "responder-owner",
                "name": "Responding",
                "handle": "responding",
                "persona_summary": "responding",
            },
        ],
    )
    connection.execute(
        metadata.tables["worlds"].insert().values(
            id="world-a",
            slug="world-a",
            owner_user_id="owner",
            name="World A",
            contract_version="world-v1",
            contract_hash="a" * 64,
            create_idempotency_key="world-a",
        )
    )
    connection.execute(
        metadata.tables["world_memberships"].insert().values(
            id="membership-a",
            world_id="world-a",
            user_id="owner",
            role="owner",
            status="active",
            joined_at=now,
        )
    )
    connection.execute(
        metadata.tables["world_characters"].insert(),
        [
            {
                "id": "wc-requester",
                "world_id": "world-a",
                "character_id": "requester-character",
                "membership_id": "membership-a",
                "role_key": "no_specific_role",
                "status": "active",
                "control_mode": "owner_controlled",
                "owner_user_id": "owner",
                "autonomous_enabled": False,
            },
            {
                "id": "wc-responding",
                "world_id": "world-a",
                "character_id": "responding-character",
                "membership_id": "membership-a",
                "role_key": "no_specific_role",
                "status": "active",
                "control_mode": "autonomous",
                "owner_user_id": None,
                "autonomous_enabled": True,
            },
        ],
    )
    thread_rows = [
        {
            "id": "thread-a",
            "requester_id": "owner",
            "character_id": "responding-character",
            "selected_model": "gemini-2.5-flash-lite",
            "created_at": now,
            "updated_at": now,
        }
    ]
    if duplicate_thread:
        thread_rows.append(
            {
                "id": "thread-b",
                "requester_id": "owner",
                "character_id": "responding-character",
                "selected_model": "gemini-2.5-flash-lite",
                "created_at": now,
                "updated_at": now,
            }
        )
    connection.execute(metadata.tables["message_threads"].insert(), thread_rows)
    connection.execute(
        metadata.tables["message_messages"].insert().values(
            thread_id="thread-a",
            role="user",
            content="원문은 그대로 보존",
            status="ok",
        )
    )


def test_v3_to_v4_resolves_unique_world_pair_and_preserves_message() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _seed_predecessor(connection)
        snapshot = capture_v3_to_v4_delta(connection)
        upgrade_v3_to_v4(connection)
        verify_v3_to_v4_delta(connection, snapshot)

        thread = connection.exec_driver_sql(
            "SELECT * FROM message_threads WHERE id = 'thread-a'"
        ).mappings().one()
        message = connection.exec_driver_sql(
            "SELECT content, status FROM message_messages WHERE thread_id = 'thread-a'"
        ).one()
        assert thread["world_scope_status"] == "resolved"
        assert thread["world_id"] == "world-a"
        assert thread["requester_world_character_id"] == "wc-requester"
        assert thread["responding_world_character_id"] == "wc-responding"
        assert tuple(message) == ("원문은 그대로 보존", "ok")
        assert list(connection.exec_driver_sql("PRAGMA foreign_key_check")) == []
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(4).schema_digest
    engine.dispose()


def test_v3_to_v4_quarantines_entire_active_tuple_collision_group() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _seed_predecessor(connection, duplicate_thread=True)
        snapshot = capture_v3_to_v4_delta(connection)
        upgrade_v3_to_v4(connection)
        verify_v3_to_v4_delta(connection, snapshot)
        rows = list(
            connection.exec_driver_sql(
                "SELECT id, world_scope_status, world_id FROM message_threads ORDER BY id"
            )
        )
        assert rows == [
            ("thread-a", "quarantined", None),
            ("thread-b", "quarantined", None),
        ]
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM message_messages"
        ).scalar_one() == 1
    engine.dispose()


def test_lossless_v4_to_v3_rollback_removes_binding_only() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _seed_predecessor(connection)
        upgrade_v3_to_v4(connection)
        rebuild_message_threads_v3(
            connection, create_legacy_unique_index=False
        )
        columns = {column["name"] for column in inspect(connection).get_columns("message_threads")}
        assert "world_id" not in columns
        assert "world_scope_status" not in columns
        assert connection.exec_driver_sql(
            "SELECT content FROM message_messages WHERE thread_id = 'thread-a'"
        ).scalar_one() == "원문은 그대로 보존"
    engine.dispose()


def test_alembic_style_v4_to_v3_rollback_restores_legacy_indexes() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _seed_predecessor(connection)
        upgrade_v3_to_v4(connection)
        rebuild_message_threads_v3(connection, create_legacy_unique_index=True)

        indexes = {
            index["name"]
            for index in inspect(connection).get_indexes("message_threads")
        }
        assert "uq_message_threads_active_requester_character" in indexes
        assert "ix_message_threads_requester_last" in indexes
    engine.dispose()


def test_v3_to_v4_rebuild_refuses_fk_enabled_connection_before_ddl() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _seed_predecessor(connection)

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        connection.commit()
        with connection.begin():
            with pytest.raises(
                RuntimeError,
                match=(
                    "sqlite_world_chat_rebuild_requires_foreign_keys_off_"
                    "before_transaction"
                ),
            ):
                upgrade_v3_to_v4(connection)

        columns = {
            column["name"]
            for column in inspect(connection).get_columns("message_threads")
        }
        assert "world_id" not in columns
        assert "message_threads_v3" not in inspect(connection).get_table_names()
        assert connection.exec_driver_sql(
            "SELECT content FROM message_messages WHERE thread_id = 'thread-a'"
        ).scalar_one() == "원문은 그대로 보존"
        assert list(connection.exec_driver_sql("PRAGMA foreign_key_check")) == []
    engine.dispose()


def test_v4_to_v3_rebuild_refuses_fk_enabled_connection_before_ddl() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _seed_predecessor(connection)
        upgrade_v3_to_v4(connection)

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        connection.commit()
        with connection.begin():
            with pytest.raises(
                RuntimeError,
                match=(
                    "sqlite_world_chat_rebuild_requires_foreign_keys_off_"
                    "before_transaction"
                ),
            ):
                rebuild_message_threads_v3(connection)

        columns = {
            column["name"]
            for column in inspect(connection).get_columns("message_threads")
        }
        assert "world_id" in columns
        assert "message_threads_v4" not in inspect(connection).get_table_names()
        assert connection.exec_driver_sql(
            "SELECT content FROM message_messages WHERE thread_id = 'thread-a'"
        ).scalar_one() == "원문은 그대로 보존"
        assert list(connection.exec_driver_sql("PRAGMA foreign_key_check")) == []
    engine.dispose()


def test_v3_to_v4_failure_keeps_active_generation_and_removes_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "p8-l-d-failed-migration"
    generation = "p8-l-d-v3"
    source = (
        root
        / "canonical"
        / "generations"
        / generation
        / "angmoo.sqlite3"
    )
    source.parent.mkdir(parents=True)
    engine = create_engine(URL.create("sqlite+pysqlite", database=str(source)))
    with engine.begin() as connection:
        _seed_predecessor(connection)
        manifest = load_sqlite_manifest(3)
        connection.exec_driver_sql(
            f"INSERT INTO {SCHEMA_VERSION_TABLE} ("
            "singleton_key, schema_version, source_revision, "
            "source_migration_count, schema_digest, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            (
                1,
                manifest.schema_version,
                manifest.source_revision,
                manifest.source_migration_count,
                sqlite_schema_digest(connection),
                encode_utc_timestamp(datetime.now(UTC)),
            ),
        )
    engine.dispose()
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    original = sqlite_registry.MIGRATIONS[3]

    def fail_after_rebuild(connection) -> None:
        original(connection)
        raise RuntimeError("injected_after_v4_rebuild")

    monkeypatch.setitem(sqlite_registry.MIGRATIONS, 3, fail_after_rebuild)
    with pytest.raises(SqliteCanonicalUpgradeError, match="step_failed"):
        SqliteCanonicalUpgradeCoordinator(
            StaticRuntimeDataPath(root),
            fallback_generation=generation,
        ).upgrade()

    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
    assert not (root / "canonical" / "current-generation.json").exists()
    assert not list((root / "canonical" / "generations").glob(".*.tmp-*"))
    engine = create_engine(URL.create("sqlite+pysqlite", database=str(source)))
    with engine.connect() as connection:
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("message_threads")
        }
        assert "world_id" not in columns
        assert connection.exec_driver_sql(
            "SELECT content FROM message_messages WHERE thread_id = 'thread-a'"
        ).scalar_one() == "원문은 그대로 보존"
    engine.dispose()


def test_v3_to_v4_verifier_rejects_undeclared_legacy_column_mutation() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _seed_predecessor(connection)
        snapshot = capture_v3_to_v4_delta(connection)
        upgrade_v3_to_v4(connection)
        connection.exec_driver_sql(
            "UPDATE message_threads SET selected_model = 'tampered-model' "
            "WHERE id = 'thread-a'"
        )
        with pytest.raises(
            SqliteMigrationDeltaError,
            match="sqlite_migration_expected_delta_mismatch",
        ):
            verify_v3_to_v4_delta(connection, snapshot)
    engine.dispose()


def test_v4_to_v3_refusal_keeps_v4_schema_and_messages_intact() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _seed_predecessor(connection)
        upgrade_v3_to_v4(connection)
        # Simulate two active World-scoped rows which cannot both fit the old
        # requester+Character uniqueness. The refusal must run before DDL.
        connection.exec_driver_sql(
            "DROP INDEX uq_message_threads_active_world_roles"
        )
        connection.exec_driver_sql(
            "INSERT INTO message_threads ("
            "id, requester_id, character_id, selected_model, created_at, updated_at, "
            "world_id, requester_world_character_id, responding_world_character_id, "
            "world_scope_status"
            ") SELECT "
            "'thread-b', requester_id, character_id, selected_model, created_at, "
            "updated_at, world_id, requester_world_character_id, "
            "responding_world_character_id, world_scope_status "
            "FROM message_threads WHERE id = 'thread-a'"
        )
        with pytest.raises(
            RuntimeError,
            match="cannot_downgrade_world_chat_duplicate_legacy_active_tuple",
        ):
            rebuild_message_threads_v3(connection)

        columns = {
            column["name"]
            for column in inspect(connection).get_columns("message_threads")
        }
        assert "world_id" in columns
        assert "world_scope_status" in columns
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM message_threads"
        ).scalar_one() == 2
        assert connection.exec_driver_sql(
            "SELECT content FROM message_messages WHERE thread_id = 'thread-a'"
        ).scalar_one() == "원문은 그대로 보존"
    engine.dispose()


def test_backfill_rejects_requester_membership_owned_by_another_user() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _seed_predecessor(connection)
        connection.exec_driver_sql(
            "UPDATE world_memberships SET user_id = 'responder-owner', role = 'member' "
            "WHERE id = 'membership-a'"
        )
        snapshot = capture_v3_to_v4_delta(connection)
        upgrade_v3_to_v4(connection)
        verify_v3_to_v4_delta(connection, snapshot)
        thread = connection.exec_driver_sql(
            "SELECT world_scope_status, world_id, requester_world_character_id "
            "FROM message_threads WHERE id = 'thread-a'"
        ).one()
        assert tuple(thread) == ("ambiguous", None, None)
        assert connection.exec_driver_sql(
            "SELECT content FROM message_messages WHERE thread_id = 'thread-a'"
        ).scalar_one() == "원문은 그대로 보존"
    engine.dispose()


def test_backfill_rejects_requester_who_is_not_the_claimed_installation_owner() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _seed_predecessor(connection)
        connection.exec_driver_sql(
            "UPDATE installation_identities SET owner_user_id = 'responder-owner' "
            "WHERE singleton_key = 'local-installation'"
        )
        snapshot = capture_v3_to_v4_delta(connection)
        upgrade_v3_to_v4(connection)
        verify_v3_to_v4_delta(connection, snapshot)
        thread = connection.exec_driver_sql(
            "SELECT world_scope_status, world_id, requester_world_character_id "
            "FROM message_threads WHERE id = 'thread-a'"
        ).one()
        assert tuple(thread) == ("ambiguous", None, None)
        assert connection.exec_driver_sql(
            "SELECT content FROM message_messages WHERE thread_id = 'thread-a'"
        ).scalar_one() == "원문은 그대로 보존"
    engine.dispose()


def test_backfill_rejects_requester_when_character_owner_disagrees() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _seed_predecessor(connection)
        connection.exec_driver_sql(
            "UPDATE characters SET owner_id = 'responder-owner' "
            "WHERE id = 'requester-character'"
        )
        snapshot = capture_v3_to_v4_delta(connection)
        upgrade_v3_to_v4(connection)
        verify_v3_to_v4_delta(connection, snapshot)
        thread = connection.exec_driver_sql(
            "SELECT world_scope_status, world_id, requester_world_character_id "
            "FROM message_threads WHERE id = 'thread-a'"
        ).one()
        assert tuple(thread) == ("ambiguous", None, None)
        assert connection.exec_driver_sql(
            "SELECT content FROM message_messages WHERE thread_id = 'thread-a'"
        ).scalar_one() == "원문은 그대로 보존"
    engine.dispose()


def test_backfill_counts_self_as_requester_before_rejecting_self_pair() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _seed_predecessor(connection)
        # Exercise a predecessor anomaly that a clean current schema prevents.
        connection.exec_driver_sql(
            "DROP INDEX uq_world_characters_active_owner_controlled"
        )
        connection.exec_driver_sql(
            "UPDATE characters SET owner_id = 'owner' "
            "WHERE id = 'responding-character'"
        )
        connection.exec_driver_sql(
            "UPDATE world_characters "
            "SET control_mode = 'owner_controlled', owner_user_id = 'owner', "
            "autonomous_enabled = 0 WHERE id = 'wc-responding'"
        )
        snapshot = capture_v3_to_v4_delta(connection)
        upgrade_v3_to_v4(connection)
        verify_v3_to_v4_delta(connection, snapshot)
        thread = connection.exec_driver_sql(
            "SELECT world_scope_status, world_id, requester_world_character_id, "
            "responding_world_character_id FROM message_threads "
            "WHERE id = 'thread-a'"
        ).one()
        assert tuple(thread) == ("ambiguous", None, None, None)
        assert connection.exec_driver_sql(
            "SELECT content FROM message_messages WHERE thread_id = 'thread-a'"
        ).scalar_one() == "원문은 그대로 보존"
    engine.dispose()
