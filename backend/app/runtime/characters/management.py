from __future__ import annotations
from app.domains.identity.repository import credentials as identity_credentials
from app.domains.identity.service import character_credentials as identity_credential_records
from app.domains.routines.service import activity_logs as agent_crud
import app.api.schemas.first_greeting as schema_api_schemas_first_greeting
import app.domains.characters.schemas as character_schemas
import app.domains.identity.schemas as schema_identity_schemas
import app.domains.local_bot.schemas as bot_schemas
import app.domains.routines.schemas as routine_schemas
import app.domains.routines.schemas.runs as routine_schemas_runs
import app.domains.social.schemas.community as social_schemas
import app.domains.social.exceptions as social_errors
import app.domains.social.service.activity_results as social_activity_results_service
import app.domains.social.service.posts as social_posts_service
import app.runtime.social.timeline as social_timeline_runtime

from app.domains.local_bot.constants import LOCAL_KEY_PREFIX

from app.domains.local_bot.service import key_management as local_key_management

from app.runtime.local_bot.keys import build_local_key_workflows

from app.domains.identity.repository import credentials as credential_repository

from app.domains.identity.service import character_credentials as character_credential_service

from app.domains.characters.service import image_settings_owner

from app.domains.characters.exceptions import ImageSettingsInvalidError

from app.domains.characters.exceptions import UnsafeImagePromptError

from app.domains.characters.repository import image_settings as image_setting_repository

from app.domains.characters.service import image_settings as image_setting_service

from app.runtime.world_characters.queries import count_enabled_autonomous_world_characters

from app.domains.characters.service import media as media_service

from app.domains.characters.service.creator import llm_credential_error_message

from app.domains.characters.exceptions import CredentialRequiredError

from app.domains.characters.exceptions import CredentialSyncError

from app.domains.characters.contracts import CharacterManagementWorkflows

from app.domains.characters.service import management as character_management

from app.domains.characters.service.management import _agent_list_sort_key

from app.domains.characters.exceptions import AgentActiveHoursInvalidError

from app.domains.characters.service import mutations as character_mutations

from datetime import UTC

from datetime import datetime

from datetime import timedelta

import hashlib

import json

import re

from typing import Any

from typing import Iterable

from typing import Literal

from uuid import uuid4

from app.domains.characters.service.promotion import PROMOTION_USAGE_POLICY_VERSION

from app.domains.characters.service.promotion import _set_promotion_usage

from app.domains.characters.service.promotion import _promotion_usage_read

from app.domains.characters.service.access import LOCAL_MODE_LLM_BLOCKED_MESSAGE

from app.domains.characters.service.access import _get_owned_character

from app.domains.characters.service.access import _ensure_not_suspended

from app.domains.characters.service.access import _is_local_mode

from app.domains.characters.service.access import _ensure_llm_mode

from app.domains.characters.service.access import _ensure_local_mode

from app.domains.characters.service.persona import PERSONA_PROMPT_SAFETY_FIELDS

from app.domains.characters.service.persona import ensure_persona_prompt_safety

from app.domains.characters.service.persona import _field_value

from app.domains.characters.exceptions import AgentServiceError

from app.domains.characters.exceptions import AgentNotFoundError

from app.domains.characters.exceptions import AgentHandleConflictError

from app.domains.characters.exceptions import AgentHandleInvalidError

from app.domains.characters.exceptions import AgentProfileNameInvalidError

from app.domains.characters.exceptions import InvalidProfileMediaError

from app.domains.characters.exceptions import PromptInjectionDetectedError

from app.domains.characters.exceptions import AgentExecutionModeError

from app.domains.characters.exceptions import AgentSuspendedError

from pydantic import BaseModel

from pydantic import Field

from sqlalchemy import delete

from sqlalchemy import or_

from sqlalchemy import select

from sqlalchemy import text

from sqlalchemy import update

