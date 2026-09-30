"""One-time v26 DDL/manifest capture. Never refresh a released older manifest."""
import json
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import postgresql

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_image_schema import IMAGE_TABLES, IMAGE_COLUMNS
from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata, create_schema_version_table, sqlite_schema_contract_digest


def main():
    register_models()
    engine = create_engine("sqlite://")
    metadata = build_sqlite_baseline_metadata()
    ddl = {}
    for name in (*IMAGE_TABLES, *IMAGE_COLUMNS):
        table = metadata.tables[name]
        ddl[name] = {"create": str(CreateTable(table).compile(dialect=engine.dialect)),
                     "indexes": [str(CreateIndex(i).compile(dialect=engine.dialect)) for i in sorted(table.indexes, key=lambda i: i.name)],
                     "postgres_create": str(CreateTable(table).compile(dialect=postgresql.dialect())),
                     "postgres_indexes": [str(CreateIndex(i).compile(dialect=postgresql.dialect())) for i in sorted(table.indexes, key=lambda i: i.name)]}
    root = ROOT / "backend/app/runtime/migrations/sqlite_versions"
    (root / "image_v26_ddl.json").write_text(json.dumps(ddl, indent=2) + "\n", encoding="utf-8")
    metadata.create_all(engine)
    with engine.begin() as connection:
        create_schema_version_table(connection)
        manifest = dict(schema_version=26, canonical_table_count=len(metadata.tables),
                        schema_digest=sqlite_schema_contract_digest(connection),
                        table_inventory=sorted(metadata.tables), source_revision="20260930_0104", source_migration_count=103)
    (root / "manifests/v26.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"v26: {len(metadata.tables)} tables")


if __name__ == "__main__":
    main()
