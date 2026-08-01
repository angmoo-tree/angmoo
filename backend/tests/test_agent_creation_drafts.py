import asyncio
import base64
from datetime import UTC, datetime, timedelta
import json
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app import models, schemas
from app.services import agent_creation_drafts as draft_service


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFUlEQVR4nGP8z8Dwn4GBgYEJRIAwAB8XAgICR7MUAAAAAElFTkSuQmCC"
)


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        del size
        if getattr(self, "_read", False):
            return b""
        self._read = True
        return json.dumps(self._payload).encode("utf-8")


def _create_draft_media_tables(engine) -> None:
    for table in (
        models.User.__table__,
        models.SiteOperationSetting.__table__,
        models.Character.__table__,
        models.AgentCreationDraft.__table__,
        models.ProfileImageQuotaReservation.__table__,
        models.ProfileImageCandidate.__table__,
    ):
        table.create(engine)


def _create_profile_media_tables(engine) -> None:
    for table in (
        models.User.__table__,
        models.SiteOperationSetting.__table__,
        models.Character.__table__,
        models.ProfileImageQuotaReservation.__table__,
        models.ProfileImageCandidate.__table__,
    ):
        table.create(engine)


def _add_user(db: Session, user_id: str = "user-1") -> models.User:
    user = models.User(id=user_id, display_name=user_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _add_draft(db: Session, user: models.User) -> models.AgentCreationDraft:
    draft = models.AgentCreationDraft(
        id="draft-1",
        user_id=user.id,
        provider="google",
        model="gemini-3.1-flash-lite",
        encrypted_api_key="encrypted",
        name="Draft Agent",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def _add_character(db: Session, user: models.User) -> models.Character:
    character = models.Character(
        id="char-1",
        owner_id=user.id,
        name="Profile Agent",
        handle="profile-agent",
        persona_summary="test",
        execution_mode="llm",
    )
    db.add(character)
    db.commit()
    db.refresh(character)
    return character


def _install_model_list(monkeypatch, models_payload: object) -> None:
    draft_service._POLLINATIONS_MODEL_CHECKED_AT.clear()
    monkeypatch.setattr(
        draft_service,
        "_open_pollinations_request",
        lambda request, timeout: _FakeResponse(models_payload),
    )


def _model_payload(
    model: str = "flux", *, paid_only: bool = False
) -> list[dict[str, object]]:
    return [
        {
            "name": model,
            "paid_only": paid_only,
            "input_modalities": ["text"],
            "output_modalities": ["image"],
        }
    ]


def _set_free_image_model(db: Session, model: str) -> None:
    db.merge(
        models.SiteOperationSetting(
            key="pollinations_free_image_model",
            value=model,
            updated_at=datetime.now(UTC),
        )
    )
    db.commit()


def _set_profile_image_model(db: Session, model: str) -> None:
    db.merge(
        models.SiteOperationSetting(
            key="pollinations_profile_image_model",
            value=model,
            updated_at=datetime.now(UTC),
        )
    )
    db.commit()


def _set_profile_image_route(db: Session, mode: str) -> None:
    db.merge(
        models.SiteOperationSetting(
            key="pollinations_profile_image_route_mode",
            value=mode,
            updated_at=datetime.now(UTC),
        )
    )
    db.commit()


def _install_profile_image_key(monkeypatch) -> None:
    monkeypatch.setattr(
        draft_service.service_image_key,
        "get_profile_image_api_key",
        lambda: "sk_profile_test",
    )
    monkeypatch.setattr(
        draft_service.service_image_key,
        "is_profile_image_available",
        lambda: True,
    )


def _install_generated_image(monkeypatch, calls: list[dict[str, object]]) -> None:
    async def fake_generate_image(**kwargs):
        calls.append(kwargs)
        return draft_service.pollinations_image.PollinationsGeneratedImage(
            content_type="image/png",
            content=PNG_BYTES,
            fallback_used=False,
        )

    monkeypatch.setattr(draft_service.pollinations_image, "generate_image", fake_generate_image)


def test_free_pollinations_url_uses_flux_without_key() -> None:
    url = draft_service._build_pollinations_image_url(
        base_url=draft_service.POLLINATIONS_LEGACY_IMAGE_URL,
        model="flux",
        prompt="a cheerful portrait",
        media_type="avatar",
        seed=123,
    )

    query = parse_qs(urlparse(url).query)
    assert query["model"] == ["flux"]
    assert query["width"] == ["768"]
    assert query["height"] == ["768"]
    assert query["nologo"] == ["true"]
    assert query["enhance"] == ["true"]
    assert "key" not in query


def test_draft_media_seed_stays_within_pollinations_limit(monkeypatch) -> None:
    monkeypatch.setattr(
        draft_service.security,
        "hash_token",
        lambda value: "ffffffff" + ("0" * 56),
    )

    seed = draft_service._draft_media_seed("draft-1", "avatar")

    assert seed == draft_service.POLLINATIONS_MAX_SEED


def test_avatar_pollinations_prompt_enforces_front_facing_composition() -> None:
    prompt = draft_service._build_pollinations_prompt(
        style="애니메풍",
        appearance="silver-haired man",
        media_type="avatar",
    )

    assert "cinematic anime style" in prompt
    assert "silver-haired man" in prompt
    assert "front-facing avatar portrait" in prompt
    assert "looking directly at the camera" in prompt
    assert "both eyes visible" in prompt
    assert "centered face" in prompt
    assert "head and shoulders visible" in prompt
    assert "symmetrical composition" in prompt
    assert "no side profile" in prompt
    assert "no back view" in prompt
    assert "no text" in prompt


def test_banner_pollinations_prompt_does_not_use_avatar_composition() -> None:
    prompt = draft_service._build_pollinations_prompt(
        style="애니메풍",
        appearance="silver-haired man",
        media_type="banner",
    )

    assert "wide banner composition" in prompt
    assert "atmospheric background" in prompt
    assert "front-facing avatar portrait" not in prompt
    assert "looking directly at the camera" not in prompt
    assert "no side profile" not in prompt


def test_generate_media_creates_server_candidate_and_consumes_daily_quota(
    monkeypatch,
    tmp_path,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_draft_media_tables(engine)
    monkeypatch.setattr(draft_service.settings, "MEDIA_ROOT", str(tmp_path))
    _install_profile_image_key(monkeypatch)
    calls: list[dict[str, object]] = []
    _install_generated_image(monkeypatch, calls)

    with Session(engine) as db:
        user = _add_user(db)
        _set_profile_image_model(db, "zimage")
        _set_profile_image_route(db, "lambda")
        _add_draft(db, user)

        result = asyncio.run(
            draft_service.generate_media(
                db,
                user,
                "draft-1",
                schemas.AgentCreationDraftGenerateMediaCreate(
                    appearance_prompt="short black hair and warm brown eyes",
                    media_type="avatar",
                    delivery="server",
                ),
            )
        )
        retry = asyncio.run(
            draft_service.generate_media(
                db,
                user,
                "draft-1",
                schemas.AgentCreationDraftGenerateMediaCreate(
                    appearance_prompt="short black hair and warm brown eyes",
                    media_type="avatar",
                    delivery="server",
                ),
            )
        )

    assert len(result.results) == 1
    media_result = result.results[0]
    assert media_result.ok is True
    assert media_result.candidate_id is not None
    assert media_result.candidate_url is not None
    assert media_result.candidate_url.startswith(
        "/api/v1/agents/drafts/draft-1/media-candidates/"
    )
    assert media_result.candidate_url.endswith("/content")
    assert media_result.usage_status is not None
    assert media_result.usage_status.bucket == "create_avatar"
    assert media_result.usage_status.used_today == 1
    assert media_result.usage_status.remaining == 0
    assert len(calls) == 1
    assert calls[0]["api_key"] == "sk_profile_test"
    assert calls[0]["model"] == "zimage"
    assert calls[0]["route_mode"] == "lambda"
    assert calls[0]["width"] == 768
    assert calls[0]["height"] == 768
    assert retry.results[0].ok is False
    assert retry.results[0].error == "profile_image_daily_limit_exceeded"
    assert retry.results[0].usage_status is not None
    assert retry.results[0].usage_status.next_available_at is not None


def test_profile_image_quota_exceeded_skips_translation_and_pollinations(
    monkeypatch,
    tmp_path,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_draft_media_tables(engine)
    monkeypatch.setattr(draft_service.settings, "MEDIA_ROOT", str(tmp_path))
    _install_profile_image_key(monkeypatch)
    monkeypatch.setattr(
        draft_service,
        "_translate_image_prompt_to_english",
        lambda _text: pytest.fail("translator must not be called after quota is exhausted"),
    )

    async def fail_generate_image(**_kwargs):
        pytest.fail("Pollinations must not be called after quota is exhausted")

    monkeypatch.setattr(draft_service.pollinations_image, "generate_image", fail_generate_image)

    with Session(engine) as db:
        user = _add_user(db)
        _add_draft(db, user)
        db.add(
                models.ProfileImageQuotaReservation(
                    user_id=user.id,
                    quota_date=draft_service._profile_image_quota_date(datetime.now(UTC)),
                    bucket="create_avatar",
                    scope="create",
                    media_type="avatar",
                status="generated",
            )
        )
        db.commit()

        result = asyncio.run(
            draft_service.generate_media(
                db,
                user,
                "draft-1",
                schemas.AgentCreationDraftGenerateMediaCreate(
                    appearance_prompt="검은 머리와 갈색 눈",
                    media_type="avatar",
                    delivery="server",
                ),
            )
        )

    assert result.results[0].ok is False
    assert result.results[0].error == "profile_image_daily_limit_exceeded"


def test_apply_draft_media_candidate_promotes_and_cleans_candidate(
    monkeypatch,
    tmp_path,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_draft_media_tables(engine)
    monkeypatch.setattr(draft_service.settings, "MEDIA_ROOT", str(tmp_path))
    _install_profile_image_key(monkeypatch)
    calls: list[dict[str, object]] = []
    _install_generated_image(monkeypatch, calls)

    with Session(engine) as db:
        user = _add_user(db)
        _add_draft(db, user)
        result = asyncio.run(
            draft_service.generate_media(
                db,
                user,
                "draft-1",
                schemas.AgentCreationDraftGenerateMediaCreate(
                    appearance_prompt="short black hair and warm brown eyes",
                    media_type="avatar",
                    delivery="server",
                ),
            )
        )
        candidate_id = result.results[0].candidate_id
        assert candidate_id is not None
        candidate = db.get(models.ProfileImageCandidate, candidate_id)
        assert candidate is not None
        candidate_path = draft_service.profile_media.media_url_to_path(candidate.url)
        assert candidate_path.is_file()

        draft_read = draft_service.apply_draft_media_candidate(
            db,
            user,
            "draft-1",
            candidate_id,
        )

        reservation = db.get(models.ProfileImageQuotaReservation, 1)
        assert draft_read.avatar_temp_url is not None
        assert draft_read.avatar_temp_url == "/api/v1/agents/drafts/draft-1/media/avatar"
        assert reservation is not None
        assert reservation.status == "applied"
        assert reservation.candidate_id == candidate_id
        assert db.get(models.ProfileImageCandidate, candidate_id) is None
        assert not candidate_path.exists()


def test_cleanup_expired_drafts_removes_profile_image_candidates(
    monkeypatch,
    tmp_path,
) -> None:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    _create_draft_media_tables(engine)
    monkeypatch.setattr(draft_service.settings, "MEDIA_ROOT", str(tmp_path))
    now = datetime.now(UTC)

    with Session(engine) as db:
        user = _add_user(db)
        db.add_all(
            [
                models.AgentCreationDraft(
                    id="draft-expired",
                    user_id=user.id,
                    provider="google",
                    model="gemini-3.1-flash-lite",
                    encrypted_api_key="encrypted",
                    name="Expired Draft",
                    expires_at=now - timedelta(minutes=5),
                ),
                models.AgentCreationDraft(
                    id="draft-active",
                    user_id=user.id,
                    provider="google",
                    model="gemini-3.1-flash-lite",
                    encrypted_api_key="encrypted",
                    name="Active Draft",
                    expires_at=now + timedelta(hours=1),
                ),
            ]
        )
        candidate_paths = {}
        for candidate_id, draft_id in (
            ("profile-candidate-expired", "draft-expired"),
            ("profile-candidate-active", "draft-active"),
        ):
            candidate_dir = tmp_path / "profile-candidates" / user.id / candidate_id
            candidate_dir.mkdir(parents=True)
            candidate_path = candidate_dir / "avatar.webp"
            candidate_path.write_bytes(b"candidate")
            candidate_paths[candidate_id] = candidate_path
            db.add(
                models.ProfileImageCandidate(
                    id=candidate_id,
                    user_id=user.id,
                    draft_id=draft_id,
                    scope="create",
                    bucket="create_avatar",
                    media_type="avatar",
                    url=f"/media/profile-candidates/{user.id}/{candidate_id}/avatar.webp",
                    content_type="image/webp",
                    byte_size=9,
                    width=1,
                    height=1,
                    model="zimage",
                    route_mode="lambda",
                    expires_at=now + timedelta(hours=1),
                )
            )
        db.commit()

        draft_service._cleanup_expired_drafts(db)

        assert db.get(models.AgentCreationDraft, "draft-expired") is None
        assert db.get(models.ProfileImageCandidate, "profile-candidate-expired") is None
        assert not candidate_paths["profile-candidate-expired"].exists()
        assert db.get(models.AgentCreationDraft, "draft-active") is not None
        assert db.get(models.ProfileImageCandidate, "profile-candidate-active") is not None
        assert candidate_paths["profile-candidate-active"].exists()


def test_generate_profile_media_creates_profile_candidate(
    monkeypatch,
    tmp_path,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_profile_media_tables(engine)
    monkeypatch.setattr(draft_service.settings, "MEDIA_ROOT", str(tmp_path))
    _install_profile_image_key(monkeypatch)
    calls: list[dict[str, object]] = []
    _install_generated_image(monkeypatch, calls)

    with Session(engine) as db:
        user = _add_user(db)
        _set_profile_image_model(db, "flux")
        _set_profile_image_route(db, "direct")
        character = _add_character(db, user)

        result = asyncio.run(
            draft_service.generate_profile_media(
                db,
                user,
                character.id,
                schemas.AgentProfileMediaGenerateCreate(
                    appearance_prompt="long silver hair and a blue coat",
                    media_type="banner",
                    delivery="server",
                ),
            )
        )

    assert len(result.results) == 1
    media_result = result.results[0]
    assert media_result.ok is True
    assert media_result.candidate_id is not None
    assert media_result.candidate_url is not None
    assert media_result.usage_status is not None
    assert media_result.usage_status.bucket == "profile_banner"
    assert media_result.usage_status.used_today == 1
    assert media_result.usage_status.remaining == 0
    assert calls[0]["model"] == "flux"
    assert calls[0]["route_mode"] == "direct"
    assert calls[0]["width"] == 1024
    assert calls[0]["height"] == 384


def test_profile_image_quota_resets_by_kst_date(monkeypatch, tmp_path) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_draft_media_tables(engine)
    monkeypatch.setattr(draft_service.settings, "MEDIA_ROOT", str(tmp_path))
    _install_profile_image_key(monkeypatch)
    calls: list[dict[str, object]] = []
    _install_generated_image(monkeypatch, calls)

    with Session(engine) as db:
        user = _add_user(db)
        _add_draft(db, user)
        db.add(
                models.ProfileImageQuotaReservation(
                    user_id=user.id,
                    quota_date=(
                        draft_service._profile_image_quota_date(datetime.now(UTC))
                        - timedelta(days=1)
                    ),
                    bucket="create_avatar",
                    scope="create",
                    media_type="avatar",
                status="generated",
            )
        )
        db.commit()

        result = asyncio.run(
            draft_service.generate_media(
                db,
                user,
                "draft-1",
                schemas.AgentCreationDraftGenerateMediaCreate(
                    appearance_prompt="short black hair and warm brown eyes",
                    media_type="avatar",
                    delivery="server",
                ),
            )
        )

    assert result.results[0].ok is True
    assert result.results[0].usage_status is not None
    assert result.results[0].usage_status.used_today == 1
    assert len(calls) == 1


def test_pollinations_flux_availability_check_accepts_text_to_image(monkeypatch) -> None:
    _install_model_list(monkeypatch, _model_payload("flux"))

    draft_service._ensure_pollinations_model_available("flux")

    assert "flux" in draft_service._POLLINATIONS_MODEL_CHECKED_AT


def test_pollinations_flux_availability_check_rejects_paid_only(monkeypatch) -> None:
    _install_model_list(monkeypatch, _model_payload("flux", paid_only=True))

    with pytest.raises(draft_service.AgentCreationDraftMediaError):
        draft_service._ensure_pollinations_model_available("flux")


def test_pollinations_flux_availability_check_rejects_missing_model(monkeypatch) -> None:
    _install_model_list(monkeypatch, [])

    with pytest.raises(draft_service.AgentCreationDraftMediaError):
        draft_service._ensure_pollinations_model_available("flux")


def test_pollinations_availability_cache_is_model_specific(monkeypatch) -> None:
    calls: list[str] = []
    payloads = {
        "flux": _model_payload("flux"),
        "zimage": _model_payload("zimage"),
    }
    draft_service._POLLINATIONS_MODEL_CHECKED_AT.clear()

    def fake_urlopen(request, timeout):
        model = "zimage" if calls else "flux"
        calls.append(model)
        return _FakeResponse(payloads[model])

    monkeypatch.setattr(draft_service, "_open_pollinations_request", fake_urlopen)

    draft_service._ensure_pollinations_model_available("flux")
    draft_service._ensure_pollinations_model_available("zimage")

    assert calls == ["flux", "zimage"]
    assert set(draft_service._POLLINATIONS_MODEL_CHECKED_AT) == {"flux", "zimage"}
