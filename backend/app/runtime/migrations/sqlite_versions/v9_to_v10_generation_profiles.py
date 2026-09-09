"""Add model thinking snapshots without rewriting keys, history or pending work."""

from sqlalchemy import Connection
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError


from app.runtime.persistence.sqlite_generation_profiles import ADDED_COLUMNS

MUTABLE_IDENTITY_TABLES = frozenset(ADDED_COLUMNS)


def capture_v9_to_v10_delta(connection: Connection) -> dict:
    snapshot = {}
    for table in ADDED_COLUMNS:
        result = connection.exec_driver_sql(f'SELECT * FROM "{table}"')
        columns = tuple(result.keys())
        if set(columns).intersection(ADDED_COLUMNS[table]):
            raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
        snapshot[table] = (columns, sorted((tuple(row) for row in result), key=repr))
    return snapshot


def verify_v9_to_v10_delta(connection: Connection, snapshot: dict) -> None:
    for table, (columns, rows) in snapshot.items():
        names = ', '.join(f'"{name}"' for name in columns)
        actual = sorted((tuple(row) for row in connection.exec_driver_sql(f'SELECT {names} FROM "{table}"')), key=repr)
        if rows != actual:
            raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
        for column in ADDED_COLUMNS[table]:
            expected = None if column == "retry_request_key" else 1 if column == "execution_version" else "high"
            values = connection.exec_driver_sql(f'SELECT "{column}" FROM "{table}"')
            if any(row[0] != expected for row in values):
                raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")


def upgrade_v9_to_v10(connection: Connection) -> None:
    for table, columns in ADDED_COLUMNS.items():
        for column, declaration in columns.items():
            connection.exec_driver_sql(f'ALTER TABLE "{table}" ADD COLUMN {column} {declaration}')
