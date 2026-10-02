"""Physical request ceilings survive restarts and competing real SQL sessions."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base
from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service.activity_engines import bind_run
from app.runtime.autonomous_activity.combined_provider import RecoveryLedger
from app.runtime.autonomous_activity.output_recovery import MAX_CALL_BUDGET, NORMAL_CALL_BUDGET, RECOVERY_CALL_BUDGET
from social.test_feed_reaction_intent import _seed

pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.fixture
def canonical(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "requests.sqlite3").as_posix(),
        connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        ctx, _ = _seed(db, with_candidate=False)
        actor = db.get(WorldCharacter, "world-character-actor")
        run = bind_run(db, actor=actor, activity_id=ctx.run_id)
        identifier = run.activity_id
        db.commit()
    yield engine, identifier
    engine.dispose()


def test_fixed_ten_normal_five_recovery_reservations_survive_new_sessions(canonical):
    engine, identifier = canonical
    assert (NORMAL_CALL_BUDGET, RECOVERY_CALL_BUDGET, MAX_CALL_BUDGET) == (10, 5, 15)
    for index in range(10):
        with Session(engine) as db:
            RecoveryLedger(db, identifier).reserve_normal("normal:" + str(index))
    for index in range(5):
        with Session(engine) as db:
            RecoveryLedger(db, identifier).reserve("recovery:" + str(index))
    with Session(engine) as db:
        row = db.get(ActivityGraphRun, identifier)
        assert len(row.result["normal_reservations"]) + len(row.result["recovery_reservations"]) == 15
        with pytest.raises(ValueError, match="activity_recovery_exhausted"):
            RecoveryLedger(db, identifier).reserve_normal("eleventh")
        with pytest.raises(ValueError, match="activity_recovery_exhausted"):
            RecoveryLedger(db, identifier).reserve("sixth")
        assert "checkpoint_retention" in row.result


def test_same_recovery_key_has_one_winner_across_competing_sql_sessions(canonical):
    engine, identifier = canonical
    ready = Barrier(2)
    def attempt():
        with Session(engine) as db:
            ready.wait(timeout=10)
            try:
                RecoveryLedger(db, identifier).reserve("RoutineActionPlanner:json")
                return "authorized"
            except ValueError as exc:
                assert str(exc) in {"activity_recovery_conflict", "activity_recovery_exhausted"}
                return "rejected"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ["authorized", "rejected"]
    with Session(engine) as db:
        assert db.get(ActivityGraphRun, identifier).result["recovery_reservations"] == ["RoutineActionPlanner:json"]
