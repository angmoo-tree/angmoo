from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from model_fixture_support import models as registered_models  # noqa: F401 - explicit registry is G5
from app.models import Base
from app.domains.characters.models import Character
from app.domains.identity.models import User
from app.domains.character_lore import models
from app.domains.character_lore.constants import EMBEDDING_DIMENSION
from app.domains.character_lore.dependencies import get_current_user, get_db
from app.domains.character_lore.service import documents
from app.runtime.character_lore import build_lore_workflows


@pytest.fixture
def context():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(
            id="lore-owner",
            display_name="Lore owner",
            password_hash="unused",
            privacy_policy_version="test",
            terms_version="test",
        )
        character = Character(
            id="lore-character",
            owner_id=user.id,
            name="Lore character",
            handle="lore-character",
            status="inactive",
            persona_summary="memo",
        )
        db.add_all([user, character])
        db.commit()
        yield db, user, character
    engine.dispose()


def test_upload_duplicate_and_rebuild_keep_session_commit_and_embedding_reuse(
    context, monkeypatch
):
    db, user, character = context
    base = build_lore_workflows()
    looked_up, embedded, writes = [], [], []

    def lookup(session, character_id):
        looked_up.append((session, character_id))
        return base.get_character(session, character_id)

    def embed(api_key, text):
        embedded.append((api_key, text))
        return [0.25] * EMBEDDING_DIMENSION

    def key(session, character_id):
        assert session is db and character_id == character.id
        return "test-material"

    workflows = replace(base, get_character=lookup, api_key=key, embed_text=embed)
    original_commit, original_refresh = db.commit, db.refresh

    def commit():
        writes.append("commit")
        original_commit()

    def refresh(instance, *args, **kwargs):
        writes.append(("refresh", type(instance)))
        return original_refresh(instance, *args, **kwargs)

    monkeypatch.setattr(db, "commit", commit)
    monkeypatch.setattr(db, "refresh", refresh)
    arguments = dict(
        filename="memo.txt",
        content_type="text/plain",
        file_bytes=b"A quiet memory.",
        workflows=workflows,
    )
    uploaded = documents.upload_lore_source(db, user, character.id, **arguments)
    assert uploaded.status == "ready"
    assert writes == ["commit", ("refresh", models.CharacterLoreSource)]
    assert len(embedded) == 1
    writes.clear()
    duplicate = documents.upload_lore_source(db, user, character.id, **arguments)
    assert duplicate.id == uploaded.id
    assert writes == [] and len(embedded) == 1
    rebuilt = documents.rebuild_lore_source(
        db, user, character.id, uploaded.id, workflows=workflows
    )
    assert rebuilt.status == "ready" and rebuilt.chunk_count == 1
    assert len(embedded) == 1
    assert writes == ["commit", ("refresh", models.CharacterLoreSource)]
    assert looked_up == [(db, character.id)] * 3


def test_failed_embedding_is_saved_and_empty_scope_skips_provider(context):
    db, user, character = context
    calls = []

    def fail_embed(api_key, text):
        calls.append((api_key, text))
        raise RuntimeError("embedding failed")

    workflows = replace(
        build_lore_workflows(),
        api_key=lambda session, character_id: "test-material",
        embed_text=fail_embed,
    )
    result = documents.upload_lore_source(
        db,
        user,
        character.id,
        filename="memo.txt",
        content_type="text/plain",
        file_bytes=b"A quiet memory.",
        workflows=workflows,
    )
    source = db.get(models.CharacterLoreSource, result.id)
    assert source is not None and source.status == "embedding_failed"
    assert source.chunks[0].error_message == "embedding failed"
    assert len(calls) == 1
    empty_scope = documents.retrieve_lore_for_query(
        db,
        character=SimpleNamespace(id="another-character"),
        query="memory",
        workflows=workflows,
    )
    assert empty_scope.mode == "fallback_no_lore"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "profile", ["full", "public"], ids=["full", "public"]
)
def test_both_factories_wire_lore_same_session_and_original_authentication(
    context, profile
):
    from app import main

    db, user, character = context
    factory = main.create_app if profile == "full" else main.create_public_app
    application = factory(
        **(
            {"prepare_media_directories": False}
            if profile == "public"
            else {}
        )
    )
    original = application.state.lore_workflows()
    observed = []

    def lookup(session, character_id):
        observed.append((session, character_id))
        return original.get_character(session, character_id)

    application.state.lore_workflows = lambda: replace(original, get_character=lookup)
    application.dependency_overrides[get_db] = lambda: db
    application.dependency_overrides[get_current_user] = lambda: user
    response = TestClient(application).get(f"/api/v1/agents/{character.id}/lore-status")
    assert response.status_code == 200
    assert response.json()["source_count"] == 0
    assert observed == [(db, character.id)]
    from app.api.identity_dependencies import get_current_user as canonical_auth

    assert get_current_user is canonical_auth
