from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session

from app import models as _models  # noqa: F401 - register canonical metadata
from app.integrations.ladybug_projection import LadybugRelationshipProjection
from app.integrations.relationship_graph_read import RelationshipGraphRepository
from app.runtime.migrations.embedded_data import EmbeddedDataUpgradeCoordinator
from app.runtime.migrations.embedded_sqlite import SqliteCanonicalUpgradeError
from app.runtime.migrations.ladybug_versions import registry as graph_registry
from app.runtime.migrations.local_app_data import LegacyLocalAppDataMigration
from app.runtime.migrations.sqlite_versions import registry as sqlite_registry
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_codecs import encode_utc_timestamp
from app.runtime.persistence.sqlite_schema import (
    SCHEMA_VERSION_TABLE,
    SQLITE_V1_SOURCE_ALEMBIC_MIGRATION_COUNT,
    SQLITE_V1_SOURCE_ALEMBIC_REVISION,
    SQLITE_SCHEMA_VERSION,
    WORLD_PACKAGE_REGISTRY_TABLES,
    build_sqlite_v1_metadata,
    create_schema_version_table,
    sqlite_schema_digest,
)
from p7_graph_support import seed_projection_fixture


GENERATION = "contributor-v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_v1(
    root: Path,
    *,
    with_graph: bool = True,
    generation: str = GENERATION,
) -> Path:
    secret = root / "secrets" / "app-secret"
    secret.parent.mkdir(parents=True)
    secret.write_text("embedded-migration-fixture-secret\n", encoding="utf-8")
    media = root / "media" / "world-a" / "banner.txt"
    media.parent.mkdir(parents=True)
    media.write_text("keep-media", encoding="utf-8")
    database = (
        root
        / "canonical"
        / "generations"
        / generation
        / "angmoo.sqlite3"
    )
    database.parent.mkdir(parents=True)
    engine = create_engine(URL.create("sqlite+pysqlite", database=str(database)))
    metadata = build_sqlite_v1_metadata()
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        create_schema_version_table(connection)
        metadata.create_all(connection)
        raw_digest = sqlite_schema_digest(connection)
        connection.exec_driver_sql(
            f"INSERT INTO {SCHEMA_VERSION_TABLE} ("
            "singleton_key, schema_version, source_revision, "
            "source_migration_count, schema_digest, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            (
                1,
                1,
                SQLITE_V1_SOURCE_ALEMBIC_REVISION,
                SQLITE_V1_SOURCE_ALEMBIC_MIGRATION_COUNT,
                raw_digest,
                encode_utc_timestamp(datetime.now(UTC)),
            ),
        )
        connection.execute(
            metadata.tables["users"].insert().values(
                id="owner-v1",
                display_name="Existing Owner",
                display_name_normalized="existing owner",
                profile_setup_completed=True,
            )
        )
    engine.dispose()
    if with_graph:
        with LadybugRelationshipProjection(
            database_root=root / "graph" / "ladybug"
        ) as graph:
            graph.verify_connectivity()
    return database


def test_legacy_marker_survives_forward_sqlite_generation_upgrade(
    tmp_path: Path,
) -> None:
    source = tmp_path / "com.angmoo.desktop"
    target = tmp_path / "Angmoo"
    legacy_generation = "er6-preview-v1"
    _seed_v1(source, generation=legacy_generation)

    legacy_migration = LegacyLocalAppDataMigration(
        source_root=source,
        target_root=target,
        runtime_root=target / "runtime",
        process_alive=lambda _pid: False,
    )
    imported = legacy_migration.migrate_if_needed()
    assert imported.status == "migrated"
    assert imported.generation == legacy_generation
    assert imported.schema_version == 1
    assert imported.canonical_table_count == 83

    upgraded = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(target),
        fallback_generation=legacy_generation,
    ).upgrade()
    assert upgraded.canonical.source_version == 1
    assert upgraded.canonical.target_version == SQLITE_SCHEMA_VERSION
    assert upgraded.canonical.migrated is True
    assert upgraded.canonical.generation != legacy_generation

    # The ER6 marker attests the immutable v1 generation that was imported.
    # It must not reject a later active generation as marker corruption.
    completed = legacy_migration.migrate_if_needed()
    assert completed.status == "already_migrated"
    assert completed.generation == legacy_generation
    assert completed.schema_version == 1
    assert completed.canonical_table_count == 83


