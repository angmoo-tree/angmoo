"""Final editable values, private source and transaction boundaries, without AI."""
import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from test_local_creator_v2 import db
from app.domains.characters import models, schemas
from app.domains.characters.exceptions import AgentCreationDraftHandleConflictError, AgentCreationDraftNotFoundError, AgentCreationDraftValidationError
from app.domains.characters.service import drafts, card_import, settings_copy
from app.runtime.characters.creator import build_creator_workflows
from app.domains.worlds.service.creator import create_world
from app.domains.worlds.schemas import WorldDraftCreate


def card_bytes():
    return json.dumps({"spec": "chara_card_v2", "spec_version": "2.0", "data": {
        "name": "Original", "description": "{{char}} studies stars.", "personality": "Curious",
        "scenario": "A fictional meeting", "first_mes": "RAW_GREETING_ONLY",
        "mes_example": "{{char}}: Hello {{user}}", "system_prompt": "RAW_SYSTEM_ONLY",
        "post_history_instructions": "RAW_HISTORY_ONLY", "character_book": {"entries": []},
    }}).encode()


def test_card_final_edits_are_only_registered_persona_and_source_stays_private(db):
    session, owner = db
    workflows = build_creator_workflows()
    draft = asyncio.run(drafts.create_draft(session, owner, schemas.AgentCreationDraftCreate(), workflows=workflows))
    imported = card_import.import_card(session, owner, draft.id, revision=1, content=card_bytes(), workflows=workflows)
    assert imported["draft"].speech_style == "Original: Hello 대화 상대"
    assert "scenario_manual_merge" in imported["review"]
    with pytest.raises(AgentCreationDraftNotFoundError):
        card_import.read_source(session, SimpleNamespace(id="foreign"), draft.id)
    edited = drafts.update_draft(session, owner, draft.id, schemas.AgentCreationDraftUpdate(
        revision=imported["draft"].revision, name="Edited", personality="Edited persona", speech_style="Edited voice"), workflows=workflows)
    result = drafts.complete_draft(session, owner, draft.id, schemas.AgentCreationDraftComplete(revision=edited.revision), workflows=workflows)
    stored = session.get(models.Character, result.character.id)
    assert stored.personality == "Edited persona" and stored.speech_style == "Edited voice"
    assert "RAW_" not in stored.persona_summary
    from app.domains.worlds.models import World
    from app.domains.world_characters.models import WorldCharacter
    from app.domains.worlds.service import build_world_generation_context
    from app.domains.world_characters.service.setup_validation import build_world_character_generation_input
    from app.runtime.autonomous_activity.inputs import shared_input
    from app.domains.chat.service.profiles import _response_profile
    actor = session.scalar(select(WorldCharacter).where(WorldCharacter.character_id == stored.id))
    world = session.get(World, actor.world_id)
    preparation = build_world_character_generation_input(character=stored, world_character=actor,
        world_context=build_world_generation_context(session, world))
    sns = shared_input(SimpleNamespace(db=session, user_id=owner.id, character=stored), actor, world)
    chat = _response_profile(stored)
    assert preparation["character"]["personality"] == sns["persona"]["personality"] == chat.personality == "Edited persona"
    assert preparation["character"]["speech_style"] == sns["persona"]["speech_style"] == chat.speech_style == "Edited voice"
    assert "RAW_" not in json.dumps(preparation) + json.dumps(sns) + str(chat)
    source = session.scalar(select(models.CharacterCardSource).where(models.CharacterCardSource.draft_id == draft.id))
    assert source.source_bytes == card_bytes() and source.character_id == stored.id
    draft_row = session.get(models.AgentCreationDraft, draft.id)
    draft_row.expires_at = datetime.now(UTC) - timedelta(days=20)
    session.commit()
    assert drafts.get_draft(session, owner, draft.id, workflows=workflows).status == "completed"
    assert card_import.read_source(session, owner, draft.id)["document"]["data"]["name"] == "Original"
    with pytest.raises(AgentCreationDraftHandleConflictError):
        drafts.update_draft(session, owner, draft.id, schemas.AgentCreationDraftUpdate(revision=edited.revision, name="Wrong"), workflows=workflows)


def test_card_failed_commit_rolls_back_original_source_and_revision(db, monkeypatch):
    session, owner = db
    workflows = build_creator_workflows()
    draft = asyncio.run(drafts.create_draft(session, owner, schemas.AgentCreationDraftCreate(), workflows=workflows))
    first = card_import.import_card(session, owner, draft.id, revision=1, content=card_bytes(), workflows=workflows)
    def fail():
        raise RuntimeError("synthetic commit failure")
    monkeypatch.setattr(session, "commit", fail)
    with pytest.raises(RuntimeError, match="synthetic"):
        card_import.import_card(session, owner, draft.id, revision=first["draft"].revision,
            content=card_bytes().replace(b"Original", b"Replacement"), workflows=workflows)
    assert session.get(models.AgentCreationDraft, draft.id).revision == first["draft"].revision
    assert card_import.read_source(session, owner, draft.id)["document"]["data"]["name"] == "Original"


