"""Frozen v19 outbox rows upgrade without rewriting observation evidence."""

from datetime import UTC, datetime, timedelta
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.relationships import models
from app.runtime.migrations.embedded_sqlite import (
    SqliteCanonicalUpgradeCoordinator, SqliteCanonicalUpgradeError,
)
from app.runtime.migrations.sqlite_versions import observation_outbox_v20 as migration
from app.runtime.migrations.sqlite_versions import registry
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.persistence.sqlite_schema import (
    build_sqlite_v19_metadata, create_schema_version_table,
    sqlite_schema_contract_digest, sqlite_schema_digest,
)
from app.runtime.social.observations import observe_source
from p7_graph_support import seed_projection_fixture


def _seed_v19(path: Path) -> tuple[str, str]:
    register_models()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with engine.begin() as connection:
        build_sqlite_v19_metadata().create_all(connection)
        create_schema_version_table(connection)
        manifest = load_sqlite_manifest(19)
        assert sqlite_schema_contract_digest(connection) == manifest.schema_digest
        connection.exec_driver_sql(
            "INSERT INTO angmoo_schema_version "
            "(singleton_key, schema_version, source_revision, source_migration_count, schema_digest, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (1, 19, manifest.source_revision, manifest.source_migration_count,
             sqlite_schema_digest(connection), "2026-09-24T00:00:00Z"),
        )
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="legacy-observation")
        result = observe_source(
            db,
            world_id=fixture.world.id,
            observer_world_character_id=fixture.target_world_character.id,
            source_social_event_id=fixture.event.id,
            source_post_id=fixture.reply_post.id,
            lane="feed",
            observed_at=datetime(2026, 9, 24, tzinfo=UTC),
        )
        db.commit()
        row = db.scalar(select(models.GraphProjectionOutbox).where(
            models.GraphProjectionOutbox.payload_version == "relationship-observation-v1"
        ))
        assert row is not None
        row.status = "succeeded"
        row.attempt_count = 2
        row.completed_at = datetime(2026, 9, 24, tzinfo=UTC) + timedelta(minutes=1)
        db.commit()
        outbox_id = row.id
    with engine.begin() as connection:
        connection.execute(text(
            "UPDATE graph_projection_outbox SET relationship_state_id = NULL WHERE id = :id"
        ), {"id": outbox_id})
    engine.dispose()
    return outbox_id, result.relationship_state_id


def _outbox_row(connection, row_id: str) -> dict[str, object]:
    return dict(connection.execute(text(
        "SELECT * FROM graph_projection_outbox WHERE id = :id"
    ), {"id": row_id}).mappings().one())


def test_frozen_v19_still_rejects_second_observation_event_key(tmp_path: Path) -> None:
    database = tmp_path / "frozen-v19.sqlite3"
    row_id, _ = _seed_v19(database)
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.connect() as connection:
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(19).schema_digest
        with pytest.raises(IntegrityError):
            connection.execute(text(
                "INSERT INTO graph_projection_outbox "
                "(id, world_id, source_event_id, relationship_state_id, projection_type, "
                "payload_version, payload, source_signature, dedupe_key, status, attempt_count) "
                "SELECT :new_id, world_id, source_event_id, relationship_state_id, "
                "projection_type, payload_version, payload, source_signature, :new_dedupe, "
                "status, attempt_count FROM graph_projection_outbox WHERE id = :old_id"
            ), {"new_id": "second-observer-old-key", "new_dedupe": "different-observer-key",
                "old_id": row_id})
        connection.rollback()
    engine.dispose()


def test_v19_to_v20_backfills_only_verified_relationship_id(tmp_path: Path) -> None:
    database = tmp_path / "v19.sqlite3"
    row_id, state_id = _seed_v19(database)
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.connect() as connection:
        old = _outbox_row(connection, row_id)
        assert old["relationship_state_id"] is None
        connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
        connection.commit()
        with connection.begin():
            before = migration.capture_delta(connection)
            assert before.observation_count == before.backfill_count == 1
            migration.upgrade(connection)
            migration.verify_delta(connection, before)
            assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(20).schema_digest
            new = _outbox_row(connection, row_id)
            assert new == {**old, "relationship_state_id": state_id}
            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM graph_projection_outbox"
            ).scalar_one() == 2
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()


def test_invalid_legacy_observation_stops_before_rebuild(tmp_path: Path) -> None:
    database = tmp_path / "bad-v19.sqlite3"
    row_id, _ = _seed_v19(database)
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text(
            "UPDATE graph_projection_outbox SET source_signature = :signature WHERE id = :id"
        ), {"signature": "0" * 64, "id": row_id})
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
        connection.commit()
        with pytest.raises(SqliteMigrationDeltaError, match="observation_outbox_legacy_hash_invalid"):
            migration.upgrade(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(19).schema_digest
        assert _outbox_row(connection, row_id)["relationship_state_id"] is None
    engine.dispose()


def test_coordinator_rejects_invalid_legacy_before_promotion(tmp_path: Path) -> None:
    database = tmp_path / "canonical" / "generations" / "bad-v19" / "angmoo.sqlite3"
    row_id, _ = _seed_v19(database)
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text(
            "UPDATE graph_projection_outbox SET source_signature = :signature WHERE id = :id"
        ), {"signature": "0" * 64, "id": row_id})
    engine.dispose()
    coordinator = SqliteCanonicalUpgradeCoordinator(
        StaticRuntimeDataPath(tmp_path), fallback_generation="bad-v19"
    )
    with pytest.raises(SqliteCanonicalUpgradeError, match="observation_outbox_legacy_hash_invalid"):
        coordinator.upgrade()
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.connect() as connection:
        assert _outbox_row(connection, row_id)["relationship_state_id"] is None
        assert connection.exec_driver_sql(
            "SELECT schema_version FROM angmoo_schema_version"
        ).scalar_one() == 19
    engine.dispose()


