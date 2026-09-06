from __future__ import annotations
from app.domains.routines.contracts.activity_presentation import ActivityPresentationReads
from app.domains.routines.service import activity_presentation, activity_logs, runtime_guards
from app.domains.characters.service import profile as character_profile
from app.domains.routines.contracts.tendency_analysis import TendencyAnalysisRunner
from app.domains.characters.exceptions import ActiveSlotBusyError
from app.domains.identity.contracts import CharacterCredentialWorkflows
from app.domains.worlds.repository import credential_scope as credential_worlds
from app.domains.world_characters.repository import credential_scope as credential_world_characters
from app.domains.routines.service import activity_settings
from app.domains.routines.exceptions import LlmCredentialInvalidError
from app.domains.routines.contracts.tendency_analysis import TendencyAnalysisWorkflows
from app.domains.routines.constants import TENDENCY_LLM_TOOLS_ALLOW
from app.runtime.resident import tendency_analysis
from app.domains.routines.service import first_greeting
from app.domains.routines.service.first_greeting import _first_greeting_available_at
from app.domains.routines.schemas.first_greeting import _FirstGreetingWriterPayload
from app.domains.routines.constants import FIRST_GREETING_COOLDOWN, FIRST_GREETING_SESSION_MARKER, FIRST_GREETING_WRITER_OUTPUT_TOKENS
from app.domains.routines.contracts.first_greeting import FirstGreetingWorkflows
from app.domains.social.repository import posts as social_post_queries
from app.runtime.resident.first_greeting import resolve_first_greeting_key, _run_first_greeting_writer, _attach_first_greeting_image
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
DELETED_CHARACTER_NAME = "삭제한 앵무"
DELETED_CHARACTER_PLACEHOLDER = "삭제된 앵무입니다."
# OpenClaw validates the global tool allowlist before honoring tool_choice="none".
LOCAL_KEY_PREFIX = "angmoo_local_"


















DemoAccountLockedError = demo_lock.DemoAccountLockedError






class UnsafeImagePromptError(AgentServiceError):
    pass


class ImageSettingsInvalidError(AgentServiceError):
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
    setting = activity_settings.ensure_setting(db, character.id)
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
    setting = activity_settings.ensure_setting(db, character.id)
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











