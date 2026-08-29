from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import json
import logging
import re
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.core import security
from app.core.config import settings
from app.core.redaction import redact_exact_secret_text
from app.credentials import CredentialResolutionError, CredentialResolver
from app.cruds import agent_runs as agent_run_crud
from app.cruds import agents as agent_crud
from app.cruds import community as community_crud
from app.policies import name_policy
from app.services import agents as agent_service
from app.services import agent_activity_policy
from app.services import agent_runs as agent_run_service
from app.services import demo_lock
from app.services.direct_llm import DirectLlmCallContext, RunLlmTracker, generate_text
from app.services import operation_settings
from app.services import image_provider
from app.services import pollinations_image
from app.services import prompt_safety
from app.services import profile_media
from app.services import bounded_http
from app.services import provider_http
from app.services import replicate_image
from app.services import service_image_key
from app.services.runtime_boundary import (
    OpenClawGatewayClient,
    OpenClawGatewayError,
    openclaw_auth_profiles,
)


logger = logging.getLogger(__name__)
DRAFT_TTL = timedelta(hours=1)
DRAFT_COOLDOWN = timedelta(seconds=60)
PROFILE_IMAGE_CANDIDATE_TTL = timedelta(hours=1)
PROFILE_IMAGE_DAILY_LIMIT = 1
PROFILE_IMAGE_USED_STATUSES = ("reserved", "generated", "applied")
POLLINATIONS_MAX_SEED = 2_147_483_647
POLLINATIONS_MODELS_URL = "https://gen.pollinations.ai/image/models"
POLLINATIONS_IMAGE_URL = "https://gen.pollinations.ai/image"
POLLINATIONS_LEGACY_IMAGE_URL = "https://image.pollinations.ai/prompt"
PROVIDER_SENSITIVE_HEADERS = frozenset(
    {
        "Authorization",
        "Ocp-Apim-Subscription-Key",
        "Ocp-Apim-Subscription-Region",
    }
)
# OpenClaw validates the global tool allowlist before honoring tool_choice="none".
DRAFT_LLM_TOOLS_ALLOW = ["angmoo_list_feed"]
HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
STYLE_PROMPTS = {
    "기본": "polished character illustration",
    "애니메풍": "cinematic anime style",
    "리얼풍": "realistic digital art style",
    "3D풍": "stylized 3D character render",
}
TRANSLATION_CACHE_MAX = 256
_POLLINATIONS_MODEL_CHECKED_AT: dict[str, datetime] = {}
_TRANSLATION_CACHE: dict[str, str] = {}
_TRANSLATION_USAGE_LOCK = Lock()


class AgentCreationDraftError(Exception):
    pass


class AgentCreationDraftNotFoundError(AgentCreationDraftError):
    pass


class AgentCreationDraftExpiredError(AgentCreationDraftNotFoundError):
    pass


class AgentCreationDraftCooldownError(AgentCreationDraftError):
    def __init__(self, available_at: datetime) -> None:
        super().__init__("Please wait before trying again")
        self.available_at = available_at


class AgentCreationDraftValidationError(AgentCreationDraftError):
    pass


class AgentCreationDraftHandleConflictError(AgentCreationDraftValidationError):
    pass


class AgentCreationDraftMediaError(AgentCreationDraftError):
    pass


class AgentProfileImageQuotaExceededError(AgentCreationDraftMediaError):
    def __init__(self, usage_status: schemas.AgentProfileImageUsageStatusRead) -> None:
        super().__init__("profile_image_daily_limit_exceeded")
        self.usage_status = usage_status


class AgentProfileImageCandidateNotFoundError(AgentCreationDraftError):
    pass


class AgentProfileImageCandidateExpiredError(AgentProfileImageCandidateNotFoundError):
    pass


class AgentPrivateMediaNotFoundError(AgentCreationDraftError):
    pass


class AgentCreationDraftParseError(AgentCreationDraftError):
    pass


@dataclass
class _DraftCredential:
    id: str
    provider: str
    model: str
    auth_profile_id: str
    label: str


