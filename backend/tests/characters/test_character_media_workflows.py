from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.config import settings
from app.api.v1.routes import agents as mixed
from app.domains.characters import dependencies, models, router, schemas
from app.domains.characters.contracts import CharacterMediaWorkflows
from app.domains.characters.service import media, media_storage
from app.domains.identity.models import User
from app.runtime.characters import management


def _database():
    engine = create_engine("sqlite:///:memory:")
    for model in (User, models.Character, models.AgentCreationDraft,
                  models.ProfileImageQuotaReservation, models.ProfileImageCandidate):
        model.__table__.create(engine)
    return engine


def _character(db):
    owner = User(id="owner", display_name="Owner")
    character = models.Character(
        id="bird", owner_id="owner", name="Bird", handle="bird", persona_summary="Fixture bird"
    )
    db.add_all([owner, character])
    db.commit()
    return owner, character


def test_upload_callbacks_keep_session_and_commit_before_activity_log(monkeypatch):
    engine = _database()
    events = []
    with Session(engine) as db:
        owner, character = _character(db)
        event.listen(db, "after_commit", lambda session: events.append("commit"))
        def save(**kwargs):
            assert kwargs["character_id"] == character.id
            events.append("save")
            return "/media/characters/bird/new.webp"
        def invalidate(session, character_id):
            assert session is db and character_id == character.id
            events.append("invalidate")
        def log(session, **kwargs):
            assert session is db
            assert kwargs["reason"] == "user_uploaded_avatar"
            events.append("log")
        def detail(session, actual):
            assert session is db and actual is character
            events.append("detail")
            return actual
        monkeypatch.setattr(media_storage, "save_profile_media", save)
        callbacks = CharacterMediaWorkflows(invalidate, log, detail)
        result = media.upload_profile_media(
            db, owner, character.id,
            schemas.AgentProfileMediaUpload(
                media_type="avatar", filename="fixture.png", content_type="image/png", data_base64="fixture"
            ),
            workflows=callbacks,
        )
        assert result is character
        assert events == ["save", "invalidate", "commit", "log", "detail"]
        assert character.avatar_url == "/media/characters/bird/new.webp"
    engine.dispose()


def test_apply_candidate_keeps_quota_and_log_in_commit_before_file_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    image = BytesIO()
    Image.new("RGB", (8, 8), (50, 60, 70)).save(image, format="PNG")
    saved = media_storage.save_profile_image_candidate_bytes(
        user_id="owner", candidate_id="candidate", media_type="avatar",
        content_type="image/png", content=image.getvalue(),
    )
    engine = _database()
    events = []
    with Session(engine) as db:
        owner, character = _character(db)
        reservation = models.ProfileImageQuotaReservation(
            user_id=owner.id, quota_date=date(2026, 9, 5), bucket="profile_avatar",
            scope="profile", media_type="avatar", status="generated",
        )
        db.add(reservation)
        db.flush()
        candidate = models.ProfileImageCandidate(
            id="candidate", user_id=owner.id, character_id=character.id,
            quota_reservation_id=reservation.id, scope="profile", bucket="profile_avatar",
            media_type="avatar", url=saved["url"], model="fixture", route_mode="direct",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(candidate)
        db.commit()
        event.listen(db, "after_commit", lambda session: events.append("commit"))
        delete = media_storage.delete_profile_image_candidate
        def cleanup(candidate_id, user_id):
            assert events == ["invalidate", "log", "commit"]
            events.append("cleanup")
            delete(candidate_id, user_id)
        def invalidate(session, character_id):
            assert session is db and character_id == character.id
            events.append("invalidate")
        def log(session, **kwargs):
            assert session is db and reservation.status == "applied"
            assert kwargs["reason"] == "user_applied_generated_avatar"
            events.append("log")
        def detail(session, actual):
            assert session is db and actual is character
            events.append("detail")
            return actual
        monkeypatch.setattr(media_storage, "delete_profile_image_candidate", cleanup)
        result = media.apply_profile_media_candidate(
            db, owner, character.id, candidate.id,
            workflows=CharacterMediaWorkflows(invalidate, log, detail),
        )
        assert result is character
        assert events == ["invalidate", "log", "commit", "cleanup", "detail"]
        assert db.get(models.ProfileImageCandidate, "candidate") is None
        assert reservation.status == "applied"
        assert not (tmp_path / "profile-candidates" / owner.id / "candidate").exists()
        assert media.media_files.media_url_to_path(character.avatar_url).is_file()
    engine.dispose()


@pytest.mark.parametrize("kind", ["draft", "profile"])
def test_private_http_keeps_owner_dependency_file_headers_and_route_identity(tmp_path, monkeypatch, kind):
    file = tmp_path / "preview.webp"
    file.write_bytes(b"private-preview")
    owner, db, workflow = SimpleNamespace(id="owner"), object(), object()
    calls = []
    def preview(session, actual_owner, *args, **kwargs):
        calls.append((session, actual_owner, args, kwargs))
        return file, "image/webp"
    name, function, path = (
        ("get_agent_draft_media", "get_draft_media_content", "/api/v1/agents/drafts/draft/media/avatar")
        if kind == "draft" else
        ("get_agent_profile_media_candidate_content", "get_profile_candidate_content", "/api/v1/agents/bird/media-candidates/candidate/content")
    )
    monkeypatch.setattr(media, function, preview)
    assert next(r for r in mixed.router.routes if r.name == name) is next(r for r in router.router.routes if r.name == name)
    app = FastAPI()
    app.include_router(mixed.router, prefix="/api/v1")
    app.dependency_overrides[dependencies.get_current_user] = lambda: owner
    app.dependency_overrides[dependencies.get_db] = lambda: db
    app.state.creator_workflows = lambda: workflow
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200
    assert response.content == b"private-preview"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert calls[0][0] is db and calls[0][1] is owner
    assert calls[0][3] == ({"workflows": workflow} if kind == "draft" else {})


def test_both_factories_supply_same_media_runtime_callbacks():
    from app.main import create_app as hosted
    from app.public_main import create_app as local
    for factory in (hosted, local):
        request = Request({"type": "http", "app": factory()})
        callbacks = dependencies.get_character_media_workflows(request)
        assert callbacks.invalidate_visual_identity is management._invalidate_image_visual_identity_if_present
        assert callbacks.log_activity is management.agent_crud.log_activity
        assert callbacks.build_detail is management._build_agent_detail
