from __future__ import annotations

from app.domains.social.service import image_generation as image_policy
from app.domains.social.service.image_generation import _image_key_source, _has_user_image_key

from app.domains.social.service.image_attachment import (
    attach_prepared_post_image,
    release_prepared_post_image_quota,
)
from app.domains.social.service.image_reference_policy import (
    _pollinations_reference_url,
    _reference_image_url,
    _accepts_pollinations_reference,
    _requires_pollinations_reference,
    _requires_reference,
    _allows_reference_fallback,
)
from app.domains.social.service.image_attempts import (
    _pollinations_failed,
    _replicate_failed,
)

from app.domains.social.contracts.image_generation import (
    PreparedPostImage,
)
from app.domains.social.schemas.image_generation import (
    _VisualIdentityPayload,
    _ImagePromptPayload,
)
from app.domains.social.service.image_prompts import (
    _visual_identity_system_prompt,
    _image_prompt_system_prompt,
    _default_image_prompt_system_prompt,
    _klein_image_prompt_system_prompt,
    _flux_schnell_image_prompt_system_prompt,
    _zimage_image_prompt_system_prompt,
    _sana_image_prompt_system_prompt,
    _pruna_edit_image_prompt_system_prompt,
    _compose_pollinations_prompt,
    _append_prompt_suffix,
    _compose_local_api_pollinations_prompt,
    _fallback_visual_identity,
    _image_llm_model_for_writing_mode,
    json_safe_prompt,
    json_dumps,
)
from app.domains.social.exceptions import ServiceImageQuotaError
from app.domains.social.service.image_quota import (
    _daily_image_count,
    _daily_image_usage,
    _daily_image_window_count,
    _daily_image_window,
    _service_quota_date,
    _reserve_service_image_quota,
    _finalize_service_image_quota,
)
from app.domains.social.service.image_attempts import (
    _service_failure_class,
    _skipped,
    _failed,
)
from app.domains.social.constants import (
    POLLINATIONS_IMAGE_TIMEOUT_SECONDS,
    IMAGE_PROMPT_MAX_LENGTH,
    LOCAL_API_PROMPT_SAFETY_SUFFIX,
    KLEIN_BODY_STRUCTURE_PROMPT_SUFFIX,
    SERVICE_IMAGE_ACTIVE_RESERVATION_STATUSES,
    IMAGE_VISUAL_IDENTITY_FIRST_GREETING_MODEL,
)

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
import hashlib
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.core import security  # compatibility hook for existing image tests
from app.core.image_generation import (
    POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN,
    POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL,
    POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
    POLLINATIONS_IMAGE_MODEL_SANA,
    POLLINATIONS_IMAGE_MODEL_ZIMAGE,
    REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA,
    REPLICATE_IMAGE_MODEL_PRUNA_EDIT,
    DEFAULT_POLLINATIONS_IMAGE_MODEL,
    IMAGE_MODEL_OPTIONS,
    POST_IMAGE_TARGET_MAX_BYTES,
    POST_IMAGE_TARGET_SIZE,
    POST_IMAGE_WEBP_QUALITY_STEPS,
)
from app.credentials import (
    CredentialPurpose,
    CredentialResolutionError,
    CredentialResolver,
)
from app.cruds import agents as agent_crud
from app.cruds import community as community_crud
from app.integrations import image_provider, pollinations_image, replicate_image
from app.domains.social.service import media_storage as profile_media
from app.integrations.media import files as media_files
from app.services import (
    agent_activity_policy,
    image_prompt_safety,
    operation_settings,
    service_image_key,
)
from app.services.direct_llm import (
    DirectLlmCallContext,
    DirectLlmError,
    DirectLlmImagePart,
    RunLlmTracker,
    generate_json,
)


@dataclass(frozen=True)
class _ReferenceImage:
    source: str
    url: str
    source_hash: str
    llm_part: DirectLlmImagePart
    public_url: str | None


