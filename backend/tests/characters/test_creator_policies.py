"""Creator role extraction preserves quota, owner, error and model contracts."""
from datetime import UTC, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app import models as registered_models
from app.core.db import Base
from app.core.response_schemas import UtcInstantResponseModel
from app.domains.characters import exceptions, models, schemas
from app.domains.characters.service import access, creator, image_quota, mutations
from app.runtime.characters import creator as creator_runtime
from app.runtime.characters import management
from app.domains.routines.schemas.runs import UtcInstantResponseModel as old_response_base


@pytest.fixture
def engine(tmp_path):
    value = create_engine(f"sqlite:///{tmp_path / 'creator-roles.sqlite3'}")
    for table in (
        registered_models.User.__table__, models.Character.__table__,
        models.AgentCreationDraft.__table__,
        models.ProfileImageQuotaReservation.__table__,
        models.ProfileImageCandidate.__table__,
    ):
        table.create(value)
    with Session(value) as db:
        db.add(registered_models.User(id="owner", display_name="Owner"))
        db.commit()
    yield value
    value.dispose()


def test_creator_models_errors_and_utc_base_keep_their_identity():
    for name in ("AgentCreationDraft", "ProfileImageCandidate", "ProfileImageQuotaReservation"):
        canonical = getattr(models, name)
        assert canonical is getattr(registered_models, name)
        assert canonical.metadata is Base.metadata
    assert creator_runtime.AgentCreationDraftError is exceptions.AgentCreationDraftError
    assert management.AgentServiceError is exceptions.AgentServiceError
    assert issubclass(management.AgentAutonomyCapacityError, exceptions.AgentServiceError)
    assert old_response_base is UtcInstantResponseModel
    result = schemas.AgentPromotionUsageRead(
        promotion_usage_allowed=True,
        promotion_usage_agreed_at=datetime(2026, 9, 5, 2, 3),
    )
    assert result.promotion_usage_agreed_at == datetime(2026, 9, 5, 2, 3, tzinfo=UTC)


def test_quota_window_treats_naive_input_as_utc_and_resets_at_seoul_midnight():
    for at in (datetime(2026, 9, 4, 16), datetime(2026, 9, 4, 16, tzinfo=UTC)):
        assert image_quota._profile_image_quota_date(at).isoformat() == "2026-09-05"
        assert image_quota._profile_image_reset_at(at) == datetime(2026, 9, 6, tzinfo=ZoneInfo("Asia/Seoul"))
    with pytest.raises(exceptions.AgentCreationDraftMediaError, match="invalid_profile_image_scope"):
        image_quota._profile_image_bucket("post", "avatar")
    with pytest.raises(exceptions.AgentCreationDraftMediaError, match="invalid_profile_image_media_type"):
        image_quota._profile_image_bucket("profile", "post")


def test_reservation_commits_but_finalization_only_flushes_in_the_same_session(engine):
    owner = SimpleNamespace(id="owner")
    commits = []
    with Session(engine) as db:
        event.listen(db, "after_commit", lambda session: commits.append(session))
        reservation = image_quota._reserve_profile_image_quota(
            db, user=owner, scope="create", media_type="avatar", model="flux", route_mode="service",
        )
        reservation_id = reservation.id
        assert commits == [db]
        assert image_quota._profile_image_usage_status(db, user=owner, scope="create", media_type="avatar").remaining == 0
        assert image_quota._profile_image_usage_status(db, user=owner, scope="profile", media_type="avatar").remaining == 1
        assert image_quota._profile_image_usage_status(db, user=owner, scope="create", media_type="banner").remaining == 1
        with pytest.raises(exceptions.AgentProfileImageQuotaExceededError) as error:
            image_quota._reserve_profile_image_quota(
                db, user=owner, scope="create", media_type="avatar", model="flux", route_mode="service",
            )
        assert error.value.usage_status.remaining == 0
        image_quota._finalize_profile_image_quota(db, reservation_id=reservation_id, status="applied", candidate_id="candidate")
        assert reservation.status == "applied"
        assert commits == [db]
        db.rollback()
    with Session(engine) as db:
        stored = db.get(models.ProfileImageQuotaReservation, reservation_id)
        assert stored.status == "reserved"
        assert stored.candidate_id is None


def test_owner_admission_hides_foreign_and_deleted_characters_before_mode_gates(engine):
    with Session(engine) as db:
        character = models.Character(
            id="character", owner_id="owner", name="Bird", handle="bird",
            persona_summary="Quiet", execution_mode="local",
        )
        db.add(character)
        db.commit()
        assert access._get_owned_character(db, SimpleNamespace(id="owner"), character.id) is character
        with pytest.raises(exceptions.AgentNotFoundError):
            access._get_owned_character(db, SimpleNamespace(id="foreign"), character.id)
        with pytest.raises(exceptions.AgentExecutionModeError, match="서버 LLM"):
            access._ensure_llm_mode(character)
        character.moderation_status = "suspended"
        with pytest.raises(exceptions.AgentSuspendedError, match="character_suspended"):
            access._ensure_not_suspended(character)
        character.deleted_at = datetime.now(UTC)
        with pytest.raises(exceptions.AgentNotFoundError):
            access._get_owned_character(db, SimpleNamespace(id="owner"), character.id)


def test_creator_json_and_cooldown_keep_their_error_contract():
    assert creator._parse_json_object('```json\n{"personality":"quiet"}\n```') == {"personality": "quiet"}
    assert creator._safe_payload_text([" tea ", 2, {"ignored": True}], 30) == "tea\n2"
    with pytest.raises(exceptions.AgentCreationDraftParseError):
        creator._parse_json_object("[]")
    with pytest.raises(exceptions.AgentCreationDraftParseError):
        creator._parse_json_object("not-json")
    future = datetime(2099, 1, 1, tzinfo=UTC)
    with pytest.raises(exceptions.AgentCreationDraftCooldownError) as error:
        creator._ensure_not_in_cooldown(future)
    assert error.value.available_at is future


def test_owned_profile_mutations_preserve_commits_without_activity_or_credential_tables(engine):
    owner = SimpleNamespace(id="owner", email="owner@example.test")
    commits = []
    with Session(engine) as db:
        event.listen(db, "after_commit", lambda session: commits.append(session))
        character = mutations.create_owned_character(
            db, owner, schemas.AgentCreate(execution_mode="local", name="Bird", promotion_usage_allowed=True),
        )
        assert commits == [db, db]
        assert character.status == "inactive"
        assert character.promotion_usage_allowed is True
        assert character.promotion_usage_agreed_at is not None
        result, media_changed = mutations.update_owned_profile(
            db, owner, character.id, schemas.AgentProfileUpdate(one_liner="new", avatar_url="/media/bird.webp"),
        )
        assert result is character
        assert media_changed is True
        assert character.one_liner == "new"
        assert commits == [db, db, db]
        with pytest.raises(exceptions.AgentNotFoundError):
            mutations.update_owned_profile(
                db, SimpleNamespace(id="foreign"), character.id, schemas.AgentProfileUpdate(name="Other"),
            )
        assert len(commits) == 3