def test_v1_sqlite_is_copied_to_latest_and_existing_data_is_preserved(
    tmp_path: Path,
) -> None:
    root = tmp_path / "한글 contributor data"
    source = _seed_v1(root)
    source_sha = _sha256(source)
    secret_sha = _sha256(root / "secrets" / "app-secret")
    media_sha = _sha256(root / "media" / "world-a" / "banner.txt")

    first = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=GENERATION,
    ).upgrade()

    assert first.canonical.source_version == 1
    assert first.canonical.target_version == SQLITE_SCHEMA_VERSION
    assert first.canonical.migrated is True
    assert first.canonical.generation != GENERATION
    assert source.is_file()
    assert _sha256(source) == source_sha
    assert _sha256(root / "secrets" / "app-secret") == secret_sha
    assert _sha256(root / "media" / "world-a" / "banner.txt") == media_sha
    assert first.graph.rebuilt is False
    assert first.graph.degraded is False
    assert first.graph.database_root == (root / "graph" / "ladybug").resolve()

    connection = sqlite3.connect(first.canonical.database_path)
    try:
        version = connection.execute(
            f"SELECT schema_version FROM {SCHEMA_VERSION_TABLE}"
        ).fetchone()[0]
        owner = connection.execute(
            "SELECT display_name FROM users WHERE id = 'owner-v1'"
        ).fetchone()[0]
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()
    assert version == SQLITE_SCHEMA_VERSION
    assert owner == "Existing Owner"
    assert set(WORLD_PACKAGE_REGISTRY_TABLES) <= tables

    previous = json.loads(
        (root / "canonical" / "previous-generation.json").read_text(
            encoding="utf-8"
        )
    )
    assert previous["generation"] == GENERATION
    assert previous["data_version"] == 1

    current_before = (
        root / "canonical" / "current-generation.json"
    ).read_bytes()
    graph_current_before = (
        root / "graph" / "current-generation.json"
    ).read_bytes()
    second = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=GENERATION,
    ).upgrade()
    assert second.canonical.migrated is False
    assert second.canonical.database_path == first.canonical.database_path
    assert (
        root / "canonical" / "current-generation.json"
    ).read_bytes() == current_before
    assert second.graph.rebuilt is False
    assert (
        root / "graph" / "current-generation.json"
    ).read_bytes() == graph_current_before


def test_failed_sqlite_step_keeps_v1_active_and_removes_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "failure"
    source = _seed_v1(root)
    source_sha = _sha256(source)

    def fail_step(_connection) -> None:
        raise RuntimeError("injected")

    monkeypatch.setitem(sqlite_registry.MIGRATIONS, 1, fail_step)
    with pytest.raises(SqliteCanonicalUpgradeError, match="step_failed"):
        EmbeddedDataUpgradeCoordinator(
            StaticRuntimeDataPath(root),
            fallback_generation=GENERATION,
        ).upgrade()

    assert _sha256(source) == source_sha
    assert not (root / "canonical" / "current-generation.json").exists()
    assert not list((root / "canonical" / "generations").glob(".*.tmp-*"))


def test_newer_sqlite_generation_fails_closed_without_replacement(
    tmp_path: Path,
) -> None:
    root = tmp_path / "newer-version"
    source = _seed_v1(root)
    source_sha = _sha256(source)
    connection = sqlite3.connect(source)
    try:
        connection.execute(
            f"UPDATE {SCHEMA_VERSION_TABLE} SET schema_version = 99 "
            "WHERE singleton_key = 1"
        )
        connection.commit()
    finally:
        connection.close()
    newer_sha = _sha256(source)

    with pytest.raises(
        SqliteCanonicalUpgradeError,
        match="newer_than_runtime",
    ):
        EmbeddedDataUpgradeCoordinator(
            StaticRuntimeDataPath(root),
            fallback_generation=GENERATION,
        ).upgrade()

    assert source_sha != newer_sha
    assert _sha256(source) == newer_sha
    assert not (root / "canonical" / "current-generation.json").exists()
    assert not list((root / "canonical" / "generations").glob(".*.tmp-*"))