def test_copy_new_world_creates_new_identity_without_key_or_raw_source(db):
    session, owner = db
    workflows = build_creator_workflows()
    original = asyncio.run(drafts.create_draft(session, owner, schemas.AgentCreationDraftCreate(), workflows=workflows))
    imported = card_import.import_card(session, owner, original.id, revision=1, content=card_bytes(), workflows=workflows)["draft"]
    saved = drafts.complete_draft(session, owner, original.id, schemas.AgentCreationDraftComplete(revision=imported.revision), workflows=workflows)
    other = create_world(session, user=owner, data=WorldDraftCreate(name="Other", idempotency_key="other-world"))
    draft = asyncio.run(drafts.create_draft(session, owner, schemas.AgentCreationDraftCreate(target_world_id=other.world.id), workflows=workflows))
    copied = settings_copy.copy_settings(session, owner, draft.id, schemas.CharacterSettingsCopy(revision=1, character_id=saved.character.id), workflows=workflows)
    registered = drafts.complete_draft(session, owner, draft.id, schemas.AgentCreationDraftComplete(revision=copied.revision), workflows=workflows)
    assert registered.character.id != saved.character.id
    row = session.get(models.Character, registered.character.id)
    assert row.personality == "Curious" and row.credential is None and not row.activity_setting.auto_enabled
    assert session.scalar(select(models.CharacterCardSource).where(models.CharacterCardSource.character_id == row.id)) is None
    same_world = asyncio.run(drafts.create_draft(session, owner, schemas.AgentCreationDraftCreate(), workflows=workflows))
    with pytest.raises(AgentCreationDraftValidationError):
        settings_copy.copy_settings(session, owner, same_world.id, schemas.CharacterSettingsCopy(revision=1, character_id=saved.character.id), workflows=workflows)


def test_keyless_draft_never_enters_legacy_ai_enhancement(db):
    session, owner = db
    def forbidden(*args, **kwargs):
        raise AssertionError("provider must not be reached")
    workflows = replace(build_creator_workflows(), run_llm=forbidden)
    draft = asyncio.run(drafts.create_draft(session, owner, schemas.AgentCreationDraftCreate(), workflows=workflows))
    with pytest.raises(AgentCreationDraftValidationError):
        asyncio.run(drafts.enhance_persona(session, owner, draft.id, workflows=workflows))


def test_canonical_backup_retains_registered_private_card_bytes(db, tmp_path):
    import sqlite3
    from pathlib import Path
    from app.runtime.migrations.embedded_sqlite import _backup_database
    session, owner = db
    workflows = build_creator_workflows()
    draft = asyncio.run(drafts.create_draft(session, owner, schemas.AgentCreationDraftCreate(), workflows=workflows))
    imported = card_import.import_card(session, owner, draft.id, revision=1, content=card_bytes(), workflows=workflows)["draft"]
    registered = drafts.complete_draft(session, owner, draft.id, schemas.AgentCreationDraftComplete(revision=imported.revision), workflows=workflows)
    character_id = registered.character.id
    session.commit()
    destination = tmp_path / "restored-canonical.sqlite3"
    _backup_database(Path(session.get_bind().url.database), destination)
    with sqlite3.connect(destination) as restored:
        row = restored.execute("SELECT source_bytes, character_id FROM character_card_sources WHERE draft_id=?", (draft.id,)).fetchone()
        assert row == (card_bytes(), character_id)
        assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert restored.execute("PRAGMA foreign_key_check").fetchall() == []


def test_foreign_media_and_stale_card_replacement_cannot_change_draft(db):
    session, owner = db
    workflows = build_creator_workflows()
    draft = asyncio.run(drafts.create_draft(session, owner, schemas.AgentCreationDraftCreate(), workflows=workflows))
    imported = card_import.import_card(session, owner, draft.id, revision=1, content=card_bytes(), workflows=workflows)["draft"]
    with pytest.raises(AgentCreationDraftHandleConflictError):
        card_import.import_card(session, owner, draft.id, revision=1, content=card_bytes().replace(b"Original", b"Wrong"), workflows=workflows)
    assert card_import.read_source(session, owner, draft.id)["document"]["data"]["name"] == "Original"
    with pytest.raises(AgentCreationDraftValidationError):
        drafts.update_draft(session, owner, draft.id, schemas.AgentCreationDraftUpdate(
            revision=imported.revision, avatar_temp_url="/media/drafts/foreign/avatar.webp"), workflows=workflows)
    assert session.get(models.AgentCreationDraft, draft.id).avatar_temp_url is None
