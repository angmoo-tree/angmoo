from sqlalchemy import create_engine
from app import models as _models
from app.runtime.persistence.sqlite_schema import (
    build_sqlite_v8_metadata,
    create_schema_version_table,
    sqlite_schema_contract_digest,
)
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.migrations.sqlite_versions.v8_to_v9_memory_batch import (
    capture_v8_to_v9_delta,
    upgrade_v8_to_v9,
    verify_v8_to_v9_delta,
)


def test_v8_to_v9_is_additive_empty_and_matches_latest_manifest():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        create_schema_version_table(connection)
        build_sqlite_v8_metadata().create_all(connection)
        assert (
            sqlite_schema_contract_digest(connection)
            == load_sqlite_manifest(8).schema_digest
        )
        before = capture_v8_to_v9_delta(connection)
        upgrade_v8_to_v9(connection)
        verify_v8_to_v9_delta(connection, before)
        assert (
            sqlite_schema_contract_digest(connection)
            == load_sqlite_manifest(9).schema_digest
        )
