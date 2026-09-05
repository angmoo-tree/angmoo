from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import main, models, public_main
from app.config import settings
from app.core.db import Base
from app.domains.identity import dependencies, schemas
from app.domains.identity.service import auth
from app.runtime import account_deletion


@pytest.mark.parametrize("factory", [main.create_app, public_main.create_app])
def test_app_factory_supplies_the_runtime_account_deletion_workflow(factory) -> None:
    application = factory()
    request = Request({"type": "http", "app": application})
    assert dependencies.get_account_deletion_workflow(request) is account_deletion.delete_current_user_account


def test_identity_admission_and_real_deletion_share_the_session_and_one_commit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "AGENT_ACTIVITY_ENGINE", "langgraph")
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = models.User(
            id="identity-uow-owner", email="identity-uow@example.test",
            display_name="identity-uow-owner", display_name_normalized="identity-uow-owner",
            privacy_policy_version="test", terms_version="test",
        )
        character = models.Character(
            id="identity-uow-character", owner_id=user.id,
            name="identity-uow-character", handle="identity-uow-character",
            avatar_url="/media/characters/identity-uow-character/avatar.webp",
            banner_url="/media/characters/identity-uow-character/banner.webp",
            one_liner="one", personality="private", speech_style="private",
            worldview="private", topic_preferences="private", safety_rules="private",
            status="inactive", persona_summary="private",
        )
        db.add_all([user, character])
        db.commit()
        committed = []
        original_commit = db.commit

        def commit() -> None:
            committed.append(db)
            original_commit()

        def workflow(session: Session, principal: models.User) -> None:
            assert session is db
            assert principal is user
            account_deletion.delete_current_user_account(session, principal)

        monkeypatch.setattr(db, "commit", commit)
        auth.delete_current_user_account(
            db, user, schemas.AccountDeletionCreate(confirmation=auth.ACCOUNT_DELETE_CONFIRMATION),
            workflow=workflow,
        )
        assert committed == [db]
        assert db.get(models.User, user.id).deleted_at is not None
        assert db.get(models.Character, character.id).deleted_at is not None
    engine.dispose()
