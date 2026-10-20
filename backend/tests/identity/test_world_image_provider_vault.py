"""Synthetic provider switching, atomic CAS, scoped tombstones and revisions."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.identity.schemas import WorldCredentialWrite, WorldCredentialDelete
from app.domains.identity.service import world_credentials, world_image_credentials
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.identity.models_world_image_credentials import WorldImageProviderCredential
from app.domains.identity.models import User
from app.domains.media.models_world_policy import WorldImagePolicy
from app.domains.media.contracts import ImagePreparationError
from app.runtime.world_characters import credentials
from app.runtime.world_characters.management import management_service
from world_configuration_fixture_support import seed_configuration_fixture

SCOPE = dict(owner_id="fixture-owner", world_id="config-world-a", world_character_id="config-role-a")


@pytest.fixture
def db(tmp_path, deny_external_network):
    engine = seed_configuration_fixture(tmp_path / "vault.sqlite3")
    with Session(engine) as session:
        yield session
    engine.dispose()


def save(db, provider, *, key=None, partner=None, model=None, expected_key=None):
    current = world_credentials.find(db, **SCOPE, purpose="image")
    key_meta = world_image_credentials.metadata(db, **SCOPE, provider=provider)
    return world_credentials.save(db, **SCOPE, purpose="image", data=WorldCredentialWrite(
        provider=provider, model=model or {"novelai":"nai-diffusion-4-5-full", "comfyui":"workflow", "openrouter":"openai/gpt-image-2.5-flare"}[provider],
        expected_revision=current.revision if current else 0, expected_key_revision=key_meta.key_revision if expected_key is None else expected_key,
        api_key=key, partner_api_key=partner))


def test_switch_and_model_reuse_preserve_exact_admitted_revision(db):
    save(db,"novelai",key="synthetic-novel")
    admitted = world_credentials.find(db, **SCOPE,purpose="image").revision
    save(db,"comfyui",partner="synthetic-partner")
    assert world_credentials.resolve(db, **SCOPE,purpose="image",revision=admitted).reveal() == "synthetic-novel"
    assert world_credentials.resolve_image_keys(db,**SCOPE) == (None,"synthetic-partner")
    save(db,"openrouter",key="synthetic-openrouter")
    save(db,"openrouter",model="google/gemini-3.1-flash-image")
    assert world_credentials.resolve_image_keys(db,**SCOPE)[0].reveal() == "synthetic-openrouter"
    save(db,"novelai")
    assert world_credentials.resolve_image_keys(db,**SCOPE)[0].reveal() == "synthetic-novel"
    assert len(list(db.scalars(select(WorldImageProviderCredential)))) == 3


def test_inactive_provider_delete_revokes_only_that_provider_and_never_resurrects(db):
    save(db,"novelai",key="synthetic-novel")
    save(db,"comfyui",partner="synthetic-partner")
    current = world_credentials.find(db, **SCOPE,purpose="image")
    revision=current.revision
    world_image_credentials.delete_provider(db,**SCOPE,data=WorldCredentialDelete(expected_revision=revision,provider="novelai",expected_key_revision=1))
    assert current.provider == "comfyui" and current.revision == revision
    assert world_credentials.resolve_image_keys(db,**SCOPE) == (None,"synthetic-partner")
    with pytest.raises(CredentialResolutionError,match="key_required"):
        world_credentials.resolve(db,**SCOPE,purpose="image",revision=1)
    save(db,"novelai")
    assert not world_credentials.metadata(current,purpose="image").has_key
    with pytest.raises(CredentialResolutionError,match="key_revision_conflict"):
        save(db,"novelai",key="stale",expected_key=1)


def test_current_and_provider_and_policy_cas_roll_back_as_one_unit(db):
    service=management_service(db); user=db.get(User,"fixture-owner")
    policy=db.get(WorldImagePolicy,"config-role-a")
    policy_revision=policy.revision if policy else 0
    good=WorldCredentialWrite(expected_revision=0,expected_key_revision=0,expected_configuration_revision=policy_revision,
        provider="novelai",model="nai-diffusion-4-5-full",api_key="synthetic-first")
    first=credentials.write(service,world_id=SCOPE['world_id'],world_character_id=SCOPE['world_character_id'],user=user,purpose="image",data=good)
    assert first.key_revision == 1
    for changes,code in [({"expected_revision":0},"revision_conflict"),({"expected_key_revision":0},"key_revision_conflict"),({"expected_configuration_revision":policy_revision},"policy_revision_conflict")]:
        update=good.model_copy(update={"expected_revision":first.revision,"expected_key_revision":1,
            "expected_configuration_revision":first.configuration_revision,"api_key":good.api_key,**changes})
        with pytest.raises((ImagePreparationError,CredentialResolutionError),match=code):
            credentials.write(service,world_id=SCOPE['world_id'],world_character_id=SCOPE['world_character_id'],user=user,purpose="image",data=update)
        assert world_credentials.resolve_image_keys(db,**SCOPE)[0].reveal() == "synthetic-first"
        assert world_image_credentials.metadata(db,**SCOPE,provider="novelai").key_revision == 1


def test_keyless_comfy_raw_key_rejection_and_scope_metadata(db):
    saved=save(db,"comfyui")
    assert not saved.has_key and not saved.has_partner_key
    assert world_credentials.resolve_image_keys(db,**SCOPE) == (None,None)
    with pytest.raises(CredentialResolutionError,match="server_key_not_supported"):
        save(db,"comfyui",key="not-supported")
    save(db,"novelai",key="synthetic-scoped")
    for change in [{"world_id":"config-world-b"},{"world_character_id":"config-role-b"},{"owner_id":"fixture-outsider"}]:
        assert not world_image_credentials.metadata(db,**{**SCOPE,**change},provider="novelai").has_key
    with pytest.raises(ValueError):
        credentials.read_image_provider(management_service(db),world_id=SCOPE['world_id'],world_character_id=SCOPE['world_character_id'],user=db.get(User,"fixture-outsider"),provider="novelai")


def test_failed_commit_rolls_back_current_vault_and_policy(db, monkeypatch):
    service, user = management_service(db), db.get(User, "fixture-owner")
    original_policy = db.get(WorldImagePolicy, "config-role-a")
    original_revision = original_policy.revision if original_policy else 0
    def fail_commit():
        db.flush()
        raise RuntimeError("injected_commit_failure")
    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="injected_commit_failure"):
        credentials.write(service, world_id=SCOPE["world_id"], world_character_id=SCOPE["world_character_id"],
            user=user, purpose="image", data=WorldCredentialWrite(expected_revision=0, expected_key_revision=0,
                expected_configuration_revision=original_revision, provider="novelai", model="nai-diffusion-4-5-full", api_key="synthetic-rollback"))
    assert world_credentials.find(db, **SCOPE, purpose="image") is None
    assert world_image_credentials.find(db, **SCOPE, provider="novelai") is None
    assert db.get(WorldImagePolicy, "config-role-a").revision == original_revision


def test_generic_image_delete_uses_vault_cas_and_tombstone(db):
    saved = save(db, "novelai", key="synthetic-delete")
    with pytest.raises(CredentialResolutionError, match="key_revision_conflict"):
        world_credentials.delete(db, **SCOPE, purpose="image", expected_revision=saved.revision)
    world_credentials.delete(db, **SCOPE, purpose="image", expected_revision=saved.revision,
        provider="novelai", expected_key_revision=saved.key_revision)
    assert world_image_credentials.find(db, **SCOPE, provider="novelai").tombstone
    save(db, "comfyui"); save(db, "novelai")
    assert not world_image_credentials.metadata(db, **SCOPE, provider="novelai").has_key
    with pytest.raises(CredentialResolutionError, match="key_required"):
        world_credentials.resolve(db, **SCOPE, purpose="image", revision=1)


def test_policy_conflict_http_409_then_metadata_read_preserves_data(db):
    """The HTTP path handles a CAS conflict without an unhandled server error."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.identity_dependencies import get_current_user
    from app.domains.world_characters.router.management import (
        router, get_management_service, credential_workflows,
    )
    from types import SimpleNamespace

    app = FastAPI()
    app.include_router(router)
    service, user = management_service(db), db.get(User, "fixture-owner")
    app.dependency_overrides[get_management_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[credential_workflows] = lambda: SimpleNamespace(
        write=credentials.write, read=credentials.read)
    path = f"/worlds/{SCOPE['world_id']}/world-characters/{SCOPE['world_character_id']}/credentials/image"
    headers = {"Origin": "http://127.0.0.1:3000"}
    with TestClient(app, base_url="http://127.0.0.1:3000") as client:
        before = client.get(path, headers=headers)
        assert before.status_code == 200, before.text
        snapshot = before.json()
        valid = dict(expected_revision=snapshot["revision"],
            expected_configuration_revision=snapshot["configuration_revision"],
            expected_key_revision=snapshot["key_revision"], provider="novelai",
            model="nai-diffusion-4-5-full", api_key="synthetic-atomic")
        saved = client.put(path, json=valid, headers=headers)
        assert saved.status_code == 200, saved.text
        latest = saved.json()
        conflict = client.put(path, json={**valid, "expected_revision": latest["revision"],
            "expected_key_revision": latest["key_revision"], "api_key": "synthetic-not-saved"}, headers=headers)
        assert conflict.status_code == 409, conflict.text
        assert conflict.json()["detail"] == "world_image_policy_revision_conflict"
        after = client.get(path, headers=headers)
        assert after.status_code == 200
        assert after.json() == latest
        assert world_credentials.resolve_image_keys(db, **SCOPE)[0].reveal() == "synthetic-atomic"


def test_generic_programming_error_is_not_reclassified_as_conflict(db):
    from app.domains.world_characters.router.management import _credential_call
    from starlette.requests import Request
    request = Request({"type": "http", "method": "PUT",
        "headers": [(b"origin", b"http://127.0.0.1:3000"), (b"host", b"127.0.0.1:3000")]})
    def invalid(_service):
        raise ValueError("synthetic_programming_fault")
    with pytest.raises(ValueError, match="synthetic_programming_fault"):
        _credential_call(invalid, management_service(db), request, mutation=True)
