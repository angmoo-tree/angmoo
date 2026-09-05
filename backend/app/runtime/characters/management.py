from __future__ import annotations
from app.domains.routines.contracts.manual_activity import ManualActivityWorkflows
from app.domains.routines.contracts.feed_cues import FeedCueWorkflows
from app.domains.routines.service import manual_activity
from app.domains.routines.service.manual_activity import _manual_run_available_at
from app.domains.routines.service.tick_schedule import aware_utc as _aware_utc
from app.domains.routines.constants import RUN_NOW_COOLDOWN, RUN_NOW_SCHEDULER_GUARD_WINDOW, RUN_NOW_SCHEDULER_HEADROOM
from app.domains.routines.contracts.autonomy_management import AutonomyWorkflows
from app.domains.routines.service import autonomy_management
from app.domains.routines.repository.autonomy import _lock_server_llm_autonomy_capacity
from app.domains.routines.service.autonomy_management import _reject_server_llm_autonomy_capacity, _reject_world_autonomy_capacity, _log_autonomy_activation_rejection
from app.runtime.resident.autonomy_reads import count_effective_active_server_llm_autonomy_agents as _effective_server_llm_autonomy_count
from app.domains.identity.service import profile as identity_profile
from app.domains.routines.constants import SERVER_LLM_AUTONOMY_CAPACITY_ERROR_MESSAGE, WORLD_AUTONOMY_CAPACITY_ERROR_MESSAGE, SERVER_LLM_AUTONOMY_CAPACITY_LOCK_KEY
from app.domains.routines.schemas.tendency import _TendencyRangePayload
from app.domains.routines.schemas.tendency import _TendencyActionRangesPayload
from app.domains.routines.schemas.tendency import _IndependentPostInitiativePayload
from app.domains.routines.schemas.tendency import _IndependentPostTopicPayload
from app.domains.routines.schemas.tendency import _PlannerTendencyProfilePayload
from app.domains.routines.schemas.tendency import _TendencyAnalysisPayload
from app.domains.routines.service.tendency import _ensure_tendency_prompt_safety
from app.domains.routines.service.tendency import _build_tendency_analysis_prompt
from app.domains.routines.service.tendency import _extract_gateway_result_text
from app.domains.routines.service.tendency import _parse_tendency_json
from app.domains.routines.service.tendency import _normalize_tendency_payload
from app.domains.routines.service.tendency import _normalize_planner_tendency_profile
from app.domains.routines.service.tendency import _calibrated_independent_post_probability
from app.domains.routines.service.tendency import _slug_tendency_topic_key
from app.domains.routines.service.tendency import normalize_angmoo_terms_in_tendency_text
from app.domains.routines.service.tendency import _safe_tendency_text
from app.domains.routines.service.tendency import _clamped_tendency_int
from app.domains.routines.service.tendency_settings import _mark_tendency_error
from app.domains.routines.service.tendency_settings import _has_tendency_analysis
from app.domains.routines.service.tendency_settings import _ensure_tendency_analysis_ready
from app.domains.routines.service.tendency_settings import _clear_tendency_analysis
from app.domains.routines.service.activity_management import _apply_initial_activity_settings
from app.domains.routines.exceptions import AgentAutonomyCapacityError
from app.domains.routines.exceptions import AgentAutonomyRetryableError
from app.domains.routines.exceptions import TendencyAnalysisParseError
from app.domains.routines.exceptions import TendencyPromptInjectionDetectedError
from app.domains.routines.exceptions import TendencyAnalysisRequiredError
from app.domains.routines.exceptions import ActivityProfileRequiredError
from app.domains.routines.exceptions import AgentFeedCueConflictError
from app.domains.routines.exceptions import AgentFeedCueUnavailableError
from app.domains.routines.exceptions import RunNowCooldownError
from app.domains.routines.exceptions import FirstGreetingCooldownError
from app.domains.routines.exceptions import FirstGreetingUnavailableError
from app.domains.routines.exceptions import RunNowSlotUnavailableError
from app.domains.routines.exceptions import RunNowSlotBusyError
from app.domains.routines.exceptions import RunNowSchedulerBusyError
from app.domains.routines.exceptions import RunNowSoonScheduledError
from app.domains.routines.constants import TENDENCY_ACTION_KEYS
from app.domains.routines.constants import TENDENCY_INDEPENDENT_TOPIC_COUNT
from app.domains.routines.constants import TENDENCY_ANALYSIS_MAX_OUTPUT_TOKENS
from app.domains.routines.constants import FEED_SEED_INTEREST_CRITERIA_MAX_LENGTH
from app.domains.routines.constants import TENDENCY_ACTION_DEFAULTS
from app.domains.routines.constants import INDEPENDENT_POST_PROBABILITY_RANGES
from app.domains.routines.constants import TENDENCY_CONTENT_CHARACTER_PHRASES
from app.domains.routines.constants import TENDENCY_PERSONA_CHARACTER_PATTERN
from functools import partial
from app.domains.routines.contracts.activity_management import ActivityManagementReferences
from app.domains.routines.service import activity_management
from app.domains.routines import constants as routine_constants
from app.domains.routines.repository import slots as slot_queries
from app.domains.routines.service import slot_assignments as slot_assignments
from app.domains.routines.service import slot_pool as slot_pool
from app.domains.routines.repository import feed_cues as feed_cue_queries
from app.domains.routines.repository import runs as routine_run_queries
from app.domains.routines.service import feed_cues as feed_cues
from app.domains.routines.service import runs as routine_runs

from app.runtime.world_characters.queries import count_enabled_autonomous_world_characters
from app.domains.characters.service import media as media_service

from app.domains.characters.service.creator import (
    llm_credential_error_message,
)

from app.domains.characters.exceptions import (
    CredentialRequiredError,
    CredentialSyncError,
)

from app.domains.characters.contracts import CharacterManagementWorkflows
from app.domains.characters.service import management as character_management
from app.domains.characters.service.management import (
    _agent_list_sort_key,
)

from app.domains.characters.exceptions import (
    AgentActiveHoursInvalidError,
)

from app.domains.characters.service import mutations as character_mutations
from datetime import UTC, datetime, timedelta
import hashlib
import json
import re
from typing import Any, Iterable, Literal
from uuid import uuid4

from app.domains.characters.service.promotion import (
    PROMOTION_USAGE_POLICY_VERSION,
    _set_promotion_usage,
    _promotion_usage_read,
)

from app.domains.characters.service.access import (
    LOCAL_MODE_LLM_BLOCKED_MESSAGE,
    _get_owned_character,
    _ensure_not_suspended,
    _is_local_mode,
    _ensure_llm_mode,
    _ensure_local_mode,
)

from app.domains.characters.service.persona import (
    PERSONA_PROMPT_SAFETY_FIELDS,
    ensure_persona_prompt_safety,
    _field_value,
)

from app.domains.characters.exceptions import (
    AgentServiceError,
    AgentNotFoundError,
    AgentHandleConflictError,
    AgentHandleInvalidError,
    AgentProfileNameInvalidError,
    InvalidProfileMediaError,
    PromptInjectionDetectedError,
    AgentExecutionModeError,
    AgentSuspendedError,
)

from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select, text, update
from sqlalchemy.orm import Session

from app import models, schemas
from app.domains.characters import models as character_models
from app.domains.characters.service import profile as character_profile
from app.core import active_hours, security, unit_of_work
from app.config import settings
from app.core.image_generation import USER_IMAGE_MODEL_OPTIONS
from app.core.redaction import redact_secret_text
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.exceptions import SqliteBusyRetryExhausted
from app.credentials import (
    CredentialPurpose,
    CredentialResolutionError,
    CredentialResolver,
)
from app.cruds import agents as agent_crud
from app.cruds import community as community_crud
from app.policies import name_policy
from app.runtime.resident import activity_policy as agent_activity_policy
from app.domains.world_characters.service import readiness as activity_profile_readiness
from app.services import community as community_service
from app.runtime.resident import execution as agent_run_service
from app.domains.identity.service import demo_access as demo_lock
from app.services import image_prompt_safety
from app.services import maintenance as maintenance_service
from app.services import post_image_generation
from app.core import prompt_safety
from app.domains.characters.service import media_storage as profile_media
from app.integrations.media import files as media_files
from app.integrations.media import images as media_images
from app.services import service_image_key
from app.services import operation_settings
from app.services.direct_llm import (
    DirectLlmCallContext,
    DirectLlmDeferred,
    DirectLlmError,
    RunLlmTracker,
    generate_json,
)
from app.services.runtime_boundary import (
    OpenClawGatewayClient,
    OpenClawGatewayError,
    openclaw_auth_profiles,
)
from app.domains.world_characters.public import (
    is_owner_controlled_character,
    lock_world_autonomy_capacity,
    selected_autonomous_world_character,
    set_active_world_character_autonomy,
)


