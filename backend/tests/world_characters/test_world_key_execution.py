from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import json
import pytest
from sqlalchemy import event

from identity.test_world_credentials import world_session, write
from app.domains.identity.service import world_credentials
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.identity.schemas import WorldCredentialWrite
from app.domains.media.service import world_policy
from app.domains.media.generation_contracts import ImagePreparationError
from app.domains.media.models_world_policy import WorldImagePolicy
from app.domains.world_characters.service.configuration import effective_configuration
from app.runtime.world_credential_binding import capture, resolve
from app.runtime.media.world_vision import WorldVisionPolicies
from app.runtime.media.world_generation import prepare_intent, prepare_execution, validate_settings
from app.runtime.world_characters.management import management_service
from app.runtime.world_characters.status import read as read_status
from world_configuration_fixture_support import fixture_owner


SCOPE = dict(owner_id="fixture-owner", world_id="config-world-a", world_character_id="config-role-a")


def test_frozen_purpose_binding_cannot_borrow_chat_key_or_latest_rotation(world_session):
    db = world_session
    world_credentials.save(db, **SCOPE, purpose="chat", data=write())
    with pytest.raises(CredentialResolutionError, match="required"):
        capture(db, owner_id=SCOPE["owner_id"], world_id=SCOPE["world_id"], actor_id=SCOPE["world_character_id"], purpose="sns")
    world_credentials.save(db, **SCOPE, purpose="sns", data=write())
    frozen = capture(db, owner_id=SCOPE["owner_id"], world_id=SCOPE["world_id"], actor_id=SCOPE["world_character_id"], purpose="sns")
    assert "synthetic-direct-key" not in json.dumps(frozen)
    world_credentials.save(db, **SCOPE, purpose="sns", data=write(1, "rotated-own-key"))
    assert resolve(db, frozen, owner_id=SCOPE["owner_id"], world_id=SCOPE["world_id"], actor_id=SCOPE["world_character_id"], purpose="sns").reveal() == "synthetic-direct-key"
    world_credentials.delete(db, **SCOPE, purpose="sns", expected_revision=2)
    with pytest.raises(CredentialResolutionError):
        resolve(db, frozen, owner_id=SCOPE["owner_id"], world_id=SCOPE["world_id"], actor_id=SCOPE["world_character_id"], purpose="sns")
    assert world_credentials.resolve(db, **SCOPE, purpose="chat").reveal() == "synthetic-direct-key"


def test_vision_sns_chat_combined_cap_rotation_does_not_reset_usage(world_session):
    db, now = world_session, datetime(2026, 10, 7, 3, tzinfo=UTC)
    world_credentials.save(db, **SCOPE, purpose="vision", data=write(thinking="medium"))
    policy = db.get(WorldImagePolicy, SCOPE["world_character_id"])
    assert (policy.generation_limit, policy.vision_limit) == (20, 10)
    world_policy.patch(db, world_character_id=policy.world_character_id, expected_revision=policy.revision,
        changes={"vision_enabled": True}, require_key=lambda purpose: world_credentials.resolve(db, **SCOPE, purpose=purpose))
    for i in range(10):
        args = dict(world_character_id=policy.world_character_id, purpose="vision", request_key=f"attempt-{i}",
            lane="chat" if i % 2 else "sns", credential_revision=1, now=now, timezone="Asia/Seoul")
        assert world_policy.reserve(db, **args).id == world_policy.reserve(db, **args).id
    db.commit()
    world_credentials.save(db, **SCOPE, purpose="vision", data=write(1, "rotated-vision-key", thinking="medium"))
    assert world_policy.usage(db, world_character_id=policy.world_character_id, purpose="vision", now=now, timezone="Asia/Seoul") == 10
    with pytest.raises(ImagePreparationError, match="daily_limit_reached"):
        world_policy.reserve(db, world_character_id=policy.world_character_id, purpose="vision", request_key="next",
            lane="sns", credential_revision=2, now=now, timezone="Asia/Seoul")
    assert world_policy.usage(db, world_character_id=policy.world_character_id, purpose="image", now=now, timezone="Asia/Seoul") == 0
    assert world_policy.usage(db, world_character_id=policy.world_character_id, purpose="vision", now=now + timedelta(days=1), timezone="Asia/Seoul") == 0
    adapter = WorldVisionPolicies()
    assert adapter.read(db, SCOPE["owner_id"], SimpleNamespace(scope_kind="world", scope_id=SCOPE["world_id"]), SCOPE["world_character_id"]).model == "gemini-3.1-flash-lite"
    with pytest.raises(ImagePreparationError, match="scope_unavailable"):
        adapter.read(db, SCOPE["owner_id"], SimpleNamespace(scope_kind="world", scope_id="config-world-b"), SCOPE["world_character_id"])


def test_world_status_read_has_actual_typed_state_and_no_writes(world_session):
    db = world_session
    statements = []
    def record(_, __, statement, *args):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
            statements.append(statement.split()[0])
    event.listen(db.get_bind(), "before_cursor_execute", record)
    try:
        value = read_status(management_service(db), world_id=SCOPE["world_id"], world_character_id=SCOPE["world_character_id"], user=fixture_owner(db))
        assert value.contract_version == "world-character-status-v1" and value.state.state == "off"
        assert value.persona["worldview"] == "Original world"
        assert set(value.summary["allowed_actions"]) <= {"post", "reply", "like"}
        assert value.summary["posts"] == value.summary["replies"] == value.summary["likes"] == 0
        assert statements == []
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", record)


def test_comfy_partner_write_only_and_client_cannot_invent_connection(world_session):
    db = world_session
    with pytest.raises(CredentialResolutionError, match="comfy_server_key_not_supported"):
        world_credentials.save(db, **SCOPE, purpose="image", data=WorldCredentialWrite(expected_revision=0, expected_key_revision=0,
            provider="comfyui", model="workflow", thinking_level=None, api_key="server-only", partner_api_key="partner-only"))
    row = world_credentials.save(db, **SCOPE, purpose="image", data=WorldCredentialWrite(expected_revision=0, expected_key_revision=0,
        provider="comfyui", model="workflow", thinking_level=None, partner_api_key="partner-only"))
    assert not row.has_key and row.has_partner_key and "server-only" not in row.model_dump_json() and "partner-only" not in row.model_dump_json()
    primary, partner = world_credentials.resolve_image_keys(db, **SCOPE)
    assert primary is None and partner == "partner-only"
    with pytest.raises(ImagePreparationError, match="connection_unverified"):
        validate_settings({"profiles": {"comfyui:workflow": {"options": {}, "connection": {"ready": True}}}})
    world_credentials.save(db, **SCOPE, purpose="image", data=WorldCredentialWrite(expected_revision=1, expected_key_revision=1,
        provider="comfyui", model="workflow", thinking_level=None, clear_partner_key=True))
    primary, partner = world_credentials.resolve_image_keys(db, **SCOPE)
    assert primary is None and partner is None
