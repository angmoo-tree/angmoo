"""Duplicate-card HTTP, privacy, rollback and optional original-file contracts."""
import asyncio
import base64
import hashlib
import io
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
from sqlalchemy import select

from test_local_creator_v2 import db
from app.config import settings
from app.domains.characters import dependencies, models, router, schemas
from app.domains.characters.service import card_import, drafts
from app.integrations.character_cards.parser import PARSER_VERSION, parse_card
from app.runtime.characters.creator import build_creator_workflows

pytestmark = pytest.mark.usefixtures("deny_external_network")


def synthetic_card(name="Original", version=2):
    return {"spec": f"chara_card_v{version}", "spec_version": f"{version}.0", "data": {
        "name": name, "description": "A synthetic observer.", "personality": "",
        "scenario": "", "first_mes": "RAW_GREETING", "mes_example": "",
        "system_prompt": "RAW_SYSTEM", "character_book": {"entries": []},
    }}


def duplicate_png(first=None, second=None):
    metadata = PngImagePlugin.PngInfo()
    for value in [first or synthetic_card(), second or synthetic_card("Other")]:
        key = "ccv3" if value["spec"] == "chara_card_v3" else "chara"
        metadata.add_text(key, base64.b64encode(json.dumps(value).encode()).decode())
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(output, "PNG", pnginfo=metadata)
    return output.getvalue()


