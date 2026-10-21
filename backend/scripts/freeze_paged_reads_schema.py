"""Explicit v41 authoring; only synthetic schema, never a user's database."""
import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateIndex
from sqlalchemy.dialects.sqlite import dialect
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata, create_schema_version_table, sqlite_schema_contract_digest
from app.runtime.migrations.sqlite_versions.paged_reads_v41 import INDEXES


def main():
    register_models()
    metadata = build_sqlite_baseline_metadata()
    indexes = sorted((index for table in metadata.tables.values() for index in table.indexes if index.name in INDEXES), key=lambda index: index.name)
    assert len(indexes) == 2
    root = Path(__file__).resolve().parents[1] / "app/runtime/migrations/sqlite_versions"
    (root / "paged_reads_v41_ddl.json").write_text(json.dumps([str(CreateIndex(index).compile(dialect=dialect())) for index in indexes], indent=2) + "\n", encoding="utf-8")
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        metadata.create_all(connection)
        create_schema_version_table(connection)
        manifest = dict(schema_version=41, canonical_table_count=len(metadata.tables),
            schema_digest=sqlite_schema_contract_digest(connection), source_revision="20261022_0118",
            source_migration_count=117, table_inventory=sorted(metadata.tables))
    engine.dispose()
    (root / "manifests/v41.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
