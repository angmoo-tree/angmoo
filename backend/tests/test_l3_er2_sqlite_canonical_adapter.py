from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
import math
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.domains.identity.service.local_owner import LocalIdentityService as SqlAlchemyIdentityRepository
from app.domains.runtime.ports.unit_of_work import UnitOfWorkPort
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_codecs import (
    decode_json_document,
    decode_utc_timestamp,
    encode_enum_value,
    encode_json_document,
    encode_ulid_text,
    encode_utc_timestamp,
    encode_uuid_text,
    encode_vector_json,
)
from app.runtime.persistence.sqlite_database import (
    LocalAppDataRuntimeDataPath,
    SqliteCanonicalDatabase,
    SqliteCanonicalSettings,
    SqliteSchemaMismatchError,
)
from app.runtime.persistence.sqlite_schema import (
    EXPECTED_CANONICAL_TABLE_COUNT,
    SOURCE_ALEMBIC_MIGRATION_COUNT,
    SOURCE_ALEMBIC_REVISION,
    SQLITE_SCHEMA_VERSION,
)
from app.runtime.persistence.sqlite_unit_of_work import SqliteUnitOfWork


class _ExampleState(str, Enum):
    READY = "ready"


def _database(tmp_path: Path, *, generation: str = "test-v1") -> SqliteCanonicalDatabase:
    return SqliteCanonicalDatabase(
        StaticRuntimeDataPath(tmp_path / "앵무 데이터"),
        settings=SqliteCanonicalSettings(generation=generation),
    )


def test_sqlite_canonical_codecs_are_deterministic_and_strict() -> None:
    uuid_value = uuid4()
    assert encode_uuid_text(uuid_value.hex.upper()) == str(uuid_value)
    assert UUID(encode_uuid_text(uuid_value)) == uuid_value
    assert encode_ulid_text("01arz3ndektsv4rrffq69g5fav") == (
        "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    )
    with pytest.raises(ValueError, match="invalid ULID"):
        encode_ulid_text("not-a-ulid")
    with pytest.raises(ValueError, match="invalid ULID"):
        encode_ulid_text("81ARZ3NDEKTSV4RRFFQ69G5FAV")

    source_time = datetime(
        2026,
        8,
        20,
        9,
        10,
        11,
        123456,
        tzinfo=timezone(timedelta(hours=9)),
    )
    encoded_time = encode_utc_timestamp(source_time)
    assert encoded_time == "2026-08-20T00:10:11.123456Z"
    assert decode_utc_timestamp(encoded_time) == source_time.astimezone(timezone.utc)
    with pytest.raises(ValueError, match="UTC Z suffix"):
        decode_utc_timestamp("2026-08-20T00:10:11.123456+00:00")
    with pytest.raises(ValueError, match="timezone-aware"):
        encode_utc_timestamp(datetime(2026, 8, 20))

    encoded_json = encode_json_document({"한글": "앵무", "z": [2, 1], "a": True})
    assert encoded_json == '{"a":true,"z":[2,1],"한글":"앵무"}'
    assert decode_json_document(encoded_json)["한글"] == "앵무"
    with pytest.raises(ValueError):
        encode_json_document({"bad": math.nan})

    assert encode_enum_value(_ExampleState.READY, allowed={"ready"}) == "ready"
    with pytest.raises(ValueError, match="unsupported enum"):
        encode_enum_value("failed", allowed={"ready"})
    assert encode_vector_json([0, 1.5, -2]) == "[0.0,1.5,-2.0]"
    with pytest.raises(ValueError, match="finite"):
        encode_vector_json([math.inf])


def test_local_app_data_path_and_generation_are_side_effect_free(tmp_path: Path) -> None:
    local_app_data = tmp_path / "사용자 로컬 데이터"
    resolver = LocalAppDataRuntimeDataPath(
        environ={"LOCALAPPDATA": str(local_app_data)},
        home=tmp_path / "home",
        os_name="nt",
    )

    paths = resolver.resolve()

    assert paths.root == (local_app_data / "Angmoo").resolve()
    assert paths.canonical == paths.root / "canonical"
    assert paths.graph == paths.root / "graph"
    assert not paths.root.exists()
    with pytest.raises(ValueError, match="invalid SQLite generation"):
        SqliteCanonicalSettings(generation="../escape")


def test_file_backed_baseline_records_lineage_pragmas_and_schema_digest(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)

    first = database.open()

    assert Path(first.database_path).is_file()
    assert Path(first.database_path) == (
        tmp_path
        / "앵무 데이터"
        / "canonical"
        / "generations"
        / "test-v1"
        / "angmoo.sqlite3"
    ).resolve()
    assert first.schema_version == SQLITE_SCHEMA_VERSION
    assert first.source_revision == SOURCE_ALEMBIC_REVISION
    assert first.source_migration_count == SOURCE_ALEMBIC_MIGRATION_COUNT
    assert first.canonical_table_count == EXPECTED_CANONICAL_TABLE_COUNT
    assert first.schema_digest_matches is True
    assert first.foreign_keys is True
    assert first.journal_mode == "WAL"
    assert first.synchronous == "FULL"
    assert first.busy_timeout_ms == 5_000
    assert first.wal_autocheckpoint_pages == 1_000
    assert first.page_size == 4_096
    assert database.checkpoint()[0] == 0

    inspector = inspect(database.engine)
    partial_indexes = [
        index
        for table_name in inspector.get_table_names()
        for index in inspector.get_indexes(table_name)
        if index.get("dialect_options", {}).get("sqlite_where") is not None
    ]
    # P8-L-D adds the resolved World-role tuple and unresolved legacy-pair
    # uniqueness guards to the existing canonical partial-index set.
    assert len(partial_indexes) == 15
    lore_columns = {
        column["name"]: str(column["type"])
        for column in inspector.get_columns("character_lore_chunks")
    }
    assert lore_columns["embedding"] == "TEXT"

    database.close()
    reopened = database.open()
    assert reopened.schema_digest == first.schema_digest
    assert reopened.schema_digest_matches is True
    database.close()


def test_foreign_keys_checks_and_postgresql_partial_indexes_keep_meaning(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    database.open()
    now = datetime.now(timezone.utc)
    with database.session() as session:
        session.add(
            models.User(
                id="owner",
                display_name="Owner",
                display_name_normalized="owner",
                profile_setup_completed=True,
            )
        )
        session.add(
            models.Character(
                id="character-a",
                owner_id="owner",
                name="Mango",
                handle="mango-sqlite",
                persona_summary="Mango",
            )
        )
        session.commit()

        session.execute(
            text("INSERT INTO agent_slots (agent_id, status) VALUES (:id, 'idle')"),
            {"id": "slot-null-a"},
        )
        session.execute(
            text("INSERT INTO agent_slots (agent_id, status) VALUES (:id, 'idle')"),
            {"id": "slot-null-b"},
        )
        session.execute(
            text(
                "INSERT INTO agent_slots "
                "(agent_id, status, assigned_character_id) "
                "VALUES (:id, 'idle', 'character-a')"
            ),
            {"id": "slot-character-a"},
        )
        session.commit()

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO agent_slots "
                    "(agent_id, status, assigned_character_id) "
                    "VALUES (:id, 'idle', 'character-a')"
                ),
                {"id": "slot-character-duplicate"},
            )
            session.commit()
        session.rollback()

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO auth_sessions "
                    "(token_hash, user_id, auth_method) "
                    "VALUES ('missing-user-token', 'missing-user', 'local_owner')"
                )
            )
            session.commit()
        session.rollback()

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO installation_identities "
                    "(singleton_key, installation_id, bootstrap_state) "
                    "VALUES ('wrong-key', 'installation-a', 'unclaimed')"
                )
            )
            session.commit()
        session.rollback()
    database.close()


