from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import URL, create_engine

from app import models as _models  # noqa: F401 - register canonical metadata
from app.domains.memory.infrastructure.sqlalchemy_models import (
    MEMORY_SCHEMA_V1_TABLES,
    drop_memory_schema_v1,
)
from app.runtime.migrations.embedded_sqlite import (
    SqliteCanonicalUpgradeCoordinator,
    SqliteCanonicalUpgradeError,
)
from app.runtime.migrations.sqlite_versions import registry as sqlite_registry
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.migrations.sqlite_versions.v4_to_v5_canonical_memory import (
    capture_v4_to_v5_delta,
    upgrade_v4_to_v5,
    verify_v4_to_v5_delta,
)
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_codecs import encode_utc_timestamp
from app.runtime.persistence.sqlite_schema import (
    SCHEMA_VERSION_TABLE,
    build_sqlite_v4_metadata,
    create_schema_version_table,
    sqlite_schema_contract_digest,
    sqlite_schema_digest,
)


def _seed_v4(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create("sqlite+pysqlite", database=str(path)))
    manifest = load_sqlite_manifest(4)
    with engine.begin() as connection:
        create_schema_version_table(connection)
        metadata = build_sqlite_v4_metadata()
        metadata.create_all(connection)
        connection.execute(
            metadata.tables["users"].insert().values(
                id="preserved-owner",
                email="preserved@example.test",
                display_name="Preserved Owner",
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


def test_v4_to_v5_adds_only_empty_memory_tables_and_is_reversible() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        create_schema_version_table(connection)
        build_sqlite_v4_metadata().create_all(connection)
        snapshot = capture_v4_to_v5_delta(connection)
        upgrade_v4_to_v5(connection)
        verify_v4_to_v5_delta(connection, snapshot)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(5).schema_digest
        assert all(
            connection.exec_driver_sql(
                f'SELECT count(*) FROM "{table}"'
            ).scalar_one()
            == 0
            for table in MEMORY_SCHEMA_V1_TABLES
        )

        drop_memory_schema_v1(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(4).schema_digest
    engine.dispose()


def test_v4_generation_upgrades_copy_on_write_and_preserves_source(tmp_path: Path) -> None:
    root = tmp_path / "p8-l-f-v4-upgrade"
    generation = "p8-l-f-v4"
    source = (
        root
        / "canonical"
        / "generations"
        / generation
        / "angmoo.sqlite3"
    )
    _seed_v4(source)
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()

    result = SqliteCanonicalUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=generation,
    ).upgrade()

    assert result.source_version == 4
    assert result.target_version == 5
    assert result.migrated is True
    assert result.database_path != source
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha

    source_connection = sqlite3.connect(source)
    upgraded_connection = sqlite3.connect(result.database_path)
    try:
        assert source_connection.execute(
            f"SELECT schema_version FROM {SCHEMA_VERSION_TABLE}"
        ).fetchone() == (4,)
        assert upgraded_connection.execute(
            f"SELECT schema_version FROM {SCHEMA_VERSION_TABLE}"
        ).fetchone() == (5,)
        assert upgraded_connection.execute(
            "SELECT display_name FROM users WHERE id = 'preserved-owner'"
        ).fetchone() == ("Preserved Owner",)
        tables = {
            row[0]
            for row in upgraded_connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert set(MEMORY_SCHEMA_V1_TABLES) <= tables
        assert upgraded_connection.execute("PRAGMA integrity_check").fetchone() == (
            "ok",
        )
        assert upgraded_connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        source_connection.close()
        upgraded_connection.close()


def test_v4_to_v5_failure_keeps_original_generation_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "p8-l-f-failed-upgrade"
    generation = "p8-l-f-v4"
    source = (
        root
        / "canonical"
        / "generations"
        / generation
        / "angmoo.sqlite3"
    )
    _seed_v4(source)
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    original = sqlite_registry.MIGRATIONS[4]

    def fail_after_schema(connection) -> None:
        original(connection)
        raise RuntimeError("injected_after_memory_schema")

    monkeypatch.setitem(sqlite_registry.MIGRATIONS, 4, fail_after_schema)
    with pytest.raises(SqliteCanonicalUpgradeError, match="step_failed"):
        SqliteCanonicalUpgradeCoordinator(
            StaticRuntimeDataPath(root),
            fallback_generation=generation,
        ).upgrade()

    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
    assert not (root / "canonical" / "current-generation.json").exists()
    assert not list((root / "canonical" / "generations").glob(".*.tmp-*"))
