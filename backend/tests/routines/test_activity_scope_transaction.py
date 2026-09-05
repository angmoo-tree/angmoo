from __future__ import annotations

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
from app.domains.world_packages.models import WorldPackageImport
from app.runtime.resident import activity_policy
from routines.test_activity_persistence import _file_engine
from routine_posts.test_runtime import _seed


def test_enabled_world_character_does_not_open_a_database_transaction(tmp_path):
    engine = _file_engine(tmp_path)
    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def executed(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    with Session(engine) as db:
        character = WorldCharacter(autonomous_enabled=True)
        assert activity_policy.is_imported_world_runtime_locked(db, character) is False
        assert statements == []
        assert db.in_transaction() is False
    engine.dispose()


@pytest.mark.parametrize("selected_world", (False, True))
def test_import_activation_gate_reads_caller_pending_registry_without_committing(
    tmp_path, selected_world,
):
    engine = _file_engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db, autonomous_enabled=False)
        active = db.get(CharacterActiveWorld, fixture.character.id)
        assert active is not None
        if not selected_world:
            db.delete(active)
            db.commit()
        registry = WorldPackageImport(
            import_id="pending-activity-import", local_owner_id=fixture.user.id,
            package_id="package-activity", package_version=1, content_digest="c" * 64,
            imported_world_id=fixture.world.id, trust_state="checksum_verified_unsigned",
            license_expression="CC0-1.0", idempotency_key="pending-activity-key",
        )
        db.add(registry)
        commits = []

        @event.listens_for(db, "after_commit")
        def committed(_session):
            commits.append(True)

        assert activity_policy.is_imported_world_runtime_locked_for_character(
            db, character_id=fixture.character.id,
        ) is True
        assert activity_policy.is_imported_world_runtime_locked(
            db, fixture.world_character,
        ) is True
        assert commits == []
        with Session(engine) as observer:
            assert observer.get(WorldPackageImport, registry.import_id) is None
            assert activity_policy.is_imported_world_runtime_locked_for_character(
                observer, character_id=fixture.character.id,
            ) is False
        db.rollback()
        assert db.get(WorldPackageImport, registry.import_id) is None
        assert activity_policy.is_imported_world_runtime_locked_for_character(
            db, character_id=fixture.character.id,
        ) is False
    engine.dispose()
