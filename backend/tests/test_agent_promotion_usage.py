from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.domains.characters.schemas as schemas
from model_fixture_support import models
from app.runtime.characters import creator as draft_service
from app.runtime.characters import management as agent_service


def _create_tables(engine) -> None:
    for table in (
        models.User.__table__,
        models.LocalEnvironment.__table__,
        models.EnvironmentTimezoneChange.__table__,
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


def test_complete_draft_records_promotion_usage_consent() -> None:
    """Keyless registration retains its receipt; consent is an explicit later edit."""
    from app.runtime.persistence.model_registration import register_models
    from app.domains.identity.models import InstallationIdentity
    from app.domains.worlds.service.default_space import ensure_default_space

    engine = create_engine("sqlite:///:memory:")
    register_models().create_all(engine)
    with Session(engine) as db:
        user = _add_user(db)
        db.add(InstallationIdentity(singleton_key="local-installation", installation_id="fixture",
            owner_user_id=user.id, bootstrap_state="claimed", claimed_at=datetime.now(UTC)))
        db.commit()
        world = ensure_default_space(db, owner_id=user.id)
        draft = models.AgentCreationDraft(id="draft-consent", user_id=user.id, contract_version=2,
            target_world_id=world.id, provider="google", model="gemini-3.1-flash-lite",
            name="Draft Agent", worldview="A quiet and kind test character.",
            expires_at=datetime.now(UTC) + timedelta(hours=1))
        db.add(draft)
        db.commit()
        with pytest.raises(draft_service.AgentCreationDraftValidationError, match="등록 후"):
            draft_service.complete_draft(db, user, draft.id,
                schemas.AgentCreationDraftComplete(revision=draft.revision, promotion_usage_allowed=True))
        detail = draft_service.complete_draft(db, user, draft.id,
            schemas.AgentCreationDraftComplete(revision=draft.revision))
        assert detail.promotion_usage.promotion_usage_allowed is False
        detail = agent_service.update_promotion_usage(db, user, detail.character.id,
            schemas.AgentPromotionUsageUpdate(promotion_usage_allowed=True))
        character = db.get(models.Character, detail.character.id)
        assert character is not None
        assert detail.promotion_usage.promotion_usage_allowed is True
        assert character.promotion_usage_allowed is True
        assert character.promotion_usage_agreed_at is not None
        assert character.promotion_usage_revoked_at is None
        assert character.promotion_usage_policy_version == "2026-06-25"
        retained = db.get(models.AgentCreationDraft, draft.id)
        assert retained is not None and retained.status == "completed"


def test_complete_legacy_draft_requires_adoption_without_consuming_consent(monkeypatch) -> None:
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

        # V1 drafts require explicit adoption under the existing keyless creator
        # contract. Consent updates on registered characters are covered below.
        with pytest.raises(draft_service.AgentCreationDraftValidationError, match="이전 초안"):
            draft_service.complete_draft(db, user, "draft-1",
                schemas.AgentCreationDraftComplete(promotion_usage_allowed=True))
        assert db.scalar(select(models.Character)) is None
        retained = db.get(models.AgentCreationDraft, "draft-1")
        assert retained is not None and retained.encrypted_api_key == "encrypted"


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
