"""The cross-owner Character write keeps the caller transaction boundary."""
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from app import models
from app.core.db import Base
from app.domains.characters.service.owner_controlled import (
    seed_owner_controlled_character, update_owner_controlled_character,
)


def _database():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(models.User(id="owner", email="owner@example.test", display_name="owner",
                           display_name_normalized="owner", privacy_policy_version="test",
                           terms_version="test", profile_setup_completed=True))
        db.commit()
    return engine


def _seed(db):
    return seed_owner_controlled_character(
        db, character_id="owner-character-id", owner_id="owner", display_name="Original",
        avatar_url=None, intro="Introduction", interests=("one", "two"), background="Background",
    )


def test_owner_character_seed_flushes_once_and_rollback_removes_the_attached_row():
    engine = _database()
    with Session(engine) as db:
        calls = []
        event.listen(db, "after_flush", lambda *_: calls.append("flush"))
        event.listen(db, "after_commit", lambda *_: calls.append("commit"))
        character = _seed(db)
        assert inspect(character).session is db
        assert calls == ["flush"]
        assert character.handle == "owner-owner-character-id"
        assert character.topic_preferences == "one, two"
        assert character.persona_summary == "Background"
        assert character.status == "active" and character.execution_mode == "local"
        assert character.promotion_usage_allowed is False
        db.rollback()
        assert db.get(models.Character, "owner-character-id") is None


def test_owner_character_update_defers_flush_and_preserves_unrelated_fields():
    engine = _database()
    with Session(engine) as db:
        character = _seed(db)
        db.commit()
        db.refresh(character)
        calls = []
        event.listen(db, "after_flush", lambda *_: calls.append("flush"))
        event.listen(db, "after_commit", lambda *_: calls.append("commit"))
        original_handle = character.handle
        update_owner_controlled_character(
            character, display_name="Changed", avatar_url="/avatar.png", intro="New intro",
            interests=("three",), background="",
        )
        assert calls == []
        assert inspect(character).session is db
        assert character.name == "Changed" and character.persona_summary == "New intro"
        assert character.handle == original_handle and character.execution_mode == "local"
        assert character.promotion_usage_allowed is False
        db.rollback()
        assert character.name == "Original" and character.persona_summary == "Background"