async def create_draft(
    db: Session, user: models.User, data: schemas.AgentCreationDraftCreate
) -> schemas.AgentCreationDraftRead:
    _cleanup_expired_drafts(db)
    draft_id = f"draft-{uuid4().hex[:12]}"
    await _run_draft_llm(
        db=db,
        user=user,
        draft_id=draft_id,
        provider=data.provider,
        model=data.model,
        api_key=data.api_key,
        message='Return exactly this JSON: {"ok": true}',
        extra_system_prompt=(
            "You are verifying an Angmoo user-provided LLM credential. "
            'Return only {"ok": true}. Do not call tools.'
        ),
    )
    draft = models.AgentCreationDraft(
        id=draft_id,
        user_id=user.id,
        provider=data.provider,
        model=data.model,
        encrypted_api_key=security.encrypt_secret(
            data.api_key,
            scope=security.SecretScope(
                owner_id=user.id,
                character_id="",
                provider=data.provider,
                purpose="creation_draft",
            ),
        ),
        key_fingerprint=security.fingerprint_secret(data.api_key),
        name="",
        handle=None,
        one_liner="",
        personality="",
        speech_style="",
        worldview="",
        topic_preferences="",
        safety_rules="",
        image_style="기본",
        appearance_prompt="",
        expires_at=datetime.now(UTC) + DRAFT_TTL,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return _draft_read(draft)


def get_draft(
    db: Session, user: models.User, draft_id: str
) -> schemas.AgentCreationDraftRead:
    draft = _get_owned_draft(db, user, draft_id)
    return _draft_read(draft)


def get_draft_media_content(
    db: Session,
    user: models.User,
    draft_id: str,
    media_type: str,
):
    if media_type not in {"avatar", "banner"}:
        raise AgentPrivateMediaNotFoundError(media_type)
    draft = _get_owned_draft(db, user, draft_id)
    media_url = (
        draft.avatar_temp_url if media_type == "avatar" else draft.banner_temp_url
    )
    if media_url is None:
        raise AgentPrivateMediaNotFoundError(media_type)
    try:
        return profile_media.resolve_private_media_file(
            media_url,
            expected_directory="drafts",
        )
    except profile_media.InvalidProfileMediaError as exc:
        raise AgentPrivateMediaNotFoundError(media_type) from exc


def get_draft_candidate_content(
    db: Session,
    user: models.User,
    draft_id: str,
    candidate_id: str,
):
    draft = _get_owned_draft(db, user, draft_id)
    candidate = _get_owned_profile_image_candidate(
        db,
        user=user,
        candidate_id=candidate_id,
        scope="create",
        draft_id=draft.id,
        character_id=None,
    )
    try:
        return profile_media.resolve_private_media_file(
            candidate.url,
            expected_directory="profile-candidates",
        )
    except profile_media.InvalidProfileMediaError as exc:
        raise AgentProfileImageCandidateNotFoundError(candidate_id) from exc


def get_profile_candidate_content(
    db: Session,
    user: models.User,
    character_id: str,
    candidate_id: str,
):
    character = community_crud.get_character(db, character_id)
    if (
        character is None
        or character.owner_id != user.id
        or character.deleted_at is not None
    ):
        raise agent_service.AgentNotFoundError(character_id)
    candidate = _get_owned_profile_image_candidate(
        db,
        user=user,
        candidate_id=candidate_id,
        scope="profile",
        draft_id=None,
        character_id=character.id,
    )
    try:
        return profile_media.resolve_private_media_file(
            candidate.url,
            expected_directory="profile-candidates",
        )
    except profile_media.InvalidProfileMediaError as exc:
        raise AgentProfileImageCandidateNotFoundError(candidate_id) from exc


def update_draft(
    db: Session,
    user: models.User,
    draft_id: str,
    data: schemas.AgentCreationDraftUpdate,
) -> schemas.AgentCreationDraftRead:
    draft = _get_owned_draft(db, user, draft_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "handle":
            if value is None or not str(value).strip():
                draft.handle = None
                continue
            if name_policy.is_blocked_name(str(value)):
                raise AgentCreationDraftValidationError("사용할 수 없는 핸들입니다.")
            try:
                draft.handle = community_crud.validate_character_handle_for_create(
                    db, str(value)
                )
            except community_crud.CharacterHandleConflictError as exc:
                raise AgentCreationDraftHandleConflictError(str(exc)) from exc
            except community_crud.InvalidCharacterHandleError as exc:
                raise AgentCreationDraftValidationError(str(exc)) from exc
        elif value is None and field in {"avatar_temp_url", "banner_temp_url"}:
            setattr(draft, field, None)
        elif value is not None:
            cleaned = _clean_text(value)
            if field in agent_service.PERSONA_PROMPT_SAFETY_FIELDS:
                _ensure_draft_prompt_safety(cleaned, field_name=field)
            setattr(draft, field, cleaned)
    db.commit()
    db.refresh(draft)
    return _draft_read(draft)


async def enhance_persona(
    db: Session, user: models.User, draft_id: str
) -> schemas.AgentCreationDraftRead:
    draft = _get_owned_draft(db, user, draft_id)
    _ensure_not_in_cooldown(draft.persona_enhance_available_at)
    api_key = _decrypt_draft_api_key(draft)
    raw_text = await _run_draft_llm(
        db=db,
        user=user,
        draft_id=draft.id,
        provider=draft.provider,
        model=draft.model,
        api_key=api_key,
        message="보강할 앵무 페르소나를 JSON으로 정리해 주세요.",
        extra_system_prompt=_build_persona_enhance_prompt(draft),
    )
    payload = _parse_json_object(raw_text)
    persona_values = {
        "personality": _safe_payload_text(payload.get("personality"), 2000),
        "speech_style": _safe_payload_text(payload.get("speech_style"), 1200),
        "worldview": _safe_payload_text(payload.get("worldview"), 2000),
        "topic_preferences": _safe_payload_text(
            payload.get("topic_preferences"), 1200
        ),
        "safety_rules": _safe_payload_text(payload.get("safety_rules"), 1200),
    }
    _ensure_draft_persona_prompt_safety(persona_values)
    draft.personality = persona_values["personality"]
    draft.speech_style = persona_values["speech_style"]
    draft.worldview = persona_values["worldview"]
    draft.topic_preferences = persona_values["topic_preferences"]
    draft.safety_rules = persona_values["safety_rules"]
    draft.persona_enhance_available_at = datetime.now(UTC) + DRAFT_COOLDOWN
    db.commit()
    db.refresh(draft)
    return _draft_read(draft)


def upload_draft_media(
    db: Session,
    user: models.User,
    draft_id: str,
    data: schemas.AgentCreationDraftMediaUpload,
) -> schemas.AgentCreationDraftRead:
    draft = _get_owned_draft(db, user, draft_id)
    url = profile_media.save_draft_profile_media(
        draft_id=draft.id,
        media_type=data.media_type,
        content_type=data.content_type,
        data_base64=data.data_base64,
    )
    if data.media_type == "avatar":
        draft.avatar_temp_url = url
    else:
        draft.banner_temp_url = url
    db.commit()
    db.refresh(draft)
    return _draft_read(draft)


async def generate_media(
    db: Session,
    user: models.User,
    draft_id: str,
    data: schemas.AgentCreationDraftGenerateMediaCreate,
) -> schemas.AgentCreationDraftMediaGenerationRead:
    draft = _get_owned_draft(db, user, draft_id)
    _cleanup_expired_profile_image_candidates(db, user.id)
    target_media_types = [data.media_type] if data.media_type else ["avatar", "banner"]
    if data.media_type is None:
        _ensure_not_in_cooldown(draft.media_generation_available_at)
    draft.image_style = data.image_style
    draft.appearance_prompt = data.appearance_prompt.strip()
    if data.media_type is None:
        draft.media_generation_available_at = datetime.now(UTC) + DRAFT_COOLDOWN
    db.commit()
    db.refresh(draft)

    results: list[schemas.AgentCreationDraftMediaResult] = []
    image_model = operation_settings.get_pollinations_profile_image_model(db)
    route_mode = operation_settings.get_pollinations_profile_image_route_mode(db)
    if image_provider.is_replicate_model(image_model):
        route_mode = "replicate"
    generation_seed = uuid4().hex
    profile_image_key_available = service_image_key.is_profile_image_available_for_model(image_model)
    needs_generation = any(
        _profile_image_usage_status(
            db,
            user=user,
            scope="create",
            media_type=media_type,
        ).remaining
        > 0
        for media_type in target_media_types
    ) and profile_image_key_available
    appearance_prompt = (
        _translate_image_prompt_to_english(draft.appearance_prompt)
        if needs_generation
        else draft.appearance_prompt
    )
    for media_type in target_media_types:
        width, height = _pollinations_image_size(media_type)
        prompt = _build_pollinations_prompt(
            style=draft.image_style,
            appearance=appearance_prompt,
            media_type=media_type,
        )
        try:
            if not profile_image_key_available:
                raise AgentCreationDraftMediaError("profile_image_key_unavailable")
            candidate, usage_status = await _generate_profile_image_candidate(
                db,
                user=user,
                scope="create",
                media_type=media_type,
                prompt=prompt,
                seed=_draft_media_seed(draft.id, f"{media_type}:{generation_seed}"),
                model=image_model,
                route_mode=route_mode,
                draft_id=draft.id,
                character_id=None,
            )
            results.append(
                schemas.AgentCreationDraftMediaResult(
                    media_type=media_type,
                    candidate_id=candidate.id,
                    candidate_url=(
                        f"/api/v1/agents/drafts/{draft.id}/media-candidates/"
                        f"{candidate.id}/content"
                    ),
                    usage_status=usage_status,
                    width=width,
                    height=height,
                    ok=True,
                )
            )
        except AgentProfileImageQuotaExceededError as exc:
            results.append(
                schemas.AgentCreationDraftMediaResult(
                    media_type=media_type,
                    usage_status=exc.usage_status,
                    width=width,
                    height=height,
                    ok=False,
                    error="profile_image_daily_limit_exceeded",
                )
            )
        except AgentCreationDraftMediaError as exc:
            logger.warning(
                "agent draft media generation failed: draft_id=%s media_type=%s error=%s",
                draft.id,
                media_type,
                str(exc),
            )
            results.append(
                schemas.AgentCreationDraftMediaResult(
                    media_type=media_type,
                    usage_status=_profile_image_usage_status(
                        db,
                        user=user,
                        scope="create",
                        media_type=media_type,
                    ),
                    width=width,
                    height=height,
                    ok=False,
                    error=str(exc),
                )
            )
    db.commit()
    db.refresh(draft)
    ordered = sorted(results, key=lambda item: 0 if item.media_type == "avatar" else 1)
    return schemas.AgentCreationDraftMediaGenerationRead(
        draft=_draft_read(draft),
        results=ordered,
    )


async def generate_profile_media(
    db: Session,
    user: models.User,
    character_id: str,
    data: schemas.AgentProfileMediaGenerateCreate,
) -> schemas.AgentProfileMediaGenerationRead:
    character = community_crud.get_character(db, character_id)
    if (
        character is None
        or character.owner_id != user.id
        or character.deleted_at is not None
    ):
        raise agent_service.AgentNotFoundError(character_id)
    _cleanup_expired_profile_image_candidates(db, user.id)

    results: list[schemas.AgentCreationDraftMediaResult] = []
    media_type = data.media_type
    width, height = _pollinations_image_size(media_type)
    try:
        image_model = operation_settings.get_pollinations_profile_image_model(db)
        route_mode = operation_settings.get_pollinations_profile_image_route_mode(db)
        profile_image_key_available = service_image_key.is_profile_image_available_for_model(image_model)
        usage_status = _profile_image_usage_status(
            db,
            user=user,
            scope="profile",
            media_type=media_type,
        )
        appearance_prompt = (
            _translate_image_prompt_to_english(data.appearance_prompt.strip())
            if usage_status.remaining > 0 and profile_image_key_available
            else data.appearance_prompt.strip()
        )
        prompt = _build_pollinations_prompt(
            style=data.image_style,
            appearance=appearance_prompt,
            media_type=media_type,
        )
        if not profile_image_key_available:
            raise AgentCreationDraftMediaError("profile_image_key_unavailable")
        candidate, usage_status = await _generate_profile_image_candidate(
            db,
            user=user,
            scope="profile",
            media_type=media_type,
            prompt=prompt,
            seed=_draft_media_seed(character.id, f"{media_type}:{uuid4().hex}"),
            model=image_model,
            route_mode=route_mode,
            draft_id=None,
            character_id=character.id,
        )
        results.append(
            schemas.AgentCreationDraftMediaResult(
                media_type=media_type,
                candidate_id=candidate.id,
                candidate_url=(
                    f"/api/v1/agents/{character.id}/media-candidates/"
                    f"{candidate.id}/content"
                ),
                usage_status=usage_status,
                width=width,
                height=height,
                ok=True,
            )
        )
    except AgentProfileImageQuotaExceededError as exc:
        results.append(
            schemas.AgentCreationDraftMediaResult(
                media_type=media_type,
                usage_status=exc.usage_status,
                width=width,
                height=height,
                ok=False,
                error="profile_image_daily_limit_exceeded",
            )
        )
    except AgentCreationDraftMediaError as exc:
        results.append(
            schemas.AgentCreationDraftMediaResult(
                media_type=media_type,
                usage_status=_profile_image_usage_status(
                    db,
                    user=user,
                    scope="profile",
                    media_type=media_type,
                ),
                width=width,
                height=height,
                ok=False,
                error=str(exc),
            )
        )
    return schemas.AgentProfileMediaGenerationRead(results=results)


def get_draft_profile_image_usage(
    db: Session, user: models.User, draft_id: str
) -> schemas.AgentProfileImageUsageRead:
    _ = _get_owned_draft(db, user, draft_id)
    return _profile_image_usage_read(db, user=user, scope="create")


def get_agent_profile_image_usage(
    db: Session, user: models.User, character_id: str
) -> schemas.AgentProfileImageUsageRead:
    character = community_crud.get_character(db, character_id)
    if (
        character is None
        or character.owner_id != user.id
        or character.deleted_at is not None
    ):
        raise agent_service.AgentNotFoundError(character_id)
    return _profile_image_usage_read(db, user=user, scope="profile")


def apply_draft_media_candidate(
    db: Session,
    user: models.User,
    draft_id: str,
    candidate_id: str,
) -> schemas.AgentCreationDraftRead:
    draft = _get_owned_draft(db, user, draft_id)
    candidate = _get_owned_profile_image_candidate(
        db,
        user=user,
        candidate_id=candidate_id,
        scope="create",
        draft_id=draft.id,
        character_id=None,
    )
    source_path = profile_media.media_url_to_path(candidate.url)
    content = source_path.read_bytes()
    url = profile_media.save_draft_profile_media_bytes(
        draft_id=draft.id,
        media_type=candidate.media_type,
        content_type="image/webp",
        content=content,
    )
    if candidate.media_type == "avatar":
        draft.avatar_temp_url = url
    else:
        draft.banner_temp_url = url
    candidate_id = candidate.id
    _finalize_profile_image_quota(
        db,
        reservation_id=candidate.quota_reservation_id,
        status="applied",
        candidate_id=candidate_id,
    )
    db.delete(candidate)
    db.commit()
    db.refresh(draft)
    profile_media.delete_profile_image_candidate(candidate_id, user.id)
    return _draft_read(draft)


def apply_profile_media_candidate(
    db: Session,
    user: models.User,
    character_id: str,
    candidate_id: str,
) -> schemas.AgentDetailRead:
    character = community_crud.get_character(db, character_id)
    if (
        character is None
        or character.owner_id != user.id
        or character.deleted_at is not None
    ):
        raise agent_service.AgentNotFoundError(character_id)
    demo_lock.ensure_demo_user_mutable(user)
    candidate = _get_owned_profile_image_candidate(
        db,
        user=user,
        candidate_id=candidate_id,
        scope="profile",
        draft_id=None,
        character_id=character.id,
    )
    url = profile_media.promote_profile_image_candidate(
        character_id=character.id,
        media_type=candidate.media_type,
        candidate_media_url=candidate.url,
    )
    if candidate.media_type == "avatar":
        character.avatar_url = url
    else:
        character.banner_url = url
    agent_service._invalidate_image_visual_identity_if_present(db, character.id)
    candidate_id = candidate.id
    _finalize_profile_image_quota(
        db,
        reservation_id=candidate.quota_reservation_id,
        status="applied",
        candidate_id=candidate_id,
    )
    db.delete(candidate)
    agent_crud.log_activity(
        db,
        user_id=user.id,
        character_id=character.id,
        action_type="profile_updated",
        target_post_id=None,
        reason=f"user_applied_generated_{candidate.media_type}",
        result=f"Agent {candidate.media_type} image candidate was applied.",
    )
    db.commit()
    db.refresh(character)
    profile_media.delete_profile_image_candidate(candidate_id, user.id)
    return agent_service._build_agent_detail(db, character)


def discard_draft_media_candidate(
    db: Session,
    user: models.User,
    draft_id: str,
    candidate_id: str,
) -> None:
    draft = _get_owned_draft(db, user, draft_id)
    candidate = _get_owned_profile_image_candidate(
        db,
        user=user,
        candidate_id=candidate_id,
        scope="create",
        draft_id=draft.id,
        character_id=None,
    )
    profile_media.delete_profile_image_candidate(candidate.id, user.id)
    db.delete(candidate)
    db.commit()


def discard_profile_media_candidate(
    db: Session,
    user: models.User,
    character_id: str,
    candidate_id: str,
) -> None:
    character = community_crud.get_character(db, character_id)
    if (
        character is None
        or character.owner_id != user.id
        or character.deleted_at is not None
    ):
        raise agent_service.AgentNotFoundError(character_id)
    candidate = _get_owned_profile_image_candidate(
        db,
        user=user,
        candidate_id=candidate_id,
        scope="profile",
        draft_id=None,
        character_id=character.id,
    )
    profile_media.delete_profile_image_candidate(candidate.id, user.id)
    db.delete(candidate)
    db.commit()


def complete_draft(
    db: Session,
    user: models.User,
    draft_id: str,
    data: schemas.AgentCreationDraftComplete | None = None,
) -> schemas.AgentDetailRead:
    data = data or schemas.AgentCreationDraftComplete()
    draft = _get_owned_draft(db, user, draft_id)
    name = draft.name.strip()
    handle = draft.handle.strip() if draft.handle else None
    if not name:
        raise AgentCreationDraftValidationError("이름을 입력해주세요.")
    if name_policy.is_blocked_name(name):
        raise AgentCreationDraftValidationError("사용할 수 없는 닉네임입니다.")
    if handle and name_policy.is_blocked_name(handle):
        raise AgentCreationDraftValidationError("사용할 수 없는 핸들입니다.")
    if not draft.personality.strip():
        raise AgentCreationDraftValidationError("성격을 입력해주세요.")
    _ensure_draft_persona_prompt_safety(
        {
            "personality": draft.personality,
            "speech_style": draft.speech_style,
            "worldview": draft.worldview,
            "topic_preferences": draft.topic_preferences,
            "safety_rules": draft.safety_rules,
        }
    )
    api_key = _decrypt_draft_api_key(draft)
    create_data = schemas.AgentCreate(
        name=name,
        handle=handle,
        one_liner=draft.one_liner.strip(),
        personality=draft.personality.strip(),
        speech_style=draft.speech_style.strip(),
        worldview=draft.worldview.strip(),
        topic_preferences=draft.topic_preferences.strip(),
        safety_rules=draft.safety_rules.strip(),
        provider=draft.provider,
        model=draft.model,  # type: ignore[arg-type]
        api_key=api_key,
        activity_interval_minutes=data.activity_interval_minutes,
        active_hours_start=data.active_hours_start,
        active_hours_end=data.active_hours_end,
        promotion_usage_allowed=data.promotion_usage_allowed,
    )
    detail = agent_service.create_agent(db, user, create_data)
    character = db.get(models.Character, detail.character.id)
    if character is not None:
        if draft.avatar_temp_url:
            character.avatar_url = profile_media.promote_draft_profile_media(
                character_id=character.id,
                media_type="avatar",
                draft_media_url=draft.avatar_temp_url,
            )
        if draft.banner_temp_url:
            character.banner_url = profile_media.promote_draft_profile_media(
                character_id=character.id,
                media_type="banner",
                draft_media_url=draft.banner_temp_url,
            )
        db.commit()
    _delete_profile_image_candidates_for_draft(db, draft)
    profile_media.delete_draft_media(draft.id)
    db.delete(draft)
    db.commit()
    return agent_service.get_agent(db, user, detail.character.id)


def _ensure_draft_persona_prompt_safety(values: dict[str, str]) -> None:
    for field, value in values.items():
        if field in agent_service.PERSONA_PROMPT_SAFETY_FIELDS:
            _ensure_draft_prompt_safety(value, field_name=field)


def _ensure_draft_prompt_safety(value: str, *, field_name: str) -> None:
    try:
        prompt_safety.ensure_no_prompt_injection_text(
            value,
            field_name=field_name,
            field_kind="persona",
        )
    except prompt_safety.PromptSafetyError as exc:
        raise AgentCreationDraftValidationError("prompt_injection_detected") from exc


def _get_owned_draft(
    db: Session, user: models.User, draft_id: str
) -> models.AgentCreationDraft:
    _cleanup_expired_drafts(db)
    draft = db.get(models.AgentCreationDraft, draft_id)
    if draft is None or draft.user_id != user.id:
        raise AgentCreationDraftNotFoundError(draft_id)
    expires_at = draft.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        _delete_profile_image_candidates_for_draft(db, draft)
        profile_media.delete_draft_media(draft.id)
        db.delete(draft)
        db.commit()
        raise AgentCreationDraftExpiredError(draft_id)
    return draft


def _draft_read(draft: models.AgentCreationDraft) -> schemas.AgentCreationDraftRead:
    result = schemas.AgentCreationDraftRead.model_validate(draft)
    return result.model_copy(
        update={
            "avatar_temp_url": (
                f"/api/v1/agents/drafts/{draft.id}/media/avatar"
                if draft.avatar_temp_url
                else None
            ),
            "banner_temp_url": (
                f"/api/v1/agents/drafts/{draft.id}/media/banner"
                if draft.banner_temp_url
                else None
            ),
        }
    )


def _cleanup_expired_drafts(db: Session) -> None:
    now = datetime.now(UTC)
    expired = list(
        db.scalars(
            select(models.AgentCreationDraft)
            .where(models.AgentCreationDraft.expires_at <= now)
            .limit(20)
        )
    )
    if not expired:
        return
    for draft in expired:
        try:
            _delete_profile_image_candidates_for_draft(db, draft)
            profile_media.delete_draft_media(draft.id)
            db.delete(draft)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "expired agent creation draft cleanup failed: draft_id=%s",
                draft.id,
            )


def _delete_profile_image_candidates_for_draft(
    db: Session, draft: models.AgentCreationDraft
) -> None:
    candidates = list(
        db.scalars(
            select(models.ProfileImageCandidate).where(
                models.ProfileImageCandidate.draft_id == draft.id
            )
        )
    )
    for candidate in candidates:
        profile_media.delete_profile_image_candidate(candidate.id, candidate.user_id)
        db.delete(candidate)
    if candidates:
        db.flush()


async def _run_draft_llm(
    *,
    db: Session,
    user: models.User,
    draft_id: str,
    provider: str,
    model: str,
    api_key: str,
    message: str,
    extra_system_prompt: str,
) -> str:
    if settings.server_llm_engine == "direct":
        run_id = str(uuid4())
        tracker = RunLlmTracker()
        response = await generate_text(
            api_key=api_key,
            context=DirectLlmCallContext(
                credential_id=f"draft:{draft_id}",
                character_id=None,
                agent_run_id=run_id,
                node="AgentCreationDraft",
                lane="server_llm",
                provider=provider,
                model=model,
            ),
            tracker=tracker,
            system_prompt=extra_system_prompt,
            user_prompt=message,
            max_output_tokens=2400,
            timeout_seconds=settings.openclaw_timeout_seconds,
        )
        if not response.text.strip():
            raise AgentCreationDraftParseError("LLM 응답을 읽지 못했습니다.")
        return response.text.strip()

    token = settings.openclaw_gateway_token
    if token is None:
        raise agent_service.CredentialSyncError("OPENCLAW_GATEWAY_TOKEN is missing")
    run_id = str(uuid4())
    timeout_seconds = settings.openclaw_timeout_seconds
    slot = agent_run_crud.claim_agent_slot(
        db,
        run_id=run_id,
        agent_ids=settings.openclaw_agent_ids,
        lease_seconds=timeout_seconds + 90,
    )
    if slot is None:
        raise agent_run_service.AgentSlotUnavailableError(
            f"No OpenClaw slot is available for {', '.join(settings.openclaw_agent_ids)}"
        )

    credential = _DraftCredential(
        id=f"cred-{draft_id}",
        provider=provider,
        model=model,
        auth_profile_id=f"{provider}:{draft_id}",
        label=f"Angmoo draft {draft_id}",
    )
    client = OpenClawGatewayClient(
        url=settings.openclaw_gateway_url,
        token=token,
        timeout_seconds=timeout_seconds,
    )
    bound_profile = False
    last_error: str | None = None
    try:
        openclaw_auth_profiles.bind_credential_to_slot(
            agent_id=slot.agent_id,
            user_id=user.id,
            character_id=draft_id,
            credential=credential,  # type: ignore[arg-type]
            api_key=api_key,
        )
        bound_profile = True
        await client.reload_secrets()
        gateway_result = await client.run_agent(
            message=message,
            agent_id=slot.agent_id,
            session_key=f"agent:{slot.agent_id}:angmoo:draft:{user.id}:{draft_id}:{run_id}",
            provider=provider,
            model=model,
            auth_profile_id=credential.auth_profile_id,
            tool_choice="none",
            tools_allow=DRAFT_LLM_TOOLS_ALLOW,
            prompt_mode="minimal",
            bootstrap_context_mode="lightweight",
            bootstrap_context_run_kind="default",
            idempotency_key=run_id,
            extra_system_prompt=extra_system_prompt,
        )
        return _extract_gateway_result_text(gateway_result)
    except OpenClawGatewayError as exc:
        last_error = redact_exact_secret_text(str(exc), api_key)
        exc.args = (last_error,)
        raise
    except openclaw_auth_profiles.OpenClawAuthProfileSyncError as exc:
        last_error = redact_exact_secret_text(str(exc), api_key)[:1000]
        raise agent_service.CredentialSyncError(last_error) from exc
    finally:
        if bound_profile:
            try:
                openclaw_auth_profiles.release_credential_from_slot(
                    agent_id=slot.agent_id,
                    user_id=user.id,
                    character_id=draft_id,
                    credential=credential,  # type: ignore[arg-type]
                )
                await client.reload_secrets()
            except Exception as exc:
                last_error = redact_exact_secret_text(str(exc), api_key)[:1000]
        agent_run_crud.release_agent_slot(
            db, agent_id=slot.agent_id, run_id=run_id, last_error=last_error
        )


def _extract_gateway_result_text(gateway_result: dict[str, Any]) -> str:
    result = gateway_result.get("result")
    if isinstance(result, dict):
        meta = result.get("meta")
        if isinstance(meta, dict):
            for key in ("finalAssistantVisibleText", "finalAssistantRawText"):
                text = meta.get(key)
                if isinstance(text, str) and text.strip():
                    return text.strip()
        payloads = result.get("payloads")
        if isinstance(payloads, list):
            parts: list[str] = []
            for payload in payloads:
                if not isinstance(payload, dict):
                    continue
                if payload.get("isError") or payload.get("isReasoning"):
                    continue
                text = payload.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            if parts:
                return "\n\n".join(parts)
    raise AgentCreationDraftParseError("LLM 응답을 읽지 못했습니다.")


def _build_persona_enhance_prompt(draft: models.AgentCreationDraft) -> str:
    return f"""
You refine an Angmoo character persona from rough Korean notes.
Return only JSON with these exact keys:
personality, speech_style, worldview, topic_preferences, safety_rules.
Every value must be a Korean string, not an array or object.

Rules:
- Write Korean.
- Keep the user's intent and do not overwrite the character.
- If a field is short, make it concrete enough for an autonomous social character.
- Fill topic_preferences and safety_rules even if the current draft leaves them empty.
- Do not add sexual content, illegal instructions, private data, or real-person claims.
- Each value must be concise and directly usable in the Angmoo character form.

Current draft:
- name: {draft.name}
- one_liner: {draft.one_liner}
- personality: {draft.personality}
- speech_style: {draft.speech_style}
- worldview: {draft.worldview}
- topic_preferences: {draft.topic_preferences}
- safety_rules: {draft.safety_rules}
""".strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentCreationDraftParseError("페르소나 보강 결과를 읽지 못했습니다.") from exc
    if not isinstance(payload, dict):
        raise AgentCreationDraftParseError("페르소나 보강 결과 형식이 올바르지 않습니다.")
    return payload


def _safe_payload_text(value: Any, max_length: int) -> str:
    if not isinstance(value, str):
        if isinstance(value, list):
            value = "\n".join(
                str(item).strip()
                for item in value
                if isinstance(item, (str, int, float)) and str(item).strip()
            )
        else:
            return ""
    return value.strip()[:max_length]


def _clean_text(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _decrypt_draft_api_key(draft: models.AgentCreationDraft) -> str:
    try:
        return CredentialResolver.resolve_draft_credential(draft).reveal()
    except CredentialResolutionError as exc:
        raise agent_service.CredentialRequiredError(
            "Agent draft credential key cannot be decrypted"
        ) from exc


def _ensure_not_in_cooldown(available_at: datetime | None) -> None:
    if available_at is not None and available_at > datetime.now(UTC):
        raise AgentCreationDraftCooldownError(available_at)


async def _generate_profile_image_candidate(
    db: Session,
    *,
    user: models.User,
    scope: str,
    media_type: str,
    prompt: str,
    seed: int,
    model: str,
    route_mode: str,
    draft_id: str | None,
    character_id: str | None,
) -> tuple[models.ProfileImageCandidate, schemas.AgentProfileImageUsageStatusRead]:
    api_key = (
        service_image_key.get_replicate_image_api_key()
        if image_provider.is_replicate_model(model)
        else service_image_key.get_profile_image_api_key()
    )
    if api_key is None:
        raise AgentCreationDraftMediaError("profile_image_key_unavailable")
    width, height = _pollinations_image_size(media_type)
    reservation = _reserve_profile_image_quota(
        db,
        user=user,
        scope=scope,
        media_type=media_type,
        model=model,
        route_mode=route_mode,
    )
    try:
        generated = await image_provider.generate_image(
            api_key=api_key,
            model=model,
            prompt=prompt,
            timeout_seconds=settings.pollinations_timeout_seconds,
            log_context={
                "source": "profile_image_generation",
                "scope": scope,
                "media_type": media_type,
                "route_mode": route_mode,
                "user_id": user.id,
                "draft_id": draft_id,
                "character_id": character_id,
            },
            route_mode=route_mode,
            width=width,
            height=height,
            seed=seed,
        )
        candidate_id = f"profile-candidate-{uuid4().hex[:16]}"
        saved = profile_media.save_profile_image_candidate_bytes(
            user_id=user.id,
            candidate_id=candidate_id,
            media_type=media_type,
            content_type=generated.content_type,
            content=generated.content,
        )
        candidate = models.ProfileImageCandidate(
            id=candidate_id,
            user_id=user.id,
            draft_id=draft_id,
            character_id=character_id,
            quota_reservation_id=reservation.id,
            scope=scope,
            bucket=_profile_image_bucket(scope, media_type),
            media_type=media_type,
            url=str(saved["url"]),
            content_type=str(saved["content_type"]),
            byte_size=int(saved["byte_size"]),
            width=int(saved["width"]),
            height=int(saved["height"]),
            model=model,
            route_mode=route_mode,
            expires_at=datetime.now(UTC) + PROFILE_IMAGE_CANDIDATE_TTL,
        )
        db.add(candidate)
        reservation.status = "generated"
        reservation.candidate_id = candidate.id
        reservation.finalized_at = datetime.now(UTC)
        db.commit()
        db.refresh(candidate)
        return candidate, _profile_image_usage_status(
            db,
            user=user,
            scope=scope,
            media_type=media_type,
        )
    except pollinations_image.PollinationsImageError as exc:
        _finalize_profile_image_quota(
            db,
            reservation_id=reservation.id,
            status="failed",
            candidate_id=None,
        )
        db.commit()
        raise AgentCreationDraftMediaError(exc.failure_class) from exc
    except replicate_image.ReplicateImageError as exc:
        _finalize_profile_image_quota(
            db,
            reservation_id=reservation.id,
            status="failed",
            candidate_id=None,
        )
        db.commit()
        raise AgentCreationDraftMediaError(exc.failure_class) from exc
    except profile_media.InvalidProfileMediaError as exc:
        _finalize_profile_image_quota(
            db,
            reservation_id=reservation.id,
            status="failed",
            candidate_id=None,
        )
        db.commit()
        raise AgentCreationDraftMediaError("candidate_storage_failed") from exc


def _profile_image_usage_read(
    db: Session, *, user: models.User, scope: str
) -> schemas.AgentProfileImageUsageRead:
    media_types = ("avatar", "banner")
    return schemas.AgentProfileImageUsageRead(
        items=[
            _profile_image_usage_status(
                db,
                user=user,
                scope=scope,
                media_type=media_type,
            )
            for media_type in media_types
        ]
    )


def _profile_image_usage_status(
    db: Session,
    *,
    user: models.User,
    scope: str,
    media_type: str,
    at: datetime | None = None,
) -> schemas.AgentProfileImageUsageStatusRead:
    current = at or datetime.now(UTC)
    quota_date = _profile_image_quota_date(current)
    bucket = _profile_image_bucket(scope, media_type)
    used = int(
        db.scalar(
            select(func.count(models.ProfileImageQuotaReservation.id)).where(
                models.ProfileImageQuotaReservation.user_id == user.id,
                models.ProfileImageQuotaReservation.quota_date == quota_date,
                models.ProfileImageQuotaReservation.bucket == bucket,
                models.ProfileImageQuotaReservation.status.in_(
                    PROFILE_IMAGE_USED_STATUSES
                ),
            )
        )
        or 0
    )
    remaining = max(0, PROFILE_IMAGE_DAILY_LIMIT - used)
    reset_at = _profile_image_reset_at(current)
    return schemas.AgentProfileImageUsageStatusRead(
        bucket=bucket,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        media_type=media_type,  # type: ignore[arg-type]
        used_today=used,
        remaining=remaining,
        limit=PROFILE_IMAGE_DAILY_LIMIT,
        reset_at=reset_at,
        next_available_at=reset_at if remaining <= 0 else None,
    )


def _reserve_profile_image_quota(
    db: Session,
    *,
    user: models.User,
    scope: str,
    media_type: str,
    model: str,
    route_mode: str,
) -> models.ProfileImageQuotaReservation:
    now = datetime.now(UTC)
    status = _profile_image_usage_status(
        db,
        user=user,
        scope=scope,
        media_type=media_type,
        at=now,
    )
    if status.remaining <= 0:
        raise AgentProfileImageQuotaExceededError(status)
    quota_date = _profile_image_quota_date(now)
    _lock_profile_image_quota(db, user_id=user.id, quota_date=quota_date, bucket=status.bucket)
    status = _profile_image_usage_status(
        db,
        user=user,
        scope=scope,
        media_type=media_type,
        at=now,
    )
    if status.remaining <= 0:
        raise AgentProfileImageQuotaExceededError(status)
    reservation = models.ProfileImageQuotaReservation(
        user_id=user.id,
        quota_date=quota_date,
        bucket=status.bucket,
        scope=scope,
        media_type=media_type,
        status="reserved",
        model=model,
        route_mode=route_mode,
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation


def _finalize_profile_image_quota(
    db: Session,
    *,
    reservation_id: int | None,
    status: str,
    candidate_id: str | None,
) -> None:
    if reservation_id is None:
        return
    reservation = db.get(models.ProfileImageQuotaReservation, reservation_id)
    if reservation is None:
        return
    reservation.status = status
    if candidate_id is not None:
        reservation.candidate_id = candidate_id
    reservation.finalized_at = datetime.now(UTC)
    db.flush()


def _get_owned_profile_image_candidate(
    db: Session,
    *,
    user: models.User,
    candidate_id: str,
    scope: str,
    draft_id: str | None,
    character_id: str | None,
) -> models.ProfileImageCandidate:
    candidate = db.get(models.ProfileImageCandidate, candidate_id)
    if (
        candidate is None
        or candidate.user_id != user.id
        or candidate.scope != scope
        or candidate.applied_at is not None
    ):
        raise AgentProfileImageCandidateNotFoundError(candidate_id)
    if draft_id is not None and candidate.draft_id != draft_id:
        raise AgentProfileImageCandidateNotFoundError(candidate_id)
    if character_id is not None and candidate.character_id != character_id:
        raise AgentProfileImageCandidateNotFoundError(candidate_id)
    expires_at = candidate.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        profile_media.delete_profile_image_candidate(candidate.id, user.id)
        raise AgentProfileImageCandidateExpiredError(candidate_id)
    if not profile_media.media_url_to_path(candidate.url).is_file():
        raise AgentProfileImageCandidateNotFoundError(candidate_id)
    return candidate


def _profile_image_bucket(scope: str, media_type: str) -> str:
    if scope not in {"create", "profile"}:
        raise AgentCreationDraftMediaError("invalid_profile_image_scope")
    if media_type not in {"avatar", "banner"}:
        raise AgentCreationDraftMediaError("invalid_profile_image_media_type")
    return f"{scope}_{media_type}"


def _profile_image_quota_date(at: datetime) -> date:
    local_at = (
        at.astimezone(agent_activity_policy.APP_TIMEZONE)
        if at.tzinfo
        else at.replace(tzinfo=UTC).astimezone(agent_activity_policy.APP_TIMEZONE)
    )
    return local_at.date()


def _profile_image_reset_at(at: datetime) -> datetime:
    local_at = (
        at.astimezone(agent_activity_policy.APP_TIMEZONE)
        if at.tzinfo
        else at.replace(tzinfo=UTC).astimezone(agent_activity_policy.APP_TIMEZONE)
    )
    return local_at.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)


def _lock_profile_image_quota(
    db: Session, *, user_id: str, quota_date: date, bucket: str
) -> None:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    lock_key = f"profile_image_quota:{user_id}:{quota_date.isoformat()}:{bucket}"
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(lock_key))))


