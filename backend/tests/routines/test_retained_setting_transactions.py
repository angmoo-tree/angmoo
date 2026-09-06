"""Original retained owner-setting writes keep their exact commit/flush contract."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from model_fixture_support import models as _registered_models
from app.domains.characters.models import Character
from app.domains.characters.service import mutations
from app.domains.identity.models import User
from app.domains.routines.models import AgentActivitySetting
from app.domains.routines.service import activity_settings
from app.runtime.resident.autonomy_reads import list_other_active_settings


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retained-settings.sqlite3'}")
    for table in (User.__table__, Character.__table__, AgentActivitySetting.__table__):
        table.create(engine)
    return engine


@pytest.mark.parametrize("commit", [False, True])
def test_retained_other_settings_keep_owner_join_and_commit_or_flush(tmp_path, commit):
    engine = _engine(tmp_path)
    try:
        with Session(engine, expire_on_commit=False) as db:
            db.add_all([User(id="owner", display_name="owner"), User(id="other", display_name="other")])
            at = datetime(2026, 9, 1, tzinfo=UTC)
            settings = {}
            for key in ["keep", "one", "two", "deleted", "foreign", "disabled"]:
                db.add(Character(id=key, owner_id="other" if key == "foreign" else "owner", name=key, handle=key, persona_summary="fixture", deleted_at=at if key == "deleted" else None))
                settings[key] = AgentActivitySetting(character_id=key, auto_enabled=key != "disabled", updated_at=at)
                db.add(settings[key])
            db.commit()
            selected = list_other_active_settings(db, user_id="owner", keep_character_id="keep")
            assert {item.character_id for item in selected} == {"one", "two"}
            assert all(item is settings[item.character_id] for item in selected)
            events = []
            event.listen(db, "before_commit", lambda *_: events.append("commit"))
            event.listen(db, "after_flush", lambda *_: events.append("flush"))
            result = activity_settings.disable_other_active_settings(db, selected, commit=commit)
            assert result is selected
            assert events == (["commit", "flush"] if commit else ["flush"])
            assert settings["one"].updated_at == settings["two"].updated_at
            with Session(engine) as observer:
                assert observer.get(AgentActivitySetting, "one").auto_enabled is (not commit)
                assert observer.get(AgentActivitySetting, "keep").auto_enabled is True
                assert observer.get(AgentActivitySetting, "foreign").auto_enabled is True
                assert observer.get(AgentActivitySetting, "deleted").auto_enabled is True
            db.rollback()
            assert settings["one"].auto_enabled is (not commit)
            events.clear()
            empty = []
            assert activity_settings.disable_other_active_settings(db, empty, commit=commit) is empty
            assert events == []
    finally:
        engine.dispose()


def test_retained_character_status_commits_the_original_caller_transaction(tmp_path):
    engine = _engine(tmp_path)
    try:
        with Session(engine) as db:
            db.add(User(id="owner", display_name="owner"))
            character = Character(id="character", owner_id="owner", name="original", handle="character", persona_summary="fixture", status="inactive")
            db.add(character)
            db.commit()
            character.name = "pending same transaction"
            assert mutations.set_character_status(db, character, "active") is None
            with Session(engine) as observer:
                row = observer.get(Character, "character")
                assert row.status == "active"
                assert row.name == "pending same transaction"
            db.rollback()
            assert character.status == "active"
    finally:
        engine.dispose()
