from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.core.db import Base
from app.domains.routines import models
from app.domains.routines.exceptions import ActivityRuntimeValidationError
from app.domains.routines.service import lifecycle
from app.runtime.routines.lifecycle_references import SqlAlchemyLifecycleReferences
from routines.test_daily_activity_runtime import _prepare, _seed, _utc


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'lifecycle-composition.sqlite3'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_elapsed_owner_join_observes_pending_state_without_committing(engine) -> None:
    now = _utc(datetime(2026, 8, 9, 0, 30))
    after_dawn = _utc(datetime(2026, 8, 9, 6, 1))
    with Session(engine, expire_on_commit=False) as db:
        _world, first, second = _seed(db, two_characters=True)
        assert second is not None
        _prepare(db, first, now=now, key="first-join-plan")
        _prepare(db, second, now=now, key="second-join-plan")
        second.world_character.control_mode = "owner_controlled"
        second.world_character.owner_user_id = second.user.id
        selects = []
        commits = []

        def select_statement(_connection, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().upper().startswith("SELECT"):
                selects.append(statement)

        event.listen(engine, "before_cursor_execute", select_statement)
        event.listen(db, "after_commit", lambda _session: commits.append(True))
        references = SqlAlchemyLifecycleReferences(db)
        ids = references.elapsed_autonomous_world_character_ids(now=after_dawn)
        event.remove(engine, "before_cursor_execute", select_statement)

        assert ids == [first.world_character.id]
        assert len(selects) == 1
        assert commits == []
        db.rollback()
        assert second.world_character.control_mode == "autonomous"
        assert set(references.elapsed_autonomous_world_character_ids(now=after_dawn)) == {
            first.world_character.id, second.world_character.id
        }


def test_reconcile_preserves_each_character_commit_when_later_scope_fails(engine) -> None:
    now = _utc(datetime(2026, 8, 9, 0, 30))
    after_dawn = _utc(datetime(2026, 8, 9, 6, 1))
    with Session(engine, expire_on_commit=False) as db:
        _world, first, second = _seed(db, two_characters=True)
        assert second is not None
        first_plan = _prepare(db, first, now=now, key="first-commit-plan")
        second_plan = _prepare(db, second, now=now, key="second-commit-plan")
        first_item = first_plan.items[0]
        second_item = second_plan.items[0]
        assert second_item.episode is not None
        missing = db.get(models.ActivityEpisode, second_item.episode.id)
        assert missing is not None
        db.delete(missing)
        db.commit()
        commits = []
        event.listen(db, "after_commit", lambda _session: commits.append(True))

        class OrderedReferences(SqlAlchemyLifecycleReferences):
            def elapsed_autonomous_world_character_ids(self, *, now):
                actual = super().elapsed_autonomous_world_character_ids(now=now)
                assert set(actual) == {first.world_character.id, second.world_character.id}
                return [first.world_character.id, second.world_character.id]

        with pytest.raises(ActivityRuntimeValidationError, match="activity_episode_missing"):
            lifecycle.reconcile_all_elapsed_routines(
                db, references=OrderedReferences(db), now=after_dawn
            )
        db.rollback()
        assert commits == [True]

    with Session(engine) as observer:
        first_saved = observer.get(models.DailyActivityPlanItem, first_item.id)
        second_saved = observer.get(models.DailyActivityPlanItem, second_item.id)
        assert first_saved is not None
        assert second_saved is not None
        assert first_saved.status == "skipped"
        assert first_saved.terminal_reason_code == "daypart_window_elapsed"
        assert second_saved.status == "planned"
        assert second_saved.terminal_reason_code is None
        assert observer.scalar(select(models.ActivityBeat.id).limit(1)) is None