from sqlalchemy.orm import Session



from app.domains.routines.models.resident import AgentActivityLog as _model_AgentActivityLog

from app.domains.routines.models.resident import AgentActivitySetting as _model_AgentActivitySetting

from app.domains.memory.models.daypart import AgentDaypartMemoryEvent as _model_AgentDaypartMemoryEvent

from app.domains.routines.models.resident import AgentFeedCue as _model_AgentFeedCue

from app.domains.characters.models import AgentImageGenerationSetting as _model_AgentImageGenerationSetting

from app.domains.local_bot.models import AgentLocalKey as _model_AgentLocalKey

from app.domains.routines.models.resident import AgentPublicActionExecution as _model_AgentPublicActionExecution

from app.domains.relationships.models.points import AgentRelationshipPoint as _model_AgentRelationshipPoint

from app.domains.routines.models.resident import AgentRun as _model_AgentRun

from app.domains.routines.models.resident import AgentSlot as _model_AgentSlot

from app.domains.character_lore.models import CharacterLoreChunk as _model_CharacterLoreChunk

from app.domains.character_lore.models import CharacterLoreSource as _model_CharacterLoreSource

from app.domains.chat.models import CharacterMessageSetting as _model_CharacterMessageSetting

from app.domains.identity.models import LlmCredential as _model_LlmCredential

from app.domains.chat.models import MessageMessage as _model_MessageMessage

from app.domains.chat.models import MessageThread as _model_MessageThread

from app.domains.social.models.posts import Notification as _model_Notification

from app.domains.social.models.posts import Post as _model_Post

from app.domains.social.models.posts import PostImageGenerationJob as _model_PostImageGenerationJob

from app.domains.social.models.posts import PostImageQuotaReservation as _model_PostImageQuotaReservation

from app.domains.social.models.posts import PostLike as _model_PostLike

from app.domains.social.models.posts import PostRepost as _model_PostRepost

from app.domains.social.models.posts import ProfileFollow as _model_ProfileFollow

from app.domains.identity.models import User as _model_User

from app.domains.chat.models import UserMessagePreference as _model_UserMessagePreference

from app.domains.world_characters.models import WorldCharacter as _model_WorldCharacter

from app.domains.worlds.models import WorldMembership as _model_WorldMembership

from app.runtime.persistence.model_registration import register_models

from app.domains.characters import models as character_models

from app.domains.characters.service import profile as character_profile

from app.core import active_hours

from app.core import security

from app.core import unit_of_work

from app.config import settings

from app.core.image_generation import USER_IMAGE_MODEL_OPTIONS

from app.core.redaction import redact_secret_text

from app.core.sqlite_concurrency import run_sqlite_session_immediate

from app.exceptions import SqliteBusyRetryExhausted

from app.credentials import CredentialPurpose

from app.credentials import CredentialResolutionError

from app.credentials import CredentialResolver





from app.policies import name_policy

from app.runtime.routines import activity_policy as agent_activity_policy

from app.domains.world_characters.service import readiness as activity_profile_readiness



from app.runtime.resident import execution as agent_run_service

from app.domains.identity.service import demo_access as demo_lock

from app.core import image_prompt_safety

from app.domains.operations.service import maintenance as maintenance_service

from app.runtime.social import image_generation as post_image_generation

from app.domains.social.service import image_attachment

from app.core import prompt_safety

from app.domains.characters.service import media_storage as profile_media

from app.integrations.media import files as media_files

from app.integrations.media import images as media_images

from app.credentials import service_images as service_image_key

from app.domains.operations.service import settings as operation_settings

from app.integrations.direct_llm import DirectLlmCallContext

from app.integrations.direct_llm import DirectLlmDeferred

from app.integrations.direct_llm import DirectLlmError

from app.integrations.direct_llm import RunLlmTracker

from app.integrations.direct_llm import generate_json

from app.runtime.extensions.resident_adapter import OpenClawGatewayClient

