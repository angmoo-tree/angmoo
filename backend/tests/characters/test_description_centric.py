"""Description-first settings retain optional detail without extraction calls."""

from types import SimpleNamespace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from model_fixture_support import models as registered_models
from app.domains.characters import models, schemas
from app.domains.characters.exceptions import AgentPersonaValidationError, AgentCreationDraftValidationError
from app.domains.characters.service.prompt_persona import model_persona, legacy_persona_summary
from app.domains.characters.service import profile
from app.domains.characters.service.card_mapping import map_card
from app.integrations.character_cards.parser import parse_card
from app.domains.identity.models import InstallationIdentity
from app.domains.worlds.service.default_space import ensure_default_space
from app.runtime.characters.registration import register_draft
from app.runtime.persistence.model_registration import register_models


def test_model_persona_preserves_packed_and_split_settings_without_duplication():
    source = SimpleNamespace(
        name="마린", one_liner="", worldview="조용한 서점 주인. 책 이야기에 열정적이다. 존댓말을 쓴다.",
        character_background="서점 이전에는 오래된 기록 보관소에서 일했다.",
        personality="", speech_style="", topic_preferences="", safety_rules="", persona_summary="",
    )
    source.persona_summary = legacy_persona_summary(source)
    payload = model_persona(source)
    assert payload["description"] == source.worldview
    assert payload["character_background"] == source.character_background
    assert payload["speech_style"] == ""
    assert "legacy_persona_summary_extra" not in payload
    source.persona_summary = "과거 승인된 별도 인물 요약"
    assert model_persona(source)["legacy_persona_summary_extra"] == source.persona_summary
    assert model_persona({"worldview": "옛 설명"})["character_background"] == ""


def test_card_description_is_kept_whole_without_required_personality():
    import json

    card = {"spec": "chara_card_v2", "spec_version": "2.0", "data": {
        "name": "마린", "description": "[성격: 다정함]\n[말투: 존댓말]\n옛 왕국 출신",
        "personality": "", "mes_example": "", "scenario": "", "first_mes": "",
    }}
    mapped = map_card(parse_card(json.dumps(card, ensure_ascii=False).encode()))
    assert mapped.fields["worldview"] == card["data"]["description"]
    assert mapped.fields["personality"] == mapped.fields["speech_style"] == ""
    assert "description_required_review" not in mapped.review
    card["data"]["description"] = ""
    assert "description_required_review" in map_card(parse_card(json.dumps(card).encode())).review


def test_legacy_persona_edit_preserves_omitted_background_and_explicitly_clears_it(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'persona.sqlite3'}")
    registered_models.User.__table__.create(engine)
    models.Character.__table__.create(engine)
    with Session(engine) as db:
        db.add(registered_models.User(id="owner", display_name="Owner"))
        db.add(models.Character(id="bird", owner_id="owner", name="Bird", handle="bird",
            worldview="설명", character_background="옛 왕국 출신", personality="", persona_summary=""))
        db.commit()
        character = db.get(models.Character, "bird")
        profile.update_character_persona(db, character, schemas.AgentPersonaUpdate(worldview="새 설명"))
        assert character.character_background == "옛 왕국 출신"
        profile.update_character_persona(db, character, schemas.AgentPersonaUpdate(
            worldview="새 설명", character_background=""))
        assert character.character_background == ""
        with pytest.raises(AgentPersonaValidationError):
            profile.update_character_persona(db, character, schemas.AgentPersonaUpdate(worldview="   "))
        assert character.worldview == "새 설명"
    engine.dispose()


def test_new_llm_registration_schema_requires_description_not_personality():
    with pytest.raises(ValueError, match="description"):
        schemas.AgentCreate(name="Bird", api_key="fixture", worldview="")
    value = schemas.AgentCreate(name="Bird", api_key="fixture", worldview="서점 주인")
    assert value.personality == ""
    assert value.character_background == ""
    # The existing local executor's no-description admission is distinct.
    assert schemas.AgentCreate(name="Bird", execution_mode="local").worldview == ""


def test_description_only_draft_registers_keyless_off_and_preserves_background(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'registration.sqlite3'}")
    register_models().create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = registered_models.User(id="owner", display_name="Owner")
        db.add(owner)
        db.add(InstallationIdentity(singleton_key="local-installation", installation_id="fixture",
            owner_user_id=owner.id, bootstrap_state="claimed", claimed_at=datetime.now(UTC)))
        db.commit()
        world = ensure_default_space(db, owner_id=owner.id)
        draft = models.AgentCreationDraft(id="draft", user_id=owner.id, contract_version=2,
            target_world_id=world.id, model="gemini-3.1-flash-lite", name="Book Bird",
            worldview="책을 사랑하는 서점 주인이다.", character_background="옛 왕국 출신이다.",
            personality="", speech_style="", expires_at=datetime.now(UTC) + timedelta(days=1))
        db.add(draft)
        db.commit()
        result = register_draft(db, owner, draft, schemas.AgentCreationDraftComplete(revision=draft.revision))
        character = db.get(models.Character, result.character.id)
        assert character.worldview == "책을 사랑하는 서점 주인이다."
        assert character.character_background == "옛 왕국 출신이다."
        assert character.personality == ""
        assert character.execution_mode == "llm"
        assert result.character.id == register_draft(db, owner, draft,
            schemas.AgentCreationDraftComplete(revision=draft.revision)).character.id
        missing = models.AgentCreationDraft(id="missing", user_id=owner.id, contract_version=2,
            target_world_id=world.id, model="gemini-3.1-flash-lite", name="No Description",
            worldview="", personality="quiet", expires_at=datetime.now(UTC) + timedelta(days=1))
        db.add(missing)
        db.commit()
        with pytest.raises(AgentCreationDraftValidationError, match="설명"):
            register_draft(db, owner, missing, schemas.AgentCreationDraftComplete(revision=missing.revision))
    engine.dispose()
