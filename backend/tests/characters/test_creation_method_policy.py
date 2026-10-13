"""New registration policy, explicit draft recovery and preservation boundaries."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import select, func

from test_local_creator_v2 import db  # noqa: F401 - isolated canonical fixture
from app.domains.characters.models import AgentCreationDraft, Character, CharacterRegistrationReceipt
from app.domains.characters.schemas import AgentCreate, AgentCreationDraftCreate, AgentCreationDraftUpdate, AgentCreationDraftComplete
from app.domains.characters.service import drafts, management
from app.domains.characters.exceptions import AgentCreationDraftValidationError, AgentCreationDraftHandleConflictError, AgentCreationDraftExpiredError, AgentExecutionModeError
from app.runtime.characters.creator import build_creator_workflows
from app.domains.identity.models import User
from app.domains.characters.schemas import AgentCreationDraftAdopt
from app.domains.characters.exceptions import AgentCreationDraftNotFoundError


def _external(session, owner):
    workflows = build_creator_workflows()
    read = asyncio.run(drafts.create_draft(session, owner, AgentCreationDraftCreate(), workflows=workflows))
    row = session.get(AgentCreationDraft, read.id)
    row.source_kind = "external"
    row.name, row.worldview, row.one_liner = "Preserved", "Original description", "Original intro"
    row.encrypted_api_key = "private-legacy-material"
    session.commit()
    return row, workflows


def test_unsupported_create_rejects_before_cleanup_or_target(db):
    session, owner = db
    resolver, cleanup = Mock(side_effect=AssertionError("unexpected side effect")), Mock()
    workflows = replace(build_creator_workflows(), resolve_target=resolver, delete_draft_media=cleanup)
    data = AgentCreationDraftCreate.model_construct(execution_mode="local", target_world_id=None)
    with pytest.raises(AgentCreationDraftValidationError):
        asyncio.run(drafts.create_draft(session, owner, data, workflows=workflows))
    resolver.assert_not_called(); cleanup.assert_not_called()
    assert session.scalar(select(func.count()).select_from(AgentCreationDraft)) == 0
    with pytest.raises(AgentExecutionModeError):
        management.create_agent(session, owner, AgentCreate.model_construct(execution_mode="local"), workflows=Mock())
    assert session.scalar(select(func.count()).select_from(Character)) == 0


def test_external_registration_rejects_without_new_rows(db):
    session, owner = db
    row, workflows = _external(session, owner)
    with pytest.raises(AgentCreationDraftValidationError):
        drafts.complete_draft(session, owner, row.id, AgentCreationDraftComplete(revision=row.revision), workflows=workflows)
    assert session.scalar(select(func.count()).select_from(Character)) == 0
    assert session.get(CharacterRegistrationReceipt, row.id) is None
    assert row.source_kind == "external" and row.encrypted_api_key == "private-legacy-material"


def test_explicit_reselection_preserves_input_and_registers_keyless(db):
    session, owner = db
    row, workflows = _external(session, owner)
    assert drafts.get_draft(session, owner, row.id, workflows=workflows).source_kind == "external"
    changed = drafts.update_draft(session, owner, row.id, AgentCreationDraftUpdate(revision=row.revision,
        creation_method="direct", target_world_id=row.target_world_id), workflows=workflows)
    assert changed.source_kind == "direct"
    assert (changed.name, changed.worldview, changed.one_liner) == ("Preserved", "Original description", "Original intro")
    assert row.encrypted_api_key == "private-legacy-material"
    result = drafts.complete_draft(session, owner, row.id, AgentCreationDraftComplete(revision=changed.revision), workflows=workflows)
    assert result.character.execution_mode == "llm" and result.credential is None
    assert result.settings.auto_enabled is False


@pytest.mark.parametrize("failure", ["stale", "target", "registering", "expired"])
def test_reselection_failures_preserve_source_and_fields(db, failure):
    session, owner = db
    row, workflows = _external(session, owner)
    if failure == "registering": row.status = "registering"
    if failure == "expired": row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    revision = row.revision + 1 if failure == "stale" else row.revision
    target = "foreign-world" if failure == "target" else row.target_world_id
    with pytest.raises((AgentCreationDraftValidationError, AgentCreationDraftHandleConflictError, AgentCreationDraftExpiredError)):
        drafts.update_draft(session, owner, row.id, AgentCreationDraftUpdate(revision=revision,
            creation_method="direct", target_world_id=target), workflows=workflows)
    session.rollback()
    assert session.get(AgentCreationDraft, row.id).source_kind == "external"
    assert row.name == "Preserved"


def test_reselection_commit_failure_rolls_back(db, monkeypatch):
    session, owner = db
    row, workflows = _external(session, owner)
    monkeypatch.setattr(session, "commit", Mock(side_effect=RuntimeError("injected failure")))
    with pytest.raises(RuntimeError):
        drafts.update_draft(session, owner, row.id, AgentCreationDraftUpdate(revision=row.revision, creation_method="direct"), workflows=workflows)
    assert session.get(AgentCreationDraft, row.id).source_kind == "external"


def test_completed_external_receipt_remains_readable(db, monkeypatch):
    session, owner = db
    row, workflows = _external(session, owner)
    changed = drafts.update_draft(session, owner, row.id, AgentCreationDraftUpdate(revision=row.revision, creation_method="direct"), workflows=workflows)
    request = AgentCreationDraftComplete(revision=changed.revision)
    result = drafts.complete_draft(session, owner, row.id, request, workflows=workflows)
    row.source_kind = "external"
    session.commit()
    replay = drafts.complete_draft(session, owner, row.id, request, workflows=workflows)
    assert replay.character.id == result.character.id


def test_legacy_external_adoption_requires_separate_reselection_and_preserves_media(db, tmp_path):
    session, owner = db
    row, workflows = _external(session, owner)
    row.contract_version = 1
    media = tmp_path / "retained-avatar.png"
    media.write_bytes(b"synthetic-owned-avatar")
    row.avatar_temp_url = "/media/drafts/retained-avatar.png"
    session.commit()
    adopted = drafts.adopt_legacy_draft(session, owner, row.id,
        AgentCreationDraftAdopt(revision=row.revision, target_world_id=row.target_world_id), workflows=workflows)
    assert adopted.contract_version == 2 and adopted.source_kind == "external"
    assert drafts.get_draft(session, owner, row.id, workflows=workflows).source_kind == "external"
    changed = drafts.update_draft(session, owner, row.id,
        AgentCreationDraftUpdate(revision=adopted.revision, creation_method="direct", target_world_id=row.target_world_id), workflows=workflows)
    assert changed.avatar_temp_url == adopted.avatar_temp_url
    assert row.avatar_temp_url == "/media/drafts/retained-avatar.png"
    assert changed.worldview == "Original description" and media.read_bytes() == b"synthetic-owned-avatar"
    assert row.encrypted_api_key == "private-legacy-material"


def test_foreign_owner_cannot_reselect_or_read_external_draft(db):
    session, owner = db
    row, workflows = _external(session, owner)
    stranger = User(id="stranger", display_name="Stranger")
    session.add(stranger); session.commit()
    with pytest.raises(AgentCreationDraftNotFoundError):
        drafts.update_draft(session, stranger, row.id,
            AgentCreationDraftUpdate(revision=row.revision, creation_method="direct"), workflows=workflows)
    with pytest.raises(AgentCreationDraftNotFoundError):
        drafts.get_draft(session, stranger, row.id, workflows=workflows)
    assert row.source_kind == "external" and row.name == "Preserved"
