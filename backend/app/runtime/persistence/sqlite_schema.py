"""Versioned SQLite baseline derived from the frozen canonical model schema."""

from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy import Connection, MetaData, text

from app.models import Base


SQLITE_SCHEMA_VERSION = 19
SOURCE_ALEMBIC_REVISION = "20260918_0096"
SOURCE_ALEMBIC_MIGRATION_COUNT = 95
EXPECTED_CANONICAL_TABLE_COUNT = 133
SCHEMA_VERSION_TABLE = "angmoo_schema_version"

ACTIVITY_V19_TABLES = (
    "world_character_activity_states", "world_character_state_receipts",
    "activity_engine_policies", "activity_graph_runs",
)

CONSOLIDATION_V14_TABLES = ("memory_consolidation_requests", "memory_consolidation_jobs")
RECOMMENDATION_V15_TABLES = (
    "social_recommendation_catalogs", "social_recommendation_topics",
    "social_recommendation_topic_sources", "social_recommendation_posts",
    "social_recommendation_post_topics", "social_recommendation_preparations",
    "social_recommendation_deliveries",
)

EPISODE_V13_TABLES = (
    "chat_message_thoughts", "social_activity_thoughts",
    "memory_episode_bundles", "memory_episode_info", "memory_episode_units",
    "memory_episode_unit_evidence", "memory_episode_processed_units", "memory_episode_links",
)

MEMORY_BATCH_V9_TABLES = (
    "memory_batch_profiles",
    "memory_batch_settings",
    "memory_activation_epochs",
    "memory_source_deliveries",
    "memory_batch_runs",
    "memory_selection_decisions",
)
SQLITE_V8_SCHEMA_VERSION = 8
SQLITE_V8_SOURCE_ALEMBIC_REVISION = "20260904_0088"
SQLITE_V8_SOURCE_ALEMBIC_MIGRATION_COUNT = 87
SQLITE_V8_CANONICAL_TABLE_COUNT = 96

SQLITE_V5_SCHEMA_VERSION = 5
SQLITE_V5_SOURCE_ALEMBIC_REVISION = "20260831_0085"
SQLITE_V5_SOURCE_ALEMBIC_MIGRATION_COUNT = 84
SQLITE_V5_CANONICAL_TABLE_COUNT = 94
RESPONSE_REQUEST_V6_TABLES = ("chat_response_requests",)

SQLITE_V6_SCHEMA_VERSION = 6
SQLITE_V6_SOURCE_ALEMBIC_REVISION = "20260831_0086"
SQLITE_V6_SOURCE_ALEMBIC_MIGRATION_COUNT = 85
SQLITE_V6_CANONICAL_TABLE_COUNT = 95

SQLITE_V7_SCHEMA_VERSION = 7
SQLITE_V7_SOURCE_ALEMBIC_REVISION = "20260903_0087"
SQLITE_V7_SOURCE_ALEMBIC_MIGRATION_COUNT = 86
SQLITE_V7_CANONICAL_TABLE_COUNT = 95
SUBJECTIVE_CONTEXT_V8_TABLES = ("social_action_subjective_contexts",)

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
                index.dialect_options["sqlite"]["where"] = text(str(postgresql_where))
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

    from app.domains.chat.infrastructure.world_scope_migration import (
        add_world_scoped_message_threads_v4_table,
    )

    metadata = MetaData()
    for table_name in sorted(Base.metadata.tables):
        if table_name in EPISODE_V13_TABLES + CONSOLIDATION_V14_TABLES:
            continue
        if (
            table_name == "message_threads"
            or table_name in MEMORY_V5_TABLES
            or table_name in MEMORY_BATCH_V9_TABLES
            or table_name in RESPONSE_REQUEST_V6_TABLES
            or table_name in SUBJECTIVE_CONTEXT_V8_TABLES
        ):
            continue
        Base.metadata.tables[table_name].to_metadata(metadata)
    add_world_scoped_message_threads_v4_table(metadata)
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
        if table_name in EPISODE_V13_TABLES + CONSOLIDATION_V14_TABLES:
            continue
        if (
            table_name == "message_threads"
            or table_name in MEMORY_V5_TABLES
            or table_name in MEMORY_BATCH_V9_TABLES
            or table_name in RESPONSE_REQUEST_V6_TABLES
            or table_name in SUBJECTIVE_CONTEXT_V8_TABLES
        ):
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


