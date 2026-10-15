"""Add delivery identity without rewriting any prior notification or read state."""
from hashlib import sha256
import json
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError

MUTABLE_IDENTITY_TABLES = frozenset({"notifications"})


def _digest(connection, columns):
    names = ",".join(f'"{name}"' for name in columns)
    digest, count = sha256(), 0
    for row in connection.exec_driver_sql(f'SELECT {names} FROM notifications ORDER BY id'):
        digest.update(json.dumps(tuple(row), ensure_ascii=False, default=str).encode())
        count += 1
    return count, digest.hexdigest()


def capture_delta(connection):
    columns = tuple(row[1] for row in connection.exec_driver_sql("PRAGMA table_info(notifications)"))
    if "delivery_key" in columns:
        raise SqliteMigrationDeltaError("notification_delivery_key_already_present")
    return columns, _digest(connection, columns)


def upgrade(connection):
    connection.exec_driver_sql("ALTER TABLE notifications ADD COLUMN delivery_key VARCHAR(64)")
    connection.exec_driver_sql("CREATE UNIQUE INDEX uq_notifications_delivery_key ON notifications (delivery_key)")
    connection.exec_driver_sql("CREATE INDEX ix_notifications_world_recipient_id ON notifications (world_id, recipient_world_character_id, id)")
    # Refresh only this table's existing write fences in the migration UoW so
    # an accepted World erasure also protects the newly added delivery field.
    from app.runtime.world_deletion.fences import install_fences
    for operation in ("insert", "update"):
        connection.exec_driver_sql(f'DROP TRIGGER IF EXISTS "world_erasure_notifications_{operation}"')
    install_fences(connection)


def verify_delta(connection, before):
    columns, digest = before
    if _digest(connection, columns) != digest or connection.exec_driver_sql("SELECT count(*) FROM notifications WHERE delivery_key IS NOT NULL").scalar_one():
        raise SqliteMigrationDeltaError("notification_history_changed")
