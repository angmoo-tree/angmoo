import base64
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.domains.characters import dependencies, models, router
from app.domains.characters.contracts import CharacterImageSettingsWorkflows
from app.domains.characters.repository import image_settings
from app.domains.identity.models import User
from app.domains.operations.models import SiteOperationSetting
from app.domains.social.models.posts import PostImageQuotaReservation
from app.domains.social.repository.media import count_service_image_quota_used


@pytest.fixture
def image_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (User, models.Character, models.AgentImageGenerationSetting,
                  SiteOperationSetting, PostImageQuotaReservation):
        model.__table__.create(engine)
    with Session(engine) as db:
        owner = User(id="image-owner", display_name="Image Owner")
        db.add(owner)
        db.flush()
        character = models.Character(id="image-bird", owner_id=owner.id, name="Bird",
                                     handle="image-bird", persona_summary="Fixture bird")
        db.add(character)
        db.commit()
        setting = image_settings.ensure_image_generation_setting(db, character.id)
        quota_reads = []

        def usage(session, *, user_id, quota_date):
            assert session is db and user_id == owner.id
            assert quota_date == datetime.now(ZoneInfo("Asia/Seoul")).date()
            quota_reads.append(setting.seed_image_url)
            return count_service_image_quota_used(session, user_id=user_id, quota_date=quota_date)

        callbacks = CharacterImageSettingsWorkflows(lambda: False, lambda model: False,
                                                   usage, ZoneInfo("Asia/Seoul"))
        app = FastAPI()
        app.state.image_settings_workflows = lambda: callbacks
        app.include_router(router.router)
        app.dependency_overrides[dependencies.get_db] = lambda: db
        app.dependency_overrides[dependencies.get_current_user] = lambda: owner
        with TestClient(app) as client:
            yield client, db, setting, quota_reads, tmp_path
    engine.dispose()


@pytest.mark.parametrize("identity_mode", ["manual", "auto"])
def test_image_seed_http_keeps_manual_identity_and_commits_real_file_lifecycle(image_owner, identity_mode):
    client, db, setting, quota_reads, media_root = image_owner
    setting.visual_identity_prompt = "Fixture character portrait"
    setting.visual_identity_source_hash = None if identity_mode == "manual" else "fixture-source-hash"
    db.commit()
    commits = []
    event.listen(db, "after_commit", lambda session: commits.append(session))
    response = client.get("/agents/image-bird/image-settings")
    assert response.status_code == 200
    assert response.json()["visual_identity_mode"] == identity_mode
    image = BytesIO()
    Image.new("RGB", (8, 8), (40, 80, 120)).save(image, format="PNG")
    response = client.post("/agents/image-bird/image-settings/seed", json={
        "filename": "seed.png", "content_type": "image/png",
        "data_base64": base64.b64encode(image.getvalue()).decode(),
    })
    assert response.status_code == 200
    expected_mode = "manual" if identity_mode == "manual" else "none"
    assert response.json()["visual_identity_mode"] == expected_mode
    url = response.json()["seed_image_url"]
    assert url == setting.seed_image_url
    stored = media_root / "characters" / "image-bird" / url.rsplit("/", 1)[-1]
    assert stored.is_file()
    with Session(db.bind) as observer:
        saved = observer.get(models.AgentImageGenerationSetting, "image-bird")
        assert saved.seed_image_url == url
        assert saved.visual_identity_source_hash is None
        assert saved.visual_identity_prompt == ("Fixture character portrait" if identity_mode == "manual" else None)
    response = client.delete("/agents/image-bird/image-settings/seed")
    assert response.status_code == 200
    assert response.json()["seed_image_url"] is None
    assert response.json()["visual_identity_mode"] == expected_mode
    assert not stored.exists()
    assert commits == [db, db]
    assert quota_reads == [None, url, None]


def test_image_settings_http_preserves_owner_and_missing_key_admission(image_owner):
    client, db, setting, quota_reads, media_root = image_owner
    assert client.get("/agents/missing/image-settings").status_code == 404
    response = client.put("/agents/image-bird/image-settings", json={"image_key_mode": "user"})
    assert response.status_code == 422
    assert "key" in response.json()["detail"]
    assert setting.image_key_mode == "disabled"
    response = client.delete("/agents/image-bird/image-settings/key")
    assert response.status_code == 200
    assert response.json()["image_key_mode"] == "disabled"
    assert response.json()["has_pollinations_api_key"] is False
    assert quota_reads == [None]
    assert list(media_root.rglob("*.webp")) == []
