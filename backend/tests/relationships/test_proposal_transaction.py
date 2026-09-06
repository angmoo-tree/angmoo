from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, object_session

from model_fixture_support import models
from app.models import Base
from app.domains.relationships.service import proposals
from app.runtime.activity_proposals import references as proposal_references
from relationships.test_activity_proposals import _published_proposal_fixture, _post, _record_post_event, _utc


@pytest.mark.parametrize("fail_after_reservation", (False, True))
def test_acceptance_reservation_uses_same_session_and_caller_rollback(tmp_path, monkeypatch, fail_after_reservation):
    engine = create_engine(f"sqlite:///{tmp_path / 'proposal.sqlite3'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    now = _utc(datetime(2026, 8, 9, 9, 0))
    with Session(engine, expire_on_commit=False) as db:
        fixture = _published_proposal_fixture(db, now=now, prefix="owner-transaction")
        references = proposal_references.SqlAlchemyProposalReferences(db)
        schedule = proposals.resolve_acceptance_schedule(
            db, references=references, proposal_id=fixture.proposal.id,
            now=now + timedelta(minutes=2),
        )
        reply = _post(db, post_id="owner-acceptance", fixture=fixture.acceptor,
                      body="Yes, this evening.", created_at=now + timedelta(minutes=3),
                      reply_to_post_id=fixture.proposal_comment.id)
        source = _record_post_event(
            db, world_id=fixture.world.id, actor_world_character_id=fixture.acceptor.world_character.id,
            target_world_character_id=fixture.proposer.world_character.id, event_type="joint_accepted",
            source=reply, target_post_id=fixture.proposal_comment.id, root_post_id=fixture.root.id,
            occurred_at=now + timedelta(minutes=3), idempotency_key="owner-accepted",
            proposal_decision="accept",
        )
        original_create = proposal_references.joint_activity.create_scheduled_joint
        calls = []

        def create_in_transaction(session, **kwargs):
            assert session is db
            assert kwargs["references"]._db is db
            assert kwargs["proposal"] is fixture.proposal
            assert object_session(kwargs["proposal"]) is db
            assert kwargs["proposal"].status == "accepted"
            result = original_create(session, **kwargs)
            assert object_session(result.joint_activity) is db
            calls.append(result.joint_activity)
            if fail_after_reservation:
                raise RuntimeError("after reservation")
            return result

        monkeypatch.setattr(proposal_references.joint_activity, "create_scheduled_joint", create_in_transaction)
        kwargs = dict(references=references, proposal_id=fixture.proposal.id,
                      response_event=source, decision="accept", resolved_schedule=schedule,
                      now=now + timedelta(minutes=3))
        if fail_after_reservation:
            with pytest.raises(RuntimeError, match="after reservation"):
                proposals.apply_response(db, **kwargs)
        else:
            result = proposals.apply_response(db, **kwargs)
            assert result.joint_activity is calls[0]
            assert result.proposal is fixture.proposal
        assert len(calls) == 1
        with Session(engine) as observer:
            assert observer.get(models.ActivityProposal, fixture.proposal.id).status == "proposed"
            assert observer.scalars(select(models.JointActivity)).all() == []
            assert observer.get(models.SocialEvent, source.id) is None
        db.rollback()
        assert fixture.proposal.status == "proposed"
        assert fixture.proposal.source_response_event_id is None
        assert db.scalars(select(models.JointActivity)).all() == []
        assert db.scalars(select(models.JointActivityParticipant)).all() == []
        assert db.scalar(select(models.SocialEvent).where(models.SocialEvent.idempotency_key == "owner-accepted")) is None
    engine.dispose()