def build_sqlite_v5_metadata() -> MetaData:
    """Return the immutable pre-response-lifecycle embedded inventory."""

    from app.domains.chat.infrastructure.world_scope_migration import (
        add_world_scoped_message_threads_v4_table,
    )

    metadata = MetaData()
    for table_name in sorted(Base.metadata.tables):
        if table_name in EPISODE_V13_TABLES + CONSOLIDATION_V14_TABLES:
            continue
        if (
            table_name == "message_threads"
            or table_name in RESPONSE_REQUEST_V6_TABLES
            or table_name in MEMORY_BATCH_V9_TABLES
            or table_name in SUBJECTIVE_CONTEXT_V8_TABLES
        ):
            continue
        Base.metadata.tables[table_name].to_metadata(metadata)
    add_world_scoped_message_threads_v4_table(metadata)
    _copy_partial_index_predicates(metadata)
    if len(metadata.tables) != SQLITE_V5_CANONICAL_TABLE_COUNT:
        raise RuntimeError(
            "SQLite v5 table inventory drifted: "
            f"expected {SQLITE_V5_CANONICAL_TABLE_COUNT}, got {len(metadata.tables)}"
        )
    return metadata


def build_sqlite_v6_metadata() -> MetaData:
    """Return the immutable pre-model-binding embedded inventory."""

    from app.domains.chat.infrastructure.world_scope_migration import (
        add_world_scoped_message_threads_v4_table,
    )

    metadata = MetaData()
    for table_name in sorted(Base.metadata.tables):
        if table_name in EPISODE_V13_TABLES + CONSOLIDATION_V14_TABLES:
            continue
        if (
            table_name == "message_threads"
            or table_name in SUBJECTIVE_CONTEXT_V8_TABLES
            or table_name in MEMORY_BATCH_V9_TABLES
        ):
            continue
        Base.metadata.tables[table_name].to_metadata(metadata)
    add_world_scoped_message_threads_v4_table(metadata)
    _copy_partial_index_predicates(metadata)
    if len(metadata.tables) != SQLITE_V6_CANONICAL_TABLE_COUNT:
        raise RuntimeError(
            "SQLite v6 table inventory drifted: "
            f"expected {SQLITE_V6_CANONICAL_TABLE_COUNT}, got {len(metadata.tables)}"
        )
    return metadata


def build_sqlite_v7_metadata() -> MetaData:
    """Return the immutable pre-subjective-context embedded inventory."""

    metadata = MetaData()
    for table_name in sorted(Base.metadata.tables):
        if table_name in EPISODE_V13_TABLES + CONSOLIDATION_V14_TABLES:
            continue
        if (
            table_name in SUBJECTIVE_CONTEXT_V8_TABLES
            or table_name in MEMORY_BATCH_V9_TABLES
        ):
            continue
        Base.metadata.tables[table_name].to_metadata(metadata)
    _copy_partial_index_predicates(metadata)
    if len(metadata.tables) != SQLITE_V7_CANONICAL_TABLE_COUNT:
        raise RuntimeError(
            "SQLite v7 table inventory drifted: "
            f"expected {SQLITE_V7_CANONICAL_TABLE_COUNT}, got {len(metadata.tables)}"
        )
    return metadata


