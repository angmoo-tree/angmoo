from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, object_session

from app import models as registered_models  # Resolve the existing foreign-key metadata.
from app.domains.relationships.models.points import AgentRelationshipPoint
from app.domains.relationships.service import points


def _request(**changes):
    return {
        "kind": "reply_received",
        "recipient_character_id": "recipient",
        "source_character_id": "source",
        "source_post_id": "post",
        "expires_at": datetime(2026, 9, 6, tzinfo=UTC) + timedelta(days=3),
        **changes,
    }


def test_point_admission_and_existing_duplicate_do_not_write_or_reset_state(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'points.sqlite3'}")
    AgentRelationshipPoint.__table__.create(engine)
    sql = []
    event.listen(engine, "before_cursor_execute", lambda connection, cursor, statement, parameters, context, executemany: sql.append(statement))
    with Session(engine) as db:
        for changes, reason in (
            ({"kind": "other"}, "invalid_kind"),
            ({"source_post_id": ""}, "missing_required_field"),
            ({"recipient_character_id": "source"}, "self_relationship_point"),
        ):
            assert points.create_relationship_point(db, **_request(**changes)) == (None, reason)
        assert sql == []
        point, reason = points.create_relationship_point(db, **_request(topic_brief="original"))
        assert reason is None
        points.mark_relationship_point_selected(db, point, run_id="selected-run", now=datetime(2026, 9, 6, tzinfo=UTC))
        sql.clear()
        commits = []
        event.listen(db, "after_commit", lambda session: commits.append(session))
        duplicate, reason = points.create_relationship_point(db, **_request(topic_brief="replacement"))
        assert duplicate is point and object_session(duplicate) is db
        assert reason == "duplicate"
        assert (point.topic_brief, point.status, point.selected_run_id) == ("original", "selected", "selected-run")
        assert len(sql) == 1 and sql[0].lstrip().upper().startswith("SELECT")
        assert commits == []
    engine.dispose()


def test_point_unique_collision_rolls_back_then_reads_the_committed_winner(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'collision.sqlite3'}")
    AgentRelationshipPoint.__table__.create(engine)
    calls = []
    winner_id = []
    with Session(engine) as db:
        def commit_winner_before_first_insert(session):
            assert session is db
            calls.append("winner")
            with Session(engine) as observer:
                winner, reason = points.create_relationship_point(observer, **_request(topic_brief="winner"))
                assert reason is None
                winner_id.append(winner.id)
        event.listen(db, "before_commit", commit_winner_before_first_insert, once=True)
        event.listen(db, "after_soft_rollback", lambda session, transaction: calls.append("rollback"))
        point, reason = points.create_relationship_point(db, **_request(topic_brief="loser"))
        assert reason == "duplicate"
        assert point.id == winner_id[0] and point.topic_brief == "winner"
        assert object_session(point) is db and db.is_active
        assert calls[0] == "winner" and "rollback" in calls[1:]
        assert db.scalar(select(func.count(AgentRelationshipPoint.id))) == 1
        db.rollback()
    with Session(engine) as observer:
        assert observer.get(AgentRelationshipPoint, winner_id[0]).topic_brief == "winner"
    engine.dispose()