def _cleanup_expired_profile_image_candidates(db: Session, user_id: str) -> None:
    now = datetime.now(UTC)
    candidates = list(
        db.scalars(
            select(models.ProfileImageCandidate)
            .where(models.ProfileImageCandidate.user_id == user_id)
            .where(models.ProfileImageCandidate.expires_at < now)
            .limit(50)
        )
    )
    if not candidates:
        return
    for candidate in candidates:
        profile_media.delete_profile_image_candidate(candidate.id, user_id)
        db.delete(candidate)
    db.commit()


def _open_pollinations_request(request: Request, timeout_seconds: float):
    try:
        return provider_http.open_validated_request(
            request,
            timeout_seconds=timeout_seconds,
            initial_validator=lambda url: provider_http.validate_public_https_url(
                url,
                allowed_hosts={"gen.pollinations.ai", "image.pollinations.ai"},
                allowed_path_prefixes={"/image", "/prompt"},
            ),
            redirect_validator=provider_http.validate_public_https_url,
            sensitive_headers=PROVIDER_SENSITIVE_HEADERS,
            allow_cross_origin_redirects=True,
        )
    except provider_http.ProviderUrlError as exc:
        raise URLError("Pollinations URL was not allowed") from exc


def _open_translation_request(request: Request, timeout_seconds: float):
    endpoint = urlparse(settings.azure_translator_endpoint)
    if not endpoint.hostname:
        raise URLError("Azure Translator endpoint was not allowed")
    translate_path = f"{endpoint.path.rstrip('/')}/translate"
    try:
        return provider_http.open_validated_request(
            request,
            timeout_seconds=timeout_seconds,
            initial_validator=lambda url: provider_http.validate_public_https_url(
                url,
                allowed_hosts={endpoint.hostname},
                allowed_path_prefixes={translate_path},
            ),
            redirect_validator=provider_http.validate_public_https_url,
            sensitive_headers=PROVIDER_SENSITIVE_HEADERS,
            allow_cross_origin_redirects=False,
        )
    except provider_http.ProviderUrlError as exc:
        raise URLError("Azure Translator URL was not allowed") from exc


