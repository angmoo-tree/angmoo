"""Forward nullable diagnostics; old rows and execution JSON stay identical."""
import hashlib
from .contracts import SqliteMigrationDeltaError

MUTABLE_IDENTITY_TABLES = frozenset({"post_image_generation_jobs"})


def capture_delta(connection):
    columns = tuple(row[1] for row in connection.exec_driver_sql("PRAGMA table_info(post_image_generation_jobs)") if row[1] != "provider_diagnostic_json")
    selection = ",".join(f'"{name}"' for name in columns)
    rows = tuple(connection.exec_driver_sql(f"SELECT {selection} FROM post_image_generation_jobs ORDER BY id"))
    return {"columns": columns, "digest": hashlib.sha256(repr(rows).encode()).hexdigest()}


def verify_delta(connection, before):
    if capture_delta(connection) != before or connection.exec_driver_sql("SELECT count(*) FROM post_image_generation_jobs WHERE provider_diagnostic_json IS NOT NULL").scalar_one():
        raise SqliteMigrationDeltaError("comfy_diagnostic_history_changed")


def upgrade(connection):
    if "provider_diagnostic_json" not in {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(post_image_generation_jobs)")}:
        connection.exec_driver_sql("ALTER TABLE post_image_generation_jobs ADD COLUMN provider_diagnostic_json TEXT")
