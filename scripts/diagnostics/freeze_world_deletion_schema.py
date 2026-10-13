"""Emit only the new v37 manifest/DDL from temporary SQLite; never touch user DB."""
import json
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects.sqlite import dialect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import sqlite_schema_contract_digest, create_schema_version_table, build_sqlite_baseline_metadata
from app.runtime.world_deletion.fences import install_fences

register_models()
metadata = build_sqlite_baseline_metadata()
entries = []
for name in ("world_deletion_requests", "world_deletion_cleanup_items"):
    table = metadata.tables[name]
    entries.append({"table": name, "create": str(CreateTable(table).compile(dialect=dialect())),
        "indexes": [str(CreateIndex(index).compile(dialect=dialect())) for index in sorted(table.indexes, key=lambda value: value.name)]})
base = ROOT / "backend/app/runtime/migrations/sqlite_versions"
(base / "world_deletion_v37_ddl.json").write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
engine = create_engine("sqlite://")
with engine.begin() as connection:
    create_schema_version_table(connection)
    metadata.create_all(connection)
    install_fences(connection)
    manifest = {"schema_version": 37, "canonical_table_count": len(metadata.tables),
        "schema_digest": sqlite_schema_contract_digest(connection), "table_inventory": sorted(metadata.tables),
        "source_revision": "20261012_0114", "source_migration_count": 113}
(base / "manifests/v37.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: value for key, value in manifest.items() if key != "table_inventory"}))
