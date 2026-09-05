from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.routines.service import action_admission, action_menu
from app.domains.social.models import posts as models
from app.runtime.resident.context_references import SqlAlchemyResidentActionReferences
from routine_posts.test_runtime import _seed
from social.test_resident_context_queries import _engine, _post


def _setup(db):
    fixture = _seed(db)
    other = Character(id="other", owner_id=fixture.user.id, name="Other", handle="other-resident", persona_summary="A neighbour")
    db.add(other)
    db.flush()
    root = _post("root", other.id)
    db.add(root)
    db.commit()
    return fixture, other, root


def test_action_admission_uses_same_session_pending_reactions_and_caller_rollback(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture, other, root = _setup(db)
        actor_id = fixture.character.id
        refs = SqlAlchemyResidentActionReferences(db)
        assert refs.get_post(root.id) is root
        db.add_all([
            models.PostLike(post_id=root.id, user_id=fixture.user.id, character_id=actor_id),
            models.ProfileFollow(follower_character_id=actor_id, target_character_id=other.id),
        ])
        kwargs = dict(character_id=actor_id, allowed={"like", "reply", "repost", "follow"}, post_id=root.id, author_target_type="character", author_target_id=other.id, reply_root_post_id=root.id)
        allowed = action_admission._v6_allowed_tool_calls(refs, **kwargs, reply_label="reply")
        unavailable = action_admission._v6_unavailable_post_actions(refs, **kwargs)
        assert "- tool: angmoo_like_post" not in allowed
        assert "- tool: angmoo_follow_profile" not in allowed
        assert "- tool: angmoo_reply_to_post_from_brief" in allowed
        assert "- tool: angmoo_repost_post" in allowed
        assert "- like: already liked" in unavailable
        assert "- follow: already following author" in unavailable
        with Session(engine) as observer:
            outside = action_admission._v6_allowed_tool_calls(SqlAlchemyResidentActionReferences(observer), **kwargs, reply_label="reply")
            assert "- tool: angmoo_like_post" in outside
            assert "- tool: angmoo_follow_profile" in outside
        db.rollback()
        restored = action_admission._v6_allowed_tool_calls(refs, **kwargs, reply_label="reply")
        assert "- tool: angmoo_like_post" in restored
        assert "- tool: angmoo_follow_profile" in restored
    engine.dispose()


def test_action_menu_keeps_hidden_parent_context_out_without_committing_hide(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture, other, root = _setup(db)
        reply = _post("reply", other.id, parent_id=root.id)
        reply.body = "private-context-marker"
        db.add(reply)
        db.commit()
        refs = SqlAlchemyResidentActionReferences(db)
        kwargs = dict(character_id=fixture.character.id, allowed_actions=("like", "reply"), inbox_candidates=[], feed_interest_payload={"interests": [{"post_id": reply.id, "reason": "interesting"}]})
        visible = action_menu._format_v6_action_menu_table(refs, **kwargs)
        assert "Feed candidate 1" in visible
        assert "private-context-marker" in visible
        root.report_hidden_at = datetime.now(UTC)
        hidden = action_menu._format_v6_action_menu_table(refs, **kwargs)
        assert "Feed candidate 1" not in hidden
        assert "private-context-marker" not in hidden
        with Session(engine) as observer:
            outside = action_menu._format_v6_action_menu_table(SqlAlchemyResidentActionReferences(observer), **kwargs)
            assert "Feed candidate 1" in outside
        db.rollback()
        restored = action_menu._format_v6_action_menu_table(refs, **kwargs)
        assert "Feed candidate 1" in restored
    engine.dispose()
