"""Versioned SQLite baseline derived from the frozen canonical model schema."""

from __future__ import annotations

import hashlib
import json
import re

from pgvector.sqlalchemy import Vector
from sqlalchemy import Connection, MetaData, text
from sqlalchemy.ext.compiler import compiles

from app.core.db import Base


SQLITE_SCHEMA_VERSION = 1
SOURCE_ALEMBIC_REVISION = "20260819_0082"
SOURCE_ALEMBIC_MIGRATION_COUNT = 81
EXPECTED_CANONICAL_TABLE_COUNT = 83
SCHEMA_VERSION_TABLE = "angmoo_schema_version"


@compiles(Vector, "sqlite")
def _compile_vector_for_sqlite(
    _type: Vector, _compiler: object, **_kwargs: object
) -> str:
    # Vector recall stays OFF in ER2. Existing values use a deterministic JSON-like
    # text representation until the optional vector port is explicitly enabled.
    return "TEXT"


def build_sqlite_baseline_metadata() -> MetaData:
    """Copy registered canonical metadata and preserve partial-index meaning.

    Application composition owns importing the canonical model registry before
    this adapter opens. Runtime persistence does not reach upward into the
    legacy ``app.models`` compatibility surface.
    """

    metadata = MetaData()
    for table_name in sorted(Base.metadata.tables):
        Base.metadata.tables[table_name].to_metadata(metadata)
    for table in metadata.tables.values():
        for index in table.indexes:
            postgresql_where = index.dialect_options["postgresql"].get("where")
            if postgresql_where is not None:
                index.dialect_options["sqlite"]["where"] = text(
                    str(postgresql_where)
                )
    if len(metadata.tables) != EXPECTED_CANONICAL_TABLE_COUNT:
        raise RuntimeError(
            "canonical table inventory drifted: "
            f"expected {EXPECTED_CANONICAL_TABLE_COUNT}, got {len(metadata.tables)}"
        )
    return metadata


def create_schema_version_table(connection: Connection) -> None:
    connection.exec_driver_sql(
        f"""
        CREATE TABLE {SCHEMA_VERSION_TABLE} (
            singleton_key INTEGER PRIMARY KEY CHECK (singleton_key = 1),
            schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
            source_revision TEXT NOT NULL,
            source_migration_count INTEGER NOT NULL CHECK (source_migration_count >= 1),
            schema_digest TEXT NOT NULL CHECK (length(schema_digest) = 64),
            created_at TEXT NOT NULL
        )
        """
    )


def sqlite_schema_digest(connection: Connection) -> str:
    rows = connection.exec_driver_sql(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL
        ORDER BY type, name, tbl_name
        """
    ).mappings()
    canonical = [
        {
            "type": str(row["type"]),
            "name": str(row["name"]),
            "table": str(row["tbl_name"]),
            "sql": _normalize_sql(str(row["sql"])),
        }
        for row in rows
    ]
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_sql(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


__all__ = [
    "EXPECTED_CANONICAL_TABLE_COUNT",
    "SCHEMA_VERSION_TABLE",
    "SOURCE_ALEMBIC_MIGRATION_COUNT",
    "SOURCE_ALEMBIC_REVISION",
    "SQLITE_SCHEMA_VERSION",
    "build_sqlite_baseline_metadata",
    "create_schema_version_table",
    "sqlite_schema_digest",
]
