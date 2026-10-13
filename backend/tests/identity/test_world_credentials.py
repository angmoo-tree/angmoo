import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.identity.models import User
from app.domains.identity.schemas import WorldCredentialWrite
from app.domains.identity.service import world_credentials
from app.runtime.world_characters.management import management_service
from app.runtime.world_characters import credentials
from world_configuration_fixture_support import seed_configuration_fixture


@pytest.fixture
def world_session(tmp_path, deny_external_network):
    engine = seed_configuration_fixture(tmp_path / "world-key.sqlite3")
    with Session(engine) as db:
        yield db
    engine.dispose()


def write(revision=0, key="synthetic-direct-key", model="gemini-3.1-flash-lite", thinking="high", provider="google"):
    return WorldCredentialWrite(expected_revision=revision, provider=provider, model=model, thinking_level=thinking, api_key=key)


def test_direct_keys_independent_by_actor_purpose_and_rotation(world_session):
    db = world_session
    scope = dict(owner_id="fixture-owner", world_id="config-world-a", world_character_id="config-role-a")
    for purpose in ("sns", "chat", "consolidation"):
        row = world_credentials.save(db, **scope, purpose=purpose, data=write())
        assert row.has_key and row.revision == 1 and "synthetic-direct-key" not in row.model_dump_json()
    original = world_credentials.resolve(db, **scope, purpose="chat", revision=1)
    saved = world_credentials.save(db, **scope, purpose="sns", data=write(1, ""))
    assert saved.has_key and saved.revision == 2
    assert world_credentials.resolve(db, **scope, purpose="chat", revision=1).reveal() == original.reveal()
    world_credentials.delete(db, **scope, purpose="sns", expected_revision=2)
    with pytest.raises(CredentialResolutionError, match="key_required"):
        world_credentials.resolve(db, **scope, purpose="sns")
    assert world_credentials.resolve(db, **scope, purpose="consolidation").reveal() == "synthetic-direct-key"
    for modified in ({"world_id": "config-world-b"}, {"owner_id": "fixture-outsider"}, {"world_character_id": "config-role-b"}):
        with pytest.raises(CredentialResolutionError, match="key_required"):
            world_credentials.resolve(db, **{**scope, **modified}, purpose="chat")


@pytest.mark.parametrize("purpose,data", [
    ("embedding", write(model="gemini-3.1-flash-lite", thinking=None)),
    ("embedding", write(model="gemini-embedding-2")),
    ("vision", write(model="gemini-embedding-2")),
    ("consolidation", write(model="openai/gpt-image-2.5-flare", provider="openrouter")),
    ("image", write()),
])
def test_wrong_capability_rejected_without_registering_key(world_session, purpose, data):
    scope = dict(owner_id="fixture-owner", world_id="config-world-a", world_character_id="config-role-a", purpose=purpose)
    with pytest.raises(CredentialResolutionError, match="profile_invalid"):
        world_credentials.save(world_session, **scope, data=data)
    assert world_credentials.find(world_session, **scope) is None


def test_foreign_picker_payload_and_unowned_actor_rejected(world_session):
    with pytest.raises(ValidationError):
        WorldCredentialWrite(**{**write().model_dump(), "credential_id": "foreign"})
    service = management_service(world_session)
    outsider = world_session.get(User, "fixture-outsider")
    with pytest.raises(ValueError):
        credentials.read(service, world_id="config-world-a", world_character_id="config-role-a", user=outsider, purpose="chat")


def test_model_only_save_requires_current_revision(world_session):
    scope = dict(owner_id="fixture-owner", world_id="config-world-a", world_character_id="config-role-a", purpose="vision")
    world_credentials.save(world_session, **scope, data=write(thinking="medium"))
    row = world_credentials.save(world_session, **scope, data=write(1, None, thinking="high"))
    assert row.has_key and row.thinking_level == "high"
    with pytest.raises(CredentialResolutionError, match="revision_conflict"):
        world_credentials.save(world_session, **scope, data=write(1))


def test_admitted_revision_survives_rotation_but_not_explicit_revoke(world_session):
    db = world_session
    scope = dict(owner_id="fixture-owner", world_id="config-world-a", world_character_id="config-role-a", purpose="chat")
    world_credentials.save(db, **scope, data=write())
    original_id = world_credentials.find(db, **scope).id
    world_credentials.save(db, **scope, data=write(1, "rotated", model="gemini-3.5-flash-lite", thinking="medium"))
    old = world_credentials.resolve(db, **scope, revision=1)
    assert (old.reveal(), old.model, old.thinking_level) == ("synthetic-direct-key", "gemini-3.1-flash-lite", "high")
    assert world_credentials.resolve(db, **scope).reveal() == "rotated"
    with pytest.raises(CredentialResolutionError, match="binding_changed"):
        world_credentials.find_revision(db, **{**scope, "world_character_id": "config-role-b"}, credential_id=original_id, revision=1)
    world_credentials.delete(db, **scope, expected_revision=2)
    world_credentials.save(db, **scope, data=write(3, "registered-again"))
    with pytest.raises(CredentialResolutionError, match="revision_changed"):
        world_credentials.resolve(db, **scope, revision=1)
    assert world_credentials.resolve(db, **scope, revision=4).reveal() == "registered-again"