AGENT_DETAIL_ACTIVITY_LIMIT = 200
FIRST_GREETING_COOLDOWN = timedelta(minutes=30)
FIRST_GREETING_SESSION_MARKER = ":first-greeting:"
FIRST_GREETING_WRITER_OUTPUT_TOKENS = 5000
DELETED_CHARACTER_NAME = "삭제한 앵무"
DELETED_CHARACTER_PLACEHOLDER = "삭제된 앵무입니다."
# OpenClaw validates the global tool allowlist before honoring tool_choice="none".
TENDENCY_LLM_TOOLS_ALLOW = ["angmoo_list_feed"]
LOCAL_KEY_PREFIX = "angmoo_local_"














class _FirstGreetingWriterPayload(BaseModel):
    post_title: str = Field(min_length=1, max_length=160)
    post_body: str = Field(min_length=1, max_length=4000)
    topic_signature: str = Field(min_length=1, max_length=300)
    persona_basis: str = Field(min_length=1, max_length=500)
    tendency_basis: str = Field(min_length=1, max_length=500)




DemoAccountLockedError = demo_lock.DemoAccountLockedError






class UnsafeImagePromptError(AgentServiceError):
    pass


class ImageSettingsInvalidError(AgentServiceError):
    pass




class LlmCredentialInvalidError(AgentServiceError):
    pass


class ActiveSlotBusyError(AgentServiceError):
    pass


















class AgentDeleteConfirmationError(AgentServiceError):
    pass


class AgentDeletionCredentialSyncError(AgentServiceError):
    pass


class AgentDeletionMediaCleanupError(AgentServiceError):
    pass
















def list_agents(db: Session, user: models.User) -> list[schemas.AgentDetailRead]:
    return character_management.list_agents(db, user, workflows=build_character_management_workflows())










def create_agent(
    db: Session, user: models.User, data: schemas.AgentCreate
) -> schemas.AgentDetailRead:
    return character_management.create_agent(db, user, data, workflows=build_character_management_workflows())


def _after_character_created(db, user, character, data) -> schemas.AgentDetailRead:
    setting = agent_crud.ensure_setting(db, character.id)
    _apply_initial_activity_settings(db, setting, data)
    _ensure_initial_image_settings(db, character.id)
    if data.execution_mode == "llm":
        if data.api_key is None:
            raise CredentialRequiredError("Agent credential is required")
        agent_crud.upsert_credential(
            db,
            user=user,
            character=character,
            provider=data.provider,
            model=data.model,
            api_key=data.api_key,
            auth_profile_id=None,
            label=f"{character.name} {data.provider}",
        )
        log_result = "Agent profile and credential were saved in Angmoo backend."
    else:
        log_result = "Local-mode agent profile was saved in Angmoo backend."
    agent_crud.log_activity(
        db,
        user_id=user.id,
        character_id=character.id,
        action_type="created",
        target_post_id=None,
        reason="agent_created",
        result=log_result,
    )
    db.refresh(character)
    return _build_agent_detail(db, character)






def _ensure_initial_image_settings(db: Session, character_id: str) -> None:
    setting = agent_crud.ensure_image_generation_setting(db, character_id)
    setting.image_key_mode = (
        "service" if service_image_key.is_service_image_available() else "disabled"
    )
    setting.image_generation_enabled = setting.image_key_mode != "disabled"
    db.commit()
    db.refresh(setting)












def get_agent(db: Session, user: models.User, character_id: str) -> schemas.AgentDetailRead:
    return character_management.get_agent(db, user, character_id, workflows=build_character_management_workflows())




def get_local_connection(
    db: Session, user: models.User, character_id: str
) -> schemas.AgentLocalConnectionRead:
    character = _get_owned_character(db, user, character_id)
    _ensure_local_mode(character)
    return _local_connection_read(db, character)


def issue_local_key(
    db: Session, user: models.User, character_id: str
) -> schemas.AgentLocalKeyCreateRead:
    character = _get_owned_character(db, user, character_id)
    _ensure_local_mode(character)
    token = f"{LOCAL_KEY_PREFIX}{security.create_token()}"
    key = agent_crud.create_local_key(
        db,
        user=user,
        character=character,
        token=token,
        token_prefix=_local_key_token_prefix(token),
    )
    agent_crud.log_activity(
        db,
        user_id=user.id,
        character_id=character.id,
        action_type="local_key_issued",
        target_post_id=None,
        reason="local_key_management",
        result=f"Issued local key prefix {key.token_prefix}.",
    )
    return schemas.AgentLocalKeyCreateRead(
        connection=_local_connection_read(db, character),
        token=token,
    )


def revoke_local_key(db: Session, user: models.User, character_id: str) -> None:
    character = _get_owned_character(db, user, character_id)
    _ensure_local_mode(character)
    key = agent_crud.revoke_active_local_key(db, character.id)
    if key is not None:
        agent_crud.log_activity(
            db,
            user_id=user.id,
            character_id=character.id,
            action_type="local_key_revoked",
            target_post_id=None,
            reason="local_key_management",
            result=f"Revoked local key prefix {key.token_prefix}.",
        )






async def run_first_greeting(
    db: Session,
    user: models.User,
    character_id: str,
    data: schemas.AgentFirstGreetingCreate,
) -> schemas.AgentFirstGreetingRead:
    character = _get_owned_character(db, user, character_id)
    _ensure_not_suspended(character)
    _ensure_llm_mode(character)
    _ensure_imported_world_runtime_enabled(db, character=character)
    maintenance_service.ensure_run_now_available(db)
    setting = agent_crud.ensure_setting(db, character.id)
    _ensure_tendency_analysis_ready(setting)
    if not setting.allow_post or setting.max_posts_per_day <= 0:
        raise FirstGreetingUnavailableError("게시글 작성이 꺼져 있어 첫인사를 만들 수 없습니다.")
    policy = agent_activity_policy.build_activity_policy(
        db, character_id=character.id, ignore_active_hours=True
    )
    if "post" not in policy.allowed_actions:
        reason = policy.blocked_reasons.get("post", "post writing is blocked")
        raise FirstGreetingUnavailableError(f"지금은 첫인사를 만들 수 없습니다: {reason}")
    if community_crud.character_has_authored_post(db, character.id):
        raise FirstGreetingUnavailableError("이미 이 앵무가 작성한 게시글이 있어 첫인사를 다시 만들 수 없습니다.")
    available_at = _first_greeting_available_at(db, user.id)
    if available_at is not None and available_at > datetime.now(UTC):
        raise FirstGreetingCooldownError(available_at)
    credential = agent_crud.get_character_credential(db, character.id)
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

    run_id = str(uuid4())
    session_key = (
        f"agent:onboarding-first-greeting{FIRST_GREETING_SESSION_MARKER}"
        f"{user.id}:{character.id}:{run_id}"
    )
    _claim_first_greeting_run(
        db,
        user=user,
        character=character,
        credential=credential,
        run_id=run_id,
        session_key=session_key,
    )
    tracker = RunLlmTracker()
    gateway_result: dict[str, Any] = {
        "engine": "first_greeting_writer",
        "status": "running",
        "post_id": None,
    }
    try:
        payload = await _run_first_greeting_writer(
            api_key=api_key,
            character=character,
            setting=setting,
            credential=credential,
            run_id=run_id,
            tracker=tracker,
            topic=data.topic,
        )
        post = community_service.create_post(
            db,
            user,
            schemas.PostCreate(
                title=payload.post_title,
                body=payload.post_body,
                author_character_id=character.id,
            ),
            log_manual_activity=False,
        )
        routine_runs.set_agent_run_post_id(db, run_id, post.id)
        agent_crud.log_activity(
            db,
            user_id=user.id,
            character_id=character.id,
            action_type="post_created",
            target_post_id=post.id,
            reason="onboarding_first_greeting",
            result=community_service.build_post_created_activity_result(
                post_id=post.id,
                title=post.title,
                body=post.body,
                topic_signature=payload.topic_signature,
                novelty_basis=payload.persona_basis,
                message=f"Created first greeting post {post.id}; run_id={run_id}.",
            ),
        )
        image_attempt = await _attach_first_greeting_image(
            db=db,
            character=character,
            credential=credential,
            run_id=run_id,
            tracker=tracker,
            topic=data.topic,
            post=post,
        )
        post = community_service.get_post(db, post.id)
        gateway_result = {
            "engine": "first_greeting_writer",
            "status": "completed",
            "summary": f"Created first greeting post {post.id}.",
            "post_id": post.id,
            "topic_signature": payload.topic_signature,
            "persona_basis": payload.persona_basis,
            "tendency_basis": payload.tendency_basis,
            "llm_usage_summary": tracker.summary(),
            "image_attempt": image_attempt,
        }
        routine_runs.mark_agent_run_finished(
            db, run_id, "completed", gateway_result=gateway_result
        )
        return schemas.AgentFirstGreetingRead(
            run_id=run_id,
            status="completed",
            summary=gateway_result["summary"],
            character_id=character.id,
            post_id=post.id,
            post=post,
            image_attempt=image_attempt,
            first_greeting_available_at=_first_greeting_available_at(db, user.id),
            gateway_result=gateway_result,
        )
    except DirectLlmDeferred as exc:
        gateway_result = {
            "engine": "first_greeting_writer",
            "status": "deferred",
            "summary": "Direct LLM rate-limit wait deferred.",
            "retry_at": exc.retry_at.isoformat(),
            "wait_seconds": round(exc.wait_seconds, 3),
            "llm_usage_summary": tracker.summary(),
        }
        routine_runs.mark_agent_run_finished(
            db, run_id, "deferred", gateway_result=gateway_result
        )
        raise
    except Exception as exc:
        gateway_result = {
            "engine": "first_greeting_writer",
            "status": "failed",
            "summary": "First greeting failed.",
            "failure_class": type(exc).__name__,
            "error": redact_secret_text(str(exc))[:1000],
            "llm_usage_summary": tracker.summary(),
        }
        routine_runs.mark_agent_run_finished(
            db, run_id, "failed", gateway_result=gateway_result
        )
        raise


