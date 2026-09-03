from __future__ import annotations

from sqlalchemy import create_engine

from app import models as _models  # noqa: F401
from app.domains.social.infrastructure.sqlalchemy_subjective_context_models import (
    drop_subjective_context_schema,
)
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.migrations.sqlite_versions.v7_to_v8_social_action_subjective_context import (
    capture_v7_to_v8_delta,
    upgrade_v7_to_v8,
    verify_v7_to_v8_delta,
)
from app.runtime.persistence.sqlite_schema import (
    build_sqlite_v7_metadata,
    create_schema_version_table,
    sqlite_schema_contract_digest,
)


def test_v7_to_v8_adds_only_empty_subjective_context_table_and_is_reversible() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        create_schema_version_table(connection)
        build_sqlite_v7_metadata().create_all(connection)
        snapshot = capture_v7_to_v8_delta(connection)
        upgrade_v7_to_v8(connection)
        verify_v7_to_v8_delta(connection, snapshot)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(8).schema_digest
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM social_action_subjective_contexts"
        ).scalar_one() == 0
        drop_subjective_context_schema(connection)
        assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(7).schema_digest
    engine.dispose()
