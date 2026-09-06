from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, object_session

from model_fixture_support import models
from app.models import Base
from app.domains.routines.service import public_action_executions
from app.runtime.relationships import sqlalchemy_social_event as events
from relationships.test_social_event_runtime import _post, _seed


@pytest.mark.parametrize("missing_execution", (False, True))
def test_execution_link_stays_in_the_event_transaction(tmp_path, monkeypatch, missing_execution):
    engine = create_engine(f"sqlite:///{tmp_path / 'event.sqlite3'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        post = _post(db, post_id="execution-source", author=fixture.actor,
                     author_world_character=fixture.actor_world_character, body="source")
        run = models.AgentRun(id="event-run", user_id=fixture.actor.owner_id,
                              character_id=fixture.actor.id, agent_id="event-agent",
                              session_key="event-session", status="running")
        db.add(run)
        db.flush()
        execution = models.AgentPublicActionExecution(
            run_id=run.id, character_id=fixture.actor.id, signature="event-signature",
            scope="feed", action_type="post", status="succeeded",
        )
        db.add(execution)
        db.commit()
        execution_id = execution.id
        get_execution = public_action_executions.get_execution
        set_event_id = public_action_executions.set_social_event_id
        calls = []
        statements = []

        @event.listens_for(engine, "before_cursor_execute")
        def executed(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        def get_in_caller(session, identifier):
            assert session is db
            value = get_execution(session, identifier + int(missing_execution))
            assert value is (None if missing_execution else execution)
            calls.append("get")
            return value

        def link_attached(value, *, social_event_id):
            assert value is execution
            assert object_session(value) is db
            before = len(statements)
            set_event_id(value, social_event_id=social_event_id)
            assert len(statements) == before
            calls.append("set")

        monkeypatch.setattr(public_action_executions, "get_execution", get_in_caller)
        monkeypatch.setattr(public_action_executions, "set_social_event_id", link_attached)
        kwargs = dict(
            world_id=fixture.world.id, actor_world_character_id=fixture.actor_world_character.id,
            target_world_character_id=None, event_type="post_published",
            occurred_at=datetime(2026, 9, 6, tzinfo=UTC), idempotency_key="event-link",
            evidence=events.EvidenceInput(evidence_kind="post", source_object_type="post",
                                         source_object_id=post.id,
                                         public_action_execution_id=execution_id),
        )
        if missing_execution:
            with pytest.raises(events.SocialEventRuntimeError, match="execution_evidence_invalid"):
                events.record_successful_social_event(db, **kwargs)
            assert calls == ["get"]
        else:
            result = events.record_successful_social_event(db, **kwargs)
            assert execution.social_event_id == result.event.id
            assert calls == ["get", "set"]
        with Session(engine) as observer:
            assert observer.get(models.AgentPublicActionExecution, execution_id).social_event_id is None
            assert observer.scalars(select(models.SocialEvent)).all() == []
        db.rollback()
        assert execution.social_event_id is None
        assert db.scalars(select(models.SocialEvent)).all() == []
        assert db.scalars(select(models.SocialEventEvidence)).all() == []
        assert db.scalars(select(models.GraphProjectionOutbox)).all() == []
    engine.dispose()
