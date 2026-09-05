from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.runtime.characters import creator as draft_service
from app.runtime.characters import management as agent_service


def _create_tables(engine) -> None:
    for table in (
        models.User.__table__,
        models.Character.__table__,
        models.CharacterActiveWorld.__table__,
        models.CharacterState.__table__,
        models.Post.__table__,
        models.PostMedia.__table__,
        models.PostImageQuotaReservation.__table__,
        models.LlmCredential.__table__,
        models.AgentRun.__table__,
        models.AgentActivitySetting.__table__,
        models.AgentImageGenerationSetting.__table__,
        models.AgentSlot.__table__,
        models.AgentActivityLog.__table__,
        models.AgentFeedCue.__table__,
        models.SiteOperationBanner.__table__,
        models.SiteOperationSetting.__table__,
        models.AgentCreationDraft.__table__,
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


def _create_local_agent(
    db: Session,
    user: models.User,
    *,
    name: str = "Local Agent",
    promotion_usage_allowed: bool = False,
) -> schemas.AgentDetailRead:
    return agent_service.create_agent(
        db,
        user,
        schemas.AgentCreate(
            execution_mode="local",
            name=name,
            one_liner="",
            personality="",
            speech_style="",
            worldview="",
            topic_preferences="",
            safety_rules="",
            promotion_usage_allowed=promotion_usage_allowed,
        ),
    )


def test_create_agent_defaults_promotion_usage_to_false() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)

    with Session(engine) as db:
        user = _add_user(db)

        detail = _create_local_agent(db, user)

        character = db.get(models.Character, detail.character.id)
        assert character is not None
        assert detail.promotion_usage.promotion_usage_allowed is False
        assert character.promotion_usage_allowed is False
        assert character.promotion_usage_agreed_at is None
        assert character.promotion_usage_revoked_at is None
        assert character.promotion_usage_policy_version is None


def test_create_agent_records_promotion_usage_consent() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)

    with Session(engine) as db:
        user = _add_user(db)

        detail = _create_local_agent(db, user, promotion_usage_allowed=True)

        character = db.get(models.Character, detail.character.id)
        assert character is not None
        assert detail.promotion_usage.promotion_usage_allowed is True
        assert character.promotion_usage_allowed is True
        assert character.promotion_usage_agreed_at is not None
        assert character.promotion_usage_revoked_at is None
        assert character.promotion_usage_policy_version == "2026-06-25"


def test_complete_draft_records_promotion_usage_consent(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)

    monkeypatch.setattr(
        draft_service,
        "_decrypt_draft_api_key",
        lambda draft: "test-api-key",
    )
    monkeypatch.setattr(
        draft_service.profile_media,
        "delete_draft_media",
        lambda draft_id: None,
    )

    with Session(engine) as db:
        user = _add_user(db)
        db.add(
            models.AgentCreationDraft(
                id="draft-1",
                user_id=user.id,
                provider="google",
                model="gemini-3.1-flash-lite",
                encrypted_api_key="encrypted",
                name="Draft Agent",
                one_liner="draft",
                personality="quiet and kind",
                speech_style="plain",
                worldview="test world",
                topic_preferences="tests",
                safety_rules="be safe",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        db.commit()

        detail = draft_service.complete_draft(
            db,
            user,
            "draft-1",
            schemas.AgentCreationDraftComplete(promotion_usage_allowed=True),
        )

        character = db.get(models.Character, detail.character.id)
        assert character is not None
        assert character.promotion_usage_allowed is True
        assert character.promotion_usage_agreed_at is not None
        assert character.promotion_usage_revoked_at is None
        assert character.promotion_usage_policy_version == "2026-06-25"
        assert db.scalar(select(models.AgentCreationDraft)) is None


def test_update_promotion_usage_tracks_revocation_and_regrant() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)

    with Session(engine) as db:
        user = _add_user(db)
        detail = _create_local_agent(db, user)

        agreed = agent_service.update_promotion_usage(
            db,
            user,
            detail.character.id,
            schemas.AgentPromotionUsageUpdate(promotion_usage_allowed=True),
        )
        first_agreed_at = agreed.promotion_usage.promotion_usage_agreed_at
        assert agreed.promotion_usage.promotion_usage_allowed is True
        assert first_agreed_at is not None
        assert agreed.promotion_usage.promotion_usage_revoked_at is None

        revoked = agent_service.update_promotion_usage(
            db,
            user,
            detail.character.id,
            schemas.AgentPromotionUsageUpdate(promotion_usage_allowed=False),
        )
        revoked_at = revoked.promotion_usage.promotion_usage_revoked_at
        assert revoked.promotion_usage.promotion_usage_allowed is False
        assert revoked.promotion_usage.promotion_usage_agreed_at == first_agreed_at
        assert revoked_at is not None

        regranted = agent_service.update_promotion_usage(
            db,
            user,
            detail.character.id,
            schemas.AgentPromotionUsageUpdate(promotion_usage_allowed=True),
        )
        assert regranted.promotion_usage.promotion_usage_allowed is True
        assert regranted.promotion_usage.promotion_usage_revoked_at is None
        assert regranted.promotion_usage.promotion_usage_agreed_at is not None
        assert regranted.promotion_usage.promotion_usage_agreed_at != first_agreed_at
        assert (
            regranted.promotion_usage.promotion_usage_policy_version
            == "2026-06-25"
        )


def test_update_promotion_usage_requires_owner() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)

    with Session(engine) as db:
        owner = _add_user(db, "owner")
        other = _add_user(db, "other")
        detail = _create_local_agent(db, owner)

        with pytest.raises(agent_service.AgentNotFoundError):
            agent_service.update_promotion_usage(
                db,
                other,
                detail.character.id,
                schemas.AgentPromotionUsageUpdate(promotion_usage_allowed=True),
            )