def test_coordinator_preserves_source_generation_and_promotes_v20(tmp_path: Path) -> None:
    database = tmp_path / "canonical" / "generations" / "observed-v19" / "angmoo.sqlite3"
    row_id, state_id = _seed_v19(database)
    result = SqliteCanonicalUpgradeCoordinator(
        StaticRuntimeDataPath(tmp_path), fallback_generation="observed-v19"
    ).upgrade()
    assert result.migrated is True
    assert result.source_version == 19 and result.target_version == 20
    assert result.database_path != database
    old_engine = create_engine(f"sqlite:///{database.as_posix()}")
    new_engine = create_engine(f"sqlite:///{result.database_path.as_posix()}")
    with old_engine.connect() as old, new_engine.connect() as new:
        assert _outbox_row(old, row_id)["relationship_state_id"] is None
        assert _outbox_row(new, row_id)["relationship_state_id"] == state_id
        assert new.exec_driver_sql(
            "SELECT schema_version, source_revision FROM angmoo_schema_version"
        ).one() == (20, "20260924_0098")
    old_engine.dispose()
    new_engine.dispose()


def test_failed_staging_upgrade_leaves_v19_active_and_is_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "canonical" / "generations" / "observed-v19" / "angmoo.sqlite3"
    row_id, state_id = _seed_v19(database)
    coordinator = SqliteCanonicalUpgradeCoordinator(
        StaticRuntimeDataPath(tmp_path), fallback_generation="observed-v19"
    )

    def fail_after_rebuild(connection):
        migration.upgrade(connection)
        raise RuntimeError("injected_staging_failure")

    with monkeypatch.context() as patch:
        patch.setitem(registry.MIGRATIONS, 19, fail_after_rebuild)
        with pytest.raises(SqliteCanonicalUpgradeError, match="sqlite_migration_step_failed"):
            coordinator.upgrade()
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.connect() as connection:
        assert _outbox_row(connection, row_id)["relationship_state_id"] is None
        assert connection.exec_driver_sql(
            "SELECT schema_version FROM angmoo_schema_version"
        ).scalar_one() == 19
    engine.dispose()
    upgraded = coordinator.upgrade()
    engine = create_engine(f"sqlite:///{upgraded.database_path.as_posix()}")
    with engine.connect() as connection:
        assert _outbox_row(connection, row_id)["relationship_state_id"] == state_id
    engine.dispose()


def test_alembic_sqlite_revision_uses_frozen_upgrade(tmp_path: Path) -> None:
    database = tmp_path / "alembic-v19.sqlite3"
    row_id, state_id = _seed_v19(database)
    migration_file = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/20260924_0098_observation_outbox_identity.py"
    )
    spec = importlib.util.spec_from_file_location("observation_alembic_revision", migration_file)
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
        connection.commit()
        with connection.begin():
            revision.op = Operations(MigrationContext.configure(connection))
            revision.upgrade()
            assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(20).schema_digest
            assert _outbox_row(connection, row_id)["relationship_state_id"] == state_id
    engine.dispose()


def test_alembic_offline_revision_refuses_unverified_sql() -> None:
    migration_file = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/20260924_0098_observation_outbox_identity.py"
    )
    spec = importlib.util.spec_from_file_location("observation_alembic_offline", migration_file)
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    revision.op = Operations(MigrationContext.configure(
        dialect_name="sqlite", opts={"as_sql": True}
    ))
    with pytest.raises(RuntimeError, match="observation_outbox_online_migration_required"):
        revision.upgrade()


def test_alembic_online_sqlite_env_prepares_foreign_keys(tmp_path: Path) -> None:
    database = tmp_path / "alembic-online-v19.sqlite3"
    row_id, state_id = _seed_v19(database)
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
        connection.exec_driver_sql(
            "INSERT INTO alembic_version (version_num) VALUES ('20260923_0097')"
        )
    engine.dispose()
    backend = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite+pysqlite:///{database.as_posix()}"
    environment["APP_ENV"] = "test"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(backend / "alembic.ini"),
         "upgrade", "head"],
        cwd=tmp_path, env=environment, text=True, capture_output=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == "20260924_0098"
        assert _outbox_row(connection, row_id)["relationship_state_id"] == state_id
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        indexes = {row[1] for row in connection.exec_driver_sql(
            "PRAGMA index_list(graph_projection_outbox)"
        )}
        assert {"uq_graph_projection_outbox_observation",
                "uq_graph_projection_outbox_source_event"} <= indexes
    engine.dispose()
