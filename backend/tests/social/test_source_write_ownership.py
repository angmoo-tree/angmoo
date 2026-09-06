from sqlalchemy import event, func, select
from sqlalchemy.orm import object_session

from model_fixture_support import models
from app.runtime.social import source_references
from app.runtime.social.sqlalchemy_unit_of_work import SqlAlchemySocialWriteUnitOfWork
from social.test_l4_social_write_uow import _owner_post, _session_factory


def test_source_collaborators_read_after_begin_and_share_one_commit(monkeypatch, tmp_path):
    factory = _session_factory(tmp_path)
    with factory() as db:
        calls, commits = [], []
        original_actor = source_references.get_source_actor
        original_event = source_references.record_source_post_event

        def actor(session, world_character_id):
            assert session is db
            assert session.connection().connection.driver_connection.in_transaction
            row = original_actor(session, world_character_id)
            assert object_session(row) is db
            calls.append(("actor", world_character_id))
            return row

        def source_event(session, **kwargs):
            assert session is db
            assert object_session(kwargs["post"]) is db
            assert kwargs["root_post"] is kwargs["post"]
            assert commits == []
            original_event(session, **kwargs)
            calls.append(("source", kwargs["post"].id))
            stored = session.scalar(select(models.SocialEvent))
            assert stored.retrieval_status == "audit_only"
            assert session.scalar(select(func.count(models.SocialEventEvidence.id))) == 1
            assert session.scalar(select(func.count(models.RelationshipState.id))) == 0
            assert session.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 0

        monkeypatch.setattr(source_references, "get_source_actor", actor)
        monkeypatch.setattr(source_references, "record_source_post_event", source_event)
        event.listen(db, "before_commit", lambda *_: commits.append("commit"))
        assert not db.in_transaction()
        writer = SqlAlchemySocialWriteUnitOfWork(db)
        # Constructing services/collaborators must not read or create a Session.
        assert not db.in_transaction()
        assert calls == []
        result = writer.create_owner_post(_owner_post())
        assert commits == ["commit"]
        assert calls == [
            ("actor", "social-uow-owner-actor"),
            ("source", result.post.id),
            ("actor", "social-uow-owner-actor"),
        ]
        assert not result.replayed
        assert result.post.can_owner_reply is False
        calls.clear()
        replay = writer.create_owner_post(_owner_post())
        assert replay.replayed and replay.post.id == result.post.id
        assert calls == [
            ("actor", "social-uow-owner-actor"),
            ("actor", "social-uow-owner-actor"),
        ]
        assert commits == ["commit", "commit"]
        assert db.scalar(select(func.count(models.OwnerManualSocialWrite.id))) == 1
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 1
