"""Character role moves preserve identities and distinct write contracts."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app import models as registered_models, schemas as registered_schemas
from app.core.db import Base
from app.core.unit_of_work import deferred_commits
from app.cruds import community as legacy_repository
from app.domains.characters import contracts, models, public, schemas
from app.domains.characters.service import profile, seed, state
from app.domains.media import schemas as media_schemas
from app.models import characters as legacy_models
from app.schemas import agents as legacy_agent_schemas
from app.schemas import characters as legacy_character_schemas
from app.schemas import media_security as legacy_media_schemas


@pytest.fixture
def engine(tmp_path):
    value = create_engine(f"sqlite:///{tmp_path / 'character-roles.sqlite3'}")
    for table in (
        registered_models.User.__table__, models.Character.__table__,
        models.CharacterState.__table__,
    ):
        table.create(value)
    with Session(value) as db:
        db.add(registered_models.User(id="owner", display_name="Owner"))
        db.commit()
    yield value
    value.dispose()


def seed_data(**changes):
    values = dict(
        owner_id="owner", display_name="Bird", handle_hint="Café Bird",
        one_liner="hello", personality="calm", speech_style="plain",
        worldview="a small world", topic_preferences=("gardens", "tea"),
        safety_rules=("be kind",), persona_summary="A calm bird",
    )
    values.update(changes)
    return contracts.AutonomousCharacterSeedData(**values)


def test_model_and_schema_compatibility_exports_have_one_identity():
    for name in ("Character", "CharacterState"):
        canonical = getattr(models, name)
        assert canonical is getattr(registered_models, name)
        assert canonical is getattr(legacy_models, name)
        assert canonical is getattr(public, name)
        assert canonical.metadata is Base.metadata
    for name in ("CharacterRead", "CharacterStateRead", "CharacterStateWrite", "AgentCharacterStateWrite"):
        assert getattr(schemas, name) is getattr(registered_schemas, name)
        assert getattr(schemas, name) is getattr(legacy_character_schemas, name)
    for name in ("AgentCreate", "AgentDeleteCreate", "AgentProfileUpdate", "AgentPersonaUpdate"):
        assert getattr(schemas, name) is getattr(legacy_agent_schemas, name)
    assert public.seed_autonomous_character is seed.seed_autonomous_character
    assert legacy_repository.create_character is profile.create_character
    assert legacy_repository.upsert_character_state is state.upsert_character_state
    assert legacy_media_schemas.validate_profile_media_reference is media_schemas.validate_profile_media_reference


def test_seed_flushes_in_the_callers_transaction_and_rolls_back(engine):
    commits = []
    with Session(engine) as db:
        event.listen(db, "after_commit", lambda session: commits.append(session))
        character = seed.seed_autonomous_character(db, data=seed_data())
        assert db.get(models.Character, character.id) is character
        assert character.handle == "cafe_bird"
        assert character.status == "active"
        assert character.topic_preferences == "gardens, tea"
        assert commits == []
        db.rollback()
    with Session(engine) as check:
        assert check.scalars(select(models.Character)).all() == []


def test_seed_keeps_suffix_and_planned_handle_contracts(engine):
    with Session(engine) as db:
        first = seed.seed_autonomous_character(db, data=seed_data())
        second = seed.seed_autonomous_character(db, data=seed_data())
        planned = seed.seed_autonomous_character(db, data=seed_data(planned_handle="planned_bird"))
        assert (first.handle, second.handle, planned.handle) == ("cafe_bird", "cafe_bird_2", "planned_bird")
        with pytest.raises(ValueError, match="character_handle_unavailable"):
            seed.seed_autonomous_character(db, data=seed_data(planned_handle="planned_bird"))
        db.rollback()


def test_profile_create_keeps_its_existing_commit_and_inactive_defaults(engine):
    with Session(engine) as db:
        character = profile.create_character(
            db, user=SimpleNamespace(id="owner"), character_id="char-fixed123",
            data=schemas.AgentCreate(execution_mode="local", name=" Café Bird "),
        )
        assert character.handle == "caf_bird"
        assert character.status == "inactive"
        assert character.name == "Café Bird"
        assert character.execution_mode == "local"
        db.rollback()
    with Session(engine) as check:
        assert check.get(models.Character, "char-fixed123").handle == "caf_bird"


def test_state_write_keeps_deferred_commit_participation(engine):
    with Session(engine) as db:
        character = seed.seed_autonomous_character(db, data=seed_data())
        db.commit()
        character_id = character.id
        commits = []
        event.listen(db, "after_commit", lambda session: commits.append(session))
        with deferred_commits():
            written = state.upsert_character_state(
                db, character, schemas.CharacterStateWrite(summary="temporary", memory_note="private"),
            )
            assert written.character_id == character.id
            assert commits == []
        db.rollback()
        assert db.get(models.CharacterState, character_id) is None
        state.upsert_character_state(db, character, schemas.CharacterStateWrite(summary="persisted"))
        assert commits == [db]
    with Session(engine) as check:
        assert check.get(models.CharacterState, character_id).summary == "persisted"


@pytest.mark.parametrize("values", [
    {"execution_mode": "llm", "name": "Bird", "personality": "calm"},
    {"execution_mode": "local", "name": "Bird", "api_key": "synthetic-key"},
    {"execution_mode": "local", "name": "Bird", "avatar_url": "https://example.com/bird.png"},
])
def test_creation_schema_still_rejects_invalid_mode_and_unmanaged_media(values):
    with pytest.raises(ValueError):
        schemas.AgentCreate(**values)
