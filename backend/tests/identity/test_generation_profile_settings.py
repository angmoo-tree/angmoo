"""Profile choices are separate from secrets and each feature's output budget."""

from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from model_fixture_support import models
from app.models import Base
from app.domains.identity.schemas import CredentialUpsert, CredentialRead
from app.domains.chat.schemas import MessageSettingsUpdate
from app.domains.chat.service.settings import MessageSettingsService
from app.domains.chat.policies import resolve_world_chat_model_execution_policy
from app.domains.memory.schemas.batch import MemoryBatchSettingUpdate
from app.providers.generation_profiles import GENERATION_MODELS, THINKING_LEVELS
from app.runtime.resident.context import LangGraphResidentContext


@pytest.mark.parametrize("model", GENERATION_MODELS)
@pytest.mark.parametrize("thinking", THINKING_LEVELS)
def test_four_profiles_admitted_by_all_settings(model, thinking):
    assert CredentialUpsert(model=model, thinking_level=thinking).thinking_level == thinking
    assert MessageSettingsUpdate(default_model=model, default_thinking_level=thinking).default_thinking_level == thinking
    assert MemoryBatchSettingUpdate(expected_version=0, expected_profile_version=0, ai_enabled=False,
        shutdown_enabled=True, schedule_enabled=False, local_time="22:30", model_id=model,
        thinking_level=thinking, idempotency_key="test-profile").thinking_level == thinking
    policy = resolve_world_chat_model_execution_policy(model, thinking)
    assert policy.thinking_level == thinking and policy.max_output_tokens == 3072
    from app.providers.gemini import build_generate_content_config
    payload = build_generate_content_config(model=model, system_prompt="fixture",
        max_output_tokens=65_536, thinking_level=thinking,
        response_mime_type="application/json", response_schema=None).model_dump(exclude_none=True)
    assert payload["thinking_config"] == {"thinking_level": thinking.upper()}
    assert payload["max_output_tokens"] == 65_536


@pytest.mark.parametrize("model", ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemma-4-26b-a4b-it", "gemma-4-31b-it"])
def test_retired_choices_cannot_create_new_generation(model):
    with pytest.raises(ValidationError):
        CredentialUpsert(model=model)
    with pytest.raises(ValidationError):
        MessageSettingsUpdate(default_model=model)
    with pytest.raises(ValueError):
        resolve_world_chat_model_execution_policy(model)


def test_message_default_pair_changes_preserve_key_and_do_not_change_override():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = models.User(id="profile-owner", display_name="fixture")
        credential = models.LlmCredential(id="message-key", owner_id=owner.id, provider="google", purpose="message", auth_profile_id="fixture-profile",
            model="gemini-2.5-flash", label="fixture", encrypted_api_key="synthetic-envelope", key_fingerprint="synthetic-fingerprint", enabled=True)
        preference = models.UserMessagePreference(user_id=owner.id, default_model="gemini-2.5-flash")
        follower = models.MessageThread(id="follows-default", requester_id=owner.id, character_id="fixture-character", model_binding_mode="default")
        override = models.MessageThread(id="fixed-pair", requester_id=owner.id, character_id="fixture-character", model_binding_mode="thread_override", selected_model="gemini-3.1-flash-lite", selected_thinking_level="medium")
        for thread in (follower, override):
            thread.world_scope_status = "resolved"
            thread.world_id = "profile-world"
            thread.requester_world_character_id = "profile-requester"
            thread.responding_world_character_id = "profile-responder-" + thread.id
        db.add_all([owner, credential, preference, follower, override]); db.commit()
        service = MessageSettingsService()
        assert service.get_user_settings(db, owner).default_model == "gemini-2.5-flash"
        for model in GENERATION_MODELS:
            for thinking in THINKING_LEVELS:
                saved = service.update_user_settings(db, owner, MessageSettingsUpdate(default_model=model, default_thinking_level=thinking))
                assert (saved.default_model, saved.default_thinking_level) == (model, thinking)
                assert (follower.selected_model, follower.selected_thinking_level) == (model, thinking)
                assert (override.selected_model, override.selected_thinking_level) == ("gemini-3.1-flash-lite", "medium")
                assert credential.encrypted_api_key == "synthetic-envelope"
                assert credential.key_fingerprint == "synthetic-fingerprint"


def test_resident_run_keeps_pair_even_when_orm_credential_refreshes():
    credential = SimpleNamespace(model="gemini-3.1-flash-lite", thinking_level="medium")
    context = LangGraphResidentContext(db=None, run_id="fixture", user_id="owner", agent_id="character",
        session_key="fixture", character=None, credential=credential, state=None, activity_policy=None,
        selected_post_id=None, run_started_at=None)
    credential.model, credential.thinking_level = "gemini-3.5-flash-lite", "high"
    assert (context.generation_model, context.generation_thinking_level) == ("gemini-3.1-flash-lite", "medium")
