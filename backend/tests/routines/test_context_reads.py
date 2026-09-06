from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.domains.routines.service import feed_context, social_context
from app.domains.social.models.posts import Notification, ProfileFollow
from app.runtime.resident.feed_context_references import SqlAlchemyResidentContextReferences
from routines.test_action_admission import _setup
from social.test_resident_context_queries import _engine, _post


def test_feed_interest_context_uses_original_rows_and_pending_visibility(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture, other, root = _setup(db)
        # These two policies need only concrete repository reads. Passing no Social
        # workflows detects any newly introduced eager feed/provider operation.
        refs = SqlAlchemyResidentContextReferences(db, social=SimpleNamespace())
        payload = {"interests": [{"post_id": root.id}], "topic_signature": "shared-topic"}
        visible = feed_context._format_v6_feed_interests(refs, feed_interest_payload=payload)
        assert root.id in visible
        assert other.name in visible
        assert "shared-topic" in visible
        assert refs.get_post(root.id) is root
        root.deleted_at = root.created_at
        hidden = feed_context._format_v6_feed_interests(refs, feed_interest_payload=payload)
        assert hidden == "- none"
        with Session(engine) as observer:
            outside = feed_context._format_v6_feed_interests(
                SqlAlchemyResidentContextReferences(observer, social=SimpleNamespace()),
                feed_interest_payload=payload,
            )
            assert root.id in outside
        db.rollback()
        assert feed_context._format_v6_feed_interests(refs, feed_interest_payload=payload) == visible
    engine.dispose()


def test_review_candidate_preserves_recipient_and_invalid_payload_admission(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture, other, root = _setup(db)
        reply = _post("candidate-reply", other.id, parent_id=root.id)
        db.add(reply)
        db.flush()
        notice = Notification(recipient_character_id=fixture.character.id,
                              actor_character_id=other.id, notification_type="reply",
                              source_post_id=reply.id, post_id=root.id)
        db.add(notice)
        db.flush()
        refs = SqlAlchemyResidentContextReferences(db, social=SimpleNamespace())
        result = feed_context._v6_inbox_candidates_from_review(
            refs, character_id=fixture.character.id,
            payload={"candidate_notification_id": notice.id, "candidate_reason": "direct-reply"},
        )
        assert len(result) == 1
        assert result[0]["root_post_id"] == root.id
        assert result[0]["source_post_id"] == reply.id
        assert result[0]["actor_name"] == f"{other.name} (@{other.handle})"
        assert result[0]["candidate_reason"] == "direct-reply"
        assert feed_context._v6_inbox_candidates_from_review(refs, character_id=other.id, payload={"candidate_notification_id": notice.id}) == []
        assert feed_context._v6_inbox_candidates_from_review(refs, character_id=fixture.character.id, payload={"candidate_notification_id": True}) == []
        with Session(engine) as observer:
            assert feed_context._v6_inbox_candidates_from_review(
                SqlAlchemyResidentContextReferences(observer, social=SimpleNamespace()),
                character_id=fixture.character.id, payload={"candidate_notification_id": notice.id},
            ) == []
        notice_id = notice.id
        db.rollback()
        assert feed_context._v6_inbox_candidates_from_review(refs, character_id=fixture.character.id, payload={"candidate_notification_id": notice_id}) == []
    engine.dispose()


def test_mutual_reply_candidate_preserves_strict_post_type_and_pending_follow(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture, other, root = _setup(db)
        own_reply = _post("own-mutual-reply", fixture.character.id, parent_id=root.id)
        db.add(own_reply)
        db.flush()
        target_reply = _post("target-mutual-reply", other.id, parent_id=own_reply.id)
        db.add(target_reply)
        db.commit()
        refs = SqlAlchemyResidentContextReferences(db, social=SimpleNamespace())
        kwargs = {"character_id": fixture.character.id, "feed_cue": None, "allowed_actions": ("follow",)}
        candidate = social_context._format_strong_social_connection_candidate(refs, **kwargs)
        assert "- status: available" in candidate
        assert f"- target: character:{other.id}" in candidate
        assert "own_replies=1; target_replies=1" in candidate
        assert refs.is_post_instance(target_reply)
        assert not refs.is_post_instance(SimpleNamespace(id=target_reply.id))
        db.add(ProfileFollow(follower_character_id=fixture.character.id, target_character_id=other.id))
        unavailable = social_context._format_strong_social_connection_candidate(refs, **kwargs)
        assert "- status: none" in unavailable
        with Session(engine) as observer:
            outside = social_context._format_strong_social_connection_candidate(
                SqlAlchemyResidentContextReferences(observer, social=SimpleNamespace()), **kwargs,
            )
            assert "- status: available" in outside
        db.rollback()
        assert social_context._format_strong_social_connection_candidate(refs, **kwargs) == candidate
    engine.dispose()
