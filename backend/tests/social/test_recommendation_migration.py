from sqlalchemy import create_engine
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata
from app.runtime.migrations.sqlite_versions.v14_to_v15_recommendation import TABLES, capture_delta, upgrade, verify_delta


def test_additive_migration_does_not_enroll_or_generate():
    register_models()
    metadata = build_sqlite_baseline_metadata()
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        metadata.create_all(connection, tables=[t for t in metadata.tables.values() if t.name not in TABLES])
        before = capture_delta(connection)
        upgrade(connection)
        verify_delta(connection, before)
        assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    engine.dispose()


def test_alembic_recommendation_heads_match_embedded():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from app.runtime.persistence.sqlite_schema import build_sqlite_v14_metadata, create_schema_version_table, sqlite_schema_contract_digest
    from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
    register_models()
    engine = create_engine("sqlite://")
    build_sqlite_v14_metadata().create_all(engine)
    with engine.begin() as connection:
        create_schema_version_table(connection)
        for filename in ("20260918_0095_social_recommendation.py", "20260918_0096_recommendation_mode.py"):
            spec = importlib.util.spec_from_file_location(filename[:-3], Path(__file__).parents[2] / "alembic/versions" / filename)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            module.op = Operations(MigrationContext.configure(connection))
            module.upgrade()
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(16).schema_digest
        assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    engine.dispose()


def test_populated_v14_to_v16_matches_fresh_and_keeps_switches():
    from sqlalchemy.orm import Session
    from social.test_world_feed_search import _user, _world, _add_world_character
    from app.runtime.persistence.sqlite_schema import build_sqlite_v14_metadata, create_schema_version_table, sqlite_schema_contract_digest
    from app.runtime.migrations.sqlite_versions import v15_to_v16_recommendation_mode as modes
    from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest as load_manifest
    register_models()
    engine = create_engine("sqlite://")
    build_sqlite_v14_metadata().create_all(engine)
    with engine.begin() as connection:
        create_schema_version_table(connection)
        assert sqlite_schema_contract_digest(connection) == load_manifest(14).schema_digest
    with Session(engine) as db:
        owner = _user("migrate")
        db.add(owner); db.flush()
        world = _world(owner)
        db.add(world); db.flush()
        _, _, wc = _add_world_character(db, world=world, suffix="migrant", feed_mode="keyword_search_v1")
        wc.autonomous_enabled = False
        db.commit()
    with engine.begin() as connection:
        before = capture_delta(connection)
        upgrade(connection)
        verify_delta(connection, before)
        assert sqlite_schema_contract_digest(connection) == load_manifest(15).schema_digest
        snapshot = modes.capture_delta(connection)
        modes.upgrade(connection)
        modes.verify_delta(connection, snapshot)
        assert sqlite_schema_contract_digest(connection) == load_manifest(16).schema_digest
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert connection.exec_driver_sql("SELECT autonomous_enabled FROM world_characters").scalar() == 0
    engine.dispose()
