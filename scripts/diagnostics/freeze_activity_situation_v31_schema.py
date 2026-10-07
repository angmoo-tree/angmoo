"""Freeze the new v31 schema without touching any published manifest."""
import json
import argparse
import subprocess
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.dialects import sqlite
from app.domains.memory.models.activity_situation import SITUATION_TABLES
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata, create_schema_version_table, sqlite_schema_contract_digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace-unpublished", action="store_true")
    arguments = parser.parse_args()
    register_models()
    metadata = build_sqlite_baseline_metadata()
    root = Path(__file__).resolve().parents[2] / "backend/app/runtime/migrations/sqlite_versions"
    ddl, manifest_path = root / "activity_situation_v31_ddl.json", root / "manifests/v31.json"
    if ddl.exists() or manifest_path.exists():
        repo = Path(__file__).resolve().parents[2]
        published = any(subprocess.run(["git", "cat-file", "-e", "HEAD:" + path.relative_to(repo).as_posix()],
            cwd=repo, capture_output=True).returncode == 0 for path in (ddl, manifest_path))
        if published or not arguments.replace_unpublished:
            raise SystemExit("v31_contract_already_frozen")
    statements = []
    for table in metadata.sorted_tables:
        if table.name in SITUATION_TABLES:
            statements.append(str(CreateTable(table).compile(dialect=sqlite.dialect())))
            statements.extend(str(CreateIndex(index).compile(dialect=sqlite.dialect())) for index in sorted(table.indexes, key=lambda i: i.name))
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        metadata.create_all(connection)
        create_schema_version_table(connection)
        manifest = {"schema_version": 31, "canonical_table_count": len(metadata.tables),
            "schema_digest": sqlite_schema_contract_digest(connection), "table_inventory": sorted(metadata.tables),
            "source_revision": "20261008_0108", "source_migration_count": 107}
    ddl.write_text(json.dumps(statements, indent=2) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    engine.dispose()


if __name__ == "__main__":
    main()
