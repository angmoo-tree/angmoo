from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.config import settings
from app.core.public_media import mount_public_media
from app.runtime.characters import creator as agent_creation_drafts


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.User.__table__.create(engine)
    models.AgentCreationDraft.__table__.create(engine)
    models.ProfileImageCandidate.__table__.create(engine)
    return engine


def _user(user_id: str) -> models.User:
    return models.User(
        id=user_id,
        email=f"{user_id}@example.invalid",
        display_name=user_id,
        display_name_normalized=user_id,
        profile_setup_completed=True,
    )


def test_only_final_media_directories_are_anonymously_mounted(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    for relative in (
        "characters/char-1/avatar.webp",
        "posts/post-1/image.webp",
        "drafts/draft-1/avatar.webp",
        "profile-candidates/user-1/candidate-1/avatar.webp",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic")
    app = FastAPI()
    mount_public_media(app)
    client = TestClient(app)

    assert client.get("/media/characters/char-1/avatar.webp").status_code == 200
    assert client.get("/media/posts/post-1/image.webp").status_code == 200
    assert client.get("/media/drafts/draft-1/avatar.webp").status_code == 404
    assert (
        client.get(
            "/media/profile-candidates/user-1/candidate-1/avatar.webp"
        ).status_code
        == 404
    )


def test_private_preview_requires_owner_and_exact_database_path(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    draft_path = tmp_path / "drafts" / "draft-1" / "avatar.webp"
    candidate_path = (
        tmp_path
        / "profile-candidates"
        / "owner"
        / "candidate-1"
        / "avatar.webp"
    )
    draft_path.parent.mkdir(parents=True)
    candidate_path.parent.mkdir(parents=True)
    draft_path.write_bytes(b"draft-preview")
    candidate_path.write_bytes(b"candidate-preview")
    engine = _engine()
    with Session(engine) as db:
        owner = _user("owner")
        other = _user("other")
        db.add_all(
            [
                owner,
                other,
                models.AgentCreationDraft(
                    id="draft-1",
                    user_id=owner.id,
                    provider="google",
                    model="gemini-2.5-flash",
                    encrypted_api_key="synthetic-envelope",
                    avatar_temp_url="/media/drafts/draft-1/avatar.webp",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                ),
                models.ProfileImageCandidate(
                    id="candidate-1",
                    user_id=owner.id,
                    draft_id="draft-1",
                    scope="create",
                    bucket="create_avatar",
                    media_type="avatar",
                    url=(
                        "/media/profile-candidates/owner/"
                        "candidate-1/avatar.webp"
                    ),
                    content_type="image/webp",
                    byte_size=10,
                    width=32,
                    height=32,
                    model="synthetic",
                    route_mode="fake",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                ),
            ]
        )
        db.commit()

        assert agent_creation_drafts.get_draft_media_content(
            db,
            owner,
            "draft-1",
            "avatar",
        )[0] == draft_path
        assert agent_creation_drafts.get_draft_candidate_content(
            db,
            owner,
            "draft-1",
            "candidate-1",
        )[0] == candidate_path

        with pytest.raises(
            agent_creation_drafts.AgentCreationDraftNotFoundError
        ):
            agent_creation_drafts.get_draft_media_content(
                db,
                other,
                "draft-1",
                "avatar",
            )
