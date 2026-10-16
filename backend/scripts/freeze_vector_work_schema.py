"""Explicit v39 authoring tool. Never invoked by startup or a migration."""
import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.dialects.sqlite import dialect
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import (
    build_sqlite_baseline_metadata, create_schema_version_table, sqlite_schema_contract_digest, VECTOR_V39_TABLES,
)
from app.runtime.memory.vector_mutations import statements


def main():
    register_models()
    metadata = build_sqlite_baseline_metadata()
    ddl = []
    for name in VECTOR_V39_TABLES:
        table = metadata.tables[name]
        ddl.append(str(CreateTable(table).compile(dialect=dialect())))
        ddl.extend(str(CreateIndex(index).compile(dialect=dialect())) for index in sorted(table.indexes, key=lambda index: index.name))
    ddl.extend(statements())
    root = Path(__file__).resolve().parents[1] / "app/runtime/migrations/sqlite_versions"
    (root / "vector_work_v39_ddl.json").write_text(json.dumps(ddl, indent=2) + "\n", encoding="utf-8")
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        metadata.create_all(connection)
        create_schema_version_table(connection)
        manifest = dict(schema_version=39, canonical_table_count=len(metadata.tables),
            schema_digest=sqlite_schema_contract_digest(connection), source_revision="20261016_0116",
            source_migration_count=115, table_inventory=sorted(metadata.tables))
    engine.dispose()
    (root / "manifests/v39.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
