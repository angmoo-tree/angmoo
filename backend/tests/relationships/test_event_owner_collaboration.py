from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.domains.relationships.contracts.events import EvidenceInput
from app.domains.relationships.exceptions import SocialEventRuntimeError
from app.domains.relationships.service.events import record_successful_social_event
from app.runtime.relationships import event_references
from relationships.test_social_event_runtime import _engine, _post, _seed


def test_replay_checks_current_membership_before_skipping_source_reads(monkeypatch):
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        post = _post(db, post_id="collaboration-source", author=fixture.actor,
                     author_world_character=fixture.actor_world_character, body="source")
        references = event_references.SqlAlchemyEventReferences(db)
        calls = []
        original_scope = event_references.validate_event_scope

        def validate_scope(session, **kwargs):
            assert session is db
            calls.append((kwargs["world_character_id"], kwargs["lock"]))
            return original_scope(session, **kwargs)

        monkeypatch.setattr(event_references, "validate_event_scope", validate_scope)
        kwargs = dict(
            references=references, world_id=fixture.world.id,
            actor_world_character_id=fixture.actor_world_character.id,
            target_world_character_id=fixture.target_world_character.id,
            event_type="comment_created", occurred_at=datetime(2026, 9, 6, tzinfo=UTC),
            idempotency_key="collaboration-event",
            evidence=EvidenceInput(evidence_kind="reply_post", source_object_type="post",
                                   source_object_id=post.id, source_post_id=post.id),
        )
        first = record_successful_social_event(db, **kwargs)
        db.commit()
        assert calls == [(fixture.actor_world_character.id, True), (fixture.target_world_character.id, False)]

        def unexpected_source_read(_post_id):
            raise AssertionError("idempotent replay must not reread evidence")

        monkeypatch.setattr(references, "get_post", unexpected_source_read)
        membership = db.get(models.WorldMembership, fixture.actor_world_character.membership_id)
        membership.status = "left"
        calls.clear()
        with pytest.raises(SocialEventRuntimeError) as error:
            record_successful_social_event(db, **kwargs)
        assert error.value.reason_code == "world_membership_inactive"
        assert calls == [(fixture.actor_world_character.id, True)]
        db.rollback()

        post.deleted_at = datetime(2026, 9, 6, tzinfo=UTC)
        calls.clear()
        replay = record_successful_social_event(db, **kwargs)
        assert replay.reused is True
        assert replay.event is first.event
        assert replay.relationship_state is first.relationship_state
        assert calls == [(fixture.actor_world_character.id, True), (fixture.target_world_character.id, False)]
        assert len(db.scalars(select(models.SocialEvent)).all()) == 1
        assert len(db.scalars(select(models.RelationshipStateChange)).all()) == 1
        db.rollback()
    engine.dispose()


def test_actor_validation_locks_before_target_or_evidence_queries(monkeypatch):
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        fixture.actor_world_character.status = "left"
        statements = []
        original_scalar = db.scalar

        def scalar(statement, *args, **kwargs):
            statements.append(statement)
            return original_scalar(statement, *args, **kwargs)

        monkeypatch.setattr(db, "scalar", scalar)
        with pytest.raises(SocialEventRuntimeError) as error:
            record_successful_social_event(
                db, references=event_references.SqlAlchemyEventReferences(db),
                world_id=fixture.world.id, actor_world_character_id=fixture.actor_world_character.id,
                target_world_character_id="missing-target", event_type="comment_created",
                occurred_at=datetime(2026, 9, 6, tzinfo=UTC), idempotency_key="invalid-scope",
                evidence=EvidenceInput(evidence_kind="post", source_object_type="post", source_object_id="missing-source"),
            )
        assert error.value.reason_code == "world_character_inactive"
        assert len(statements) == 1
        assert statements[0]._for_update_arg is not None
        assert db.scalars(select(models.SocialEvent)).all() == []
        db.rollback()
    engine.dispose()
