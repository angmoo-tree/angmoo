"""Creator lifecycle uses external callbacks without surrendering DB ownership."""
import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import models as registered_models
from app.core import security
from app.domains.characters import dependencies, exceptions, models, schemas
from app.domains.characters.contracts import CreatorWorkflows
from app.domains.characters.service import drafts
from app.runtime.characters import creator as runtime


def _unreachable(*args, **kwargs):
    raise AssertionError("unrelated external workflow was called")


def _workflows(**changes):
    return CreatorWorkflows(**{
        **{name: _unreachable for name in CreatorWorkflows.__dataclass_fields__},
        **changes,
    })


@pytest.fixture
def engine(tmp_path):
    value = create_engine(f"sqlite:///{tmp_path / 'draft-lifecycle.sqlite3'}")
    for table in (registered_models.User.__table__, models.Character.__table__, models.AgentCreationDraft.__table__, models.ProfileImageCandidate.__table__):
        table.create(value)
    with Session(value) as db:
        db.add(registered_models.User(id="owner", display_name="Owner"))
        db.commit()
    yield value
    value.dispose()


def _draft(identifier, expires_at):
    return models.AgentCreationDraft(
        id=identifier, user_id="owner", provider="google", model="gemini-3.1-flash-lite",
        encrypted_api_key="unused-ciphertext", key_fingerprint="fixture",
        name="Owner Bird", handle=None, one_liner="Intro", personality="Curious",
        speech_style="Calm", worldview="A garden", topic_preferences="Plants",
        safety_rules="Be kind", image_style="기본", appearance_prompt="Green bird",
        expires_at=expires_at,
    )


def test_create_verifies_before_insert_and_keeps_original_cipher_scope(engine):
    owner = SimpleNamespace(id="owner")
    calls = []
    with Session(engine) as db:
        event.listen(db, "after_commit", lambda current: calls.append(("commit", current)))
        async def verify(**kwargs):
            assert kwargs["db"] is db and kwargs["user"] is owner
            assert list(db.query(models.AgentCreationDraft)) == []
            assert calls == []
            calls.append(("verify", kwargs["draft_id"]))
            return '{"ok": true}'
        data = schemas.AgentCreationDraftCreate(api_key="test-credential")
        result = asyncio.run(drafts.create_draft(db, owner, data, workflows=_workflows(run_llm=verify)))
        stored = db.get(models.AgentCreationDraft, result.id)
        assert [name for name, _ in calls] == ["verify", "commit"]
        assert stored.user_id == owner.id
        assert stored.encrypted_api_key != data.api_key
        assert security.decrypt_secret(stored.encrypted_api_key, scope=security.SecretScope(owner_id=owner.id, character_id="", provider=data.provider, purpose="creation_draft")) == data.api_key
        with pytest.raises(exceptions.AgentCreationDraftNotFoundError):
            drafts.get_draft(db, SimpleNamespace(id="foreign"), result.id, workflows=_workflows())
        assert drafts.get_draft(db, owner, result.id, workflows=_workflows()).id == result.id


def test_expiry_cleanup_rolls_back_only_failed_draft_and_keeps_media_first(engine):
    now = datetime.now(UTC)
    deleted_files, commits, rollbacks = [], [], []
    with Session(engine) as db:
        db.add_all([_draft("first-fails", now - timedelta(minutes=1)), _draft("second-succeeds", now - timedelta(minutes=1)), _draft("still-live", now + timedelta(hours=1))])
        db.commit()
        event.listen(db, "after_commit", lambda current: commits.append(current))
        event.listen(db, "after_rollback", lambda current: rollbacks.append(current))
        def delete_file(identifier):
            assert db.get(models.AgentCreationDraft, identifier) is not None
            deleted_files.append(identifier)
            if identifier == "first-fails":
                raise OSError("fixture storage failure")
        drafts._cleanup_expired_drafts(db, workflows=_workflows(delete_draft_media=delete_file))
        assert deleted_files == ["first-fails", "second-succeeds"]
        assert commits == [db] and rollbacks == [db]
        assert db.get(models.AgentCreationDraft, "first-fails") is not None
        assert db.get(models.AgentCreationDraft, "second-succeeds") is None
        assert db.get(models.AgentCreationDraft, "still-live") is not None


def test_enhance_persona_calls_provider_after_owner_gate_and_commits_sanitized_fields(engine):
    owner = SimpleNamespace(id="owner")
    calls = []
    with Session(engine) as db:
        draft = _draft("persona", datetime.now(UTC) + timedelta(hours=1))
        db.add(draft)
        db.commit()
        async def generate(**kwargs):
            assert kwargs["db"] is db and kwargs["user"] is owner
            calls.append("provider")
            return '{"personality":"Careful", "speech_style":"Friendly", "worldview":"Garden", "topic_preferences":["Plants", "Rain"], "safety_rules":"Kind"}'
        workflows = _workflows(run_llm=generate, decrypt_api_key=lambda current: "test-credential")
        with pytest.raises(exceptions.AgentCreationDraftNotFoundError):
            asyncio.run(drafts.enhance_persona(db, SimpleNamespace(id="foreign"), draft.id, workflows=workflows))
        assert calls == []
        result = asyncio.run(drafts.enhance_persona(db, owner, draft.id, workflows=workflows))
        assert calls == ["provider"]
        assert result.personality == "Careful"
        assert result.topic_preferences == "Plants\nRain"
        assert result.persona_enhance_available_at is not None
        with Session(engine) as observer:
            assert observer.get(models.AgentCreationDraft, draft.id).personality == "Careful"


def test_both_factories_install_creator_and_draft_routes_keep_original_position():
    from app.main import create_app as hosted_factory
    from app.public_main import create_app as public_factory
    from app.api.v1.routes import agents
    from app.domains.characters import router
    for factory in (hosted_factory, public_factory):
        app = factory()
        workflows = dependencies.get_creator_workflows(Request({"type": "http", "app": app}))
        assert workflows.run_llm is runtime._run_draft_llm
        assert workflows.create_character is runtime.agent_service.create_agent
    actual = next(route for route in agents.router.routes if route.name == "get_agent_draft")
    canonical = next(route for route in router.router.routes if route.name == "get_agent_draft")
    assert actual is canonical
    paths = [route.path for route in agents.router.routes]
    assert paths.index("/agents/drafts/{draft_id}") < paths.index("/agents/{character_id}")
