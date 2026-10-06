"""Author only the additive v28 DDL/manifest; previous contracts are immutable."""
import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.dialects import sqlite
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata, create_schema_version_table, sqlite_schema_contract_digest
from app.runtime.migrations.sqlite_versions.world_configuration_v28 import NEW_TABLES


def main():
    register_models()
    metadata = build_sqlite_baseline_metadata()
    root = Path(__file__).resolve().parents[2] / "backend/app/runtime/migrations/sqlite_versions"
    targets = [root / "world_configuration_v28_ddl.json", root / "manifests/v28.json"]
    if any(path.exists() for path in targets):
        raise RuntimeError("v28_contract_already_authored")
    ddl = {name: {"create": str(CreateTable(metadata.tables[name]).compile(dialect=sqlite.dialect())),
        "indexes": sorted(str(CreateIndex(index).compile(dialect=sqlite.dialect())) for index in metadata.tables[name].indexes)} for name in NEW_TABLES}
    targets[0].write_text(json.dumps(ddl, indent=2) + "\n", encoding="utf-8")
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.begin() as connection:
        create_schema_version_table(connection)
        manifest = {"schema_version": 28, "canonical_table_count": len(metadata.tables), "schema_digest": sqlite_schema_contract_digest(connection),
            "table_inventory": sorted(metadata.tables), "source_revision": "20261005_0106", "source_migration_count": 105}
    targets[1].write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    engine.dispose()
    print(f"v28 authored: {len(metadata.tables)} tables")


if __name__ == "__main__":
    main()
