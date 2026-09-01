"""Versioned SQLite baseline derived from the frozen canonical model schema."""

from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy import Connection, MetaData, text

from app.core.db import Base


SQLITE_SCHEMA_VERSION = 5
SOURCE_ALEMBIC_REVISION = "20260831_0085"
SOURCE_ALEMBIC_MIGRATION_COUNT = 84
EXPECTED_CANONICAL_TABLE_COUNT = 94
SCHEMA_VERSION_TABLE = "angmoo_schema_version"

SQLITE_V4_SCHEMA_VERSION = 4
SQLITE_V4_SOURCE_ALEMBIC_REVISION = "20260831_0084"
SQLITE_V4_SOURCE_ALEMBIC_MIGRATION_COUNT = 83
SQLITE_V4_CANONICAL_TABLE_COUNT = 87
MEMORY_V5_TABLES = (
    "memory_scope_settings",
    "memory_candidates",
    "memory_items",
    "memory_item_evidence",
    "memory_hot_briefs",
    "memory_hot_brief_items",
    "memory_maintenance_jobs",
)

SQLITE_V1_SCHEMA_VERSION = 1
SQLITE_V1_SOURCE_ALEMBIC_REVISION = "20260819_0082"
SQLITE_V1_SOURCE_ALEMBIC_MIGRATION_COUNT = 81
SQLITE_V1_CANONICAL_TABLE_COUNT = 83
WORLD_PACKAGE_REGISTRY_TABLES = (
    "world_package_sources",
    "world_package_exports",
    "world_package_imports",
    "world_package_import_id_maps",
)


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


def build_sqlite_v1_metadata() -> MetaData:
    """Return the immutable pre-World-Package embedded SQLite inventory."""

    metadata = build_sqlite_v3_metadata()
    for table_name in reversed(WORLD_PACKAGE_REGISTRY_TABLES):
        metadata.remove(metadata.tables[table_name])
    if len(metadata.tables) != SQLITE_V1_CANONICAL_TABLE_COUNT:
        raise RuntimeError(
            "SQLite v1 table inventory drifted: "
            f"expected {SQLITE_V1_CANONICAL_TABLE_COUNT}, "
            f"got {len(metadata.tables)}"
        )
    return metadata


def build_sqlite_v4_metadata() -> MetaData:
    """Return the immutable pre-Memory embedded SQLite inventory."""

    metadata = MetaData()
    for table_name in sorted(Base.metadata.tables):
        if table_name in MEMORY_V5_TABLES:
            continue
        Base.metadata.tables[table_name].to_metadata(metadata)
    _copy_partial_index_predicates(metadata)
    if len(metadata.tables) != SQLITE_V4_CANONICAL_TABLE_COUNT:
        raise RuntimeError(
            "SQLite v4 table inventory drifted: "
            f"expected {SQLITE_V4_CANONICAL_TABLE_COUNT}, got {len(metadata.tables)}"
        )
    return metadata


def build_sqlite_v3_metadata() -> MetaData:
    """Return the immutable pre-World-Chat-v2 embedded schema."""

    from app.domains.chat.infrastructure.world_scope_migration import (
        add_legacy_message_threads_table,
    )

    metadata = MetaData()
    for table_name in sorted(Base.metadata.tables):
        if table_name == "message_threads" or table_name in MEMORY_V5_TABLES:
            continue
        Base.metadata.tables[table_name].to_metadata(metadata)
    add_legacy_message_threads_table(metadata)
    _copy_partial_index_predicates(metadata)
    if len(metadata.tables) != SQLITE_V4_CANONICAL_TABLE_COUNT:
        raise RuntimeError(
            "SQLite v3 table inventory drifted: "
            f"expected {SQLITE_V4_CANONICAL_TABLE_COUNT}, got {len(metadata.tables)}"
        )
    return metadata


def _copy_partial_index_predicates(metadata: MetaData) -> None:
    for table in metadata.tables.values():
        for index in table.indexes:
            postgresql_where = index.dialect_options["postgresql"].get("where")
            if postgresql_where is not None:
                index.dialect_options["sqlite"]["where"] = text(
                    str(postgresql_where)
                )


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


def sqlite_schema_contract_digest(connection: Connection) -> str:
    """Return an order-stable digest for immutable version manifests.

    SQLite preserves the emitted CREATE TABLE text. SQLAlchemy may emit
    semantically unordered table constraints in a different order in another
    Python process, so the mutable database marker continues to attest the raw
    SQL while version manifests use this normalized contract digest.
    """

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
            "sql": _normalize_contract_sql(
                str(row["type"]),
                str(row["sql"]),
            ),
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


def _normalize_contract_sql(object_type: str, value: str) -> str:
    normalized = _normalize_sql(value)
    if object_type != "table":
        return normalized
    opening = normalized.find("(")
    closing = normalized.rfind(")")
    if opening < 0 or closing <= opening:
        return normalized
    clauses = _split_top_level(normalized[opening + 1 : closing])
    column_clauses: list[str] = []
    constraint_clauses: list[str] = []
    constraint_prefixes = (
        "CHECK",
        "CONSTRAINT",
        "FOREIGN KEY",
        "PRIMARY KEY",
        "UNIQUE",
    )
    for clause in clauses:
        if clause.upper().startswith(constraint_prefixes):
            constraint_clauses.append(clause)
        else:
            column_clauses.append(clause)
    body = ", ".join(column_clauses + sorted(constraint_clauses))
    return f"{normalized[: opening + 1]}{body}{normalized[closing:]}"


def _split_top_level(value: str) -> list[str]:
    clauses: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    for character in value:
        if quote is not None:
            current.append(character)
            if character == quote:
                quote = None
            continue
        if character in {"'", '"', "`"}:
            quote = character
            current.append(character)
        elif character == "(":
            depth += 1
            current.append(character)
        elif character == ")":
            depth -= 1
            current.append(character)
        elif character == "," and depth == 0:
            clauses.append(_normalize_sql("".join(current)))
            current = []
        else:
            current.append(character)
    if current:
        clauses.append(_normalize_sql("".join(current)))
    return clauses


__all__ = [
    "EXPECTED_CANONICAL_TABLE_COUNT",
    "MEMORY_V5_TABLES",
    "SCHEMA_VERSION_TABLE",
    "SOURCE_ALEMBIC_MIGRATION_COUNT",
    "SOURCE_ALEMBIC_REVISION",
    "SQLITE_SCHEMA_VERSION",
    "SQLITE_V4_CANONICAL_TABLE_COUNT",
    "SQLITE_V4_SCHEMA_VERSION",
    "SQLITE_V4_SOURCE_ALEMBIC_MIGRATION_COUNT",
    "SQLITE_V4_SOURCE_ALEMBIC_REVISION",
    "SQLITE_V1_CANONICAL_TABLE_COUNT",
    "SQLITE_V1_SCHEMA_VERSION",
    "SQLITE_V1_SOURCE_ALEMBIC_MIGRATION_COUNT",
    "SQLITE_V1_SOURCE_ALEMBIC_REVISION",
    "WORLD_PACKAGE_REGISTRY_TABLES",
    "build_sqlite_baseline_metadata",
    "build_sqlite_v1_metadata",
    "build_sqlite_v3_metadata",
    "build_sqlite_v4_metadata",
    "create_schema_version_table",
    "sqlite_schema_contract_digest",
    "sqlite_schema_digest",
]