def test_graph_version_change_replays_to_staging_and_preserves_previous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "graph-rebuild"
    _seed_v1(root)
    previous_graph = root / "graph" / "ladybug" / "relationships.lbdb"
    previous_sha = _sha256(previous_graph)
    monkeypatch.setattr(
        "app.runtime.migrations.ladybug_projection."
        "inspect_ladybug_projection_schema_version",
        lambda _root: 0,
    )

    result = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=GENERATION,
    ).upgrade()

    assert result.graph.rebuilt is True
    assert result.graph.database_root != root / "graph" / "ladybug"
    assert _sha256(previous_graph) == previous_sha
    assert (result.graph.database_root / "relationships.lbdb").exists()
    current = json.loads(
        (root / "graph" / "current-generation.json").read_text(encoding="utf-8")
    )
    assert current["relative_path"].startswith("generations/ladybug-v1")
    previous = json.loads(
        (root / "graph" / "previous-generation.json").read_text(
            encoding="utf-8"
        )
    )
    assert previous["relative_path"] == "ladybug"
    assert previous["data_version"] == 0


def test_graph_rebuild_failure_degrades_without_replacing_previous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "graph-failure"
    _seed_v1(root)
    previous_graph = root / "graph" / "ladybug" / "relationships.lbdb"
    previous_sha = _sha256(previous_graph)
    monkeypatch.setattr(
        "app.runtime.migrations.ladybug_projection."
        "inspect_ladybug_projection_schema_version",
        lambda _root: 0,
    )

    def fail_rebuild(**_kwargs):
        raise graph_registry.LadybugVersionContractError(
            "ladybug_rebuild_injected"
        )

    monkeypatch.setitem(graph_registry.GRAPH_REBUILDS, 1, fail_rebuild)
    result = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=GENERATION,
    ).upgrade()

    assert result.canonical.target_version == SQLITE_SCHEMA_VERSION
    assert result.graph.degraded is True
    assert result.graph.error_code == "ladybug_rebuild_injected"
    assert _sha256(previous_graph) == previous_sha
    assert not (root / "graph" / "current-generation.json").exists()


def test_graph_rebuild_replays_direction_evidence_and_world_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "graph-parity"
    _seed_v1(root)
    initial = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=GENERATION,
    ).upgrade()
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(initial.canonical.database_path))
    )
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="embedded-upgrade")
        world_id = fixture.world.id
        actor_id = fixture.actor_world_character.id
        target_id = fixture.target_world_character.id
        event_id = fixture.event.id
    previous_graph = initial.graph.database_root / "relationships.lbdb"
    previous_sha = _sha256(previous_graph)
    monkeypatch.setattr(
        "app.runtime.migrations.ladybug_projection."
        "inspect_ladybug_projection_schema_version",
        lambda _root: 0,
    )

    rebuilt = EmbeddedDataUpgradeCoordinator(
        StaticRuntimeDataPath(root),
        fallback_generation=GENERATION,
    ).upgrade()

    assert rebuilt.graph.rebuilt is True
    assert rebuilt.graph.degraded is False
    assert _sha256(previous_graph) == previous_sha
    with LadybugRelationshipProjection(
        database_root=rebuilt.graph.database_root
    ) as projection:
        repository = RelationshipGraphRepository(projection)
        direct = repository.get_direct_relationship(
            world_id=world_id,
            source_world_character_id=actor_id,
            target_world_character_id=target_id,
        )
        reverse = repository.get_direct_relationship(
            world_id=world_id,
            source_world_character_id=target_id,
            target_world_character_id=actor_id,
        )
        evidence = repository.list_relationship_evidence(
            world_id=world_id,
            source_world_character_id=actor_id,
            target_world_character_id=target_id,
        )
        cross_world = repository.get_direct_relationship(
            world_id="another-world",
            source_world_character_id=actor_id,
            target_world_character_id=target_id,
        )
    engine.dispose()
    assert len(direct) == 1
    assert reverse == []
    assert [row.event_id for row in evidence] == [event_id]
    assert cross_world == []
