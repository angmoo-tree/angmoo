"""Populated pre-delivery SQLite upgrades preserve exact historical notification values."""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from social.test_l4_social_write_uow import _seed
from app.runtime.migrations.sqlite_versions import world_notifications_v38 as migration
from app.runtime.migrations.sqlite_versions.registry import load_sqlite_manifest
from app.runtime.persistence.sqlite_schema import build_sqlite_v37_metadata, create_schema_version_table, sqlite_schema_contract_digest
from app.runtime.persistence import sqlite_schema


@pytest.mark.parametrize("version", (1, 3, 4, 5, 6, 7, 8, 37))
def test_pre_delivery_metadata_preserves_its_released_manifest(version):
    metadata = getattr(sqlite_schema, f"build_sqlite_v{version}_metadata")()
    notifications = metadata.tables["notifications"]
    assert "delivery_key" not in notifications.c
    assert not {"uq_notifications_delivery_key", "ix_notifications_world_recipient_id"} & {
        index.name for index in notifications.indexes
    }
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            create_schema_version_table(connection)
            metadata.create_all(connection)
            assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(version).schema_digest
    finally:
        engine.dispose()


def test_populated_v37_forward_upgrade_preserves_read_and_handled_history(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'v37.sqlite3'}")
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    with engine.begin() as connection:
        create_schema_version_table(connection)
        build_sqlite_v37_metadata().create_all(connection)
    _seed(sessionmaker(bind=engine, expire_on_commit=False))
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO notifications(recipient_character_id,notification_type,read_at,handled_at,handling_outcome) "
                "VALUES ('social-uow-owner-character','like','2026-01-01','2026-01-02','legacy')")
            assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(37).schema_digest
            before = migration.capture_delta(connection)
            migration.upgrade(connection)
            migration.verify_delta(connection, before)
            assert sqlite_schema_contract_digest(connection) == load_sqlite_manifest(38).schema_digest
            row = connection.exec_driver_sql("SELECT read_at, handled_at, handling_outcome, delivery_key FROM notifications").one()
            assert str(row[0]).startswith("2026-01-01") and str(row[1]).startswith("2026-01-02")
            assert row[2:] == ("legacy", None)
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
            fence = connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name='world_erasure_notifications_update'").scalar_one()
            assert 'NEW."delivery_key"' in fence
    finally:
        engine.dispose()
