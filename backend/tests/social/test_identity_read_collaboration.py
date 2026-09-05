from datetime import UTC, datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app import models
from app.domains.identity.service.profile import get_user
from app.domains.social.service.presentation import _mentioned_characters_for_texts


def _user():
    return models.User(id="social-owner", email="social-owner@example.invalid", display_name="Owner", display_name_normalized="owner")


def test_mentions_use_one_owned_query_and_keep_input_order_and_visibility():
    engine = create_engine("sqlite://")
    models.User.__table__.create(engine)
    models.Character.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = _user()
        characters = [models.Character(id=name, owner_id=owner.id, name=name, handle=name, persona_summary="synthetic") for name in ("alpha", "beta", "hidden", "suspended")]
        characters[2].deleted_at = datetime(2026, 9, 5, tzinfo=UTC)
        characters[3].moderation_status = "suspended"
        db.add_all([owner, *characters])
        db.commit()
        statements = []
        event.listen(engine, "before_cursor_execute", lambda connection, cursor, statement, params, context, many: statements.append(statement))
        mentions = _mentioned_characters_for_texts(db, "@beta @hidden @alpha", "@beta @suspended @missing")
        assert [item.handle for item in mentions] == ["beta", "alpha"]
        assert [item.character_id for item in mentions] == ["beta", "alpha"]
        assert len(statements) == 1
        assert "characters.deleted_at IS NULL" in statements[0]
        assert "characters.moderation_status" in statements[0]
        assert _mentioned_characters_for_texts(db, "no mentions here", None) == []
        assert len(statements) == 1
        assert not db.new and not db.dirty and not db.deleted
    engine.dispose()


def test_user_lookup_preserves_nullable_same_session_unflushed_identity():
    engine = create_engine("sqlite://")
    models.User.__table__.create(engine)
    with Session(engine, autoflush=False, expire_on_commit=False) as db:
        user = _user()
        db.add(user)
        db.commit()
        events = []
        event.listen(db, "before_flush", lambda *args: events.append("flush"))
        event.listen(db, "before_commit", lambda *args: events.append("commit"))
        user.display_name = "Unflushed local change"
        assert get_user(db, user.id) is user
        assert get_user(db, user.id).display_name == "Unflushed local change"
        assert get_user(db, "missing-owner") is None
        assert events == []
        db.rollback()
        assert get_user(db, user.id).display_name == "Owner"
    engine.dispose()
