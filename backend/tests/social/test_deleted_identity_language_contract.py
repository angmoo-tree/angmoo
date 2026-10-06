"""Canonical deletion status, never placeholder text, decides UI localization."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest

from app.config import settings
from app.domains.characters.models import Character
from app.domains.characters.schemas import AgentDeleteCreate
from app.domains.identity.models import User
from app.domains.social.models.posts import Post
from app.domains.social.service.presentation import _post_summary
from app.policies.name_policy import is_blocked_name
from app.runtime.characters.management import delete_agent
from app.runtime.persistence.model_registration import register_models

pytestmark = pytest.mark.usefixtures("deny_external_network")


def test_actual_deletion_and_legacy_named_active_characters_keep_separate_identities(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "AGENT_ACTIVITY_ENGINE", "langgraph")
    engine = create_engine(f"sqlite:///{tmp_path / 'deleted.sqlite3'}")
    register_models().create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = User(id="owner", display_name="Synthetic owner")
        names = {"to-delete": "Original character", "legacy-name": "삭제한 앵무", "same-new-name": "삭제한 캐릭터"}
        db.add(owner)
        for key, name in names.items():
            db.add(Character(id=key, owner_id=owner.id, name=name, handle=key, persona_summary="앵무·둥지 are literal persona terms"))
        db.flush()
        for key, name in names.items():
            db.add(Post(id="post-"+key, author_character_id=key, author_name=name,
                        title="Original A-17", body="앵무·둥지 · 原文 · لم أوافق"))
        db.commit()
        delete_agent(db, owner, "to-delete", AgentDeleteCreate(confirmation=names["to-delete"]))
        for key, name in names.items():
            post = db.get(Post, "post-"+key)
            result = _post_summary(db, post)
            assert result.author_character_id == key
            assert result.author_deleted is (key == "to-delete")
            if key != "to-delete":
                assert result.author_name == name
                assert db.get(Character, key).name == name
            assert (result.title, result.body) == ("Original A-17", "앵무·둥지 · 原文 · لم أوافق")
        assert db.get(Character, "to-delete").deleted_at is not None
    engine.dispose()


@pytest.mark.parametrize("name", ["삭제한 캐릭터", "Deleted character", "삭제한 앵무", "deleted_character"])
def test_new_placeholder_names_stay_reserved(name):
    assert is_blocked_name(name)
