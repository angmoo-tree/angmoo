"""Freeze only the new unpublished v30 contract; historical manifests stay intact."""
import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.dialects import sqlite

from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata, create_schema_version_table, sqlite_schema_contract_digest

NEW_TABLES = (
    "world_credentials", "world_credential_revisions", "world_image_policies", "world_image_attempts",
    "memory_subject_profiles", "memory_index_preparations", "memory_episode_restrictions",
)


def main():
    register_models()
    metadata = build_sqlite_baseline_metadata()
    root = Path(__file__).resolve().parents[2] / "backend/app/runtime/migrations/sqlite_versions"
    targets = (root / "world_activity_v30_ddl.json", root / "manifests/v30.json")
    if any(path.exists() for path in targets):
        raise SystemExit("v30_contract_already_frozen")
    statements = []
    for table in metadata.sorted_tables:
        if table.name in NEW_TABLES:
            statements.append(str(CreateTable(table).compile(dialect=sqlite.dialect())))
            statements.extend(str(CreateIndex(index).compile(dialect=sqlite.dialect())) for index in sorted(table.indexes, key=lambda i: i.name))
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        metadata.create_all(connection)
        create_schema_version_table(connection)
        manifest = {"schema_version": 30, "canonical_table_count": len(metadata.tables),
            "schema_digest": sqlite_schema_contract_digest(connection), "table_inventory": sorted(metadata.tables),
            "source_revision": "20261006_0107", "source_migration_count": 106}
    targets[0].write_text(json.dumps(statements, indent=2) + "\n", encoding="utf-8")
    targets[1].write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
