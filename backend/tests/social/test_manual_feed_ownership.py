from sqlalchemy import event
from sqlalchemy.orm import object_session

from app.domains.characters.models import Character
from app.domains.social.service.manual_feed import list_owner_world_feed
from app.runtime.social.manual_feed_references import RuntimeManualFeedReferences
from social.test_l4_social_write_uow import _session_factory


def test_manual_feed_reads_owner_facts_in_order_without_committing(monkeypatch, tmp_path):
    factory = _session_factory(tmp_path)
    with factory() as db:
        calls, commits = [], []
        references = RuntimeManualFeedReferences(db)
        assert not db.in_transaction()
        for name in (
            "get_owner_identity", "get_world_character", "get_character",
            "get_membership", "active_author_id",
        ):
            original = getattr(references, name)

            def record(*args, _name=name, _original=original, **kwargs):
                assert references.db is db
                result = _original(*args, **kwargs)
                if _name in {"get_world_character", "get_character", "get_membership"}:
                    assert object_session(result) is db
                calls.append(_name)
                return result

            monkeypatch.setattr(references, name, record)
        event.listen(db, "before_commit", lambda *_: commits.append("commit"))
        feed = list_owner_world_feed(
            db, references=references, world_id="social-uow-world",
            current_user_id="social-uow-owner",
        )
        assert calls == [
            "get_owner_identity", "get_world_character", "get_character", "get_membership",
            "get_world_character", "get_character", "active_author_id",
        ]
        assert [post.id for post in feed.items] == ["social-uow-target-post"]
        assert feed.items[0].author_profile_capability == "available"
        assert feed.items[0].can_owner_reply is True
        author = db.get(Character, "social-uow-autonomous-character")
        author.moderation_status = "hidden"
        changed = list_owner_world_feed(
            db, references=references, world_id="social-uow-world",
            current_user_id="social-uow-owner",
        )
        # The mixed active-profile join sees the caller's uncommitted edit.
        # Its capability decision does not silently add a new feed filter.
        assert [post.id for post in changed.items] == ["social-uow-target-post"]
        assert changed.items[0].author_profile_capability == "unavailable"
        assert commits == []
        db.rollback()
        assert db.get(Character, author.id).moderation_status == "active"
