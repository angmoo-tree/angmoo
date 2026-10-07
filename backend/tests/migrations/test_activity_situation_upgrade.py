import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_v30_metadata, create_schema_version_table, sqlite_schema_contract_digest
from app.runtime.migrations.sqlite_versions import activity_situation_v31
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest


def test_populated_forward_upgrade_inherits_schedule_and_preserves_old_data(tmp_path):
    from memory.test_p8_l_o_memory_consolidation import _stack
    from app.domains.memory.models.batch import MemoryBatchSetting
    register_models()
    engine = create_engine(f"sqlite:///{tmp_path / 'v30.sqlite3'}")
    build_sqlite_v30_metadata().create_all(engine)
    with Session(engine) as db:
        scope, setting, *_ = _stack(db)
        db.add(MemoryBatchSetting(scope_setting_id=setting.id, ai_enabled=False,
            schedule_enabled=True, local_time="05:40", timezone="Asia/Seoul", shutdown_enabled=False, version=7))
        db.commit()
    with engine.begin() as connection:
        create_schema_version_table(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(30).schema_digest
        historical = {name: tuple(connection.execute(text(f'SELECT * FROM "{name}"'))) for name in load_sqlite_manifest(30).table_inventory}
        before = activity_situation_v31.capture_delta(connection)
        activity_situation_v31.upgrade(connection)
        activity_situation_v31.verify_delta(connection, before)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(31).schema_digest
        assert connection.execute(text("SELECT daily_enabled,local_time,timezone,shutdown_apply_enabled FROM memory_situation_settings")).one() == (1, "05:40", "Asia/Seoul", 0)
        for name, rows in historical.items():
            assert tuple(connection.execute(text(f'SELECT * FROM "{name}"'))) == rows, name
        activity_situation_v31.upgrade(connection)
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
        assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    engine.dispose()


def test_alembic_and_embedded_schema_match(tmp_path):
    register_models()
    engine = create_engine(f"sqlite:///{tmp_path / 'alembic.sqlite3'}")
    build_sqlite_v30_metadata().create_all(engine)
    path = Path(__file__).parents[2] / "alembic/versions/20261008_0108_activity_situation.py"
    spec = importlib.util.spec_from_file_location("situation_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        create_schema_version_table(connection)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(31).schema_digest
    engine.dispose()