def build_sqlite_v8_metadata() -> MetaData:
    """Immutable pre-batch settings/admission schema."""
    metadata = MetaData()
    for table_name in sorted(Base.metadata.tables):
        if table_name in EPISODE_V13_TABLES + CONSOLIDATION_V14_TABLES:
            continue
        if table_name not in MEMORY_BATCH_V9_TABLES:
            Base.metadata.tables[table_name].to_metadata(metadata)
    _copy_partial_index_predicates(metadata)
    if len(metadata.tables) != SQLITE_V8_CANONICAL_TABLE_COUNT:
        raise RuntimeError("SQLite v8 table inventory drifted")
    return metadata


def build_sqlite_v10_metadata() -> MetaData:
    """Frozen predecessor: generation thinking settings, no diagnostics table."""
    metadata = build_sqlite_v11_metadata()
    metadata.remove(metadata.tables["chat_retrieval_diagnostics"])
    return metadata


def build_sqlite_v11_metadata() -> MetaData:
    """Frozen pre-vector-registration schema; existing manifests stay immutable."""
    metadata = build_sqlite_v12_metadata()
    for name in ("memory_vector_eligibility", "memory_embedding_settings"):
        metadata.remove(metadata.tables[name])
    return metadata


def build_sqlite_v12_metadata() -> MetaData:
    """Immutable predecessor of episode/thought storage, without backfill."""
    metadata = build_sqlite_v13_metadata()
    for name in reversed(EPISODE_V13_TABLES):
        metadata.remove(metadata.tables[name])
    return metadata


def build_sqlite_v9_metadata() -> MetaData:
    """Frozen pre-generation-profile schema for supported upgrades."""
    metadata = build_sqlite_v12_metadata()
    _copy_partial_index_predicates(metadata)
    return metadata


def _copy_partial_index_predicates(metadata: MetaData) -> None:
    _remove_activity_schema(metadata)
    _remove_relationship_personalization_schema(metadata)
    _remove_recommendation_schema(metadata)
    for name in ("memory_vector_eligibility", "memory_embedding_settings"):
        if name in metadata.tables:
            metadata.remove(metadata.tables[name])
    if "chat_retrieval_diagnostics" in metadata.tables:
        metadata.remove(metadata.tables["chat_retrieval_diagnostics"])
    # All callers are historical builders. Never let current ORM additions
    # silently change an already released schema/manifest.
    from app.runtime.persistence.sqlite_generation_profiles import ADDED_COLUMNS
    for name, columns in ADDED_COLUMNS.items():
        if name in metadata.tables:
            table = metadata.tables[name]
            for column in columns:
                if column in table.c:
                    table._columns.remove(table.c[column])
    for table in metadata.tables.values():
        for index in table.indexes:
            postgresql_where = index.dialect_options["postgresql"].get("where")
            if postgresql_where is not None:
                index.dialect_options["sqlite"]["where"] = text(str(postgresql_where))


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
    "RESPONSE_REQUEST_V6_TABLES",
    "SUBJECTIVE_CONTEXT_V8_TABLES",
    "SCHEMA_VERSION_TABLE",
    "SOURCE_ALEMBIC_MIGRATION_COUNT",
    "SOURCE_ALEMBIC_REVISION",
    "SQLITE_SCHEMA_VERSION",
    "SQLITE_V6_CANONICAL_TABLE_COUNT",
    "SQLITE_V6_SCHEMA_VERSION",
    "SQLITE_V6_SOURCE_ALEMBIC_MIGRATION_COUNT",
    "SQLITE_V6_SOURCE_ALEMBIC_REVISION",
    "SQLITE_V7_CANONICAL_TABLE_COUNT",
    "SQLITE_V7_SCHEMA_VERSION",
    "SQLITE_V7_SOURCE_ALEMBIC_MIGRATION_COUNT",
    "SQLITE_V7_SOURCE_ALEMBIC_REVISION",
    "SQLITE_V5_CANONICAL_TABLE_COUNT",
    "SQLITE_V5_SCHEMA_VERSION",
    "SQLITE_V5_SOURCE_ALEMBIC_MIGRATION_COUNT",
    "SQLITE_V5_SOURCE_ALEMBIC_REVISION",
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
    "build_sqlite_v5_metadata",
    "build_sqlite_v6_metadata",
    "build_sqlite_v7_metadata",
    "create_schema_version_table",
    "sqlite_schema_contract_digest",
    "sqlite_schema_digest",
]


