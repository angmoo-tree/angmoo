"""Credential reveal and actual writer/image IO for the first-greeting lane."""
from __future__ import annotations
from datetime import UTC, datetime
from typing import Any
import json
from sqlalchemy.orm import Session
from app.config import settings
from app.core.redaction import redact_secret_text
from app.domains.characters import models as character_models
from app.domains.identity import models as identity_models
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.domains.characters.exceptions import CredentialRequiredError
from app.domains.routines import models
from app.domains.routines.schemas.first_greeting import _FirstGreetingWriterPayload
from app.domains.social.schemas import community as schemas
from app.domains.routines.service.first_greeting import _build_first_greeting_writer_prompt
from app.domains.routines.constants import FIRST_GREETING_WRITER_OUTPUT_TOKENS
from app.integrations.direct_llm import RunLlmTracker, DirectLlmCallContext, generate_json
from app.runtime.social import image_generation as post_image_generation
from app.domains.social.service import image_attachment

def resolve_first_greeting_key(
    credential: identity_models.LlmCredential | None, *, user: identity_models.User, character: character_models.Character
) -> str:
    try:
        material = CredentialResolver.resolve_llm_credential(
            credential,
            purpose=CredentialPurpose.RESIDENT_LLM,
            owner_id=user.id,
            character_id=character.id,
        )
        api_key = material.reveal()
    except CredentialResolutionError as exc:
        raise CredentialRequiredError("Agent credential key cannot be decrypted") from exc

    return api_key


async def _run_first_greeting_writer(
    *,
    api_key: str,
    character: character_models.Character,
    setting: models.AgentActivitySetting,
    credential: identity_models.LlmCredential,
    run_id: str,
    tracker: RunLlmTracker,
    topic: str,
) -> _FirstGreetingWriterPayload:
    def _validator(payload: dict[str, Any]) -> _FirstGreetingWriterPayload:
        return _FirstGreetingWriterPayload.model_validate(payload)

    user_prompt = {
        "owner_topic": topic.strip(),
        "character": {
            "name": character.name,
            "handle": character.handle,
            "one_liner": character.one_liner,
            "personality": character.personality,
            "speech_style": character.speech_style,
            "worldview": character.worldview,
            "topic_preferences": character.topic_preferences,
            "safety_rules": character.safety_rules,
        },
        "community_tendency": {
            "summary": setting.tendency_summary,
            "action_ranges": setting.tendency_action_ranges,
            "planner_profile": setting.planner_tendency_profile,
        },
    }
    return await generate_json(
        api_key=api_key,
        context=DirectLlmCallContext(
            credential_id=credential.id,
            character_id=character.id,
            agent_run_id=run_id,
            node="FirstGreetingWriter",
            lane="first_greeting_writer",
            provider=credential.provider,
            model=credential.model,
            key_fingerprint=credential.key_fingerprint,
        ),
        tracker=tracker,
        system_prompt=_build_first_greeting_writer_prompt(),
        user_prompt=json.dumps(user_prompt, ensure_ascii=False),
        response_schema=_FirstGreetingWriterPayload,
        validator=_validator,
        max_output_tokens=FIRST_GREETING_WRITER_OUTPUT_TOKENS,
        thinking_level=credential.thinking_level,
    )

async def _attach_first_greeting_image(
    *,
    db: Session,
    character: character_models.Character,
    credential: identity_models.LlmCredential,
    run_id: str,
    tracker: RunLlmTracker,
    topic: str,
    post: schemas.PostDetail,
) -> dict[str, Any] | None:
    try:
        run_started_at = datetime.now(UTC)
        prepared = await post_image_generation.prepare_post_image(
            db=db,
            character=character,
            credential=credential,
            run_id=run_id,
            tracker=tracker,
            writing_mode="first_greeting",
            post_title=post.title,
            post_body=post.body,
            writing_plan={"mode": "first_greeting", "topic": topic.strip()},
            current_time_text=run_started_at.isoformat(),
            run_started_at=run_started_at,
        )
        return image_attachment.attach_prepared_post_image(
            db=db,
            post_id=post.id,
            prepared=prepared,
        )
    except Exception as exc:
        return {
            "status": "failed",
            "failure_class": type(exc).__name__,
            "error": redact_secret_text(str(exc))[:500],
        }
