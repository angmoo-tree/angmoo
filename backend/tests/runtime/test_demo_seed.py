"""Opt-in demo initialization keeps its data and transaction boundaries."""

from types import SimpleNamespace

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app import models  # Register the existing complete mapper set.
from app.core.db import Base
from app.runtime.bootstrap import demo_seed


def _engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def test_demo_seed_keeps_initial_defaults_and_noop_replay(monkeypatch):
    monkeypatch.setattr(demo_seed, "settings", SimpleNamespace(demo_user_password=None))
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        commits = []
        event.listen(db, "before_commit", lambda *_: commits.append("commit"))
        demo_seed.seed_demo_data(db)
        user = db.get(models.User, "user-demo")
        character = db.get(models.Character, "char-mango")
        credential = db.get(models.LlmCredential, "cred-demo-google")
        state = db.get(models.CharacterState, character.id)
        setting = db.get(models.AgentActivitySetting, character.id)
        assert user.email == "demo@angmoo.local"
        assert user.password_hash is None
        assert user.profile_setup_completed
        assert character.owner_id == user.id
        assert character.status == "inactive"
        assert state.mood == "curious"
        assert credential.owner_id == user.id
        assert credential.character_id == character.id
        assert credential.provider == "google"
        assert credential.encrypted_api_key is None
        assert setting.auto_enabled is False
        assert setting.activity_interval_minutes == 60
        assert setting.comment_cooldown_minutes == 180
        assert setting.post_cooldown_hours == 24
        assert db.scalars(select(models.Post.id).order_by(models.Post.id)).all() == [
            "post-001", "post-002"
        ]
        assert commits == ["commit"]

        demo_seed.seed_demo_data(db)
        assert db.get(models.User, user.id) is user
        assert db.get(models.Character, character.id) is character
        assert db.get(models.AgentActivitySetting, character.id) is setting
        assert commits == ["commit"]
    engine.dispose()


def test_demo_seed_repairs_existing_user_then_credential_then_setting(monkeypatch):
    monkeypatch.setattr(demo_seed, "settings", SimpleNamespace(demo_user_password=None))
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        demo_seed.seed_demo_data(db)
        user = db.get(models.User, "user-demo")
        user.email = None
        user.display_name_normalized = None
        user.profile_setup_completed = False
        db.delete(db.get(models.LlmCredential, "cred-demo-google"))
        db.delete(db.get(models.AgentActivitySetting, "char-mango"))
        db.commit()
        monkeypatch.setattr(
            demo_seed, "settings", SimpleNamespace(demo_user_password="synthetic-demo-phrase")
        )
        writes = []

        def record_commit(session):
            writes.append(sorted(type(row).__name__ for row in [*session.new, *session.dirty]))

        event.listen(db, "before_commit", record_commit)
        demo_seed.seed_demo_data(db)
        assert writes == [["User"], ["LlmCredential"], ["AgentActivitySetting"]]
        assert user.email == "demo@angmoo.local"
        assert user.display_name_normalized == "demo user"
        assert user.profile_setup_completed
        assert demo_seed.security.verify_password("synthetic-demo-phrase", user.password_hash)
        assert db.get(models.Character, "char-mango").name == "망고"
        assert len(db.scalars(select(models.Post)).all()) == 2

        demo_seed.seed_demo_data(db)
        assert writes == [["User"], ["LlmCredential"], ["AgentActivitySetting"]]
    engine.dispose()
