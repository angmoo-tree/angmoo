"""Frozen v19 observation identity and v20 SQLite outbox schema.

This module intentionally does not import the current ORM or observation policy.
Only a validated NULL relationship_state_id may change during the copy.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json

from sqlalchemy import Connection, text

from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError


MUTABLE_IDENTITY_TABLES = frozenset({"graph_projection_outbox"})
COLUMNS = (
    "id", "world_id", "source_event_id", "relationship_state_id",
    "projection_type", "payload_version", "payload", "source_signature", "dedupe_key",
    "status", "attempt_count", "lease_owner", "lease_expires_at", "next_attempt_at",
    "last_error_class", "created_at", "updated_at", "completed_at",
)
_OBSERVATION_VERSION = "relationship-observation-v1"
_PAYLOAD_KEYS = frozenset({
    "world_id", "source_event_id", "actor_world_character_id",
    "target_world_character_id", "relationship_state_id",
})
_BATCH_SIZE = 500
_TABLE_DDL = """
CREATE TABLE graph_projection_outbox_v20 (
    id VARCHAR(64) NOT NULL,
    world_id VARCHAR(64) NOT NULL,
    source_event_id VARCHAR(64),
    relationship_state_id VARCHAR(64),
    projection_type VARCHAR(32) NOT NULL,
    payload_version VARCHAR(40) NOT NULL,
    payload JSON NOT NULL,
    source_signature VARCHAR(64) NOT NULL,
    dedupe_key VARCHAR(128) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    attempt_count INTEGER NOT NULL,
    lease_owner VARCHAR(128),
    lease_expires_at DATETIME,
    next_attempt_at DATETIME,
    last_error_class VARCHAR(120),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at DATETIME,
    PRIMARY KEY (id),
    CONSTRAINT ck_graph_projection_outbox_attempts CHECK (attempt_count >= 0),
    FOREIGN KEY(source_event_id) REFERENCES social_events (id),
    CONSTRAINT ck_graph_projection_outbox_observation_identity CHECK (NOT (projection_type = 'relationship_state' AND payload_version = 'relationship-observation-v1') OR (source_event_id IS NOT NULL AND relationship_state_id IS NOT NULL)),
    CONSTRAINT ck_graph_projection_outbox_status CHECK (status IN ('pending','processing','succeeded','dead','cancelled')),
    FOREIGN KEY(relationship_state_id) REFERENCES relationship_states (id),
    CONSTRAINT ck_graph_projection_outbox_type CHECK (projection_type IN ('social_event','relationship_state','source_exclusion','relationship_snapshot')),
    FOREIGN KEY(world_id) REFERENCES worlds (id),
    CONSTRAINT uq_graph_projection_outbox_dedupe UNIQUE (dedupe_key)
)
"""
_INDEX_DDL = (
    "CREATE INDEX ix_graph_projection_outbox_pending ON graph_projection_outbox (status, next_attempt_at, created_at)",
    "CREATE INDEX ix_graph_projection_outbox_world_created ON graph_projection_outbox (world_id, created_at)",
    "CREATE UNIQUE INDEX uq_graph_projection_outbox_observation ON graph_projection_outbox (projection_type, source_event_id, payload_version, relationship_state_id) WHERE projection_type = 'relationship_state' AND payload_version = 'relationship-observation-v1'",
    "CREATE UNIQUE INDEX uq_graph_projection_outbox_source_event ON graph_projection_outbox (projection_type, source_event_id, payload_version) WHERE source_event_id IS NOT NULL AND NOT (projection_type = 'relationship_state' AND payload_version = 'relationship-observation-v1')",
)


@dataclass(frozen=True)
class OutboxDelta:
    row_count: int
    before_sha256: str
    expected_sha256: str
    statuses: tuple[tuple[str, int], ...]
    observation_count: int
    backfill_count: int


def _is_observation(row: dict[str, object]) -> bool:
    return (row["projection_type"] == "relationship_state"
            and row["payload_version"] == _OBSERVATION_VERSION)


def _observation_state_id(connection: Connection, row: dict[str, object]) -> str:
    if isinstance(row["payload"], dict):
        payload = row["payload"]
    else:
        try:
            payload = json.loads(str(row["payload"]))
        except (TypeError, ValueError) as exc:
            raise SqliteMigrationDeltaError("observation_outbox_legacy_payload_invalid") from exc
    if not isinstance(payload, dict) or set(payload) != _PAYLOAD_KEYS:
        raise SqliteMigrationDeltaError("observation_outbox_legacy_payload_invalid")
    if any(not isinstance(value, str) or not value for value in payload.values()):
        raise SqliteMigrationDeltaError("observation_outbox_legacy_identity_invalid")
    state_id = payload["relationship_state_id"]
    if (
        payload["world_id"] != row["world_id"]
        or payload["source_event_id"] != row["source_event_id"]
        or row["relationship_state_id"] not in (None, state_id)
        or payload["actor_world_character_id"] == payload["target_world_character_id"]
    ):
        raise SqliteMigrationDeltaError("observation_outbox_legacy_identity_invalid")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signature = sha256(canonical.encode("utf-8")).hexdigest()
    dedupe = sha256(
        f"relationship_state|{row['source_event_id']}|{_OBSERVATION_VERSION}|{state_id}".encode("utf-8")
    ).hexdigest()
    if row["source_signature"] != signature or row["dedupe_key"] != dedupe:
        raise SqliteMigrationDeltaError("observation_outbox_legacy_hash_invalid")
    event = connection.execute(
        text("SELECT world_id, actor_world_character_id, result FROM social_events WHERE id = :id"),
        {"id": row["source_event_id"]},
    ).one_or_none()
    state = connection.execute(text(
        "SELECT world_id, actor_world_character_id, target_world_character_id "
        "FROM relationship_states WHERE id = :id"), {"id": state_id},
    ).one_or_none()
    if (
        event is None or state is None or event[0] != row["world_id"]
        or event[2] != "succeeded" or state[0] != row["world_id"]
        or state[1] != payload["actor_world_character_id"]
        or state[2] != payload["target_world_character_id"]
        or state[2] != event[1]
    ):
        raise SqliteMigrationDeltaError("observation_outbox_legacy_reference_invalid")
    receipt = connection.execute(text(
        "SELECT world_id, actor_world_character_id, target_world_character_id "
        "FROM relationship_state_changes WHERE relationship_state_id = :state_id AND social_event_id = :event_id"),
        {"state_id": state_id, "event_id": row["source_event_id"]},
    ).one_or_none()
    if (
        receipt is None or receipt[0] != row["world_id"]
        or receipt[1] != state[1] or receipt[2] != state[2]
    ):
        raise SqliteMigrationDeltaError("observation_outbox_legacy_receipt_invalid")
    return state_id


def _rows(connection: Connection, table: str):
    last_id = ""
    while True:
        batch = connection.execute(
            text(f"SELECT {', '.join(COLUMNS)} FROM {table} "
                 "WHERE id > :last_id ORDER BY id LIMIT :batch_size"),
            {"last_id": last_id, "batch_size": _BATCH_SIZE},
        ).mappings().all()
        if not batch:
            return
        for values in batch:
            row = dict(values)
            last_id = str(row["id"])
            yield row


def _digest_row(hasher, row: dict[str, object]) -> None:
    hasher.update(json.dumps(
        [row[name] for name in COLUMNS], ensure_ascii=False,
        separators=(",", ":"), sort_keys=True, default=str,
    ).encode("utf-8"))
    hasher.update(b"\n")


def capture_delta(connection: Connection) -> OutboxDelta:
    before = sha256()
    expected = sha256()
    statuses: Counter[str] = Counter()
    count = observations = backfills = 0
    for row in _rows(connection, "graph_projection_outbox"):
        count += 1
        statuses[str(row["status"])] += 1
        _digest_row(before, row)
        if _is_observation(row):
            observations += 1
            state_id = _observation_state_id(connection, row)
            if row["relationship_state_id"] is None:
                backfills += 1
                row["relationship_state_id"] = state_id
        _digest_row(expected, row)
    return OutboxDelta(
        count, before.hexdigest(), expected.hexdigest(),
        tuple(sorted(statuses.items())), observations, backfills,
    )


def upgrade(connection: Connection) -> None:
    if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0:
        raise SqliteMigrationDeltaError("observation_outbox_fk_precondition_failed")
    before = capture_delta(connection)
    connection.exec_driver_sql(_TABLE_DDL)
    columns = ", ".join(COLUMNS)
    placeholders = ", ".join("?" for _ in COLUMNS)
    insert_sql = f"INSERT INTO graph_projection_outbox_v20 ({columns}) VALUES ({placeholders})"
    copied = 0
    pending: list[tuple[object, ...]] = []
    for row in _rows(connection, "graph_projection_outbox"):
        if _is_observation(row):
            row["relationship_state_id"] = _observation_state_id(connection, row)
        pending.append(tuple(row[name] for name in COLUMNS))
        if len(pending) == _BATCH_SIZE:
            connection.exec_driver_sql(insert_sql, pending)
            pending.clear()
        copied += 1
    if pending:
        connection.exec_driver_sql(insert_sql, pending)
    if copied != before.row_count:
        raise SqliteMigrationDeltaError("observation_outbox_copy_count_invalid")
    connection.exec_driver_sql("DROP TABLE graph_projection_outbox")
    connection.exec_driver_sql(
        _TABLE_DDL.replace("graph_projection_outbox_v20", "graph_projection_outbox", 1)
    )
    # SQLite RENAME would quote the final table name in sqlite_master, making
    # the manifest differ from the same schema created on a fresh database.
    connection.exec_driver_sql(
        f"INSERT INTO graph_projection_outbox ({columns}) "
        f"SELECT {columns} FROM graph_projection_outbox_v20"
    )
    connection.exec_driver_sql("DROP TABLE graph_projection_outbox_v20")
    for statement in _INDEX_DDL:
        connection.exec_driver_sql(statement)
    verify_delta(connection, before)


def backfill_postgresql(connection: Connection) -> None:
    """Validate every legacy observation and update only missing identity IDs."""
    if connection.dialect.name != "postgresql":
        raise SqliteMigrationDeltaError("observation_outbox_dialect_invalid")
    statement = text(
        "UPDATE graph_projection_outbox SET relationship_state_id = :state_id "
        "WHERE id = :id AND relationship_state_id IS NULL"
    )
    pending: list[dict[str, str]] = []
    for row in _rows(connection, "graph_projection_outbox"):
        if not _is_observation(row):
            continue
        state_id = _observation_state_id(connection, row)
        if row["relationship_state_id"] is None:
            pending.append({"state_id": state_id, "id": str(row["id"])})
            if len(pending) == _BATCH_SIZE:
                connection.execute(statement, pending)
                pending.clear()
    if pending:
        connection.execute(statement, pending)


def verify_delta(connection: Connection, before: OutboxDelta) -> None:
    actual = sha256()
    statuses: Counter[str] = Counter()
    count = observations = 0
    for row in _rows(connection, "graph_projection_outbox"):
        count += 1
        statuses[str(row["status"])] += 1
        if _is_observation(row):
            observations += 1
            if row["relationship_state_id"] is None:
                raise SqliteMigrationDeltaError("observation_outbox_backfill_missing")
        _digest_row(actual, row)
    if (
        count != before.row_count
        or observations != before.observation_count
        or tuple(sorted(statuses.items())) != before.statuses
        or actual.hexdigest() != before.expected_sha256
    ):
        raise SqliteMigrationDeltaError("observation_outbox_delta_invalid")
