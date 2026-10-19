"""Explicit v40 authoring tool; never run at startup or against user data."""
import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.dialects.sqlite import dialect
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata, create_schema_version_table, sqlite_schema_contract_digest


def main():
    register_models()
    metadata = build_sqlite_baseline_metadata()
    table = metadata.tables["local_client_connections"]
    ddl = [str(CreateTable(table).compile(dialect=dialect()))]
    ddl.extend(str(CreateIndex(index).compile(dialect=dialect())) for index in sorted(table.indexes, key=lambda index: index.name))
    sessions = metadata.tables["auth_sessions"]
    # SQLite cannot append a table FK/check with the canonical CREATE shape.
    # No canonical table references auth_sessions; preserve every old column
    # while replacing only this leaf table inside the migration transaction.
    assert not any(fk.target_fullname.startswith("auth_sessions.") for table in metadata.tables.values() for fk in table.foreign_keys)
    ddl.extend(["ALTER TABLE auth_sessions RENAME TO auth_sessions_v39", str(CreateTable(sessions).compile(dialect=dialect()))])
    columns = ",".join(column.name for column in sessions.c if column.name not in {"local_client_id", "local_client_generation"})
    ddl.extend([f"INSERT INTO auth_sessions ({columns}) SELECT {columns} FROM auth_sessions_v39", "DROP TABLE auth_sessions_v39"])
    ddl.extend(str(CreateIndex(index).compile(dialect=dialect())) for index in sorted(sessions.indexes, key=lambda index: index.name))
    root = Path(__file__).resolve().parents[1] / "app/runtime/migrations/sqlite_versions"
    (root / "local_client_v40_ddl.json").write_text(json.dumps(ddl, indent=2) + "\n", encoding="utf-8")
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        metadata.create_all(connection)
        create_schema_version_table(connection)
        manifest = dict(schema_version=40, canonical_table_count=len(metadata.tables),
            schema_digest=sqlite_schema_contract_digest(connection), source_revision="20261019_0117",
            source_migration_count=116, table_inventory=sorted(metadata.tables))
    engine.dispose()
    (root / "manifests/v40.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