def test_existing_identity_repository_roundtrips_without_sqlite_fork(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    database.open()
    now = datetime.now(timezone.utc)
    with database.session() as session:
        repository = SqlAlchemyIdentityRepository(session)
        assert repository.get_bootstrap_status().state == "unclaimed"
        challenge = repository.create_bootstrap_challenge(now=now)
        issued = repository.claim_local_owner(
            challenge_token=challenge.token,
            owner_user_id=None,
            display_name="로컬 소유자",
            local_label="앵무 PC",
            privacy_acknowledged=True,
            now=now,
        )
        assert issued.user.display_name == "로컬 소유자"

    database.close()
    database.open()
    with database.session() as session:
        status = SqlAlchemyIdentityRepository(session).get_bootstrap_status()
        assert status.state == "claimed"
        assert status.local_label == "앵무 PC"
        assert status.owner is not None
        assert status.owner.display_name == "로컬 소유자"
        assert session.scalar(select(models.AuthSession.token_hash)) is not None
    database.close()


def test_sqlite_unit_of_work_implements_port_and_rejects_other_dialects(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    database.open()
    with database.session() as session:
        unit_of_work = SqliteUnitOfWork(session)
        assert isinstance(unit_of_work, UnitOfWorkPort)
        session.add(
            models.User(
                id="uow-owner",
                display_name="UOW Owner",
                display_name_normalized="uow owner",
                profile_setup_completed=True,
            )
        )
        unit_of_work.flush()
        unit_of_work.commit()
        assert session.get(models.User, "uow-owner") is not None
    database.close()

    class _FakeDialect:
        name = "postgresql"

    class _FakeBind:
        dialect = _FakeDialect()

    class _FakeSession:
        bind = _FakeBind()

    with pytest.raises(ValueError, match="requires a SQLite session"):
        SqliteUnitOfWork(cast(Session, _FakeSession()))


def test_schema_tamper_and_unversioned_database_fail_closed(tmp_path: Path) -> None:
    database = _database(tmp_path, generation="tampered")
    database.open()
    path = database.database_path
    database.close()

    tamper_engine = create_engine(f"sqlite+pysqlite:///{path}")
    with tamper_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE rogue (id INTEGER PRIMARY KEY)")
    tamper_engine.dispose()
    with pytest.raises(SqliteSchemaMismatchError, match="digest"):
        database.open()

    unversioned = _database(tmp_path, generation="unversioned")
    unversioned.database_path.parent.mkdir(parents=True, exist_ok=True)
    raw_engine = create_engine(f"sqlite+pysqlite:///{unversioned.database_path}")
    with raw_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE unexpected (id INTEGER PRIMARY KEY)")
    raw_engine.dispose()
    with pytest.raises(SqliteSchemaMismatchError, match="unversioned"):
        unversioned.open()


def test_existing_database_with_different_connection_contract_fails_closed(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path, generation="settings-mismatch")
    database.open()
    database.close()

    mismatched = SqliteCanonicalDatabase(
        StaticRuntimeDataPath(tmp_path / "앵무 데이터"),
        settings=SqliteCanonicalSettings(
            generation="settings-mismatch",
            page_size=8_192,
        ),
    )
    with pytest.raises(SqliteSchemaMismatchError, match="page_size=4096"):
        mismatched.open()
