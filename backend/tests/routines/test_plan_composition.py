from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import Session

from app.core.db import Base
from app.domains.identity.models import User
from app.domains.routines.schemas import WorldCharacterRuntimeModeUpdate
from app.domains.routines.service import plans
from app.domains.world_characters.models import WorldCharacter
from app.runtime.routines import plan_references
from routines.test_daily_activity_runtime import _prepare, _seed, _utc


@pytest.mark.parametrize("fail_commit", [False, True], ids=["commit", "rollback"])
def test_mode_change_and_pending_owner_write_share_one_transaction(
    tmp_path, monkeypatch, fail_commit: bool
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'plan-composition.sqlite3'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    now = _utc(datetime(2026, 8, 9, 0, 30))
    with Session(engine, expire_on_commit=False) as db:
        _world, fixture, _other = _seed(db)
        _prepare(db, fixture, now=now)
        previous_mode = fixture.world_character.activity_runtime_mode
        previous_version = fixture.world_character.version
        previous_name = fixture.user.display_name
        original_mode_write = plan_references.set_activity_runtime_mode
        original_commit = db.commit
        write_sessions = []
        commits = []

        def owner_write(world_character, *, activity_runtime_mode) -> None:
            write_sessions.append(inspect(world_character).session)
            original_mode_write(
                world_character, activity_runtime_mode=activity_runtime_mode
            )

        def commit() -> None:
            commits.append(True)
            if fail_commit:
                raise RuntimeError("test_commit_failure")
            original_commit()

        monkeypatch.setattr(plan_references, "set_activity_runtime_mode", owner_write)
        monkeypatch.setattr(db, "commit", commit)
        fixture.user.display_name = "Changed in the same request"

        def change_mode():
            return plans.update_activity_runtime_mode(
                db,
                references=plan_references.SqlAlchemyPlanReferences(db),
                character_id=fixture.character.id,
                world_id=fixture.world_character.world_id,
                user=fixture.user,
                data=WorldCharacterRuntimeModeUpdate(
                    activity_runtime_mode="routine_resident_v1"
                ),
                now=now,
            )

        if fail_commit:
            with pytest.raises(RuntimeError, match="test_commit_failure"):
                change_mode()
            # The caller still owns rollback after an unsuccessful service commit.
            db.rollback()
            assert fixture.world_character.activity_runtime_mode == previous_mode
            assert fixture.world_character.version == previous_version
            assert fixture.user.display_name == previous_name
        else:
            result = change_mode()
            assert result.activity_runtime_mode == "routine_resident_v1"
            assert result.autonomous_enabled is False

        assert write_sessions == [db]
        assert commits == [True]
        with Session(engine) as observer:
            saved_character = observer.scalar(
                select(WorldCharacter).where(WorldCharacter.id == fixture.world_character.id)
            )
            saved_user = observer.get(User, fixture.user.id)
            assert saved_character is not None
            assert saved_user is not None
            assert saved_character.activity_runtime_mode == (
                previous_mode if fail_commit else "routine_resident_v1"
            )
            assert saved_character.version == previous_version + (0 if fail_commit else 1)
            assert saved_character.autonomous_enabled is False
            assert saved_user.display_name == (
                previous_name if fail_commit else "Changed in the same request"
            )
    engine.dispose()
