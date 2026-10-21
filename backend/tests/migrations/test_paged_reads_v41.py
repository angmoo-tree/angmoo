"""Read indexes must preserve rows and roll back with the migration transaction."""
from sqlalchemy import create_engine

from app.runtime.migrations.sqlite_versions import paged_reads_v41 as migration
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.persistence.model_registration import register_models
from app.runtime.persistence import sqlite_schema as schema


def test_v40_read_indexes_preserve_rows_and_rollback(tmp_path):
    register_models()
    engine = create_engine(f"sqlite:///{tmp_path / 'paged.sqlite3'}")
    with engine.begin() as connection:
        schema.build_sqlite_v40_metadata().create_all(connection)
        schema.create_schema_version_table(connection)
        connection.exec_driver_sql("INSERT INTO users(id,email,display_name,is_admin,profile_setup_completed) VALUES ('owner','fixture@example.test','admin',0,1)")
        original = connection.exec_driver_sql("SELECT * FROM users").all()
        assert schema.sqlite_schema_contract_digest(connection) == load_sqlite_manifest(40).schema_digest
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        migration.upgrade(connection)
        connection.rollback()
        assert schema.sqlite_schema_contract_digest(connection) == load_sqlite_manifest(40).schema_digest
        connection.rollback()
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        before = migration.capture_delta(connection)
        migration.upgrade(connection)
        migration.verify_delta(connection, before)
        assert connection.exec_driver_sql("SELECT * FROM users").all() == original
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert schema.sqlite_schema_contract_digest(connection) == load_sqlite_manifest(41).schema_digest
        queries = {
            "ix_message_messages_thread_created_id": "SELECT id FROM message_messages WHERE thread_id='synthetic' AND (created_at < '2026-10-22' OR (created_at='2026-10-22' AND id<100)) ORDER BY created_at DESC,id DESC LIMIT 51",
            "ix_posts_world_root_page": "SELECT id FROM posts WHERE world_id='synthetic' AND reply_to_post_id IS NULL AND visibility='public' AND deleted_at IS NULL AND report_hidden_at IS NULL ORDER BY created_at DESC,id DESC LIMIT 31",
        }
        for index, query in queries.items():
            plan = ' '.join(row[3] for row in connection.exec_driver_sql('EXPLAIN QUERY PLAN ' + query))
            assert index in plan and 'TEMP B-TREE' not in plan
        connection.commit()
    engine.dispose()