async def prepare_post_image(
    *,
    db: Session,
    character: models.Character,
    credential: models.LlmCredential,
    run_id: str,
    tracker: RunLlmTracker,
    writing_mode: str,
    post_title: str,
    post_body: str,
    writing_plan: dict[str, Any],
    current_time_text: str,
    run_started_at: datetime,
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None = None,
) -> PreparedPostImage:
    return await image_policy.prepare_post_image(
        workflows=RuntimeImageGenerationWorkflows(),
        db=db,
        character=character,
        credential=credential,
        run_id=run_id,
        tracker=tracker,
        writing_mode=writing_mode,
        post_title=post_title,
        post_body=post_body,
        writing_plan=writing_plan,
        current_time_text=current_time_text,
        run_started_at=run_started_at,
        on_rate_limit_wait=on_rate_limit_wait,
    )


def create_local_api_post_image_request(
    *,
    db: Session,
    user_id: str,
    local_key_prefix: str,
    character: models.Character,
    post_id: str,
    image_prompt: str,
    requested_at: datetime,
) -> schemas.BotImageRequestRead:
    return image_policy.create_local_api_post_image_request(
        workflows=RuntimeImageGenerationWorkflows(),
        db=db,
        user_id=user_id,
        local_key_prefix=local_key_prefix,
        character=character,
        post_id=post_id,
        image_prompt=image_prompt,
        requested_at=requested_at,
    )


async def prepare_local_api_post_image(
    *,
    db: Session,
    character: models.Character,
    image_prompt: str,
    run_started_at: datetime,
    key_source: str = "user",
    quota_reservation_id: int | None = None,
    post_id: str | None = None,
    job_id: int | None = None,
) -> PreparedPostImage:
    return await image_policy.prepare_local_api_post_image(
        workflows=RuntimeImageGenerationWorkflows(),
        db=db,
        character=character,
        image_prompt=image_prompt,
        run_started_at=run_started_at,
        key_source=key_source,
        quota_reservation_id=quota_reservation_id,
        post_id=post_id,
        job_id=job_id,
    )


async def _ensure_visual_identity(
    *,
    db: Session,
    setting: models.AgentImageGenerationSetting,
    character: models.Character,
    credential: models.LlmCredential,
    reference: _ReferenceImage,
    tracker: RunLlmTracker,
    run_id: str,
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
    model_override: str | None = None,
) -> str | None:
    if setting.visual_identity_prompt and setting.visual_identity_source_hash is None:
        return setting.visual_identity_prompt.strip() or None
    if (
        setting.visual_identity_prompt
        and setting.visual_identity_source_hash == reference.source_hash
    ):
        return setting.visual_identity_prompt.strip() or None
    try:
        api_key = CredentialResolver.resolve_llm_credential(
            credential,
            purpose=CredentialPurpose.USER_IMAGE,
            owner_id=character.owner_id,
            character_id=character.id,
            allowed_stored_purposes={"agent"},
        ).reveal()
    except CredentialResolutionError as exc:
        raise DirectLlmError("text credential key cannot be resolved") from exc

    def _validator(payload: dict[str, Any]) -> dict[str, Any]:
        return _VisualIdentityPayload.model_validate(payload).model_dump()

    payload = await generate_json(
        api_key=api_key,
        context=DirectLlmCallContext(
            credential_id=credential.id,
            character_id=character.id,
            agent_run_id=run_id,
            node="ImageVisualIdentity",
            lane="image_visual_identity",
            provider=credential.provider,
            model=model_override or credential.model,
            key_fingerprint=credential.key_fingerprint,
        ),
        tracker=tracker,
        system_prompt=_visual_identity_system_prompt(character=character),
        user_prompt=(
            "Inspect the reference image and return JSON describing the stable visual "
            "identity to preserve for future social post illustrations."
        ),
        response_schema=_VisualIdentityPayload,
        validator=_validator,
        max_output_tokens=800,
        user_image_parts=[reference.llm_part],
        on_rate_limit_wait=on_rate_limit_wait,
    )
    try:
        identity = _VisualIdentityPayload.model_validate(payload)
    except ValidationError:
        return None
    if not identity.usable_identity or not identity.identity_prompt.strip():
        if reference.source == "banner":
            return None
        return None
    setting.visual_identity_prompt = identity.identity_prompt.strip()
    setting.visual_identity_source_hash = reference.source_hash
    db.commit()
    db.refresh(setting)
    return setting.visual_identity_prompt


