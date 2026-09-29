from sqlalchemy import create_engine
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_v24_metadata, create_schema_version_table, sqlite_schema_contract_digest
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.migrations.sqlite_versions import topic_request_v25 as migration


def test_populated_v24_upgrade_preserves_all_old_topic_bytes_and_legacy_policy(tmp_path):
    register_models()
    engine = create_engine(f"sqlite:///{tmp_path / 'topics-v24.sqlite3'}")
    metadata = build_sqlite_v24_metadata()
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.execute(metadata.tables["users"].insert().values(id="owner",
            email="names-migration@example.test", display_name="Owner"))
        connection.execute(metadata.tables["worlds"].insert().values(id="world",
            slug="migration-world", owner_user_id="owner", name="Migration World",
            contract_version="world-v1", contract_hash="a" * 64, create_idempotency_key="migration-world"))
        # The row is intentionally old request metadata, not a new name snapshot.
        connection.exec_driver_sql("INSERT INTO social_recommendation_preparations "
            "(id,world_id,source_key,state,request_id,source_digest,applied_digest,last_code) "
            "VALUES ('old','world','actor','failed','request-old','raw-digest','applied','provider_503')")
        create_schema_version_table(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(24).schema_digest
        before = migration.capture_delta(connection)
        original = connection.exec_driver_sql("SELECT * FROM social_recommendation_preparations").one()
        migration.upgrade(connection)
        migration.verify_delta(connection, before)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(25).schema_digest
        final = connection.exec_driver_sql("SELECT * FROM social_recommendation_preparations").one()
        assert tuple(final[:-1]) == tuple(original) and final[-1] is None
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()