@pytest.fixture(autouse=True)
def isolated_media(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"))


@pytest.fixture
def context(db):
    session, owner = db
    def forbidden(**kwargs):
        pytest.fail("card registration must not call an LLM")
    workflows = replace(build_creator_workflows(), run_llm=forbidden)
    draft = asyncio.run(drafts.create_draft(session, owner, schemas.AgentCreationDraftCreate(), workflows=workflows))
    return session, owner, draft, workflows


@pytest.fixture
def http(context):
    session, owner, draft, workflows = context
    application = FastAPI()
    application.include_router(router.router, prefix="/api/v1")
    application.dependency_overrides[dependencies.get_db] = lambda: session
    application.dependency_overrides[dependencies.get_current_user] = lambda: owner
    application.state.creator_workflows = lambda: workflows
    with TestClient(application) as client:
        yield client, application, context


def test_http_metadata_and_private_source_round_trip(http):
    client, app, (session, owner, draft, workflows) = http
    content = duplicate_png()
    response = client.post(f"/api/v1/agents/drafts/{draft.id}/card",
        json={"revision": 1, "data_base64": base64.b64encode(content).decode()})
    assert response.status_code == 200
    result = response.json()
    assert result["draft"]["name"] == "Original"
    assert result["metadata_selection"]["multiple_definitions"] is True
    assert result["metadata_selection"]["same_keyword_count"] == 2
    path = f"/api/v1/agents/drafts/{draft.id}/card-source"
    full = client.get(path)
    summary = client.get(path, params={"include_document": "false"})
    assert full.status_code == summary.status_code == 200
    assert full.json()["document"]["data"]["name"] == "Original"
    assert summary.json()["document"] is None
    assert summary.json()["metadata_selection"] == result["metadata_selection"]
    assert summary.json()["review"] == result["review"]
    assert summary.json()["raw_only"] == result["raw_only"]
    assert summary.json()["sha256"] == hashlib.sha256(content).hexdigest()
    assert summary.headers["cache-control"] == "private, no-store"
    assert summary.headers["x-content-type-options"] == "nosniff"
    source = session.scalar(select(models.CharacterCardSource).where(models.CharacterCardSource.draft_id == draft.id))
    assert source.source_bytes == content
    # Reading an old source through the new policy never rewrites provenance.
    source.parser_version = "angmoo-card-import-v1"
    session.commit()
    assert client.get(path).status_code == 200
    session.refresh(source)
    assert source.parser_version == "angmoo-card-import-v1" and source.source_bytes == content
    app.dependency_overrides[dependencies.get_current_user] = lambda: SimpleNamespace(id="foreign")
    assert client.get(path).status_code == client.get(path + "?include_document=false").status_code == 404
    public_fields = schemas.CharacterRead.model_fields
    assert "source_bytes" not in public_fields and "metadata_selection" not in public_fields


@pytest.mark.parametrize("case,expected", [
    ("json", "카드에 저장된 캐릭터 정보를 읽을 수 없습니다."),
    ("metadata", "이 PNG에 캐릭터 카드 정보가 없습니다."),
    ("crc", "카드 PNG 데이터가 손상되어 읽을 수 없습니다."),
    ("version", "지원하는 캐릭터 카드 형식이 아닙니다."),
])
def test_http_errors_preserve_imported_source_and_revision(http, case, expected):
    client, app, (session, owner, draft, workflows) = http
    original = duplicate_png()
    imported = card_import.import_card(session, owner, draft.id, revision=1, content=original, workflows=workflows)
    revision = imported["draft"].revision
    if case == "json":
        content = b'{"name":"one","name":"two"}'
    elif case == "metadata":
        output = io.BytesIO()
        Image.new("RGB", (2, 2)).save(output, "PNG")
        content = output.getvalue()
    elif case == "crc":
        content = bytearray(original)
        content[30] ^= 1
        content = bytes(content)
    else:
        content = json.dumps({"spec": "unknown"}).encode()
    result = client.post(f"/api/v1/agents/drafts/{draft.id}/card", json={
        "revision": revision, "data_base64": base64.b64encode(content).decode()})
    assert result.status_code == 422
    assert result.json()["detail"].startswith(expected)
    assert "RAW_" not in result.text and "source_bytes" not in result.text
    assert session.get(models.AgentCreationDraft, draft.id).revision == revision
    assert card_import.read_source(session, owner, draft.id)["sha256"] == hashlib.sha256(original).hexdigest()


def test_http_expired_foreign_and_stale_edits_keep_status(http):
    client, app, (session, owner, draft, workflows) = http
    path = f"/api/v1/agents/drafts/{draft.id}/card"
    payload = {"revision": 1, "data_base64": base64.b64encode(duplicate_png()).decode()}
    assert client.post(path, json=payload).status_code == 200
    assert client.post(path, json=payload).status_code == 409
    app.dependency_overrides[dependencies.get_current_user] = lambda: SimpleNamespace(id="foreign")
    assert client.post(path, json=payload).status_code == 404
    app.dependency_overrides[dependencies.get_current_user] = lambda: owner
    row = session.get(models.AgentCreationDraft, draft.id)
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    session.commit()
    assert client.post(path, json=payload).status_code == 410
    assert client.get(path + "-source?include_document=false").status_code == 404


def test_png_commit_failure_removes_only_new_display_file(context, monkeypatch):
    session, owner, draft, workflows = context
    original = duplicate_png()
    first = card_import.import_card(session, owner, draft.id, revision=1, content=original, workflows=workflows)
    revision = first["draft"].revision
    avatar = session.get(models.AgentCreationDraft, draft.id).avatar_temp_url
    existing = set(settings.media_root_path.rglob("*.webp"))
    def fail():
        raise RuntimeError("synthetic commit failure")
    monkeypatch.setattr(session, "commit", fail)
    with pytest.raises(RuntimeError, match="synthetic"):
        card_import.import_card(session, owner, draft.id, revision=revision,
            content=duplicate_png(synthetic_card("Replacement")), workflows=workflows)
    row = session.get(models.AgentCreationDraft, draft.id)
    assert row.revision == revision and row.avatar_temp_url == avatar
    assert set(settings.media_root_path.rglob("*.webp")) == existing
    source = session.scalar(select(models.CharacterCardSource))
    assert source.source_bytes == original


def test_partial_display_write_failure_is_compensated(context, monkeypatch):
    session, owner, draft, workflows = context
    original_write = Path.write_bytes
    def fail(path, content):
        if path.is_relative_to(settings.media_root_path):
            original_write(path, content[:8])
            raise OSError("synthetic incomplete write")
        return original_write(path, content)
    monkeypatch.setattr(Path, "write_bytes", fail)
    with pytest.raises(OSError, match="synthetic"):
        card_import.import_card(session, owner, draft.id, revision=1, content=duplicate_png(), workflows=workflows)
    assert session.get(models.AgentCreationDraft, draft.id).revision == 1
    assert session.scalar(select(models.CharacterCardSource)) is None
    assert list(settings.media_root_path.rglob("*.webp")) == []


def test_duplicate_registration_uses_edited_persona_without_raw_instructions(context):
    session, owner, draft, workflows = context
    original = duplicate_png()
    imported = card_import.import_card(session, owner, draft.id, revision=1, content=original, workflows=workflows)
    edited = drafts.update_draft(session, owner, draft.id, schemas.AgentCreationDraftUpdate(
        revision=imported["draft"].revision, name="Edited", worldview="Edited description",
        personality="", speech_style="Edited voice"), workflows=workflows)
    result = drafts.complete_draft(session, owner, draft.id,
        schemas.AgentCreationDraftComplete(revision=edited.revision), workflows=workflows)
    row = session.get(models.Character, result.character.id)
    assert row.name == "Edited" and row.worldview == "Edited description"
    assert row.personality == "" and row.speech_style == "Edited voice"
    assert "RAW_" not in row.persona_summary
    assert row.credential is None and result.settings.auto_enabled is False
    assert card_import.read_source(session, owner, draft.id)["document"]["data"]["name"] == "Original"
    assert session.scalar(select(models.CharacterCardSource)).source_bytes == original


@pytest.mark.parametrize("filename,name,worldview_length,source_hash", [
    ("main_red-69957f8d_spec_v2.png", "Red", 3362, "815c2e52205e73430cab1ae42aeef092a3e9400cecbe05c7790584d65e328b1b"),
    ("main_overprotective-father-raymond-610a34d02145_spec_v2.png", "Raymond", 6847, "d9507f310ae2c228ad23bc4e8af0f74513cbc6bdbff4173b1f58241911798bca"),
    ("main_elias-da06fb375f61_spec_v2.png", "Elias Finch", 6520, "c29ac8b9a9210af235de2e1f8081aa72a6d5f4c22c167a043dc19bf12466e23f"),
])
def test_optional_user_original_import_edit_register(context, filename, name, worldview_length, source_hash):
    directory = os.environ.get("ANGMOO_CARD_ORIGINAL_DIR")
    if not directory or not (Path(directory) / filename).is_file():
        pytest.skip("optional user originals are not provided")
    path = Path(directory) / filename
    content = path.read_bytes()
    assert hashlib.sha256(content).hexdigest() == source_hash
    session, owner, draft, workflows = context
    result = card_import.import_card(session, owner, draft.id, revision=1, content=content, workflows=workflows)
    assert result["draft"].name == name
    assert len(result["draft"].worldview) == worldview_length
    assert result["metadata_selection"]["same_keyword_count"] == 2
    assert "worldview_length_limit" not in result["review"]
    summary = card_import.read_source(session, owner, draft.id, include_document=False)
    assert summary["metadata_selection"] == result["metadata_selection"] and summary["document"] is None
    edited = drafts.update_draft(session, owner, draft.id, schemas.AgentCreationDraftUpdate(
        revision=result["draft"].revision, name=name + " edited"), workflows=workflows)
    registered = drafts.complete_draft(session, owner, draft.id,
        schemas.AgentCreationDraftComplete(revision=edited.revision), workflows=workflows)
    assert registered.character.name == name + " edited"
    source = session.scalar(select(models.CharacterCardSource))
    assert source.source_bytes == content and source.parser_version == PARSER_VERSION
    assert source.character_id == registered.character.id
    assert hashlib.sha256(path.read_bytes()).hexdigest() == source_hash
