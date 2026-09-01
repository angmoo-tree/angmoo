"""Deterministic, lossless MessageThread World-scope migration helpers."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    MetaData,
    String,
    Table,
    bindparam,
    func,
    text,
)
from sqlalchemy.schema import CreateIndex, CreateTable

from app.core.db import Base


logger = logging.getLogger(__name__)

LEGACY_MESSAGE_THREAD_COLUMNS = (
    "id",
    "requester_id",
    "character_id",
    "selected_model",
    "response_lease_token",
    "response_lease_expires_at",
    "last_message_at",
    "deleted_at",
    "created_at",
    "updated_at",
)


@dataclass(frozen=True)
class WorldScopeBackfillStats:
    total: int
    resolved: int
    ambiguous: int
    collisions: int


def add_legacy_message_threads_table(metadata: MetaData) -> Table:
    """Add the immutable pre-v4 MessageThread table to copied metadata."""

    return Table(
        "message_threads",
        metadata,
        Column("id", String(64), primary_key=True),
        Column("requester_id", ForeignKey("users.id"), nullable=False),
        Column("character_id", ForeignKey("characters.id"), nullable=False),
        Column("selected_model", String(120), nullable=False),
        Column("response_lease_token", String(64), nullable=True),
        Column("response_lease_expires_at", DateTime(timezone=True), nullable=True),
        Column("last_message_at", DateTime(timezone=True), nullable=True),
        Column("deleted_at", DateTime(timezone=True), nullable=True),
        Column(
            "created_at",
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
        Column(
            "updated_at",
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
        CheckConstraint(
            "(response_lease_token IS NULL) = "
            "(response_lease_expires_at IS NULL)",
            name="ck_message_threads_response_lease_pair",
        ),
    )


def add_world_scoped_message_threads_v4_table(metadata: MetaData) -> Table:
    """Add the immutable P8-L-D ``message_threads`` v4 table.

    Migration replay must not compile the live ORM table: later P8 stages may
    add columns or constraints to ``MessageThread`` while an installed v3
    database still needs to reproduce this exact v4 contract.
    """

    return Table(
        "message_threads",
        metadata,
        Column("id", String(64), primary_key=True),
        Column("requester_id", ForeignKey("users.id"), nullable=False),
        Column("character_id", ForeignKey("characters.id"), nullable=False),
        Column(
            "world_id",
            ForeignKey("worlds.id", name="fk_message_threads_world"),
            nullable=True,
        ),
        Column("requester_world_character_id", String(64), nullable=True),
        Column("responding_world_character_id", String(64), nullable=True),
        Column(
            "world_scope_status",
            String(20),
            nullable=False,
            server_default="ambiguous",
        ),
        Column("selected_model", String(120), nullable=False),
        Column("response_lease_token", String(64), nullable=True),
        Column("response_lease_expires_at", DateTime(timezone=True), nullable=True),
        Column("last_message_at", DateTime(timezone=True), nullable=True),
        Column("deleted_at", DateTime(timezone=True), nullable=True),
        Column(
            "created_at",
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
        Column(
            "updated_at",
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
        CheckConstraint(
            "(response_lease_token IS NULL) = "
            "(response_lease_expires_at IS NULL)",
            name="ck_message_threads_response_lease_pair",
        ),
        CheckConstraint(
            "(world_scope_status = 'resolved' AND world_id IS NOT NULL "
            "AND requester_world_character_id IS NOT NULL "
            "AND responding_world_character_id IS NOT NULL "
            "AND requester_world_character_id <> responding_world_character_id) OR "
            "(world_scope_status IN ('ambiguous', 'quarantined') "
            "AND world_id IS NULL "
            "AND requester_world_character_id IS NULL "
            "AND responding_world_character_id IS NULL)",
            name="ck_message_threads_world_scope_binding",
        ),
        ForeignKeyConstraint(
            ["requester_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_message_threads_requester_world",
        ),
        ForeignKeyConstraint(
            ["responding_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_message_threads_responding_world",
        ),
        ForeignKeyConstraint(
            ["responding_world_character_id", "character_id"],
            ["world_characters.id", "world_characters.character_id"],
            name="fk_message_threads_responding_character",
        ),
        Index(
            "uq_message_threads_active_world_roles",
            "requester_id",
            "world_id",
            "requester_world_character_id",
            "responding_world_character_id",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND world_scope_status = 'resolved'"
            ),
            sqlite_where=text(
                "deleted_at IS NULL AND world_scope_status = 'resolved'"
            ),
        ),
        Index(
            "uq_message_threads_active_legacy_ambiguous",
            "requester_id",
            "character_id",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND world_scope_status = 'ambiguous'"
            ),
            sqlite_where=text(
                "deleted_at IS NULL AND world_scope_status = 'ambiguous'"
            ),
        ),
        Index(
            "ix_message_threads_owner_world_status",
            "requester_id",
            "world_id",
            "world_scope_status",
        ),
        Index(
            "ix_message_threads_requester_last",
            "requester_id",
            "last_message_at",
        ),
    )


def rebuild_and_backfill_message_threads_v4(connection) -> WorldScopeBackfillStats:
    """Rebuild the v3 table to the canonical v4 shape and bind safe rows only."""

    _require_sqlite_rebuild_precondition(connection)
    connection.exec_driver_sql("PRAGMA defer_foreign_keys = ON")
    connection.exec_driver_sql("PRAGMA legacy_alter_table = ON")
    try:
        connection.exec_driver_sql(
            "ALTER TABLE message_threads RENAME TO message_threads_v3"
        )
        metadata = MetaData()
        for table_name in ("characters", "users", "worlds", "world_characters"):
            Base.metadata.tables[table_name].to_metadata(metadata)
        message_threads_v4 = add_world_scoped_message_threads_v4_table(metadata)
        connection.execute(CreateTable(message_threads_v4))
        old_columns = ", ".join(LEGACY_MESSAGE_THREAD_COLUMNS)
        connection.exec_driver_sql(
            "INSERT INTO message_threads ("
            f"{old_columns}, world_scope_status"
            ") SELECT "
            f"{old_columns}, 'ambiguous' FROM message_threads_v3"
        )
        stats = backfill_message_thread_world_scope(connection)
        connection.exec_driver_sql("DROP TABLE message_threads_v3")
        for index in sorted(message_threads_v4.indexes, key=lambda item: item.name or ""):
            connection.execute(CreateIndex(index))
    finally:
        connection.exec_driver_sql("PRAGMA legacy_alter_table = OFF")
    logger.info(
        "world_chat_thread_backfill total=%s resolved=%s ambiguous=%s collisions=%s",
        stats.total,
        stats.resolved,
        stats.ambiguous,
        stats.collisions,
    )
    return stats


def rebuild_message_threads_v3(
    connection, *, create_legacy_unique_index: bool = False
) -> None:
    """Restore the immutable Embedded v3 shape without changing legacy data.

    The frozen v3 manifest predates the two later ``message_threads`` indexes.
    Callers may opt into those indexes only when reconstructing a non-Embedded
    legacy deployment that is known to have carried them.
    """

    _require_sqlite_rebuild_precondition(connection)
    duplicate = connection.exec_driver_sql(
        "SELECT requester_id, character_id, count(*) AS row_count "
        "FROM message_threads WHERE deleted_at IS NULL "
        "GROUP BY requester_id, character_id HAVING count(*) > 1 LIMIT 1"
    ).mappings().first()
    if duplicate is not None:
        raise RuntimeError(
            "cannot_downgrade_world_chat_duplicate_legacy_active_tuple"
        )
    metadata = MetaData()
    for table_name in sorted(Base.metadata.tables):
        if table_name == "message_threads":
            continue
        Base.metadata.tables[table_name].to_metadata(metadata)
    legacy = add_legacy_message_threads_table(metadata)
    connection.exec_driver_sql("PRAGMA defer_foreign_keys = ON")
    connection.exec_driver_sql("PRAGMA legacy_alter_table = ON")
    try:
        connection.exec_driver_sql(
            "ALTER TABLE message_threads RENAME TO message_threads_v4"
        )
        connection.execute(CreateTable(legacy))
        old_columns = ", ".join(LEGACY_MESSAGE_THREAD_COLUMNS)
        connection.exec_driver_sql(
            f"INSERT INTO message_threads ({old_columns}) "
            f"SELECT {old_columns} FROM message_threads_v4"
        )
        connection.exec_driver_sql("DROP TABLE message_threads_v4")
        if create_legacy_unique_index:
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX uq_message_threads_active_requester_character "
                "ON message_threads (requester_id, character_id) "
                "WHERE deleted_at IS NULL"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_message_threads_requester_last "
                "ON message_threads (requester_id, last_message_at)"
            )
    finally:
        connection.exec_driver_sql("PRAGMA legacy_alter_table = OFF")


def _require_sqlite_rebuild_precondition(connection) -> None:
    """Fail before DDL when SQLite cannot safely rebuild a referenced table.

    SQLite cannot switch ``foreign_keys`` off after a transaction has begun.
    Both the Embedded copy-on-write coordinator and Alembic bootstrap therefore
    disable enforcement before opening the migration transaction, then run a
    complete ``foreign_key_check`` on the rebuilt database.  Refusing an
    unexpected FK-enabled connection here prevents child FKs from being
    rewritten to the temporary table name and prevents a half-applied rebuild.
    """

    enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
    if int(enabled) != 0:
        raise RuntimeError(
            "sqlite_world_chat_rebuild_requires_foreign_keys_off_before_transaction"
        )


def backfill_message_thread_world_scope(connection) -> WorldScopeBackfillStats:
    rows = list(
        connection.exec_driver_sql(
            "SELECT id, requester_id, character_id, deleted_at, created_at "
            "FROM message_threads ORDER BY created_at, id"
        ).mappings()
    )
    candidates: dict[str, tuple[str, str, str]] = {}
    active_by_tuple: dict[tuple[str, str, str, str], list[str]] = {}
    for row in rows:
        pairings = _candidate_pairings(
            connection,
            requester_id=str(row["requester_id"]),
            character_id=str(row["character_id"]),
        )
        if len(pairings) != 1:
            continue
        world_id, requester_id, responding_id = next(iter(pairings))
        if requester_id == responding_id:
            continue
        candidates[str(row["id"])] = (world_id, requester_id, responding_id)
        if row["deleted_at"] is None:
            key = (str(row["requester_id"]), world_id, requester_id, responding_id)
            active_by_tuple.setdefault(key, []).append(str(row["id"]))

    quarantine_ids: set[str] = set()
    for thread_ids in active_by_tuple.values():
        if len(thread_ids) <= 1:
            continue
        quarantine_ids.update(thread_ids)

    active_legacy_pairs: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        if row["deleted_at"] is None:
            active_legacy_pairs.setdefault(
                (str(row["requester_id"]), str(row["character_id"])), []
            ).append(str(row["id"]))
    for thread_ids in active_legacy_pairs.values():
        if len(thread_ids) > 1:
            quarantine_ids.update(thread_ids)
    collision_count = len(quarantine_ids)

    if quarantine_ids:
        connection.execute(
            text(
                "UPDATE message_threads SET world_scope_status = 'quarantined' "
                "WHERE id IN :thread_ids"
            ).bindparams(bindparam("thread_ids", expanding=True)),
            {"thread_ids": sorted(quarantine_ids)},
        )

    resolved = 0
    for thread_id, (world_id, requester_id, responding_id) in candidates.items():
        if thread_id in quarantine_ids:
            continue
        connection.execute(
            text(
                "UPDATE message_threads SET world_id = :world_id, "
                "requester_world_character_id = :requester_id, "
                "responding_world_character_id = :responding_id, "
                "world_scope_status = 'resolved' WHERE id = :thread_id"
            ),
            {
                "world_id": world_id,
                "requester_id": requester_id,
                "responding_id": responding_id,
                "thread_id": thread_id,
            },
        )
        resolved += 1
    return WorldScopeBackfillStats(
        total=len(rows),
        resolved=resolved,
        ambiguous=len(rows) - resolved - collision_count,
        collisions=collision_count,
    )


def expected_world_scope_bindings(
    connection, rows: list[dict[str, Any]]
) -> dict[str, tuple[str, str | None, str | None, str | None]]:
    """Return the deterministic expected v4 state for verifier fixtures."""

    ordered = sorted(rows, key=lambda row: (str(row.get("created_at")), str(row["id"])))
    candidates: dict[str, tuple[str, str, str]] = {}
    active: dict[tuple[str, str, str, str], list[str]] = {}
    for row in ordered:
        pairings = _candidate_pairings(
            connection,
            requester_id=str(row["requester_id"]),
            character_id=str(row["character_id"]),
        )
        if len(pairings) != 1:
            continue
        world_id, requester_id, responding_id = next(iter(pairings))
        if requester_id == responding_id:
            continue
        thread_id = str(row["id"])
        candidates[thread_id] = (world_id, requester_id, responding_id)
        if row.get("deleted_at") is None:
            key = (str(row["requester_id"]), world_id, requester_id, responding_id)
            active.setdefault(key, []).append(thread_id)
    quarantined = {
        thread_id
        for thread_ids in active.values()
        if len(thread_ids) > 1
        for thread_id in thread_ids
    }
    active_legacy_pairs: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        if row.get("deleted_at") is None:
            active_legacy_pairs.setdefault(
                (str(row["requester_id"]), str(row["character_id"])), []
            ).append(str(row["id"]))
    quarantined.update(
        thread_id
        for thread_ids in active_legacy_pairs.values()
        if len(thread_ids) > 1
        for thread_id in thread_ids
    )
    result: dict[str, tuple[str, str | None, str | None, str | None]] = {}
    for row in rows:
        thread_id = str(row["id"])
        candidate = candidates.get(thread_id)
        if thread_id in quarantined:
            result[thread_id] = ("quarantined", None, None, None)
        elif candidate is None:
            result[thread_id] = ("ambiguous", None, None, None)
        else:
            result[thread_id] = ("resolved", *candidate)
    return result


def _candidate_pairings(
    connection, *, requester_id: str, character_id: str
) -> set[tuple[str, str, str]]:
    rows = connection.execute(
        text(
            """
        SELECT responding.world_id AS world_id,
               requester.id AS requester_world_character_id,
               responding.id AS responding_world_character_id,
               EXISTS (
                   SELECT 1
                   FROM world_character_blocks AS wc_block
                   WHERE wc_block.world_id = responding.world_id
                     AND (
                       (wc_block.blocker_world_character_id = requester.id
                        AND wc_block.blocked_world_character_id = responding.id)
                       OR
                       (wc_block.blocker_world_character_id = responding.id
                        AND wc_block.blocked_world_character_id = requester.id)
                     )
               ) AS pair_is_blocked
        FROM world_characters AS responding
        JOIN world_memberships AS responding_membership
          ON responding_membership.id = responding.membership_id
         AND responding_membership.world_id = responding.world_id
        JOIN worlds AS world
          ON world.id = responding.world_id
        JOIN installation_identities AS installation
          ON installation.singleton_key = 'local-installation'
         AND installation.owner_user_id = :requester_id
         AND installation.bootstrap_state = 'claimed'
        JOIN characters AS responding_character
          ON responding_character.id = responding.character_id
        JOIN world_characters AS requester
          ON requester.world_id = responding.world_id
        JOIN world_memberships AS requester_membership
          ON requester_membership.id = requester.membership_id
         AND requester_membership.world_id = requester.world_id
        JOIN characters AS requester_character
          ON requester_character.id = requester.character_id
        WHERE responding.character_id = :character_id
          AND responding.status = 'active'
          AND responding_membership.status = 'active'
          AND responding_character.deleted_at IS NULL
          AND responding_character.moderation_status = 'active'
          AND world.owner_user_id = :requester_id
          AND world.status <> 'archived'
          AND requester.owner_user_id = :requester_id
          AND requester.control_mode = 'owner_controlled'
          AND requester.status = 'active'
          AND requester_membership.status = 'active'
          AND requester_membership.user_id = :requester_id
          AND requester_membership.role = 'owner'
          AND requester_character.owner_id = :requester_id
          AND requester_character.deleted_at IS NULL
          AND requester_character.moderation_status = 'active'
        ORDER BY responding.world_id, requester.id, responding.id
        """
        ),
        {"character_id": character_id, "requester_id": requester_id},
    ).mappings()
    rows = list(rows)
    # Requester cardinality is evaluated before excluding self.  Otherwise a
    # World with two owner-controlled candidates, one of which is also the
    # responding role, would be reduced to one row and falsely auto-resolved.
    requester_world_character_ids = {
        str(row["requester_world_character_id"]) for row in rows
    }
    if len(requester_world_character_ids) != 1:
        return set()
    return {
        (
            str(row["world_id"]),
            str(row["requester_world_character_id"]),
            str(row["responding_world_character_id"]),
        )
        for row in rows
        if row["requester_world_character_id"]
        != row["responding_world_character_id"]
        and not bool(row["pair_is_blocked"])
    }


__all__ = [
    "LEGACY_MESSAGE_THREAD_COLUMNS",
    "WorldScopeBackfillStats",
    "add_legacy_message_threads_table",
    "add_world_scoped_message_threads_v4_table",
    "backfill_message_thread_world_scope",
    "expected_world_scope_bindings",
    "rebuild_message_threads_v3",
    "rebuild_and_backfill_message_threads_v4",
]
