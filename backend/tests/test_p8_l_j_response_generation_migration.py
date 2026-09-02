from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path
import sqlite3

from sqlalchemy import URL, create_engine

from app import models as _models  # noqa: F401
from app.domains.chat.infrastructure.sqlalchemy_models import (
    RESPONSE_REQUEST_SCHEMA_TABLES,
    drop_response_request_schema,
)
from app.runtime.migrations.embedded_sqlite import SqliteCanonicalUpgradeCoordinator
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.migrations.sqlite_versions.v5_to_v6_chat_response_requests import (
    capture_v5_to_v6_delta,
    upgrade_v5_to_v6,
    verify_v5_to_v6_delta,
)
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_codecs import encode_utc_timestamp
from app.runtime.persistence.sqlite_schema import (
    SCHEMA_VERSION_TABLE,
    SQLITE_SCHEMA_VERSION,
    build_sqlite_v5_metadata,
    create_schema_version_table,
    sqlite_schema_contract_digest,
    sqlite_schema_digest,
)


def _seed_v5(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create("sqlite+pysqlite", database=str(path)))
    manifest = load_sqlite_manifest(5)
    with engine.begin() as connection:
        create_schema_version_table(connection)
        metadata = build_sqlite_v5_metadata()
        metadata.create_all(connection)
        connection.execute(
            metadata.tables["users"].insert().values(
                id="p8-l-j-preserved-owner",
                email="p8-l-j@example.test",
                display_name="P8-L-J Preserved Owner",
                profile_setup_completed=True,
            )
        )
        assert sqlite_schema_contract_digest(connection) == manifest.schema_digest
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


def test_v5_to_v6_adds_only_empty_response_request_table_and_is_reversible() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        create_schema_version_table(connection)
        build_sqlite_v5_metadata().create_all(connection)
        snapshot = capture_v5_to_v6_delta(connection)
        upgrade_v5_to_v6(connection)
        verify_v5_to_v6_delta(connection, snapshot)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(6).schema_digest
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM chat_response_requests"
        ).scalar_one() == 0
        drop_response_request_schema(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(5).schema_digest
    engine.dispose()


def test_v5_generation_upgrades_copy_on_write_and_preserves_source(tmp_path: Path) -> None:
    root = tmp_path / "p8-l-j-v5-upgrade"
    generation = "p8-l-j-v5"
    source = root / "canonical" / "generations" / generation / "angmoo.sqlite3"
    _seed_v5(source)
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()

    result = SqliteCanonicalUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=generation,
    ).upgrade()

    assert result.source_version == 5
    assert result.target_version == SQLITE_SCHEMA_VERSION
    assert result.migrated is True
    assert result.database_path != source
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
    source_connection = sqlite3.connect(source)
    upgraded_connection = sqlite3.connect(result.database_path)
    try:
        assert source_connection.execute(
            f"SELECT schema_version FROM {SCHEMA_VERSION_TABLE}"
        ).fetchone() == (5,)
        assert upgraded_connection.execute(
            f"SELECT schema_version FROM {SCHEMA_VERSION_TABLE}"
        ).fetchone() == (SQLITE_SCHEMA_VERSION,)
        assert upgraded_connection.execute(
            "SELECT display_name FROM users WHERE id = 'p8-l-j-preserved-owner'"
        ).fetchone() == ("P8-L-J Preserved Owner",)
        tables = {
            row[0]
            for row in upgraded_connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert set(RESPONSE_REQUEST_SCHEMA_TABLES) <= tables
        thread_columns = {
            row[1]
            for row in upgraded_connection.execute(
                "PRAGMA table_info(message_threads)"
            )
        }
        assert "model_binding_mode" in thread_columns
        assert upgraded_connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert upgraded_connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        source_connection.close()
        upgraded_connection.close()