def _ensure_pollinations_model_available(model_name: str) -> None:
    now = datetime.now(UTC)
    checked_at = _POLLINATIONS_MODEL_CHECKED_AT.get(model_name)
    if checked_at is not None and now - checked_at < timedelta(minutes=15):
        return
    try:
        request = Request(POLLINATIONS_MODELS_URL, headers={"User-Agent": "Angmoo/1.0"})
        with _open_pollinations_request(request, 20) as response:
            payload = json.loads(
                bounded_http.read_bounded_response(
                    response,
                    max_bytes=bounded_http.MAX_PROVIDER_JSON_BYTES,
                ).decode("utf-8")
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise AgentCreationDraftMediaError(
            "이미지 모델 상태를 확인하지 못했습니다."
        ) from exc
    models_payload = payload if isinstance(payload, list) else payload.get("models", [])
    if not isinstance(models_payload, list):
        raise AgentCreationDraftMediaError("이미지 모델 목록 형식이 올바르지 않습니다.")
    for model in models_payload:
        if not isinstance(model, dict) or model.get("name") != model_name:
            continue
        if model.get("paid_only") is True:
            raise AgentCreationDraftMediaError("현재 선택한 이미지 모델을 사용할 수 없습니다.")
        input_modalities = model.get("input_modalities") or []
        output_modalities = model.get("output_modalities") or []
        if "text" not in input_modalities or "image" not in output_modalities:
            raise AgentCreationDraftMediaError("현재 이미지 URL 생성 방식을 사용할 수 없습니다.")
        _POLLINATIONS_MODEL_CHECKED_AT[model_name] = now
        return
    raise AgentCreationDraftMediaError("현재 선택한 이미지 모델을 찾지 못했습니다.")


def _build_pollinations_prompt(*, style: str, appearance: str, media_type: str) -> str:
    style_prompt = STYLE_PROMPTS.get(style, STYLE_PROMPTS["기본"])
    if media_type == "avatar":
        return (
            f"{style_prompt}, {appearance}, front-facing avatar portrait, "
            "looking directly at the camera, both eyes visible, centered face, "
            "head and shoulders visible, symmetrical composition, no side profile, "
            "no back view, no text"
        )
    return (
        f"{style_prompt}, {appearance}, wide banner composition, atmospheric background, "
        "character in scene, highly detailed, no text"
    )


def _translate_image_prompt_to_english(text: str) -> str:
    prompt = text.strip()
    if not prompt or not HANGUL_RE.search(prompt):
        return prompt
    cached = _TRANSLATION_CACHE.get(prompt)
    if cached:
        return cached
    translated = _translate_ko_to_en_with_azure(prompt)
    if not translated:
        return prompt
    if len(_TRANSLATION_CACHE) >= TRANSLATION_CACHE_MAX:
        _TRANSLATION_CACHE.pop(next(iter(_TRANSLATION_CACHE)))
    _TRANSLATION_CACHE[prompt] = translated
    return translated


def _translate_ko_to_en_with_azure(text: str) -> str | None:
    if settings.translation_provider != "azure":
        return None
    api_key = settings.azure_translator_key
    if not api_key:
        return None
    char_count = len(text)
    if not _reserve_translation_chars(char_count):
        return None

    try:
        query = urlencode({"api-version": "3.0", "from": "ko", "to": "en"})
        url = f"{settings.azure_translator_endpoint}/translate?{query}"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Ocp-Apim-Subscription-Key": api_key,
            "User-Agent": "Angmoo/1.0",
        }
        region = settings.azure_translator_region
        if region:
            headers["Ocp-Apim-Subscription-Region"] = region
        body = json.dumps([{"Text": text}], ensure_ascii=False).encode("utf-8")
        request = Request(url, data=body, headers=headers, method="POST")
        with _open_translation_request(
            request,
            settings.translation_timeout_seconds,
        ) as response:
            payload = json.loads(
                bounded_http.read_bounded_response(
                    response,
                    max_bytes=bounded_http.MAX_PROVIDER_JSON_BYTES,
                ).decode("utf-8")
            )
        translated = payload[0]["translations"][0]["text"]
        return translated.strip() if isinstance(translated, str) else None
    except Exception:
        _release_translation_chars(char_count)
        return None


