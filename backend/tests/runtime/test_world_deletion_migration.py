"""Exercise the immutable v36 source and additive v37 target contract."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_v36_metadata, create_schema_version_table, sqlite_schema_contract_digest
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest, migration_chain
from app.runtime.migrations.sqlite_versions import world_deletion_v37


def test_v36_to_v37_preserves_source_rows_and_matches_frozen_manifests():
    register_models()
    engine = create_engine("sqlite://")
    with engine.begin() as db:
        create_schema_version_table(db)
        build_sqlite_v36_metadata().create_all(db)
        assert sqlite_schema_contract_digest(db) == load_sqlite_manifest(36).schema_digest
        before = tuple(db.exec_driver_sql("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"))
        world_deletion_v37.upgrade(db)
        world_deletion_v37.verify_delta(db, None)
        assert sqlite_schema_contract_digest(db) == load_sqlite_manifest(37).schema_digest
        after = {row[0]: row[1] for row in db.exec_driver_sql("SELECT name, sql FROM sqlite_master WHERE type='table'")}
        assert all(after[name] == sql for name, sql in before)
        assert tuple(db.exec_driver_sql("PRAGMA foreign_key_check")) == ()
    assert [version for version, _ in migration_chain(36)] == [36]
    engine.dispose()


def test_populated_v36_and_interrupted_additive_ddl_replay_preserve_contracts(tmp_path):
    import json
    from pathlib import Path
    from datetime import UTC, datetime
    from worlds.test_creator_routes import _user
    from worlds.test_foundation import _character
    from app.domains.worlds.models import World, WorldMembership, OwnerDefaultWorld
    from app.domains.characters.service.import_snapshots import capture_creation
    from app.domains.characters.service.import_configuration import ImportConfiguration, ImportProfile, ImportSettings
    register_models()
    engine = create_engine(f"sqlite:///{tmp_path / 'v36.sqlite'}")
    with engine.begin() as db:
        create_schema_version_table(db)
        build_sqlite_v36_metadata().create_all(db)
    with Session(engine) as db:
        db.add(_user("owner"))
        db.flush()
        db.add(World(id="original", slug="original", owner_user_id="owner", name="Unchanged definition",
            visibility="private", status="published", readiness_status="publish_ready",
            contract_hash="a" * 64, contract_version="world-v1", create_idempotency_key="first-request"))
        db.flush()
        db.add(WorldMembership(id="original-member", world_id="original", user_id="owner", role="owner", status="active"))
        db.add(OwnerDefaultWorld(owner_id="owner", world_id="original"))
        db.add(_character("source", "owner"))
        db.flush()
        capture_creation(db, character_id="source", configuration=ImportConfiguration(
            profile=ImportProfile(display_name="Initial source", handle="source"), settings=ImportSettings(personality="initial")),
            provenance="fixture first registration")
        db.commit()
    names = ("worlds", "world_memberships", "owner_default_worlds", "characters", "character_import_snapshots", "character_import_origins")
    with engine.connect() as db:
        before = {name: tuple(db.exec_driver_sql(f'SELECT * FROM "{name}"')) for name in names}
    # DDL interrupted after its first table: resume the supported additive
    # implementation without dropping or rewriting the source generation.
    statements = json.loads(Path(world_deletion_v37.__file__).with_name("world_deletion_v37_ddl.json").read_text())
    with engine.begin() as db:
        first = statements[0]
        db.exec_driver_sql(first["create"])
        for sql in first["indexes"]:
            db.exec_driver_sql(sql)
    with engine.begin() as db:
        world_deletion_v37.upgrade(db)
        world_deletion_v37.upgrade(db)
        world_deletion_v37.verify_delta(db, None)
        assert sqlite_schema_contract_digest(db) == load_sqlite_manifest(37).schema_digest
        assert before == {name: tuple(db.exec_driver_sql(f'SELECT * FROM "{name}"')) for name in names}
        assert tuple(db.exec_driver_sql("PRAGMA foreign_key_check")) == ()
    engine.dispose()