from app.runtime.extensions.resident_adapter import OpenClawGatewayError

from app.runtime.extensions.resident_adapter import openclaw_auth_profiles

from app.domains.world_characters.public import is_owner_controlled_character

from app.domains.world_characters.public import lock_world_autonomy_capacity

from app.domains.world_characters.public import selected_autonomous_world_character

from app.domains.world_characters.public import set_active_world_character_autonomy

from app.domains.routines.contracts.activity_presentation import ActivityPresentationReads

from app.domains.routines.service import activity_presentation

from app.domains.routines.service import activity_logs

from app.domains.routines.service import runtime_guards

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

from app.domains.routines.constants import FIRST_GREETING_COOLDOWN

from app.domains.routines.constants import FIRST_GREETING_SESSION_MARKER

from app.domains.routines.constants import FIRST_GREETING_WRITER_OUTPUT_TOKENS

from app.domains.routines.contracts.first_greeting import FirstGreetingWorkflows

from app.domains.social.repository import posts as social_post_queries

from app.runtime.resident.first_greeting import resolve_first_greeting_key

from app.runtime.resident.first_greeting import _run_first_greeting_writer

from app.runtime.resident.first_greeting import _attach_first_greeting_image

from app.domains.routines.contracts.manual_activity import ManualActivityWorkflows

from app.domains.routines.contracts.feed_cues import FeedCueWorkflows

from app.domains.routines.service import manual_activity

from app.domains.routines.service.manual_activity import _manual_run_available_at

from app.domains.routines.service.tick_schedule import aware_utc as _aware_utc

from app.domains.routines.constants import RUN_NOW_COOLDOWN

from app.domains.routines.constants import RUN_NOW_SCHEDULER_GUARD_WINDOW

from app.domains.routines.constants import RUN_NOW_SCHEDULER_HEADROOM

from app.domains.routines.contracts.autonomy_management import AutonomyWorkflows

from app.domains.routines.service import autonomy_management

from app.domains.routines.repository.autonomy import _lock_server_llm_autonomy_capacity

from app.domains.routines.service.autonomy_management import _reject_server_llm_autonomy_capacity

from app.domains.routines.service.autonomy_management import _reject_world_autonomy_capacity

from app.domains.routines.service.autonomy_management import _log_autonomy_activation_rejection

from app.runtime.resident.autonomy_reads import count_effective_active_server_llm_autonomy_agents as _effective_server_llm_autonomy_count

from app.domains.identity.service import profile as identity_profile

from app.domains.routines.constants import SERVER_LLM_AUTONOMY_CAPACITY_ERROR_MESSAGE

from app.domains.routines.constants import WORLD_AUTONOMY_CAPACITY_ERROR_MESSAGE

from app.domains.routines.constants import SERVER_LLM_AUTONOMY_CAPACITY_LOCK_KEY

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

register_models()

AGENT_DETAIL_ACTIVITY_LIMIT = 200

DELETED_CHARACTER_NAME = "삭제한 앵무"

DELETED_CHARACTER_PLACEHOLDER = "삭제된 앵무입니다."

DemoAccountLockedError = demo_lock.DemoAccountLockedError

class AgentDeleteConfirmationError(AgentServiceError):
    pass

class AgentDeletionCredentialSyncError(AgentServiceError):
    pass

class AgentDeletionMediaCleanupError(AgentServiceError):
    pass

def list_agents(db: Session, user: _model_User) -> list[character_schemas.AgentDetailRead]:
    return character_management.list_agents(db, user, workflows=build_character_management_workflows())

def create_agent(
    db: Session, user: _model_User, data: character_schemas.AgentCreate
) -> character_schemas.AgentDetailRead:
    return character_management.create_agent(db, user, data, workflows=build_character_management_workflows())

