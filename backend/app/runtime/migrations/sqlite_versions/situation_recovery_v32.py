"""Forward-only recovery schema on unpublished staging; historical rows stay intact."""
import hashlib
import json
from pathlib import Path

from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError

MUTABLE_IDENTITY_TABLES = frozenset({"memory_situation_runs", "memory_situation_receipts", "memory_situation_recheck_attempts"})


def _digest(connection, table, columns):
    selection = ",".join(f'"{name}"' for name in columns)
    rows = sorted((tuple(row) for row in connection.exec_driver_sql(f'SELECT {selection} FROM "{table}"')), key=repr)
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def capture_delta(connection):
    tables = {}
    for table in ("memory_situation_runs", "memory_situation_receipts"):
        columns = tuple(row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info("{table}")'))
        tables[table] = {"columns": columns, "digest": _digest(connection, table, columns)}
    sequence = connection.exec_driver_sql("SELECT seq FROM sqlite_sequence WHERE name='memory_situation_receipts'").scalar()
    return {"tables": tables, "sequence": sequence}


def verify_delta(connection, before):
    for table, saved in before["tables"].items():
        if _digest(connection, table, saved["columns"]) != saved["digest"]:
            raise SqliteMigrationDeltaError("situation_recovery_history_changed")
    if connection.exec_driver_sql("SELECT count(*) FROM memory_situation_runs WHERE work_kind <> 'pending_apply'").scalar_one():
        raise SqliteMigrationDeltaError("situation_recovery_run_recaptured")
    if connection.exec_driver_sql("SELECT count(*) FROM memory_situation_receipts WHERE state_version <> 1 OR discarded_at IS NOT NULL OR discard_request_key IS NOT NULL").scalar_one():
        raise SqliteMigrationDeltaError("situation_recovery_receipt_changed")
    if connection.exec_driver_sql("SELECT count(*) FROM memory_situation_recheck_attempts").scalar_one():
        raise SqliteMigrationDeltaError("situation_recovery_history_recaptured")
    sequence = connection.exec_driver_sql("SELECT seq FROM sqlite_sequence WHERE name='memory_situation_receipts'").scalar()
    if sequence != before["sequence"]:
        raise SqliteMigrationDeltaError("situation_recovery_sequence_changed")


def upgrade(connection):
    if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one():
        raise SqliteMigrationDeltaError("situation_recovery_requires_staging")
    columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(memory_situation_receipts)")}
    if "state_version" in columns:
        return
    ddl = json.loads(Path(__file__).with_name("situation_recovery_v32_ddl.json").read_text(encoding="utf-8"))
    sequence = connection.exec_driver_sql("SELECT seq FROM sqlite_sequence WHERE name='memory_situation_receipts'").scalar()
    for table in ("memory_situation_runs", "memory_situation_receipts"):
        names = [row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info("{table}")')]
        selection = ",".join(f'"{name}"' for name in names)
        connection.exec_driver_sql(f'CREATE TEMP TABLE "{table}_v31_copy" AS SELECT * FROM "{table}"')
        connection.exec_driver_sql(f'DROP TABLE "{table}"')
        for statement in ddl[table]:
            connection.exec_driver_sql(statement)
        connection.exec_driver_sql(f'INSERT INTO "{table}" ({selection}) SELECT {selection} FROM "{table}_v31_copy"')
        connection.exec_driver_sql(f'DROP TABLE "{table}_v31_copy"')
    if sequence is not None:
        changed = connection.exec_driver_sql("UPDATE sqlite_sequence SET seq=? WHERE name='memory_situation_receipts'", (sequence,))
        if changed.rowcount == 0:
            connection.exec_driver_sql("INSERT INTO sqlite_sequence(name,seq) VALUES('memory_situation_receipts',?)", (sequence,))
    else:
        # Even an empty INSERT ... SELECT creates a zero-valued sequence row.
        # Preserve the predecessor's absence, as well as populated high-water
        # marks, rather than changing history or weakening delta verification.
        connection.exec_driver_sql("DELETE FROM sqlite_sequence WHERE name='memory_situation_receipts'")
    for statement in ddl["memory_situation_recheck_attempts"]:
        connection.exec_driver_sql(statement)
