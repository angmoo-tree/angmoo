"""Real scoped authorizers, shared normalization/CAS and purpose-bound credentials."""
import pytest
from sqlalchemy.orm import Session
from pydantic import ValidationError
from world_configuration_fixture_support import seed_configuration_fixture, fixture_owner
from app.config import settings
from app.domains.worlds.models import World, WorldMembership
from app.domains.worlds.service import WorldServiceError
from app.domains.world_characters.models import WorldCharacter
from app.domains.characters.models import Character
from app.domains.world_characters.schemas.basic_activity import BasicActivitySettingsPatch
from app.domains.world_characters.schemas.management import ExpectedWorldRevision
from app.domains.world_characters.service.management import WorldManagementError
from app.domains.identity.schemas import WorldCredentialWrite
from app.runtime.world_characters import credentials, image_policy
from app.runtime.world_characters.management import management_service


@pytest.fixture
def basic(tmp_path, monkeypatch, deny_external_network):
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", True)
    engine = seed_configuration_fixture(tmp_path / "basic.sqlite3", browser_ready=True)
    with Session(engine, expire_on_commit=False) as db: yield db, management_service(db), fixture_owner(db)
    engine.dispose()


@pytest.mark.parametrize("actor_status", ["active", "inactive", "pending"])
def test_draft_read_save_key_preservation_and_on_denial(basic, actor_status):
    db, service, owner = basic
    db.get(World, "config-world-a").status = "draft"
    db.get(WorldCharacter, "config-role-a").status = actor_status; db.commit()
    scope = dict(world_id="config-world-a", world_character_id="config-role-a", user=owner)
    first = service.activity_settings(**scope)
    assert not first.can_activate and first.reason == "world_not_published"
    assert not db.new and not db.dirty
    saved = service.patch_activity_settings(**scope, data=BasicActivitySettingsPatch(expected_revision=1, activity_interval_minutes=45, active_hours_start="09:00", active_hours_end="02:00"))
    assert saved.revision == 2 and saved.policy.activity_interval_minutes == 45
    key = credentials.write(service, **scope, purpose="sns", data=WorldCredentialWrite(provider="google", model="gemini-3.1-flash-lite", thinking_level="high", api_key="synthetic-no-network-key", expected_revision=0, expected_configuration_revision=2))
    again = credentials.write(service, **scope, purpose="sns", data=WorldCredentialWrite(provider="google", model="gemini-3.1-flash-lite", thinking_level="medium", expected_revision=key.revision, expected_configuration_revision=2))
    assert key.fingerprint == again.fingerprint and again.has_key
    assert image_policy.read(service, **scope)["generation_enabled"] is False
    with pytest.raises(WorldManagementError): service.set_autonomy(**scope, data=ExpectedWorldRevision(expected_revision=2), enabled=True)
    assert db.get(WorldCharacter, "config-role-a").autonomous_enabled is False
    assert db.get(WorldCharacter, "config-role-b").version == 1


def test_read_and_real_activation_use_saved_facts_and_key_deletion(basic):
    db, service, owner = basic; scope = dict(world_id="config-world-a", world_character_id="config-role-a", user=owner)
    assert not service.activity_settings(**scope).can_activate
    key = credentials.write(service, **scope, purpose="sns", data=WorldCredentialWrite(provider="google", model="gemini-3.1-flash-lite", thinking_level="high", api_key="synthetic-no-network-key", expected_revision=0, expected_configuration_revision=1))
    ready = service.activity_settings(**scope); assert ready.can_activate, ready.reason
    service.set_autonomy(**scope, data=ExpectedWorldRevision(expected_revision=ready.revision), enabled=True)
    current = service.activity_settings(**scope); assert current.autonomous_enabled and current.can_deactivate
    service.set_autonomy(**scope, data=ExpectedWorldRevision(expected_revision=current.revision), enabled=False)
    from app.domains.identity.schemas import WorldCredentialDelete
    credentials.write(service, **scope, purpose="sns", data=WorldCredentialDelete(expected_revision=key.revision), remove=True)
    assert service.activity_settings(**scope).reason == "credential_required"


@pytest.mark.parametrize("change", ["membership", "deleted", "moderated", "world", "control"])
def test_basic_authorization_cannot_grant_other_features(basic, change):
    db, service, owner = basic
    actor = db.get(WorldCharacter, "config-role-a")
    if change == "membership": db.get(WorldMembership, actor.membership_id).status = "left"
    elif change == "deleted": db.get(Character, actor.character_id).deleted_at = __import__('datetime').datetime.now(__import__('datetime').UTC)
    elif change == "moderated": db.get(Character, actor.character_id).moderation_status = "blocked"
    elif change == "world": pass
    else:
        actor.control_mode = "owner_controlled"
        actor.owner_user_id = "fixture-outsider"
    db.commit()
    with pytest.raises((WorldManagementError, WorldServiceError, ValueError)):
        service.activity_settings(world_id="config-world-b" if change == "world" else "config-world-a", world_character_id=actor.id, user=owner)


