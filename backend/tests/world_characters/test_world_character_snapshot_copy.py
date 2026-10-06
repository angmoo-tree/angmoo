"""Final creation/copy paths keep permanent lineage and independent World values."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy import select
from test_local_creator_v2 import db
from app.domains.characters import models, schemas
from app.domains.characters.models_import import CharacterImportSnapshot, CharacterDraftImportOrigin, CharacterImportOrigin
from app.domains.characters.service import drafts, settings_copy
from app.domains.characters.service.import_snapshots import get_import_snapshot
from app.domains.world_characters.models import WorldCharacter, CharacterWorldBinding
from app.domains.world_characters.service.configuration import effective_configuration
from app.domains.worlds.service.creator import create_world
from app.domains.worlds.schemas import WorldDraftCreate
from app.runtime.characters.creator import build_creator_workflows


def register(session, owner, *, world=None, name="Bram"):
    workflows = build_creator_workflows()
    draft = asyncio.run(drafts.create_draft(session, owner, schemas.AgentCreationDraftCreate(target_world_id=world), workflows=workflows))
    edited = drafts.update_draft(session, owner, draft.id, schemas.AgentCreationDraftUpdate(revision=draft.revision,
        name=name, personality="First persona", speech_style="First speech", worldview="First world", one_liner="First intro"), workflows=workflows)
    data = schemas.AgentCreationDraftComplete(revision=edited.revision)
    return draft, data, drafts.complete_draft(session, owner, draft.id, data, workflows=workflows)


def test_t91_t92_t103_t104_real_registration_and_copy_reuses_first_basis_only(db):
    session, owner = db
    original_draft, data, original = register(session, owner)
    cid = original.character.id
    origin, initial = get_import_snapshot(session, cid)
    assert origin.kind == "creation" and origin.provenance == f"registration:{original_draft.id}"
    source = session.get(models.Character, cid)
    source.personality, source.name = "Source changed later", "Source renamed later"
    old_role = session.scalar(select(WorldCharacter).where(WorldCharacter.character_id == cid))
    old_role.autonomous_enabled = True
    session.commit()
    other = create_world(session, user=owner, data=WorldDraftCreate(name="Copy World", idempotency_key="copy-basis-world"))
    workflows = build_creator_workflows()
    target = asyncio.run(drafts.create_draft(session, owner, schemas.AgentCreationDraftCreate(target_world_id=other.world.id), workflows=workflows))
    copied = settings_copy.copy_settings(session, owner, target.id, schemas.CharacterSettingsCopy(revision=target.revision, character_id=cid), workflows=workflows)
    assert copied.name == "Bram" and copied.personality == "First persona"
    completed = drafts.complete_draft(session, owner, target.id, schemas.AgentCreationDraftComplete(revision=copied.revision), workflows=workflows)
    new_id = completed.character.id
    new_role = session.scalar(select(WorldCharacter).where(WorldCharacter.character_id == new_id))
    assert new_id != cid and new_role.id != old_role.id and not new_role.autonomous_enabled
    assert session.get(CharacterWorldBinding, new_id).world_id == other.world.id
    assert get_import_snapshot(session, new_id)[0].id == origin.id
    value = effective_configuration(session, world_character_id=new_role.id)
    assert value.settings.personality == "First persona" and value.profile.display_name == "Bram"
    assert session.get(models.Character, new_id).credential is None
    assert old_role.autonomous_enabled and get_import_snapshot(session, cid)[0].digest == origin.digest
    replay = drafts.complete_draft(session, owner, original_draft.id, data, workflows=workflows)
    assert replay.character.id == cid
    assert session.scalar(select(CharacterImportSnapshot.id).where(CharacterImportSnapshot.source_character_id == new_id)) is None


def test_t91_failed_creation_rolls_back_origin_and_world_instance(db, monkeypatch):
    session, owner = db
    workflows = build_creator_workflows()
    draft = asyncio.run(drafts.create_draft(session, owner, schemas.AgentCreationDraftCreate(), workflows=workflows))
    edited = drafts.update_draft(session, owner, draft.id, schemas.AgentCreationDraftUpdate(revision=draft.revision,
        name="Rollback", worldview="A fictional world"), workflows=workflows)
    before = set(session.scalars(select(CharacterImportSnapshot.id)))
    def failure():
        raise RuntimeError("controlled final commit failure")
    monkeypatch.setattr(session, "commit", failure)
    with pytest.raises(RuntimeError, match="controlled"):
        drafts.complete_draft(session, owner, draft.id, schemas.AgentCreationDraftComplete(revision=edited.revision), workflows=workflows)
    assert set(session.scalars(select(CharacterImportSnapshot.id))) == before
    assert session.scalar(select(models.Character.id).where(models.Character.name == "Rollback")) is None
    assert session.get(models.AgentCreationDraft, draft.id).status == "editing"


def test_t98_t116_copy_draft_expiry_cleans_lineage_without_mutating_basis(db):
    session, owner = db
    _, _, original = register(session, owner)
    other = create_world(session, user=owner, data=WorldDraftCreate(name="Expiry World", idempotency_key="copy-expiry-world"))
    workflows = build_creator_workflows()
    draft = asyncio.run(drafts.create_draft(session, owner, schemas.AgentCreationDraftCreate(target_world_id=other.world.id), workflows=workflows))
    settings_copy.copy_settings(session, owner, draft.id, schemas.CharacterSettingsCopy(revision=draft.revision, character_id=original.character.id), workflows=workflows)
    origin = get_import_snapshot(session, original.character.id)[0]
    saved = (origin.id, origin.digest, origin.payload)
    session.get(models.AgentCreationDraft, draft.id).expires_at = datetime.now(UTC) - timedelta(days=20)
    session.commit()
    drafts._cleanup_expired_drafts(session, workflows=workflows)
    assert session.get(models.AgentCreationDraft, draft.id) is None
    assert session.get(CharacterDraftImportOrigin, draft.id) is None
    assert (origin.id, origin.digest, origin.payload) == saved