async def _resolve_visual_identity(
    *,
    db: Session,
    setting: models.AgentImageGenerationSetting,
    character: models.Character,
    credential: models.LlmCredential,
    reference: _ReferenceImage | None,
    tracker: RunLlmTracker,
    run_id: str,
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
    model_override: str | None = None,
) -> str:
    if setting.visual_identity_prompt and setting.visual_identity_source_hash is None:
        return setting.visual_identity_prompt.strip()
    if reference is None:
        return setting.visual_identity_prompt or _fallback_visual_identity(character)
    visual_identity = await _ensure_visual_identity(
        db=db,
        setting=setting,
        character=character,
        credential=credential,
        reference=reference,
        tracker=tracker,
        run_id=run_id,
        on_rate_limit_wait=on_rate_limit_wait,
        model_override=model_override,
    )
    return visual_identity or _fallback_visual_identity(character)


async def _refine_image_prompt(
    *,
    character: models.Character,
    credential: models.LlmCredential,
    tracker: RunLlmTracker,
    run_id: str,
    image_model: str,
    current_time_text: str,
    post_title: str,
    post_body: str,
    writing_plan: dict[str, Any],
    visual_identity: str,
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
    model_override: str | None = None,
) -> dict[str, str]:
    try:
        api_key = CredentialResolver.resolve_llm_credential(
            credential,
            purpose=CredentialPurpose.USER_IMAGE,
            owner_id=character.owner_id,
            character_id=character.id,
            allowed_stored_purposes={"agent"},
        ).reveal()
    except CredentialResolutionError as exc:
        raise DirectLlmError("text credential key cannot be resolved") from exc

    def _validator(payload: dict[str, Any]) -> dict[str, Any]:
        return _ImagePromptPayload.model_validate(payload).model_dump()

    payload = await generate_json(
        api_key=api_key,
        context=DirectLlmCallContext(
            credential_id=credential.id,
            character_id=character.id,
            agent_run_id=run_id,
            node="ImagePromptRefiner",
            lane="image_prompt_refiner",
            provider=credential.provider,
            model=model_override or credential.model,
            key_fingerprint=credential.key_fingerprint,
        ),
        tracker=tracker,
        system_prompt=_image_prompt_system_prompt(
            character=character,
            image_model=image_model,
        ),
        user_prompt=json_safe_prompt(
            {
                "current_time": current_time_text,
                "post_title": post_title,
                "post_body": post_body,
                "writing_mode": writing_plan.get("mode"),
                "writing_brief": writing_plan.get("brief"),
                "active_step": writing_plan.get("active_step"),
                "visual_identity": visual_identity,
            }
        ),
        response_schema=_ImagePromptPayload,
        validator=_validator,
        max_output_tokens=1100,
        on_rate_limit_wait=on_rate_limit_wait,
    )
    refined = _ImagePromptPayload.model_validate(payload).model_dump()
    return {
        "prompt": refined["prompt"].strip(),
        "alt_text": refined["alt_text"].strip(),
    }


def _select_reference_image(
    character: models.Character,
    setting: models.AgentImageGenerationSetting,
) -> _ReferenceImage | None:
    candidates = [
        ("seed", setting.seed_image_url),
        ("avatar", character.avatar_url),
        ("banner", character.banner_url),
    ]
    for source, url in candidates:
        if not url:
            continue
        reference = _build_reference_image(source=source, url=url)
        if reference is not None:
            return reference
    return None


