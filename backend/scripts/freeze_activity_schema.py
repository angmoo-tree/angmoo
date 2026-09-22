"""Developer generator for the additive V19 migration; never run at startup."""
import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateIndex, CreateTable

from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import (
    ACTIVITY_V19_TABLES, SOURCE_ALEMBIC_REVISION, SOURCE_ALEMBIC_MIGRATION_COUNT,
    build_sqlite_baseline_metadata, create_schema_version_table, sqlite_schema_contract_digest,
)

register_models()
metadata = build_sqlite_baseline_metadata()
dialect = sqlite.dialect()
ddl = []
for name in ACTIVITY_V19_TABLES:
    table = metadata.tables[name]
    ddl.append(str(CreateTable(table).compile(dialect=dialect)))
    ddl.extend(str(CreateIndex(index).compile(dialect=dialect)) for index in sorted(table.indexes, key=lambda x: x.name))
root = Path(__file__).resolve().parents[1] / "app/runtime/migrations/sqlite_versions"
(root / "v18_to_v19_activity_graph.py").write_text(
    '"""Frozen additive V2 activity schema; existing rows are preserved."""\n'
    'from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError\n'
    f'MUTABLE_IDENTITY_TABLES = frozenset({ACTIVITY_V19_TABLES!r})\n'
    f'DDL = {ddl!r}\n\n'
    'def capture_delta(connection):\n'
    '    return frozenset(r[0] for r in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type=\'table\' AND name NOT LIKE \'sqlite_%\'"))\n\n'
    'def upgrade(connection):\n'
    '    for statement in DDL:\n'
    '        connection.exec_driver_sql(statement)\n\n'
    'def verify_delta(connection, before):\n'
    '    if capture_delta(connection) != before | MUTABLE_IDENTITY_TABLES:\n'
    '        raise SqliteMigrationDeltaError("activity_schema_inventory_invalid")\n'
    '    for table in MUTABLE_IDENTITY_TABLES:\n'
    '        if connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one():\n'
    '            raise SqliteMigrationDeltaError("activity_schema_must_start_empty")\n', encoding="utf-8")
engine = create_engine("sqlite://")
with engine.begin() as connection:
    metadata.create_all(connection)
    create_schema_version_table(connection)
    manifest = {"schema_version": 19, "canonical_table_count": len(metadata.tables),
        "schema_digest": sqlite_schema_contract_digest(connection),
        "source_revision": SOURCE_ALEMBIC_REVISION, "source_migration_count": SOURCE_ALEMBIC_MIGRATION_COUNT,
        "table_inventory": sorted(metadata.tables)}
(root / "manifests/v19.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
engine.dispose()