def _after_character_created(db, user, character, data) -> character_schemas.AgentDetailRead:
    setting = activity_settings.ensure_setting(db, character.id)
    _apply_initial_activity_settings(db, setting, data)
    _ensure_initial_image_settings(db, character.id)
    if data.execution_mode == "llm":
        if data.api_key is None:
            raise CredentialRequiredError("Agent credential is required")
        character_credential_service.upsert_credential(
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
    return image_settings_owner._ensure_initial_image_settings(db, character_id, workflows=build_image_settings_workflows())

def get_agent(db: Session, user: _model_User, character_id: str) -> character_schemas.AgentDetailRead:
    return character_management.get_agent(db, user, character_id, workflows=build_character_management_workflows())

def get_local_connection(db: Session, user: _model_User, character_id: str) -> bot_schemas.AgentLocalConnectionRead:
    return local_key_management.get_local_connection(db, user, character_id)

def issue_local_key(db: Session, user: _model_User, character_id: str) -> bot_schemas.AgentLocalKeyCreateRead:
    return local_key_management.issue_local_key(db, user, character_id, workflows=build_local_key_workflows())

def revoke_local_key(db: Session, user: _model_User, character_id: str) -> None:
    return local_key_management.revoke_local_key(db, user, character_id, workflows=build_local_key_workflows())

def update_profile(
    db: Session,
    user: _model_User,
    character_id: str,
    data: character_schemas.AgentProfileUpdate,
) -> character_schemas.AgentDetailRead:
    return character_management.update_profile(db, user, character_id, data, workflows=build_character_management_workflows())

def _after_character_profile_updated(db, user, character, media_changed) -> character_schemas.AgentDetailRead:
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
    user: _model_User,
    character_id: str,
    data: character_schemas.AgentPromotionUsageUpdate,
) -> character_schemas.AgentDetailRead:
    return character_management.update_promotion_usage(db, user, character_id, data, workflows=build_character_management_workflows())

def update_persona(
    db: Session,
    user: _model_User,
    character_id: str,
    data: character_schemas.AgentPersonaUpdate,
) -> character_schemas.AgentDetailRead:
    return character_management.update_persona(db, user, character_id, data, workflows=build_character_management_workflows())

def _after_character_persona_updated(db, user, character) -> character_schemas.AgentDetailRead:
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
    user: _model_User,
    character_id: str,
    data: character_schemas.AgentProfileMediaUpload,
) -> character_schemas.AgentDetailRead:
    return media_service.upload_profile_media(db, user, character_id, data, workflows=build_character_media_workflows())

def get_image_settings(db: Session, user: _model_User, character_id: str) -> character_schemas.AgentImageGenerationSettingRead:
    return image_settings_owner.get_image_settings(db, user, character_id, workflows=build_image_settings_workflows())

def update_image_settings(db: Session, user: _model_User, character_id: str, data: character_schemas.AgentImageGenerationSettingUpdate) -> character_schemas.AgentImageGenerationSettingRead:
    return image_settings_owner.update_image_settings(db, user, character_id, data, workflows=build_image_settings_workflows())

def upload_image_seed(db: Session, user: _model_User, character_id: str, data: character_schemas.AgentImageSeedUpload) -> character_schemas.AgentImageGenerationSettingRead:
    return image_settings_owner.upload_image_seed(db, user, character_id, data, workflows=build_image_settings_workflows())

def delete_image_seed(db: Session, user: _model_User, character_id: str) -> character_schemas.AgentImageGenerationSettingRead:
    return image_settings_owner.delete_image_seed(db, user, character_id, workflows=build_image_settings_workflows())

def delete_agent(
    db: Session, user: _model_User, character_id: str, data: character_schemas.AgentDeleteCreate
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
    setting: _model_AgentActivitySetting,
) -> character_schemas.AgentActivityProfileReadinessRead:
    return activity_profile_readiness.evaluate(
        db,
        character=character,
        setting=setting,
    )