def _build_reference_image(*, source: str, url: str) -> _ReferenceImage | None:
    if url.startswith("/media/"):
        try:
            path = media_files.media_url_to_path(url)
            content = path.read_bytes()
        except (OSError, profile_media.InvalidProfileMediaError):
            return None
        mime_type = _mime_type_from_url(url)
        source_hash = hashlib.sha256(f"{source}:{url}:".encode("utf-8") + content).hexdigest()
        return _ReferenceImage(
            source=source,
            url=url,
            source_hash=source_hash,
            llm_part=DirectLlmImagePart(mime_type=mime_type, data=content),
            public_url=_public_media_url(url),
        )
    if url.startswith("https://"):
        mime_type = _mime_type_from_url(url)
        source_hash = hashlib.sha256(f"{source}:{url}".encode("utf-8")).hexdigest()
        return _ReferenceImage(
            source=source,
            url=url,
            source_hash=source_hash,
            llm_part=DirectLlmImagePart(mime_type=mime_type, url=url),
            public_url=url,
        )
    return None


def _public_media_url(url: str) -> str | None:
    public_base_url = settings.public_base_url
    media_prefix = f"{settings.media_url_path.rstrip('/')}/"
    if public_base_url is None or not url.startswith(media_prefix):
        return None
    return f"{public_base_url}{url}"


def _mime_type_from_url(url: str) -> str:
    suffix = urlparse(url).path.lower().rsplit(".", 1)[-1]
    if suffix in {"jpg", "jpeg"}:
        return "image/jpeg"
    if suffix == "png":
        return "image/png"
    if suffix == "webp":
        return "image/webp"
    return "image/jpeg"


def _image_model_for_key_source(
    setting: models.AgentImageGenerationSetting | None,
    key_source: str,
    *,
    db: Session | None = None,
) -> str:
    return image_policy._image_model_for_key_source(workflows=RuntimeImageGenerationWorkflows(), setting=setting, key_source=key_source, db=db)


def _image_key_for_source(
    setting: models.AgentImageGenerationSetting,
    key_source: str,
    model: str,
    *,
    character: models.Character,
) -> str | None:
    if key_source == "service":
        if image_provider.is_replicate_model(model):
            return service_image_key.get_replicate_image_api_key()
        return service_image_key.get_service_image_api_key()
    encrypted_key = (
        setting.encrypted_replicate_api_token
        if image_provider.is_replicate_model(model)
        else setting.encrypted_pollinations_api_key
    )
    if not encrypted_key:
        return None
    try:
        return CredentialResolver.resolve_encrypted_material(
            encrypted_secret=encrypted_key,
            credential_id="user-image-setting",
            provider="replicate"
            if image_provider.is_replicate_model(model)
            else "pollinations",
            model=model,
            fingerprint=None,
            purpose=CredentialPurpose.USER_IMAGE,
            owner_id=character.owner_id,
            character_id=character.id,
            stored_purpose="user_image",
        ).reveal()
    except CredentialResolutionError:
        return None


def _local_api_image_skip_reason(
    *,
    db: Session,
    setting: models.AgentImageGenerationSetting | None,
    character: models.Character,
    image_prompt: str,
    requested_at: datetime,
    key_source: str,
) -> str | None:
    return image_policy._local_api_image_skip_reason(
        workflows=RuntimeImageGenerationWorkflows(),
        db=db,
        setting=setting,
        character=character,
        image_prompt=image_prompt,
        requested_at=requested_at,
        key_source=key_source,
    )


def _unsafe_image_text_reason(text: str | None) -> str | None:
    return image_prompt_safety.unsafe_image_text_reason(text)


