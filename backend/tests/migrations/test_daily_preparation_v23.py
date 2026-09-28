"""Frozen v22 migration retains populated plan/episode identities and constraints."""
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable, CreateIndex
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata, build_sqlite_v22_metadata, create_schema_version_table, sqlite_schema_contract_digest
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.migrations.sqlite_versions import daily_preparation_v23 as migration
from tests.routines.test_daily_activity_runtime import _seed, _prepare, _utc


def test_populated_v22_to_v23_preserves_history(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'historical.sqlite3'}")
    register_models()
    build_sqlite_baseline_metadata().create_all(engine)
    with Session(engine) as db:
        _, ready, _ = _seed(db)
        old = _prepare(db, ready, now=_utc(datetime(2026, 9, 28, 10)))
        identity = old.id
    old_meta = build_sqlite_v22_metadata()
    with engine.begin() as c:
        c.exec_driver_sql("PRAGMA foreign_keys=OFF")
        c.exec_driver_sql("DROP TABLE activity_preparation_jobs")
        c.exec_driver_sql("ALTER TABLE activity_beats DROP COLUMN state_schema_version")
        for name in migration.REBUILT_TABLES:
            table = old_meta.tables[name]
            columns = ','.join(table.c.keys())
            c.exec_driver_sql(f"CREATE TEMP TABLE legacy_copy AS SELECT {columns} FROM {name}")
            c.exec_driver_sql(f"DROP TABLE {name}")
            c.exec_driver_sql(str(CreateTable(table).compile(engine)))
            c.exec_driver_sql(f"INSERT INTO {name} ({columns}) SELECT {columns} FROM legacy_copy")
            c.exec_driver_sql("DROP TABLE legacy_copy")
            for index in table.indexes:
                c.exec_driver_sql(str(CreateIndex(index).compile(engine)))
        create_schema_version_table(c)
        assert sqlite_schema_contract_digest(c) == load_sqlite_manifest(22).schema_digest
        episodes = c.exec_driver_sql("SELECT * FROM activity_episodes ORDER BY id").all()
        before = migration.capture_delta(c)
        migration.upgrade(c)
        migration.verify_delta(c, before)
        assert sqlite_schema_contract_digest(c) == load_sqlite_manifest(23).schema_digest
        assert c.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert c.exec_driver_sql("SELECT * FROM activity_episodes ORDER BY id").all() == episodes
        assert c.exec_driver_sql("SELECT generation_source FROM daily_activity_plans WHERE id=?", (identity,)).scalar_one() == "repertoire"
    engine.dispose()