def _resident_openclaw_sync_enabled() -> bool:
    return settings.agent_activity_engine == "openclaw"

def _bind_slot_auth_profile(
    slot: routine_schemas_runs.AgentSlotRead,
    *,
    user_id: str,
    character: character_models.Character,
    credential: _model_LlmCredential,
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
    slot: _model_AgentSlot,
    *,
    user_id: str,
    character_id: str,
    credential: _model_LlmCredential,
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

def _local_connection_read(db: Session, character: character_models.Character) -> bot_schemas.AgentLocalConnectionRead:
    return local_key_management._local_connection_read(db, character)

def _local_key_token_prefix(token: str) -> str:
    return local_key_management._local_key_token_prefix(token)

def _agent_deletion_slot_condition(db: Session, *, user_id: str, character_id: str):
    credential_ids = list(
        db.scalars(
            select(_model_LlmCredential.id).where(
                _model_LlmCredential.owner_id == user_id,
                _model_LlmCredential.character_id == character_id,
            )
        )
    )
    conditions = [_model_AgentSlot.assigned_character_id == character_id]
    if credential_ids:
        conditions.append(_model_AgentSlot.assigned_credential_id.in_(credential_ids))
    return or_(*conditions) if len(conditions) > 1 else conditions[0]

def _ensure_agent_deletion_not_busy(
    db: Session, *, user_id: str, character_id: str
) -> None:
    active_run_id = db.scalar(
        select(_model_AgentRun.id)
        .where(
            _model_AgentRun.user_id == user_id,
            _model_AgentRun.character_id == character_id,
            _model_AgentRun.status.in_(routine_constants.ACTIVE_RUN_STATUSES),
        )
        .limit(1)
    )
    if active_run_id is not None:
        raise ActiveSlotBusyError(
            "앵무가 지금 활동 중이라 삭제할 수 없습니다. 잠시 뒤 다시 시도해주세요."
        )

    running_slot_id = db.scalar(
        select(_model_AgentSlot.agent_id)
        .where(
            _agent_deletion_slot_condition(
                db, user_id=user_id, character_id=character_id
            ),
            _model_AgentSlot.status == routine_constants.SLOT_STATUS_RUNNING,
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
            select(_model_AgentSlot)
            .where(
                _agent_deletion_slot_condition(
                    db, user_id=user_id, character_id=character_id
                )
            )
            .order_by(_model_AgentSlot.agent_id.asc())
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
        credential = db.get(_model_LlmCredential, slot.assigned_credential_id)
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
            select(_model_AgentSlot)
            .where(
                _agent_deletion_slot_condition(
                    db, user_id=user_id, character_id=character_id
                )
            )
            .order_by(_model_AgentSlot.agent_id.asc())
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

    message_thread_ids = select(_model_MessageThread.id).where(
        _model_MessageThread.character_id == character_id
    )
    db.execute(
        delete(_model_MessageMessage).where(
            _model_MessageMessage.thread_id.in_(message_thread_ids)
        )
    )
    db.execute(
        delete(_model_MessageThread).where(
            _model_MessageThread.character_id == character_id
        )
    )
    db.execute(
        update(_model_UserMessagePreference)
        .where(_model_UserMessagePreference.source_character_id == character_id)
        .values(credential_source="message_key", source_character_id=None)
    )
    db.execute(
        delete(_model_CharacterMessageSetting).where(
            _model_CharacterMessageSetting.character_id == character_id
        )
    )

    lore_source_ids = select(_model_CharacterLoreSource.id).where(
        _model_CharacterLoreSource.character_id == character_id
    )
    db.execute(
        delete(_model_CharacterLoreChunk).where(
            or_(
                _model_CharacterLoreChunk.character_id == character_id,
                _model_CharacterLoreChunk.source_id.in_(lore_source_ids),
            )
        )
    )
    db.execute(
        delete(_model_CharacterLoreSource).where(
            _model_CharacterLoreSource.character_id == character_id
        )
    )

    db.execute(
        delete(_model_PostImageGenerationJob).where(
            _model_PostImageGenerationJob.character_id == character_id
        )
    )
    db.execute(
        delete(_model_PostImageQuotaReservation).where(
            _model_PostImageQuotaReservation.character_id == character_id
        )
    )
    db.execute(
        delete(_model_AgentPublicActionExecution).where(
            _model_AgentPublicActionExecution.character_id == character_id
        )
    )
    db.execute(
        delete(_model_AgentDaypartMemoryEvent).where(
            _model_AgentDaypartMemoryEvent.character_id == character_id
        )
    )
    db.execute(
        delete(_model_AgentRelationshipPoint).where(
            or_(
                _model_AgentRelationshipPoint.recipient_character_id == character_id,
                _model_AgentRelationshipPoint.source_character_id == character_id,
            )
        )
    )

    db.execute(
        delete(_model_AgentFeedCue).where(_model_AgentFeedCue.character_id == character_id)
    )
    db.execute(
        delete(_model_AgentActivityLog).where(
            _model_AgentActivityLog.character_id == character_id
        )
    )
    db.execute(delete(_model_AgentRun).where(_model_AgentRun.character_id == character_id))
    db.execute(delete(_model_PostLike).where(_model_PostLike.character_id == character_id))
    db.execute(
        delete(_model_PostRepost).where(_model_PostRepost.character_id == character_id)
    )
    db.execute(
        delete(_model_ProfileFollow).where(
            or_(
                _model_ProfileFollow.follower_character_id == character_id,
                _model_ProfileFollow.target_character_id == character_id,
            )
        )
    )
    db.execute(
        delete(_model_Notification).where(
            or_(
                _model_Notification.recipient_character_id == character_id,
                _model_Notification.actor_character_id == character_id,
            )
        )
    )
    db.execute(
        update(_model_Post)
        .where(_model_Post.author_character_id == character_id)
        .values(author_name=DELETED_CHARACTER_NAME)
    )
    db.execute(
        delete(character_models.CharacterState).where(
            character_models.CharacterState.character_id == character_id
        )
    )
    db.execute(
        delete(_model_AgentActivitySetting).where(
            _model_AgentActivitySetting.character_id == character_id
        )
    )
    db.execute(
        delete(_model_AgentImageGenerationSetting).where(
            _model_AgentImageGenerationSetting.character_id == character_id
        )
    )
    db.execute(
        delete(_model_LlmCredential).where(
            _model_LlmCredential.character_id == character_id
        )
    )
    db.execute(
        delete(_model_AgentLocalKey).where(
            _model_AgentLocalKey.character_id == character_id
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
) -> character_schemas.AgentDetailRead:
    setting = activity_settings.ensure_setting(db, character.id)
    credential = credential_repository.get_character_credential(db, character.id)
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
    return character_schemas.AgentDetailRead(
        character=character_schemas.CharacterRead.model_validate(character),
        state=(
            character_schemas.CharacterStateRead.model_validate(character.state)
            if character.state
            else None
        ),
        credential=(
            schema_identity_schemas.CredentialRead.model_validate(credential) if credential else None
        ),
        settings=routine_schemas.AgentActivitySettingRead.model_validate(setting),
        image_settings=_image_generation_setting_read(
            db,
            image_setting_repository.ensure_image_generation_setting(db, character.id)
        ),
        promotion_usage=_promotion_usage_read(character),
        assigned_slot=routine_schemas_runs.AgentSlotRead.model_validate(slot) if slot else None,
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

def _image_generation_setting_read(db: Session, setting: _model_AgentImageGenerationSetting) -> character_schemas.AgentImageGenerationSettingRead:
    return image_settings_owner._image_generation_setting_read(db, setting, workflows=build_image_settings_workflows())

def _service_image_quota_read(db: Session, character_id: str) -> dict[str, int | str]:
    return image_settings_owner._service_image_quota_read(db, character_id, workflows=build_image_settings_workflows())

def _invalidate_image_visual_identity_if_present(db: Session, character_id: str) -> None:
    return image_settings_owner._invalidate_image_visual_identity_if_present(db, character_id)

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

def _build_full_character_detail(db: Session, character: character_models.Character) -> character_schemas.AgentDetailRead:
    return _build_agent_detail(db, character, recent_activity_limit=AGENT_DETAIL_ACTIVITY_LIMIT)

def build_character_media_workflows():
    from app.domains.characters.contracts import CharacterMediaWorkflows

    return CharacterMediaWorkflows(
        invalidate_visual_identity=_invalidate_image_visual_identity_if_present,
        log_activity=agent_crud.log_activity,
        build_detail=_build_agent_detail,
    )

def build_image_settings_workflows():
    from app.domains.characters.contracts import CharacterImageSettingsWorkflows
    from app.domains.social.repository.media import count_service_image_quota_used
    from app.domains.routines.service.tick_schedule import APP_TIMEZONE
    return CharacterImageSettingsWorkflows(
        service_image_available=service_image_key.is_service_image_available,
        service_image_available_for_model=service_image_key.is_service_image_available_for_model,
        count_service_image_quota_used=count_service_image_quota_used,
        app_timezone=APP_TIMEZONE,
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

def build_autonomy_workflows() -> AutonomyWorkflows[character_schemas.AgentDetailRead]:
    return AutonomyWorkflows(
        get_user=identity_profile.get_user,
        get_character=character_profile.get_character,
        get_owned_character=_get_owned_character,
        ensure_not_suspended=_ensure_not_suspended,
        ensure_llm_mode=_ensure_llm_mode,
        ensure_auto_ticks_available=maintenance_service.ensure_auto_ticks_available,
        evaluate_readiness=_activity_profile_readiness,
        get_credential=identity_credentials.get_character_credential,
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
        social_character_not_found_error=social_errors.CharacterNotFoundError,
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
        get_credential=identity_credentials.get_character_credential,
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
        get_credential=identity_credentials.get_character_credential,
        resolve_key=resolve_first_greeting_key,
        new_tracker=RunLlmTracker,
        _run_first_greeting_writer=_run_first_greeting_writer,
        post_input=social_schemas.PostCreate,
        build_response=schema_api_schemas_first_greeting.AgentFirstGreetingRead,
        create_post=social_timeline_runtime.timeline_service.create_post,
        build_post_created_activity_result=social_activity_results_service.build_post_created_activity_result,
        attach_image=_attach_first_greeting_image,
        get_post=social_posts_service.get_post,
        deferred_error=DirectLlmDeferred,
        social_service_error=social_errors.CommunityServiceError,
    )

def build_tendency_analysis_workflows() -> TendencyAnalysisWorkflows[character_schemas.AgentDetailRead]:
    return TendencyAnalysisWorkflows(
        get_owned_character=_get_owned_character,
        ensure_mutable=demo_lock.ensure_demo_user_mutable,
        ensure_llm_mode=_ensure_llm_mode,
        ensure_imported_world_runtime_enabled=partial(
            runtime_guards._ensure_imported_world_runtime_enabled,
            locked=agent_activity_policy.is_imported_world_runtime_locked_for_character,
            execution_mode_error=AgentExecutionModeError,
        ),
        get_credential=identity_credentials.get_character_credential,
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
        upsert_credential=identity_credential_records.upsert_credential,
        get_credential=identity_credentials.get_character_credential,
        sync_enabled=_resident_openclaw_sync_enabled,
        slot_read=routine_schemas_runs.AgentSlotRead.model_validate,
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

def build_tendency_analysis_runner() -> TendencyAnalysisRunner[character_schemas.AgentDetailRead]:
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