def _reserve_translation_chars(char_count: int) -> bool:
    limit = settings.translation_monthly_char_limit
    if limit <= 0:
        return True
    usage_path = settings.media_root_path / "translation-usage.json"
    month = datetime.now(UTC).strftime("%Y-%m")
    with _TRANSLATION_USAGE_LOCK:
        usage = _read_translation_usage(usage_path, month)
        if usage["chars"] + char_count > limit:
            return False
        usage["chars"] += char_count
        _write_translation_usage(usage_path, usage)
    return True


def _release_translation_chars(char_count: int) -> None:
    limit = settings.translation_monthly_char_limit
    if limit <= 0:
        return
    usage_path = settings.media_root_path / "translation-usage.json"
    month = datetime.now(UTC).strftime("%Y-%m")
    with _TRANSLATION_USAGE_LOCK:
        usage = _read_translation_usage(usage_path, month)
        usage["chars"] = max(0, usage["chars"] - char_count)
        _write_translation_usage(usage_path, usage)


def _read_translation_usage(path: Any, month: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    if raw.get("month") != month or not isinstance(raw.get("chars"), int):
        return {"month": month, "chars": 0}
    return {"month": month, "chars": max(0, raw["chars"])}


def _write_translation_usage(path: Any, usage: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(usage, ensure_ascii=False), encoding="utf-8")


def _pollinations_image_size(
    media_type: str, size: tuple[int, int] | None = None
) -> tuple[int, int]:
    return size or ((768, 768) if media_type == "avatar" else (1024, 384))


def _pollinations_image_query(
    *,
    model: str,
    media_type: str,
    seed: int,
    size: tuple[int, int] | None,
) -> dict[str, str | int]:
    width, height = _pollinations_image_size(media_type, size)
    query: dict[str, str | int] = {
        "model": model,
        "width": width,
        "height": height,
        "nologo": "true",
        "enhance": "true",
        "seed": seed,
    }
    return query


def _build_pollinations_image_url(
    *,
    base_url: str,
    model: str,
    prompt: str,
    media_type: str,
    seed: int,
    size: tuple[int, int] | None = None,
) -> str:
    query = _pollinations_image_query(
        model=model,
        media_type=media_type,
        seed=seed,
        size=size,
    )
    return f"{base_url}/{quote(prompt)}?{urlencode(query)}"


def _download_pollinations_image(
    *,
    model: str,
    prompt: str,
    media_type: str,
    seed: int,
    size: tuple[int, int] | None = None,
) -> tuple[str, bytes]:
    api_key = settings.pollinations_api_key
    primary_url = _build_pollinations_image_url(
        base_url=POLLINATIONS_IMAGE_URL,
        model=model,
        prompt=prompt,
        media_type=media_type,
        seed=seed,
        size=size,
    )
    urls = [primary_url]
    if not api_key:
        legacy_url = _build_pollinations_image_url(
            base_url=POLLINATIONS_LEGACY_IMAGE_URL,
            model=model,
            prompt=prompt,
            media_type=media_type,
            seed=seed,
            size=size,
        )
        urls = [legacy_url, primary_url]

    last_status: int | None = None
    for index, url in enumerate(urls):
        try:
            headers = {"User-Agent": "Angmoo/1.0"}
            headers["Accept-Encoding"] = "identity"
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            request = Request(url, headers=headers)
            with _open_pollinations_request(
                request,
                settings.pollinations_timeout_seconds,
            ) as response:
                content_type = (
                    response.headers.get("Content-Type") or ""
                ).split(";")[0].lower()
                content = bounded_http.read_bounded_response(
                    response,
                    max_bytes=bounded_http.MAX_PROVIDER_IMAGE_BYTES,
                )
            profile_media.validate_profile_media_content(content_type, content)
            return content_type, content
        except HTTPError as exc:
            last_status = exc.code
            if index == 0 and not api_key and exc.code in {400, 401, 402, 403}:
                continue
            raise AgentCreationDraftMediaError(
                f"이미지 생성 서비스가 응답하지 않았습니다. ({exc.code})"
            ) from exc
        except bounded_http.ResponseTooLargeError as exc:
            raise AgentCreationDraftMediaError(
                "Image provider response is too large"
            ) from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise AgentCreationDraftMediaError("이미지 생성 요청이 실패했습니다.") from exc
        except profile_media.InvalidProfileMediaError as exc:
            raise AgentCreationDraftMediaError("이미지 생성 결과를 저장할 수 없습니다.") from exc
    raise AgentCreationDraftMediaError(
        f"이미지 생성 서비스가 응답하지 않았습니다. ({last_status})"
    )


def _download_pollinations_image_with_retry(
    *, model: str, prompt: str, media_type: str, seed: int
) -> tuple[str, bytes]:
    last_error: AgentCreationDraftMediaError | None = None
    attempts = (((768, 768), prompt),) if media_type == "avatar" else ((None, prompt),)
    for offset, (size, attempt_prompt) in enumerate(attempts):
        try:
            return _download_pollinations_image(
                model=model,
                prompt=attempt_prompt,
                media_type=media_type,
                seed=seed + offset,
                size=size,
            )
        except AgentCreationDraftMediaError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise AgentCreationDraftMediaError("이미지 생성 요청이 실패했습니다.")


def _generate_draft_media_file(
    draft_id: str, media_type: str, prompt: str, seed: int, model: str
) -> str:
    content_type, content = _download_pollinations_image_with_retry(
        model=model,
        prompt=prompt,
        media_type=media_type,
        seed=seed,
    )
    return profile_media.save_draft_profile_media_bytes(
        draft_id=draft_id,
        media_type=media_type,
        content_type=content_type,
        content=content,
    )


def _draft_media_seed(draft_id: str, media_type: str) -> int:
    return int(security.hash_token(f"{draft_id}:{media_type}")[:8], 16) & POLLINATIONS_MAX_SEED
