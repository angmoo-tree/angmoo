"""Add two bounded-read indexes; canonical row data must remain unchanged."""
from pathlib import Path
import json

from .contracts import SqliteMigrationDeltaError

INDEXES = {"ix_message_messages_thread_created_id", "ix_posts_world_root_page"}


def capture_delta(connection):
    names = {row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='index'")}
    if names & INDEXES:
        raise SqliteMigrationDeltaError("paged_read_index_already_present")
    return names


def upgrade(connection):
    for statement in json.loads(Path(__file__).with_name("paged_reads_v41_ddl.json").read_text(encoding="utf-8")):
        connection.exec_driver_sql(statement)


def verify_delta(connection, before):
    names = {row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='index'")}
    if names != before | INDEXES:
        raise SqliteMigrationDeltaError("paged_read_index_delta_invalid")
