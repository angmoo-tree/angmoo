"""Author the new v27 manifest; existing version contracts are never rewritten."""
import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.dialects import sqlite

from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata, create_schema_version_table, sqlite_schema_contract_digest


def main():
    register_models()
    metadata = build_sqlite_baseline_metadata()
    root = Path(__file__).resolve().parents[2] / "backend/app/runtime/migrations/sqlite_versions"
    targets = [root / "environment_v27_ddl.json", root / "manifests/v27.json"]
    if any(path.exists() for path in targets):
        raise RuntimeError("v27_contract_already_authored")
    ddl = {name: {"create": str(CreateTable(metadata.tables[name]).compile(dialect=sqlite.dialect())),
        "indexes": sorted(str(CreateIndex(index).compile(dialect=sqlite.dialect())) for index in metadata.tables[name].indexes)}
        for name in ("local_environments", "environment_timezone_changes")}
    targets[0].write_text(json.dumps(ddl, indent=2) + "\n", encoding="utf-8")
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.begin() as connection:
        create_schema_version_table(connection)
        manifest = {"schema_version": 27, "canonical_table_count": len(metadata.tables),
            "schema_digest": sqlite_schema_contract_digest(connection), "table_inventory": sorted(metadata.tables),
            "source_revision": "20261003_0105", "source_migration_count": 104}
    targets[1].write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    engine.dispose()
    print(f"v27 authored: {len(metadata.tables)} tables")


if __name__ == "__main__":
    main()