def test_basic_whitelist_and_compare_swap(basic):
    db, service, owner = basic; scope = dict(world_id="config-world-a", world_character_id="config-role-a", user=owner)
    with pytest.raises(ValidationError): BasicActivitySettingsPatch(expected_revision=1, worldview="not allowed")
    service.patch_activity_settings(**scope, data=BasicActivitySettingsPatch(expected_revision=1, allow_like=False))
    with pytest.raises(WorldManagementError): service.patch_activity_settings(**scope, data=BasicActivitySettingsPatch(expected_revision=1, allow_post=False))
    with pytest.raises((ValidationError, WorldManagementError)): service.patch_activity_settings(**scope, data=BasicActivitySettingsPatch(expected_revision=2, activity_interval_minutes=1))


def test_thin_http_contract_origin_cas_and_read_only(basic):
    from sqlalchemy import event
    from world_characters.test_world_character_configuration import _client
    db, _, _ = basic
    statements = []
    def record(_conn, _cursor, statement, *_args):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            statements.append(statement)
    event.listen(db.bind, "before_cursor_execute", record)
    try:
        with _client(db.bind) as client:
            path = "/api/v1/worlds/config-world-a/world-characters/config-role-a/activity-settings"
            response = client.get(path)
            assert response.status_code == 200, response.json()
            body = response.json()
            assert body["contract_version"] == "world-activity-settings-v1"
            assert body["character_id"] == "config-actor-a"
            assert set(body["policy"]) == {"active_hours_start", "active_hours_end", "activity_interval_minutes",
                "max_posts_per_day", "max_comments_per_day", "allow_post", "allow_reply", "allow_like"}
            assert not statements and "api_key" not in str(body) and "worldview" not in body
            assert client.patch(path, json={"expected_revision": 1, "allow_like": False}).status_code == 403
            headers = {"Origin": "http://127.0.0.1:3000"}
            assert client.patch(path, headers=headers, json={"expected_revision": 1, "worldview": "forbidden"}).status_code == 422
            saved = client.patch(path, headers=headers, json={"expected_revision": 1, "allow_like": False})
            assert saved.status_code == 200 and saved.json()["revision"] == 2
            assert client.patch(path, headers=headers, json={"expected_revision": 1, "allow_post": False}).status_code == 409
            assert client.get(path.replace("config-world-a", "config-world-b")).status_code in {403, 404}
    finally:
        event.remove(db.bind, "before_cursor_execute", record)


def test_draft_image_settings_share_policy_key_revision_without_vision_grant(basic):
    from app.domains.media.schemas import WorldImagePolicyPatch
    from app.domains.media.contracts import ImagePreparationError
    db, service, owner = basic
    db.get(World, "config-world-a").status = "draft"
    db.get(WorldCharacter, "config-role-a").status = "pending"
    db.commit()
    scope = dict(world_id="config-world-a", world_character_id="config-role-a", user=owner)
    initial = image_policy.read(service, **scope)
    assert (initial["generation_limit"], initial["vision_limit"]) == (20, 10)
    saved = image_policy.write(service, **scope, data=WorldImagePolicyPatch(expected_revision=initial["revision"],
        generation_limit=21, generation_settings={"appearance": "original appearance", "style": "original style", "profiles": {}}))
    assert saved["generation_limit"] == 21 and not saved["generation_enabled"]
    key = credentials.write(service, **scope, purpose="image", data=WorldCredentialWrite(expected_revision=0, expected_key_revision=0,
        expected_configuration_revision=saved["revision"], provider="novelai", model="nai-diffusion-4-5-full", api_key="synthetic-image-key"))
    assert key.has_key and key.configuration_revision == saved["revision"] + 1
    preserved = credentials.write(service, **scope, purpose="image", data=WorldCredentialWrite(expected_revision=key.revision, expected_key_revision=key.key_revision,
        expected_configuration_revision=key.configuration_revision, provider="novelai", model="nai-diffusion-4-5-full"))
    assert preserved.has_key and preserved.fingerprint == key.fingerprint
    current = image_policy.read(service, **scope)
    assert current["generation_settings"]["appearance"] == "original appearance"
    with pytest.raises(ImagePreparationError):
        image_policy.write(service, **scope, data=WorldImagePolicyPatch(expected_revision=initial["revision"], generation_limit=22))
    with pytest.raises((WorldManagementError, WorldServiceError)):
        image_policy.write(service, **scope, data=WorldImagePolicyPatch(expected_revision=current["revision"], vision_limit=11))
