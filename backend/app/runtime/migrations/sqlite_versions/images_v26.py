"""Frozen v25→v26 image records with byte-for-byte legacy row verification."""
import hashlib
import json
from pathlib import Path
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError

REBUILT_TABLES = frozenset({"agent_image_generation_settings", "post_media", "post_image_generation_jobs"})
NEW_TABLES = frozenset({
    "media_credentials", "media_assets", "image_interpretation_settings",
    "image_interpretations", "image_interpretation_attempts", "message_attachments",
    "post_image_intents", "post_image_generation_attempts", "image_generation_policy",
})
MUTABLE_IDENTITY_TABLES = REBUILT_TABLES | NEW_TABLES
_DDL = Path(__file__).with_name("image_v26_ddl.json")


def _digest(connection, table, columns):
    names = ",".join(f'"{name}"' for name in columns)
    rows = [tuple(row) for row in connection.exec_driver_sql(f'SELECT {names} FROM "{table}" ORDER BY 1')]
    return len(rows), hashlib.sha256(json.dumps(rows, default=str, ensure_ascii=False).encode()).hexdigest()


def capture_delta(connection):
    return {name: (tuple(r[1] for r in connection.exec_driver_sql(f'PRAGMA table_info("{name}")')), None)
            for name in REBUILT_TABLES} | {
                "digests": {name: _digest(connection, name, tuple(r[1] for r in connection.exec_driver_sql(f'PRAGMA table_info("{name}")')))
                            for name in REBUILT_TABLES}}


def verify_delta(connection, before):
    for name in REBUILT_TABLES:
        if _digest(connection, name, before[name][0]) != before["digests"][name]:
            raise SqliteMigrationDeltaError("image_legacy_rows_changed")
    for name in NEW_TABLES:
        if connection.exec_driver_sql(f'SELECT count(*) FROM "{name}"').scalar_one():
            raise SqliteMigrationDeltaError("image_new_table_not_empty")
    if connection.exec_driver_sql("SELECT count(*) FROM agent_image_generation_settings WHERE generation_auto_enabled != 0").scalar_one():
        raise SqliteMigrationDeltaError("image_migration_activated_generation")


def upgrade(connection):
    if int(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()) != 0:
        raise RuntimeError("image_migration_requires_foreign_keys_off")
    ddl = json.loads(_DDL.read_text(encoding="utf-8"))
    connection.exec_driver_sql("PRAGMA legacy_alter_table=ON")
    try:
        for name, spec in ddl.items():
            if name in REBUILT_TABLES:
                columns = tuple(r[1] for r in connection.exec_driver_sql(f'PRAGMA table_info("{name}")'))
                connection.exec_driver_sql(f'ALTER TABLE "{name}" RENAME TO "{name}_v25"')
                connection.exec_driver_sql(spec["create"])
                names = ",".join(f'"{c}"' for c in columns)
                connection.exec_driver_sql(f'INSERT INTO "{name}" ({names}) SELECT {names} FROM "{name}_v25"')
                connection.exec_driver_sql(f'DROP TABLE "{name}_v25"')
            else:
                connection.exec_driver_sql(spec["create"])
            for sql in spec["indexes"]:
                connection.exec_driver_sql(sql)
    finally:
        connection.exec_driver_sql("PRAGMA legacy_alter_table=OFF")
