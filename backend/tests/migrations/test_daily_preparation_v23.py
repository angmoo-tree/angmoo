"""Frozen v22 migration retains populated plan/episode identities and constraints."""
from datetime import datetime
from sqlalchemy import create_engine
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_v22_metadata, create_schema_version_table, sqlite_schema_contract_digest
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.migrations.sqlite_versions import daily_preparation_v23 as migration
from tests.routines.test_daily_activity_runtime import _seed, _prepare, _utc
from historical_schema_fixture import populate_frozen_schema


def test_populated_v22_to_v23_preserves_history(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'historical.sqlite3'}")
    register_models()
    old_meta = build_sqlite_v22_metadata()
    old_meta.create_all(engine)
    def seed(db):
        _, ready, _ = _seed(db)
        old = _prepare(db, ready, now=_utc(datetime(2026, 9, 28, 10)))
        return old.id
    identity = populate_frozen_schema(engine, old_meta, seed)
    with engine.begin() as c:
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
