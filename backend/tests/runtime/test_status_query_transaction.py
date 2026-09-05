"""Diagnostic reads see uncommitted canonical facts and preserve rollback ownership."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
import pytest

from app.domains.runtime.contracts.status import RuntimeComponentState
from app.runtime.diagnostics.status_composition import create_runtime_status_reader


@pytest.mark.parametrize("rollback_path", ["caller", "missing_migration"])
def test_diagnostics_share_uncommitted_foreign_facts_and_original_rollback(
    tmp_path, rollback_path
):
    engine = create_engine(f"sqlite:///{tmp_path / 'diagnostics.sqlite3'}")
    try:
        # These canonical read fixtures contain only the columns used by this
        # diagnostic view. Full ORM/schema contracts are verified separately.
        with engine.begin() as connection:
            for ddl in (
                "CREATE TABLE installation_identities (singleton_key TEXT PRIMARY KEY, bootstrap_state TEXT, owner_user_id TEXT)",
                "CREATE TABLE worlds (id TEXT PRIMARY KEY, owner_user_id TEXT, status TEXT)",
                "CREATE TABLE characters (id TEXT PRIMARY KEY, owner_id TEXT)",
                "CREATE TABLE world_characters (id TEXT PRIMARY KEY, world_id TEXT, character_id TEXT, status TEXT)",
                "CREATE TABLE character_active_worlds (character_id TEXT, world_character_id TEXT)",
            ):
                connection.execute(text(ddl))

        with Session(engine) as session:
            reader = create_runtime_status_reader(session)
            assert session.in_transaction() is False
            for statement in (
                "INSERT INTO installation_identities VALUES ('local-installation', 'claimed', 'owner')",
                "INSERT INTO worlds VALUES ('visible', 'owner', 'active'), ('old', 'owner', 'archived'), ('foreign', 'other', 'active')",
                "INSERT INTO characters VALUES ('local-character', 'owner'), ('other-character', 'other')",
                "INSERT INTO world_characters VALUES ('active', 'visible', 'local-character', 'active'), ('inactive', 'old', 'local-character', 'inactive'), ('foreign', 'foreign', 'other-character', 'active')",
                "INSERT INTO character_active_worlds VALUES ('local-character', 'inactive'), ('other-character', 'foreign')",
            ):
                session.execute(text(statement))

            status = reader._owner_status()
            assert status.bootstrap_state == "claimed"
            assert status.owner_user_id == "owner"
            assert status.registered_world_count == 1
            # The existing active-world diagnostic counts active assignment,
            # without introducing an additional membership-status predicate.
            assert status.active_world_count == 1
            assert status.active_world_character_count == 1
            assert session.in_transaction() is True

            if rollback_path == "caller":
                session.rollback()
            else:
                migration = reader._migration_status()
                assert migration.state is RuntimeComponentState.DEGRADED
                assert migration.current_revision is None
            assert session.in_transaction() is False
            empty = reader._owner_status()
            assert empty.bootstrap_state == "unclaimed"
            assert empty.owner_user_id is None
            assert empty.registered_world_count == 0
            assert session.execute(text("SELECT COUNT(*) FROM worlds")).scalar_one() == 0
    finally:
        engine.dispose()
