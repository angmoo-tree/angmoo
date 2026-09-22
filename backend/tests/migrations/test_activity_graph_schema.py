from sqlalchemy import create_engine
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata, build_sqlite_v18_metadata, create_schema_version_table, sqlite_schema_contract_digest
from app.runtime.migrations.sqlite_versions import v18_to_v19_activity_graph as migration
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest


def test_v18_to_v19_additive_frozen_schema_matches_new_database():
    register_models()
    old, fresh = create_engine("sqlite://"), create_engine("sqlite://")
    with old.begin() as connection:
        build_sqlite_v18_metadata().create_all(connection)
        create_schema_version_table(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(18).schema_digest
        before = migration.capture_delta(connection)
        migration.upgrade(connection)
        migration.verify_delta(connection, before)
        migrated = sqlite_schema_contract_digest(connection)
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    with fresh.begin() as connection:
        build_sqlite_baseline_metadata().create_all(connection)
        create_schema_version_table(connection)
        assert sqlite_schema_contract_digest(connection) == migrated == load_sqlite_manifest(19).schema_digest
    old.dispose()
    fresh.dispose()


def test_frozen_alembic_upgrade_matches_v19():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    register_models()
    engine = create_engine("sqlite://")
    path = Path(__file__).parents[2] / "alembic/versions/20260923_0097_personalized_activity.py"
    spec = importlib.util.spec_from_file_location("activity_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as connection:
        build_sqlite_v18_metadata().create_all(connection)
        create_schema_version_table(connection)
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(19).schema_digest
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()