def _log_local_api_image_rejected(
    *,
    db: Session,
    user_id: str,
    character_id: str,
    post_id: str,
    local_key_prefix: str,
) -> None:
    agent_crud.log_activity(
        db,
        user_id=user_id,
        character_id=character_id,
        action_type="local_api_image_rejected",
        target_post_id=post_id,
        reason="unsafe_prompt",
        result=f"skip_reason=unsafe_prompt; token_prefix={local_key_prefix}",
    )


class RuntimeImageGenerationWorkflows:
    @property
    def llm_error(self) -> type[Exception]:
        return DirectLlmError

    def get_image_generation_setting(self, db: Session, character_id: str):
        return agent_crud.get_image_generation_setting(db, character_id)

    def service_image_available(self, model: str) -> bool:
        return service_image_key.is_service_image_available_for_model(model)

    def free_image_model(self, db: Session | None) -> str:
        return operation_settings.get_pollinations_free_image_model(db)

    def image_route_mode(self, db: Session) -> str:
        return operation_settings.get_pollinations_image_route_mode(db)

    def select_reference_image(self,
        character: models.Character,
        setting: models.AgentImageGenerationSetting,
    ) -> _ReferenceImage | None:
        return _select_reference_image(character, setting)

    async def ensure_visual_identity(self,
        *,
        db: Session,
        setting: models.AgentImageGenerationSetting,
        character: models.Character,
        credential: models.LlmCredential,
        reference: _ReferenceImage,
        tracker: RunLlmTracker,
        run_id: str,
        on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
        model_override: str | None = None,
    ) -> str | None:
        return await _ensure_visual_identity(
            db=db,
            setting=setting,
            character=character,
            credential=credential,
            reference=reference,
            tracker=tracker,
            run_id=run_id,
            on_rate_limit_wait=on_rate_limit_wait,
            model_override=model_override,
        )

    async def resolve_visual_identity(self,
        *,
        db: Session,
        setting: models.AgentImageGenerationSetting,
        character: models.Character,
        credential: models.LlmCredential,
        reference: _ReferenceImage | None,
        tracker: RunLlmTracker,
        run_id: str,
        on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
        model_override: str | None = None,
    ) -> str:
        return await _resolve_visual_identity(
            db=db,
            setting=setting,
            character=character,
            credential=credential,
            reference=reference,
            tracker=tracker,
            run_id=run_id,
            on_rate_limit_wait=on_rate_limit_wait,
            model_override=model_override,
        )

    async def refine_image_prompt(self,
        *,
        character: models.Character,
        credential: models.LlmCredential,
        tracker: RunLlmTracker,
        run_id: str,
        image_model: str,
        current_time_text: str,
        post_title: str,
        post_body: str,
        writing_plan: dict[str, Any],
        visual_identity: str,
        on_rate_limit_wait: Callable[[float], Awaitable[None]] | None,
        model_override: str | None = None,
    ) -> dict[str, str]:
        return await _refine_image_prompt(
            character=character,
            credential=credential,
            tracker=tracker,
            run_id=run_id,
            image_model=image_model,
            current_time_text=current_time_text,
            post_title=post_title,
            post_body=post_body,
            writing_plan=writing_plan,
            visual_identity=visual_identity,
            on_rate_limit_wait=on_rate_limit_wait,
            model_override=model_override,
        )

    def image_key_for_source(self,
        setting: models.AgentImageGenerationSetting,
        key_source: str,
        model: str,
        *,
        character: models.Character,
    ) -> str | None:
        return _image_key_for_source(setting, key_source, model, character=character)

    def unsafe_image_text_reason(self, text: str | None) -> str | None:
        return _unsafe_image_text_reason(text)

    def log_local_api_image_rejected(self,
        *,
        db: Session,
        user_id: str,
        character_id: str,
        post_id: str,
        local_key_prefix: str,
    ) -> None:
        return _log_local_api_image_rejected(db=db, user_id=user_id, character_id=character_id, post_id=post_id, local_key_prefix=local_key_prefix)
