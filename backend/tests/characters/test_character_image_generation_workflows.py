import asyncio
from types import SimpleNamespace

from fastapi import Request
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.domains.characters import dependencies, exceptions, models
from app.domains.characters.contracts import CharacterImageGenerationWorkflows
from app.domains.characters.service import image_generation
from app.domains.identity.models import User
from app.integrations import image_provider, pollinations_image, replicate_image
from app.runtime.characters import creator


def _engine():
    engine = create_engine("sqlite:///:memory:")
    for model in (User, models.Character, models.AgentCreationDraft,
                  models.ProfileImageQuotaReservation, models.ProfileImageCandidate):
        model.__table__.create(engine)
    return engine


def _workflows(key="fixture-key"):
    return CharacterImageGenerationWorkflows(
        get_model=lambda db: "fixture-model", get_route_mode=lambda db: "direct",
        image_key_available=lambda model: key is not None,
        resolve_api_key=lambda model: key, translate_prompt=lambda text: text,
    )


@pytest.mark.parametrize("failure", ["pollinations", "replicate", "storage"])
def test_failed_generation_commits_failed_quota_once_without_candidate(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    calls = []
    async def generate(**kwargs):
        calls.append(kwargs)
        if failure == "pollinations":
            raise pollinations_image.PollinationsImageError("failed", failure_class="provider_unavailable")
        if failure == "replicate":
            raise replicate_image.ReplicateImageError("failed", failure_class="provider_unavailable")
        return SimpleNamespace(content_type="image/png", content=b"invalid-image")
    monkeypatch.setattr(image_provider, "generate_image", generate)
    engine = _engine()
    with Session(engine) as db:
        owner = User(id="owner", display_name="Owner")
        db.add(owner)
        db.commit()
        with pytest.raises(exceptions.AgentCreationDraftMediaError) as error:
            asyncio.run(image_generation._generate_profile_image_candidate(
                db, user=owner, scope="create", media_type="avatar", prompt="fixture",
                seed=1, model="fixture-model", route_mode="direct", draft_id=None,
                character_id=None, workflows=_workflows(),
            ))
        assert str(error.value) == ("candidate_storage_failed" if failure == "storage" else "provider_unavailable")
        assert len(calls) == 1
        assert calls[0]["log_context"]["scope"] == "create"
        assert list(db.scalars(select(models.ProfileImageCandidate))) == []
    with Session(engine) as observer:
        reservations = list(observer.scalars(select(models.ProfileImageQuotaReservation)))
        assert len(reservations) == 1
        assert reservations[0].status == "failed"
        assert reservations[0].candidate_id is None
    engine.dispose()


def test_missing_service_key_does_not_reserve_quota_or_call_provider(monkeypatch):
    async def forbidden(**kwargs):
        pytest.fail("provider must not run without a service key")
    monkeypatch.setattr(image_provider, "generate_image", forbidden)
    engine = _engine()
    with Session(engine) as db:
        owner = User(id="owner", display_name="Owner")
        db.add(owner)
        db.commit()
        with pytest.raises(exceptions.AgentCreationDraftMediaError, match="profile_image_key_unavailable"):
            asyncio.run(image_generation._generate_profile_image_candidate(
                db, user=owner, scope="create", media_type="avatar", prompt="fixture",
                seed=1, model="fixture-model", route_mode="direct", draft_id=None,
                character_id=None, workflows=_workflows(None),
            ))
        assert list(db.scalars(select(models.ProfileImageQuotaReservation))) == []
    engine.dispose()


def test_both_factories_bind_original_settings_key_and_translation_callbacks():
    from app.main import create_app as hosted
    from app.public_main import create_app as local
    for factory in (hosted, local):
        request = Request({"type": "http", "app": factory()})
        workflows = dependencies.get_image_generation_workflows(request)
        assert workflows.get_model is creator.operation_settings.get_pollinations_profile_image_model
        assert workflows.get_route_mode is creator.operation_settings.get_pollinations_profile_image_route_mode
        assert workflows.translate_prompt is creator._translate_image_prompt_to_english
        assert workflows.resolve_api_key is creator._resolve_profile_image_api_key