def _build_agent_detail(
    db: Session, character: character_models.Character, *, recent_activity_limit: int = 20
) -> schemas.AgentDetailRead:
    setting = activity_settings.ensure_setting(db, character.id)
    credential = agent_crud.get_character_credential(db, character.id)
    slot = slot_queries.get_assigned_slot(db, character.id)
    recent_activity = activity_logs.list_recent_activity(
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
        activity_summary=activity_presentation.build_activity_summary(
            db, character=character, setting=setting, slot=slot, policy=policy,
            last_activity_at=last_activity_at,
            manual_run_available_at=manual_run_available_at,
            first_greeting_available_at=first_greeting_available_at,
            reads=build_activity_presentation_reads(),
        ),
        recent_activity=[
            activity_presentation._activity_log_read(db, log, reads=build_activity_presentation_reads()) for log in recent_activity
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
        social_character_not_found_error=community_service.CharacterNotFoundError,
    )











def build_manual_activity_workflows() -> ManualActivityWorkflows:
    return ManualActivityWorkflows(
        get_owned_character=_get_owned_character,
        ensure_not_suspended=_ensure_not_suspended,
        is_owner_controlled_character=is_owner_controlled_character,
        ensure_llm_mode=_ensure_llm_mode,
        ensure_imported_world_runtime_enabled=partial(
            runtime_guards._ensure_imported_world_runtime_enabled,
            locked=agent_activity_policy.is_imported_world_runtime_locked_for_character,
            execution_mode_error=AgentExecutionModeError,
        ),
        ensure_run_now_available=maintenance_service.ensure_run_now_available,
        _ensure_activity_profile_ready=partial(
            autonomy_management._ensure_activity_profile_ready,
            workflows=build_autonomy_workflows(),
        ),
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
        ensure_imported_world_runtime_enabled=partial(
            runtime_guards._ensure_imported_world_runtime_enabled,
            locked=agent_activity_policy.is_imported_world_runtime_locked_for_character,
            execution_mode_error=AgentExecutionModeError,
        ),
        ensure_feed_cues_available=maintenance_service.ensure_feed_cues_available,
        build_activity_policy=agent_activity_policy.build_activity_policy,
        prompt_injection_error=PromptInjectionDetectedError,
    )











def build_first_greeting_workflows() -> FirstGreetingWorkflows:
    return FirstGreetingWorkflows(
        get_owned_character=_get_owned_character,
        ensure_not_suspended=_ensure_not_suspended,
        ensure_llm_mode=_ensure_llm_mode,
        ensure_imported_world_runtime_enabled=partial(
            runtime_guards._ensure_imported_world_runtime_enabled,
            locked=agent_activity_policy.is_imported_world_runtime_locked_for_character,
            execution_mode_error=AgentExecutionModeError,
        ),
        ensure_run_now_available=maintenance_service.ensure_run_now_available,
        build_activity_policy=agent_activity_policy.build_activity_policy,
        has_authored_post=social_post_queries.character_has_authored_post,
        get_credential=agent_crud.get_character_credential,
        resolve_key=resolve_first_greeting_key,
        new_tracker=RunLlmTracker,
        _run_first_greeting_writer=_run_first_greeting_writer,
        post_input=schemas.PostCreate,
        build_response=schemas.AgentFirstGreetingRead,
        create_post=community_service.create_post,
        build_post_created_activity_result=community_service.build_post_created_activity_result,
        attach_image=_attach_first_greeting_image,
        get_post=community_service.get_post,
        deferred_error=DirectLlmDeferred,
        social_service_error=community_service.CommunityServiceError,
    )





def build_tendency_analysis_workflows() -> TendencyAnalysisWorkflows[schemas.AgentDetailRead]:
    return TendencyAnalysisWorkflows(
        get_owned_character=_get_owned_character,
        ensure_mutable=demo_lock.ensure_demo_user_mutable,
        ensure_llm_mode=_ensure_llm_mode,
        ensure_imported_world_runtime_enabled=partial(
            runtime_guards._ensure_imported_world_runtime_enabled,
            locked=agent_activity_policy.is_imported_world_runtime_locked_for_character,
            execution_mode_error=AgentExecutionModeError,
        ),
        get_credential=agent_crud.get_character_credential,
        bind_profile=_bind_slot_auth_profile,
        release_profile=_release_slot_auth_profile,
        build_detail=_build_agent_detail,
        credential_required_error=CredentialRequiredError,
    )





def build_character_credential_workflows() -> CharacterCredentialWorkflows:
    return CharacterCredentialWorkflows(
        get_owned_character=_get_owned_character,
        ensure_mutable=demo_lock.ensure_demo_user_mutable,
        ensure_llm_mode=_ensure_llm_mode,
        get_membership_id=credential_worlds.get_active_membership_id,
        get_world_character_id=credential_world_characters.get_accessible_world_character_id,
        get_assigned_slot=slot_queries.get_assigned_slot,
        running_slot_status=routine_constants.SLOT_STATUS_RUNNING,
        upsert_credential=agent_crud.upsert_credential,
        get_credential=agent_crud.get_character_credential,
        sync_enabled=_resident_openclaw_sync_enabled,
        slot_read=schemas.AgentSlotRead.model_validate,
        bind_profile=_bind_slot_auth_profile,
        release_profile=_release_slot_auth_profile,
        reload_secrets=_reload_openclaw_secrets_sync,
        release_slot=slot_assignments.release_resident_slot_assignment,
        disable_auto=activity_settings.disable_auto_if_present,
        set_world_autonomy=set_active_world_character_autonomy,
        set_character_status=character_mutations.set_activity_status,
        log_activity=agent_crud.log_activity,
        character_not_found_error=AgentNotFoundError,
        slot_busy_error=ActiveSlotBusyError,
        credential_required_error=CredentialRequiredError,
    )


def build_tendency_analysis_runner() -> TendencyAnalysisRunner[schemas.AgentDetailRead]:
    return partial(tendency_analysis.analyze_tendency, workflows=build_tendency_analysis_workflows())


def configure_character_activity_http(app: Any) -> None:
    """Connect the actual owner workflows once while the application is assembled."""
    app.state.activity_management_references = build_activity_management_references
    app.state.autonomy_workflows = build_autonomy_workflows
    app.state.manual_activity_workflows = build_manual_activity_workflows
    app.state.feed_cue_workflows = build_feed_cue_workflows
    app.state.first_greeting_workflows = build_first_greeting_workflows
    app.state.tendency_analysis_runner = build_tendency_analysis_runner


def build_activity_presentation_reads() -> ActivityPresentationReads:
    return ActivityPresentationReads(
        get_character=character_profile.get_character,
        get_user=identity_profile.get_user,
        activity_timezone_name=agent_activity_policy.activity_timezone_name,
        count_action_today=agent_activity_policy.count_action_today,
    )