def build_sqlite_v13_metadata() -> MetaData:
    """Frozen episode-memory schema preceding trigger receipts."""
    metadata = build_sqlite_v14_metadata()
    for name in reversed(CONSOLIDATION_V14_TABLES):
        metadata.remove(metadata.tables[name])
    return metadata


def _remove_recommendation_schema(metadata: MetaData) -> None:
    for name in reversed(RECOMMENDATION_V15_TABLES):
        if name in metadata.tables:
            metadata.remove(metadata.tables[name])
    _restore_legacy_feed_constraint(metadata)


def _restore_legacy_feed_constraint(metadata: MetaData) -> None:
    posts = metadata.tables.get("posts")
    if posts is not None:
        for index in tuple(posts.indexes):
            if index.name == "ix_posts_world_author_created":
                posts.indexes.remove(index)
    table = metadata.tables.get("world_characters")
    if table is not None:
        for constraint in table.constraints:
            if constraint.name == "ck_world_characters_feed_runtime_mode":
                constraint.sqltext = text("feed_runtime_mode IN ('legacy_latest_v1','keyword_search_v1')")


def build_sqlite_v14_metadata() -> MetaData:
    metadata = build_sqlite_v16_metadata()
    _remove_recommendation_schema(metadata)
    return metadata


def build_sqlite_v15_metadata() -> MetaData:
    metadata = build_sqlite_v16_metadata()
    _restore_legacy_feed_constraint(metadata)
    return metadata


RELATIONSHIP_V17_TABLES = (
    "relationship_policies", "relationship_experience_receipts", "relationship_metric_applications",
    "relationship_metric_budgets", "relationship_review_work", "relationship_review_memory_receipts",
)
RELATIONSHIP_V17_COLUMNS = (
    "relationship_label", "perception", "view_version", "view_updated_at", "reviewed_at", "last_metric_at",
)


def _remove_relationship_personalization_schema(metadata: MetaData) -> None:
    if "relationship_review_requests" in metadata.tables:
        metadata.remove(metadata.tables["relationship_review_requests"])
    for name in reversed(RELATIONSHIP_V17_TABLES):
        if name in metadata.tables:
            metadata.remove(metadata.tables[name])
    state = metadata.tables.get("relationship_states")
    if state is not None:
        for name in RELATIONSHIP_V17_COLUMNS:
            if name in state.c:
                state._columns.remove(state.c[name])
    outbox = metadata.tables.get("graph_projection_outbox")
    if outbox is not None:
        if "relationship_state_id" in outbox.c:
            column = outbox.c.relationship_state_id
            for fk in tuple(column.foreign_keys):
                outbox.foreign_keys.discard(fk)
                outbox.constraints.discard(fk.constraint)
            outbox._columns.remove(column)
        outbox.c.source_event_id.nullable = False
        for constraint in outbox.constraints:
            if constraint.name == "ck_graph_projection_outbox_type":
                constraint.sqltext = text("projection_type IN ('social_event','relationship_state','source_exclusion')")


def build_sqlite_v16_metadata() -> MetaData:
    metadata = build_sqlite_v18_metadata()
    _remove_relationship_personalization_schema(metadata)
    return metadata


def build_sqlite_v17_metadata() -> MetaData:
    metadata = build_sqlite_v18_metadata()
    metadata.remove(metadata.tables["relationship_review_requests"])
    return metadata


def _remove_activity_schema(metadata: MetaData) -> None:
    for name in reversed(ACTIVITY_V19_TABLES):
        if name in metadata.tables:
            metadata.remove(metadata.tables[name])


def build_sqlite_v18_metadata() -> MetaData:
    metadata = build_sqlite_baseline_metadata()
    _remove_activity_schema(metadata)
    return metadata