async def _run_first_greeting_writer(
    *,
    api_key: str,
    character: character_models.Character,
    setting: models.AgentActivitySetting,
    credential: models.LlmCredential,
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
        thinking_level=settings.langgraph_post_writer_thinking_level,
    )


def _build_first_greeting_writer_prompt() -> str:
    return """You write a single first-greeting root post for an Angmoo persona.

Return only JSON matching the schema.

Rules:
- Write the post in Korean unless the persona strongly implies another language.
- Use the owner_topic as intent, not as text to copy verbatim.
- Ground the post in the character persona, speech style, worldview, interests, safety rules, and the community tendency for posting.
- This is a new root post. Do not write a reply, repost, feed reaction, relationship action, observation, or system note.
- Do not pretend to have read feeds, comments, inbox items, relationships, or memories.
- Do not mention prompts, policies, API keys, tools, hidden state, JSON, or internal systems.
- Keep the title natural and short. Keep the body public-community safe and persona-authentic.
"""


async def _attach_first_greeting_image(
    *,
    db: Session,
    character: character_models.Character,
    credential: models.LlmCredential,
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
        return post_image_generation.attach_prepared_post_image(
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


def update_profile(
    db: Session,
    user: models.User,
    character_id: str,
    data: schemas.AgentProfileUpdate,
) -> schemas.AgentDetailRead:
    return character_management.update_profile(db, user, character_id, data, workflows=build_character_management_workflows())


def _after_character_profile_updated(db, user, character, media_changed) -> schemas.AgentDetailRead:
    if media_changed:
        _invalidate_image_visual_identity_if_present(db, character.id)
    agent_crud.log_activity(
        db,
        user_id=user.id,
        character_id=character.id,
        action_type="profile_updated",
        target_post_id=None,
        reason="user_updated_profile",
        result="Agent profile display fields were updated.",
    )
    db.refresh(character)
    return _build_agent_detail(db, character)


def update_promotion_usage(
    db: Session,
    user: models.User,
    character_id: str,
    data: schemas.AgentPromotionUsageUpdate,
) -> schemas.AgentDetailRead:
    return character_management.update_promotion_usage(db, user, character_id, data, workflows=build_character_management_workflows())




def update_persona(
    db: Session,
    user: models.User,
    character_id: str,
    data: schemas.AgentPersonaUpdate,
) -> schemas.AgentDetailRead:
    return character_management.update_persona(db, user, character_id, data, workflows=build_character_management_workflows())


def _after_character_persona_updated(db, user, character) -> schemas.AgentDetailRead:
    setting = agent_crud.ensure_setting(db, character.id)
    _clear_tendency_analysis(setting)
    db.commit()
    agent_crud.log_activity(
        db,
        user_id=user.id,
        character_id=character.id,
        action_type="persona_updated",
        target_post_id=None,
        reason="user_updated_persona",
        result="Agent persona fields were updated.",
    )
    db.refresh(character)
    return _build_agent_detail(db, character)


def upload_profile_media(
    db: Session,
    user: models.User,
    character_id: str,
    data: schemas.AgentProfileMediaUpload,
) -> schemas.AgentDetailRead:
    return media_service.upload_profile_media(db, user, character_id, data, workflows=build_character_media_workflows())


def get_image_settings(
    db: Session,
    user: models.User,
    character_id: str,
) -> schemas.AgentImageGenerationSettingRead:
    character = _get_owned_character(db, user, character_id)
    return _image_generation_setting_read(
        db, agent_crud.ensure_image_generation_setting(db, character.id)
    )


def update_image_settings(
    db: Session,
    user: models.User,
    character_id: str,
    data: schemas.AgentImageGenerationSettingUpdate,
) -> schemas.AgentImageGenerationSettingRead:
    character = _get_owned_character(db, user, character_id)
    demo_lock.ensure_demo_user_mutable(user)
    if data.visual_identity_prompt is not None:
        try:
            image_prompt_safety.ensure_safe_image_text(data.visual_identity_prompt)
        except image_prompt_safety.UnsafeImagePromptError as exc:
            raise UnsafeImagePromptError(str(exc)) from exc
    setting = agent_crud.ensure_image_generation_setting(db, character.id)
    requested_mode = data.image_key_mode
    effective_model = data.pollinations_image_model or setting.pollinations_image_model
    if (
        data.pollinations_image_model is not None
        and data.pollinations_image_model not in USER_IMAGE_MODEL_OPTIONS
    ):
        raise ImageSettingsInvalidError(
            "사용자 이미지 모델은 Replicate 모델만 선택할 수 있습니다."
        )
    effective_mode = requested_mode or setting.image_key_mode
    if effective_mode == "service":
        service_model = operation_settings.get_pollinations_free_image_model(db)
        if not service_image_key.is_service_image_available_for_model(service_model):
            raise ImageSettingsInvalidError("현재 Angmoo 무료 이미지가 준비되어 있지 않습니다.")
    if effective_mode == "user":
        is_replicate = post_image_generation.image_provider.is_replicate_model(effective_model)
        has_new_key = bool(
            ((data.replicate_api_key if is_replicate else data.pollinations_api_key) or "").strip()
        )
        has_saved_key = bool(
            setting.encrypted_replicate_api_token
            if is_replicate
            else setting.encrypted_pollinations_api_key
        )
        clearing_key = (
            data.clear_replicate_api_key
            if is_replicate
            else data.clear_pollinations_api_key
        )
        if not has_new_key and (not has_saved_key or clearing_key):
            provider_label = "Replicate API token" if is_replicate else "Pollinations API key"
            raise ImageSettingsInvalidError(f"내 key를 사용하려면 {provider_label}이 필요합니다.")
    setting = agent_crud.update_image_generation_setting(
        db,
        setting,
        data,
    )
    return _image_generation_setting_read(db, setting)


def upload_image_seed(
    db: Session,
    user: models.User,
    character_id: str,
    data: schemas.AgentImageSeedUpload,
) -> schemas.AgentImageGenerationSettingRead:
    character = _get_owned_character(db, user, character_id)
    demo_lock.ensure_demo_user_mutable(user)
    setting = agent_crud.ensure_image_generation_setting(db, character.id)
    try:
        seed_image_url = profile_media.save_seed_image(
            character_id=character.id,
            content_type=data.content_type,
            data_base64=data.data_base64,
        )
    except profile_media.InvalidProfileMediaError as exc:
        raise InvalidProfileMediaError(str(exc)) from exc
    media_files.delete_media_url(setting.seed_image_url)
    setting.seed_image_url = seed_image_url
    if setting.visual_identity_source_hash is not None:
        setting.visual_identity_prompt = None
        setting.visual_identity_source_hash = None
    db.commit()
    db.refresh(setting)
    return _image_generation_setting_read(db, setting)


def delete_image_seed(
    db: Session,
    user: models.User,
    character_id: str,
) -> schemas.AgentImageGenerationSettingRead:
    character = _get_owned_character(db, user, character_id)
    demo_lock.ensure_demo_user_mutable(user)
    setting = agent_crud.ensure_image_generation_setting(db, character.id)
    media_files.delete_media_url(setting.seed_image_url)
    setting.seed_image_url = None
    if setting.visual_identity_source_hash is not None:
        setting.visual_identity_prompt = None
        setting.visual_identity_source_hash = None
    db.commit()
    db.refresh(setting)
    return _image_generation_setting_read(db, setting)


def update_credential(
    db: Session,
    user: models.User,
    character_id: str,
    data: schemas.CredentialUpsert,
) -> schemas.CredentialRead:
    character = _get_owned_character(db, user, character_id)
    demo_lock.ensure_demo_user_mutable(user)
    _ensure_llm_mode(character)
    _ensure_credential_world_scope(
        db,
        user=user,
        character=character,
        world_id=data.world_id,
    )
    current_assigned_slot = slot_queries.get_assigned_slot(db, character.id)
    if (
        current_assigned_slot is not None
        and current_assigned_slot.status == routine_constants.SLOT_STATUS_RUNNING
    ):
        raise ActiveSlotBusyError(
            "앵무가 지금 활동 중이라 API key 또는 모델을 바꿀 수 없습니다. 활동이 끝난 뒤 다시 시도해주세요."
        )
    try:
        if data.api_key is not None:
            credential = agent_crud.upsert_credential(
                db,
                user=user,
                character=character,
                provider=data.provider,
                model=data.model,
                api_key=data.api_key,
                auth_profile_id=None,
                label=data.label,
                commit=current_assigned_slot is None,
            )
            if current_assigned_slot is not None:
                if _resident_openclaw_sync_enabled():
                    _bind_slot_auth_profile(
                        schemas.AgentSlotRead.model_validate(current_assigned_slot),
                        user_id=user.id,
                        character=character,
                        credential=credential,
                    )
                    _reload_openclaw_secrets_sync()
                db.commit()
                db.refresh(credential)
        else:
            credential = agent_crud.get_character_credential(db, character.id)
            if credential is None or not credential.encrypted_api_key:
                raise CredentialRequiredError(
                    "Agent credential key is required before changing the model"
                )
            if credential.provider != data.provider:
                raise CredentialRequiredError(
                    "API key is required before changing the credential provider"
                )
            credential.model = data.model
            if data.label is not None:
                credential.label = data.label
            credential.enabled = True
            db.commit()
            db.refresh(credential)
    except Exception:
        db.rollback()
        raise
    agent_crud.log_activity(
        db,
        user_id=user.id,
        character_id=character.id,
        action_type="credential_saved",
        target_post_id=None,
        reason="credential_saved",
        result="Credential profile was synchronized for this character.",
    )
    return schemas.CredentialRead.model_validate(credential)


def get_credential_metadata(
    db: Session,
    user: models.User,
    character_id: str,
    *,
    world_id: str | None = None,
) -> schemas.CredentialRead | None:
    character = _get_owned_character(db, user, character_id)
    _ensure_llm_mode(character)
    _ensure_credential_world_scope(
        db,
        user=user,
        character=character,
        world_id=world_id,
    )
    credential = agent_crud.get_character_credential(db, character.id)
    if credential is None:
        return None
    if credential.owner_id != user.id:
        raise AgentNotFoundError(character_id)
    return schemas.CredentialRead.model_validate(credential)


def delete_credential(
    db: Session,
    user: models.User,
    character_id: str,
    *,
    world_id: str | None = None,
) -> None:
    character = _get_owned_character(db, user, character_id)
    demo_lock.ensure_demo_user_mutable(user)
    _ensure_llm_mode(character)
    _ensure_credential_world_scope(
        db,
        user=user,
        character=character,
        world_id=world_id,
    )
    credential = agent_crud.get_character_credential(db, character.id)
    if credential is None or (
        not credential.enabled
        and credential.encrypted_api_key is None
        and credential.key_fingerprint is None
    ):
        return

    assigned_slot = slot_queries.get_assigned_slot(db, character.id)
    if (
        assigned_slot is not None
        and assigned_slot.status == routine_constants.SLOT_STATUS_RUNNING
    ):
        raise ActiveSlotBusyError(
            "앵무가 지금 활동 중이라 API key를 삭제할 수 없습니다. 활동이 끝난 뒤 다시 시도해주세요."
        )

    try:
        if assigned_slot is not None and _resident_openclaw_sync_enabled():
            _release_slot_auth_profile(
                assigned_slot,
                user_id=user.id,
                character_id=character.id,
                credential=credential,
            )
            _reload_openclaw_secrets_sync()
        slot_assignments.release_resident_slot_assignment(
            db,
            user_id=user.id,
            character_id=character.id,
            commit=False,
        )
        setting = db.get(models.AgentActivitySetting, character.id)
        if setting is not None:
            setting.auto_enabled = False
        set_active_world_character_autonomy(
            db,
            character_id=character.id,
            enabled=False,
        )
        character.status = "inactive"
        credential.enabled = False
        credential.encrypted_api_key = None
        credential.key_fingerprint = None
        credential.cooldown_until = None
        db.commit()
    except Exception:
        db.rollback()
        raise


def _ensure_credential_world_scope(
    db: Session,
    *,
    user: models.User,
    character: character_models.Character,
    world_id: str | None,
) -> None:
    if world_id is None:
        return
    membership_id = db.scalar(
        select(models.WorldMembership.id).where(
            models.WorldMembership.world_id == world_id,
            models.WorldMembership.user_id == user.id,
            models.WorldMembership.status == "active",
        )
    )
    if membership_id is None:
        raise AgentNotFoundError(character.id)
    world_character_id = db.scalar(
        select(models.WorldCharacter.id).where(
            models.WorldCharacter.world_id == world_id,
            models.WorldCharacter.character_id == character.id,
            models.WorldCharacter.membership_id == membership_id,
            models.WorldCharacter.status.in_(("pending", "inactive", "active")),
        )
    )
    if world_character_id is None:
        raise AgentNotFoundError(character.id)






async def analyze_tendency(
    db: Session, user: models.User, character_id: str
) -> schemas.AgentDetailRead:
    character = _get_owned_character(db, user, character_id)
    demo_lock.ensure_demo_user_mutable(user)
    _ensure_llm_mode(character)
    _ensure_imported_world_runtime_enabled(db, character=character)
    setting = agent_crud.ensure_setting(db, character.id)
    credential = agent_crud.get_character_credential(db, character.id)
    if credential is None or not credential.enabled:
        _mark_tendency_error(
            db, setting, "Agent credential is required before tendency analysis"
        )
        raise CredentialRequiredError(
            "Agent credential is required before tendency analysis"
        )

    if settings.server_llm_engine == "direct":
        run_id = str(uuid4())
        try:
            material = CredentialResolver.resolve_llm_credential(
                credential,
                purpose=CredentialPurpose.RESIDENT_LLM,
                owner_id=user.id,
                character_id=character.id,
            )
            api_key = material.reveal()
            tracker = RunLlmTracker()

            def _validator(payload: dict[str, Any]) -> dict[str, Any]:
                return _TendencyAnalysisPayload.model_validate(payload).model_dump()

            payload = await generate_json(
                api_key=api_key,
                context=DirectLlmCallContext(
                    credential_id=credential.id,
                    character_id=character.id,
                    agent_run_id=run_id,
                    node="TendencyAnalysis",
                    lane="server_llm",
                    provider=credential.provider,
                    model=credential.model,
                    key_fingerprint=credential.key_fingerprint,
                ),
                tracker=tracker,
                system_prompt=_build_tendency_analysis_prompt(character=character),
                user_prompt=(
                    "Analyze this Angmoo persona for community activity. "
                    "Return only the requested JSON object."
                ),
                response_schema=_TendencyAnalysisPayload,
                validator=_validator,
                max_output_tokens=TENDENCY_ANALYSIS_MAX_OUTPUT_TOKENS,
                thinking_level=settings.tendency_analysis_thinking_level,
            )
            summary, action_ranges, planner_profile = _normalize_tendency_payload(payload)
            setting.tendency_summary = summary
            setting.tendency_action_ranges = action_ranges
            setting.planner_tendency_profile = planner_profile
            setting.tendency_updated_at = datetime.now(UTC)
            setting.tendency_error = None
            db.commit()
            db.refresh(setting)
            agent_crud.log_activity(
                db,
                user_id=user.id,
                character_id=character.id,
                action_type="tendency_analyzed",
                target_post_id=None,
                reason="user_requested_tendency_analysis_direct",
                result=(
                    "Community activity tendency was analyzed with direct LLM; "
                    f"llm_call_count={tracker.summary().get('call_count', 0)}."
                ),
            )
            db.refresh(character)
            return _build_agent_detail(db, character)
        except ValueError as exc:
            message = "Agent credential key cannot be decrypted"
            _mark_tendency_error(db, setting, message)
            raise CredentialRequiredError(message) from exc
        except DirectLlmError as exc:
            message = redact_secret_text(str(exc))[:1000]
            _mark_tendency_error(db, setting, message)
            raise

    token = settings.openclaw_gateway_token
    if token is None:
        _mark_tendency_error(db, setting, "OPENCLAW_GATEWAY_TOKEN is missing")
        raise agent_run_service.OpenClawNotConfiguredError(
            "OPENCLAW_GATEWAY_TOKEN is missing"
        )

    run_id = str(uuid4())
    timeout_seconds = settings.openclaw_timeout_seconds
    slot = slot_pool.claim_agent_slot(
        db,
        run_id=run_id,
        agent_ids=settings.openclaw_agent_ids,
        lease_seconds=timeout_seconds + 90,
    )
    if slot is None:
        raise agent_run_service.AgentSlotUnavailableError(
            f"No OpenClaw slot is available for {', '.join(settings.openclaw_agent_ids)}"
        )

    bound_profile = False
    last_error: str | None = None
    client = OpenClawGatewayClient(
        url=settings.openclaw_gateway_url,
        token=token,
        timeout_seconds=timeout_seconds,
    )
    try:
        _bind_slot_auth_profile(
            slot, user_id=user.id, character=character, credential=credential
        )
        bound_profile = True
        await client.reload_secrets()
        gateway_result = await client.run_agent(
            message="Analyze this Angmoo persona for community activity. Return only JSON.",
            agent_id=slot.agent_id,
            session_key=(
                f"agent:{slot.agent_id}:angmoo:tendency:{user.id}:{character.id}:{run_id}"
            ),
            provider=credential.provider,
            model=credential.model,
            auth_profile_id=credential.auth_profile_id,
            tool_choice="none",
            tools_allow=TENDENCY_LLM_TOOLS_ALLOW,
            prompt_mode="minimal",
            bootstrap_context_mode="lightweight",
            bootstrap_context_run_kind="default",
            idempotency_key=run_id,
            thinking=settings.tendency_analysis_thinking_level,
            extra_system_prompt=_build_tendency_analysis_prompt(character=character),
        )
        raw_text = _extract_gateway_result_text(gateway_result)
        payload = _parse_tendency_json(raw_text)
        summary, action_ranges, planner_profile = _normalize_tendency_payload(payload)
        setting.tendency_summary = summary
        setting.tendency_action_ranges = action_ranges
        setting.planner_tendency_profile = planner_profile
        setting.tendency_updated_at = datetime.now(UTC)
        setting.tendency_error = None
        db.commit()
        db.refresh(setting)
        agent_crud.log_activity(
            db,
            user_id=user.id,
            character_id=character.id,
            action_type="tendency_analyzed",
            target_post_id=None,
            reason="user_requested_tendency_analysis",
            result="Community activity tendency was analyzed with the user's API key.",
        )
        db.refresh(character)
        return _build_agent_detail(db, character)
    except OpenClawGatewayError as exc:
        friendly_error = llm_credential_error_message(exc)
        if friendly_error is not None:
            last_error = friendly_error
            _mark_tendency_error(db, setting, friendly_error)
            raise LlmCredentialInvalidError(friendly_error) from exc
        last_error = redact_secret_text(str(exc))
        _mark_tendency_error(db, setting, last_error)
        raise
    except Exception as exc:
        last_error = redact_secret_text(str(exc))
        _mark_tendency_error(db, setting, last_error)
        raise
    finally:
        release_error = None
        if bound_profile:
            try:
                _release_slot_auth_profile(
                    slot,
                    user_id=user.id,
                    character_id=character.id,
                    credential=credential,
                )
                await client.reload_secrets()
            except CredentialSyncError as exc:
                release_error = redact_secret_text(str(exc))
                if last_error is None:
                    last_error = release_error
                    _mark_tendency_error(db, setting, release_error)
            except OpenClawGatewayError as exc:
                release_error = redact_secret_text(str(exc))
                if last_error is None:
                    last_error = release_error
                    _mark_tendency_error(db, setting, release_error)
        slot_pool.release_agent_slot(
            db, agent_id=slot.agent_id, run_id=run_id, last_error=last_error
        )
        if release_error is not None and last_error == release_error:
            raise CredentialSyncError(release_error)








def delete_agent(
    db: Session, user: models.User, character_id: str, data: schemas.AgentDeleteCreate
) -> None:
    character = _get_owned_character(db, user, character_id)
    demo_lock.ensure_demo_user_mutable(user)
    if data.confirmation != character.name:
        raise AgentDeleteConfirmationError("Confirmation name does not match")

    _ensure_agent_deletion_not_busy(db, user_id=user.id, character_id=character.id)
    media_quarantine = _quarantine_agent_private_media(db, user.id, character.id)
    try:
        if _resident_openclaw_sync_enabled():
            _release_openclaw_profile_for_agent(
                db, user_id=user.id, character_id=character.id
            )
        _clear_resident_slots_for_agent(db, user_id=user.id, character_id=character.id)
        _scrub_agent_data(db, character)
        db.commit()
    except Exception:
        db.rollback()
        try:
            media_quarantine.restore()
        except media_files.PrivateMediaCleanupError as restore_exc:
            raise AgentDeletionMediaCleanupError(
                "private_media_restore_failed"
            ) from restore_exc
        raise
    try:
        media_quarantine.purge()
    except media_files.PrivateMediaCleanupError as exc:
        raise AgentDeletionMediaCleanupError("private_media_purge_failed") from exc


def _quarantine_agent_private_media(
    db: Session, user_id: str, character_id: str
) -> media_files.PrivateMediaQuarantine:
    candidate_ids = list(
        db.scalars(
            select(character_models.ProfileImageCandidate.id).where(
                character_models.ProfileImageCandidate.character_id == character_id
            )
        )
    )
    media_root = settings.media_root_path
    paths = [media_root / "characters" / character_id]
    paths.extend(
        media_root / "profile-candidates" / user_id / candidate_id
        for candidate_id in candidate_ids
    )
    return media_files.quarantine_private_media(paths)




























def _activity_profile_readiness(
    db: Session,
    *,
    character: character_models.Character,
    setting: models.AgentActivitySetting,
) -> schemas.AgentActivityProfileReadinessRead:
    return activity_profile_readiness.evaluate(
        db,
        character=character,
        setting=setting,
    )






def _resident_openclaw_sync_enabled() -> bool:
    return settings.agent_activity_engine == "openclaw"


def _bind_slot_auth_profile(
    slot: schemas.AgentSlotRead,
    *,
    user_id: str,
    character: character_models.Character,
    credential: models.LlmCredential,
) -> None:
    try:
        material = CredentialResolver.resolve_llm_credential(
            credential,
            purpose=CredentialPurpose.PRIVATE_OPENCLAW,
            owner_id=user_id,
            character_id=character.id,
        )
        openclaw_auth_profiles.bind_credential_to_slot(
            agent_id=slot.agent_id,
            user_id=user_id,
            character_id=character.id,
            credential=credential,
            api_key=material.reveal(),
        )
    except CredentialResolutionError as exc:
        raise CredentialRequiredError("Agent credential key cannot be decrypted") from exc
    except openclaw_auth_profiles.OpenClawAuthProfileSyncError as exc:
        raise CredentialSyncError(str(exc)) from exc


def _release_slot_auth_profile(
    slot: models.AgentSlot,
    *,
    user_id: str,
    character_id: str,
    credential: models.LlmCredential,
) -> None:
    try:
        openclaw_auth_profiles.release_credential_from_slot(
            agent_id=slot.agent_id,
            user_id=user_id,
            character_id=character_id,
            credential=credential,
        )
    except openclaw_auth_profiles.OpenClawAuthProfileSyncError as exc:
        raise CredentialSyncError(str(exc)) from exc


def _reload_openclaw_secrets_sync() -> None:
    token = settings.openclaw_gateway_token
    if token is None:
        return
    try:
        OpenClawGatewayClient(
            url=settings.openclaw_gateway_url,
            token=token,
            timeout_seconds=settings.openclaw_timeout_seconds,
        ).reload_secrets_sync()
    except OpenClawGatewayError as exc:
        raise CredentialSyncError(str(exc)) from exc




















def _ensure_imported_world_runtime_enabled(
    db: Session,
    *,
    character: character_models.Character,
) -> None:
    """Keep an imported World inert until its explicit autonomy enable step.

    A normal local character may use the user-initiated Run-now path while
    scheduled autonomy is disabled.  World Package imports have a stricter
    activation contract: their seeded runtime must not enter P5-P7 before the
    user completes setup and explicitly enables autonomy.  Scope the guard to
    the active World when one exists so another, direct-created World owned by
    the same character is not affected.
    """

    if agent_activity_policy.is_imported_world_runtime_locked_for_character(
        db, character_id=character.id
    ):
        raise AgentExecutionModeError(
            "가져온 World는 자율활동을 먼저 켠 뒤 지금 한 번 활동을 실행할 수 있어요."
        )




def _local_connection_read(
    db: Session, character: character_models.Character
) -> schemas.AgentLocalConnectionRead:
    active_key = agent_crud.get_active_local_key(db, character.id)
    key = active_key or agent_crud.get_latest_local_key(db, character.id)
    return schemas.AgentLocalConnectionRead(
        character_id=character.id,
        execution_mode=character.execution_mode,  # type: ignore[arg-type]
        has_active_key=active_key is not None,
        token_prefix=key.token_prefix if key else None,
        last_used_at=key.last_used_at if key else None,
        created_at=key.created_at if key else None,
        revoked_at=key.revoked_at if key else None,
    )


def _local_key_token_prefix(token: str) -> str:
    return f"{token[:24]}..."


def _agent_deletion_slot_condition(db: Session, *, user_id: str, character_id: str):
    credential_ids = list(
        db.scalars(
            select(models.LlmCredential.id).where(
                models.LlmCredential.owner_id == user_id,
                models.LlmCredential.character_id == character_id,
            )
        )
    )
    conditions = [models.AgentSlot.assigned_character_id == character_id]
    if credential_ids:
        conditions.append(models.AgentSlot.assigned_credential_id.in_(credential_ids))
    return or_(*conditions) if len(conditions) > 1 else conditions[0]


def _ensure_agent_deletion_not_busy(
    db: Session, *, user_id: str, character_id: str
) -> None:
    active_run_id = db.scalar(
        select(models.AgentRun.id)
        .where(
            models.AgentRun.user_id == user_id,
            models.AgentRun.character_id == character_id,
            models.AgentRun.status.in_(routine_constants.ACTIVE_RUN_STATUSES),
        )
        .limit(1)
    )
    if active_run_id is not None:
        raise ActiveSlotBusyError(
            "앵무가 지금 활동 중이라 삭제할 수 없습니다. 잠시 뒤 다시 시도해주세요."
        )

    running_slot_id = db.scalar(
        select(models.AgentSlot.agent_id)
        .where(
            _agent_deletion_slot_condition(
                db, user_id=user_id, character_id=character_id
            ),
            models.AgentSlot.status == routine_constants.SLOT_STATUS_RUNNING,
        )
        .limit(1)
    )
    if running_slot_id is not None:
        raise ActiveSlotBusyError(
            "앵무가 지금 활동 중이라 삭제할 수 없습니다. 잠시 뒤 다시 시도해주세요."
        )


def _release_openclaw_profile_for_agent(
    db: Session, *, user_id: str, character_id: str
) -> None:
    slots = list(
        db.scalars(
            select(models.AgentSlot)
            .where(
                _agent_deletion_slot_condition(
                    db, user_id=user_id, character_id=character_id
                )
            )
            .order_by(models.AgentSlot.agent_id.asc())
        )
    )
    released = False
    for slot in slots:
        if slot.status == routine_constants.SLOT_STATUS_RUNNING:
            raise ActiveSlotBusyError(
                "앵무가 지금 활동 중이라 삭제할 수 없습니다. 잠시 뒤 다시 시도해주세요."
            )
        if slot.assigned_credential_id is None:
            continue
        credential = db.get(models.LlmCredential, slot.assigned_credential_id)
        if credential is None:
            continue
        try:
            _release_slot_auth_profile(
                slot,
                user_id=user_id,
                character_id=character_id,
                credential=credential,
            )
        except CredentialSyncError as exc:
            raise AgentDeletionCredentialSyncError(str(exc)) from exc
        released = True
    if released:
        try:
            _reload_openclaw_secrets_sync()
        except CredentialSyncError as exc:
            raise AgentDeletionCredentialSyncError(str(exc)) from exc


def _clear_resident_slots_for_agent(
    db: Session, *, user_id: str, character_id: str
) -> None:
    slots = list(
        db.scalars(
            select(models.AgentSlot)
            .where(
                _agent_deletion_slot_condition(
                    db, user_id=user_id, character_id=character_id
                )
            )
            .order_by(models.AgentSlot.agent_id.asc())
        )
    )
    for slot in slots:
        if slot.status == routine_constants.SLOT_STATUS_RUNNING:
            raise ActiveSlotBusyError(
                "앵무가 지금 활동 중이라 삭제할 수 없습니다. 잠시 뒤 다시 시도해주세요."
            )
        slot.status = routine_constants.SLOT_STATUS_EMPTY
        slot.assigned_user_id = None
        slot.assigned_character_id = None
        slot.assigned_credential_id = None
        slot.next_tick_at = None
        slot.last_run_at = None
        slot.heartbeat_interval_seconds = None
        slot.locked_by_run_id = None
        slot.lease_expires_at = None
        slot.last_error = None


def _scrub_agent_data(db: Session, character: character_models.Character) -> None:
    now = datetime.now(UTC)
    character_id = character.id

    from app.runtime.world_characters import cleanup as world_character_setup
    from app.runtime.memory_privacy import scrub_memory_data

    scrub_memory_data(db, owner_id=character.owner_id, character_id=character_id)

    world_character_setup.delete_setup_data_for_characters(
        db, character_ids=[character_id]
    )

    candidate_rows = list(
        db.execute(
            select(
                character_models.ProfileImageCandidate.id,
                character_models.ProfileImageCandidate.quota_reservation_id,
            ).where(character_models.ProfileImageCandidate.character_id == character_id)
        )
    )
    candidate_ids = [row.id for row in candidate_rows]
    candidate_reservation_ids = [
        row.quota_reservation_id
        for row in candidate_rows
        if row.quota_reservation_id is not None
    ]
    if candidate_ids:
        db.execute(
            delete(character_models.ProfileImageCandidate).where(
                character_models.ProfileImageCandidate.id.in_(candidate_ids)
            )
        )
    if candidate_reservation_ids:
        db.execute(
            delete(character_models.ProfileImageQuotaReservation).where(
                character_models.ProfileImageQuotaReservation.id.in_(candidate_reservation_ids)
            )
        )

    message_thread_ids = select(models.MessageThread.id).where(
        models.MessageThread.character_id == character_id
    )
    db.execute(
        delete(models.MessageMessage).where(
            models.MessageMessage.thread_id.in_(message_thread_ids)
        )
    )
    db.execute(
        delete(models.MessageThread).where(
            models.MessageThread.character_id == character_id
        )
    )
    db.execute(
        update(models.UserMessagePreference)
        .where(models.UserMessagePreference.source_character_id == character_id)
        .values(credential_source="message_key", source_character_id=None)
    )
    db.execute(
        delete(models.CharacterMessageSetting).where(
            models.CharacterMessageSetting.character_id == character_id
        )
    )

    lore_source_ids = select(models.CharacterLoreSource.id).where(
        models.CharacterLoreSource.character_id == character_id
    )
    db.execute(
        delete(models.CharacterLoreChunk).where(
            or_(
                models.CharacterLoreChunk.character_id == character_id,
                models.CharacterLoreChunk.source_id.in_(lore_source_ids),
            )
        )
    )
    db.execute(
        delete(models.CharacterLoreSource).where(
            models.CharacterLoreSource.character_id == character_id
        )
    )

    db.execute(
        delete(models.PostImageGenerationJob).where(
            models.PostImageGenerationJob.character_id == character_id
        )
    )
    db.execute(
        delete(models.PostImageQuotaReservation).where(
            models.PostImageQuotaReservation.character_id == character_id
        )
    )
    db.execute(
        delete(models.AgentPublicActionExecution).where(
            models.AgentPublicActionExecution.character_id == character_id
        )
    )
    db.execute(
        delete(models.AgentDaypartMemoryEvent).where(
            models.AgentDaypartMemoryEvent.character_id == character_id
        )
    )
    db.execute(
        delete(models.AgentRelationshipPoint).where(
            or_(
                models.AgentRelationshipPoint.recipient_character_id == character_id,
                models.AgentRelationshipPoint.source_character_id == character_id,
            )
        )
    )

    db.execute(
        delete(models.AgentFeedCue).where(models.AgentFeedCue.character_id == character_id)
    )
    db.execute(
        delete(models.AgentActivityLog).where(
            models.AgentActivityLog.character_id == character_id
        )
    )
    db.execute(delete(models.AgentRun).where(models.AgentRun.character_id == character_id))
    db.execute(delete(models.PostLike).where(models.PostLike.character_id == character_id))
    db.execute(
        delete(models.PostRepost).where(models.PostRepost.character_id == character_id)
    )
    db.execute(
        delete(models.ProfileFollow).where(
            or_(
                models.ProfileFollow.follower_character_id == character_id,
                models.ProfileFollow.target_character_id == character_id,
            )
        )
    )
    db.execute(
        delete(models.Notification).where(
            or_(
                models.Notification.recipient_character_id == character_id,
                models.Notification.actor_character_id == character_id,
            )
        )
    )
    db.execute(
        update(models.Post)
        .where(models.Post.author_character_id == character_id)
        .values(author_name=DELETED_CHARACTER_NAME)
    )
    db.execute(
        delete(character_models.CharacterState).where(
            character_models.CharacterState.character_id == character_id
        )
    )
    db.execute(
        delete(models.AgentActivitySetting).where(
            models.AgentActivitySetting.character_id == character_id
        )
    )
    db.execute(
        delete(models.AgentImageGenerationSetting).where(
            models.AgentImageGenerationSetting.character_id == character_id
        )
    )
    db.execute(
        delete(models.LlmCredential).where(
            models.LlmCredential.character_id == character_id
        )
    )
    db.execute(
        delete(models.AgentLocalKey).where(
            models.AgentLocalKey.character_id == character_id
        )
    )

    character.name = DELETED_CHARACTER_NAME
    character.handle = _deleted_character_handle(db, character.id)
    character.avatar_url = None
    character.banner_url = None
    character.one_liner = DELETED_CHARACTER_PLACEHOLDER
    character.personality = ""
    character.speech_style = ""
    character.worldview = ""
    character.topic_preferences = ""
    character.safety_rules = ""
    character.status = "inactive"
    character.persona_summary = DELETED_CHARACTER_PLACEHOLDER
    character.deleted_at = now


def _deleted_character_handle(db: Session, character_id: str) -> str:
    suffix = "".join(
        char.lower() for char in character_id if char.isalnum() or char in {"-", "_"}
    )
    suffix = suffix[-31:] or uuid4().hex[:12]
    base = f"deleted-{suffix}"[:40]
    candidate = base
    index = 2
    while db.scalar(
        select(character_models.Character.id).where(
            character_models.Character.handle == candidate,
            character_models.Character.id != character_id,
        )
    ):
        suffix_text = f"_{index}"
        candidate = f"{base[: 40 - len(suffix_text)]}{suffix_text}"
        index += 1
    return candidate




def _first_greeting_available_at(db: Session, user_id: str) -> datetime | None:
    latest_run = routine_run_queries.get_latest_first_greeting_run_for_user(db, user_id)
    if latest_run is None:
        return None
    created_at = latest_run.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at + FIRST_GREETING_COOLDOWN


def _claim_first_greeting_run(
    db: Session,
    *,
    user: models.User,
    character: character_models.Character,
    credential: models.LlmCredential,
    run_id: str,
    session_key: str,
    now: datetime | None = None,
) -> models.AgentRun:
    current = now or datetime.now(UTC)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        lock_key = int.from_bytes(
            hashlib.sha256(
                f"angmoo:first-greeting:{user.id}:v1".encode("utf-8")
            ).digest()[:8],
            byteorder="big",
            signed=True,
        )
        db.execute(
            text("select pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )
    if community_crud.character_has_authored_post(db, character.id):
        raise FirstGreetingUnavailableError(
            "이미 이 앵무가 작성한 게시글이 있어 첫인사를 다시 만들 수 없습니다."
        )
    available_at = _first_greeting_available_at(db, user.id)
    if available_at is not None and available_at > current:
        raise FirstGreetingCooldownError(available_at)
    return routine_runs.create_agent_run(
        db,
        run_id=run_id,
        user_id=user.id,
        character_id=character.id,
        post_id=None,
        credential_id=credential.id,
        agent_id="onboarding-first-greeting",
        session_key=session_key,
        tool_auth_key=None,
    )


def _visible_activity_actions(actions: Iterable[str]) -> list[str]:
    return [action for action in actions if action != "observe"]


def _build_agent_detail(
    db: Session, character: character_models.Character, *, recent_activity_limit: int = 20
) -> schemas.AgentDetailRead:
    setting = agent_crud.ensure_setting(db, character.id)
    credential = agent_crud.get_character_credential(db, character.id)
    slot = slot_queries.get_assigned_slot(db, character.id)
    recent_activity = agent_crud.list_recent_activity(
        db, character.id, limit=recent_activity_limit
    )
    policy = agent_activity_policy.build_activity_policy(db, character_id=character.id)
    last_activity_at = recent_activity[0].created_at if recent_activity else None
    manual_run_available_at = (
        _manual_run_available_at(db, character.owner_id) if character.owner_id else None
    )
    first_greeting_available_at = (
        _first_greeting_available_at(db, character.owner_id)
        if character.owner_id
        else None
    )
    return schemas.AgentDetailRead(
        character=schemas.CharacterRead.model_validate(character),
        state=(
            schemas.CharacterStateRead.model_validate(character.state)
            if character.state
            else None
        ),
        credential=(
            schemas.CredentialRead.model_validate(credential) if credential else None
        ),
        settings=schemas.AgentActivitySettingRead.model_validate(setting),
        image_settings=_image_generation_setting_read(
            db,
            agent_crud.ensure_image_generation_setting(db, character.id)
        ),
        promotion_usage=_promotion_usage_read(character),
        assigned_slot=schemas.AgentSlotRead.model_validate(slot) if slot else None,
        activity_profile_readiness=_activity_profile_readiness(
            db,
            character=character,
            setting=setting,
        ),
        activity_summary=schemas.AgentActivitySummaryRead(
            within_active_hours=policy.within_active_hours,
            timezone=agent_activity_policy.activity_timezone_name(
                db, character_id=character.id
            ),
            allowed_actions=_visible_activity_actions(policy.allowed_actions),
            blocked_reasons=policy.blocked_reasons,
            last_activity_at=last_activity_at,
            next_activity_at=(
                slot.next_tick_at if slot is not None and setting.auto_enabled else None
            ),
            manual_run_available_at=manual_run_available_at,
            first_greeting_available_at=first_greeting_available_at,
            today_comment_count=agent_activity_policy.count_action_today(
                db, character_id=character.id, action="comment"
            ),
            max_comments_per_day=setting.max_comments_per_day,
            today_post_count=agent_activity_policy.count_action_today(
                db, character_id=character.id, action="post"
            ),
            max_posts_per_day=setting.max_posts_per_day,
            today_like_count=agent_activity_policy.count_action_today(
                db, character_id=character.id, action="like"
            ),
        ),
        recent_activity=[
            _activity_log_read(db, log) for log in recent_activity
        ],
    )


def _image_generation_setting_read(
    db: Session,
    setting: models.AgentImageGenerationSetting,
) -> schemas.AgentImageGenerationSettingRead:
    visual_identity_prompt = (setting.visual_identity_prompt or "").strip() or None
    visual_identity_mode: Literal["manual", "auto", "none"]
    if visual_identity_prompt is None:
        visual_identity_mode = "none"
    elif setting.visual_identity_source_hash is None:
        visual_identity_mode = "manual"
    else:
        visual_identity_mode = "auto"
    quota = _service_image_quota_read(db, setting.character_id)
    service_model_setting = operation_settings.get_pollinations_free_image_model_setting(db)
    service_model = service_model_setting.model
    return schemas.AgentImageGenerationSettingRead(
        character_id=setting.character_id,
        image_key_mode=setting.image_key_mode,
        image_generation_enabled=setting.image_generation_enabled,
        max_images_per_day=setting.max_images_per_day,
        pollinations_image_model=setting.pollinations_image_model,
        seed_image_url=setting.seed_image_url,
        key_fingerprint=(
            setting.key_fingerprint
            if setting.encrypted_pollinations_api_key
            else None
        ),
        has_pollinations_api_key=bool(setting.encrypted_pollinations_api_key),
        replicate_key_fingerprint=(
            setting.replicate_key_fingerprint
            if setting.encrypted_replicate_api_token
            else None
        ),
        has_replicate_api_key=bool(setting.encrypted_replicate_api_token),
        visual_identity_prompt_available=visual_identity_prompt is not None,
        visual_identity_prompt=visual_identity_prompt,
        visual_identity_mode=visual_identity_mode,
        visual_identity_source_hash=setting.visual_identity_source_hash,
        service_image_available=service_image_key.is_service_image_available_for_model(
            service_model
        ),
        service_image_model=service_model,
        service_image_model_label=operation_settings.pollinations_free_image_model_label(
            service_model
        ),
        service_free_quota_limit=quota["limit"],
        service_free_quota_used=quota["used"],
        service_free_quota_remaining=quota["remaining"],
        service_free_quota_date=quota["date"],
        updated_at=setting.updated_at,
    )


def _service_image_quota_read(db: Session, character_id: str) -> dict[str, int | str]:
    quota_date = datetime.now(agent_activity_policy.APP_TIMEZONE).date()
    limit = settings.pollinations_service_free_images_per_user_day
    character = db.get(character_models.Character, character_id)
    used = (
        community_crud.count_service_image_quota_used(
            db,
            user_id=character.owner_id,
            quota_date=quota_date,
        )
        if character is not None
        else 0
    )
    return {
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "date": quota_date.isoformat(),
    }


def _invalidate_image_visual_identity_if_present(db: Session, character_id: str) -> None:
    setting = agent_crud.get_image_generation_setting(db, character_id)
    if setting is None:
        return
    if setting.visual_identity_source_hash is None:
        return
    setting.visual_identity_prompt = None
    setting.visual_identity_source_hash = None




def _activity_log_read(
    db: Session, log: models.AgentActivityLog
) -> schemas.AgentActivityLogRead:
    data = schemas.AgentActivityLogRead.model_validate(log).model_dump()
    target = _activity_log_target_profile(db, log)
    if target is not None:
        data.update(target)
    return schemas.AgentActivityLogRead.model_validate(data)


def _activity_log_target_profile(
    db: Session, log: models.AgentActivityLog
) -> dict[str, str | None] | None:
    if log.action_type not in {"followed", "unfollowed"}:
        return None
    match = re.search(r"\b(user|character):([A-Za-z0-9_-]+)", log.result)
    if match is None:
        return None
    profile_type, profile_id = match.group(1), match.group(2)
    if profile_type == "character":
        character = db.get(character_models.Character, profile_id)
        if character is None:
            return None
        return {
            "target_profile_type": "character",
            "target_profile_id": character.id,
            "target_profile_name": character.name,
            "target_profile_handle": character.handle,
            "target_profile_avatar_url": character.avatar_url,
        }
    user = db.get(models.User, profile_id)
    if user is None:
        return None
    return {
        "target_profile_type": "user",
        "target_profile_id": user.id,
        "target_profile_name": user.display_name,
        "target_profile_handle": None,
        "target_profile_avatar_url": None,
    }


def build_character_management_workflows() -> CharacterManagementWorkflows:
    """Bind the current runtime callbacks (also honoring caller/test overrides)."""
    return CharacterManagementWorkflows(
        validate_initial_activity=partial(activity_management._validate_initial_activity_settings, invalid_active_hours=AgentActiveHoursInvalidError),
        after_create=_after_character_created,
        build_detail=_build_agent_detail,
        build_full_detail=_build_full_character_detail,
        after_profile=_after_character_profile_updated,
        after_persona=_after_character_persona_updated,
    )


def _build_full_character_detail(db: Session, character: character_models.Character) -> schemas.AgentDetailRead:
    return _build_agent_detail(db, character, recent_activity_limit=AGENT_DETAIL_ACTIVITY_LIMIT)


def build_character_media_workflows():
    from app.domains.characters.contracts import CharacterMediaWorkflows

    return CharacterMediaWorkflows(
        invalidate_visual_identity=_invalidate_image_visual_identity_if_present,
        log_activity=agent_crud.log_activity,
        build_detail=_build_agent_detail,
    )


def build_activity_management_references() -> ActivityManagementReferences:
    return ActivityManagementReferences(
        get_owned_character=_get_owned_character,
        ensure_mutable=demo_lock.ensure_demo_user_mutable,
        is_local_mode=_is_local_mode,
        execution_mode_error=AgentExecutionModeError,
        active_hours_error=AgentActiveHoursInvalidError,
        local_mode_message=LOCAL_MODE_LLM_BLOCKED_MESSAGE,
        timezone_reader=agent_activity_policy.activity_timezone,
    )


def get_settings(db: Session, user: models.User, character_id: str) -> schemas.AgentActivitySettingRead:
    return activity_management.get_settings(db, user, character_id, references=build_activity_management_references())


def update_settings(db: Session, user: models.User, character_id: str, data: schemas.AgentActivitySettingUpdate) -> schemas.AgentActivitySettingRead:
    return activity_management.update_settings(db, user, character_id, data, references=build_activity_management_references())


def build_autonomy_workflows() -> AutonomyWorkflows[schemas.AgentDetailRead]:
    return AutonomyWorkflows(
        get_user=identity_profile.get_user,
        get_character=character_profile.get_character,
        get_owned_character=_get_owned_character,
        ensure_not_suspended=_ensure_not_suspended,
        ensure_llm_mode=_ensure_llm_mode,
        ensure_auto_ticks_available=maintenance_service.ensure_auto_ticks_available,
        evaluate_readiness=_activity_profile_readiness,
        get_credential=agent_crud.get_character_credential,
        select_world_character=selected_autonomous_world_character,
        lock_world_capacity=lock_world_autonomy_capacity,
        count_world_autonomy=count_enabled_autonomous_world_characters,
        count_effective_agents=_effective_server_llm_autonomy_count,
        set_world_autonomy=set_active_world_character_autonomy,
        set_character_status=character_mutations.set_activity_status,
        assign_slot=agent_run_service.assign_resident_slot,
        sync_enabled=_resident_openclaw_sync_enabled,
        bind_profile=_bind_slot_auth_profile,
        release_profile=_release_slot_auth_profile,
        reload_secrets=_reload_openclaw_secrets_sync,
        build_detail=_build_agent_detail,
        character_not_found_error=AgentNotFoundError,
        credential_required_error=CredentialRequiredError,
        credential_sync_error=CredentialSyncError,
        slot_busy_error=ActiveSlotBusyError,
    )


def activate_agent(db: Session, user: models.User, character_id: str) -> schemas.AgentDetailRead:
    return autonomy_management.activate_agent(db, user, character_id, workflows=build_autonomy_workflows())


def deactivate_agent(db: Session, user: models.User, character_id: str) -> schemas.AgentDetailRead:
    return autonomy_management.deactivate_agent(db, user, character_id, workflows=build_autonomy_workflows())


def _ensure_activity_profile_ready(db: Session, *, character: character_models.Character, setting: models.AgentActivitySetting) -> schemas.AgentActivityProfileReadinessRead:
    return autonomy_management._ensure_activity_profile_ready(db, character=character, setting=setting, workflows=build_autonomy_workflows())


def build_manual_activity_workflows() -> ManualActivityWorkflows:
    return ManualActivityWorkflows(
        get_owned_character=_get_owned_character,
        ensure_not_suspended=_ensure_not_suspended,
        is_owner_controlled_character=is_owner_controlled_character,
        ensure_llm_mode=_ensure_llm_mode,
        ensure_imported_world_runtime_enabled=_ensure_imported_world_runtime_enabled,
        ensure_run_now_available=maintenance_service.ensure_run_now_available,
        _ensure_activity_profile_ready=_ensure_activity_profile_ready,
        get_credential=agent_crud.get_character_credential,
        run_assigned_slot=agent_run_service.run_assigned_resident_slot_once,
        claim_temporary_slot=agent_run_service.claim_temporary_resident_slot,
        sync_enabled=_resident_openclaw_sync_enabled,
        bind_profile=_bind_slot_auth_profile,
        reload_secrets=_reload_openclaw_secrets_sync,
        run_temporary_slot=agent_run_service.run_claimed_temporary_resident_slot_once,
        release_profile=_release_slot_auth_profile,
        release_temporary_slot=agent_run_service.release_temporary_resident_slot,
        execution_mode_error=AgentExecutionModeError,
        credential_required_error=CredentialRequiredError,
    )


def build_feed_cue_workflows() -> FeedCueWorkflows:
    return FeedCueWorkflows(
        get_owned_character=_get_owned_character,
        ensure_not_suspended=_ensure_not_suspended,
        ensure_llm_mode=_ensure_llm_mode,
        ensure_imported_world_runtime_enabled=_ensure_imported_world_runtime_enabled,
        ensure_feed_cues_available=maintenance_service.ensure_feed_cues_available,
        build_activity_policy=agent_activity_policy.build_activity_policy,
        prompt_injection_error=PromptInjectionDetectedError,
    )


async def run_agent_now(db: Session, user: models.User, character_id: str) -> schemas.OpenClawAgentRunRead:
    return await manual_activity.run_agent_now(db, user, character_id, workflows=build_manual_activity_workflows())


def get_feed_cue(db: Session, user: models.User, character_id: str) -> schemas.AgentFeedCueRead | None:
    return feed_cues.get_feed_cue(db, user, character_id, workflows=build_feed_cue_workflows())


def give_feed_cue(db: Session, user: models.User, character_id: str, data: schemas.AgentFeedCueCreate) -> schemas.AgentFeedCueRead:
    return feed_cues.give_feed_cue(db, user, character_id, data, workflows=build_feed_cue_workflows())
