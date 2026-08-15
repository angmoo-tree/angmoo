from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
import hashlib
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.config import settings
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
from app.services import (
    agent_activity_policy,
    image_prompt_safety,
    image_provider,
    operation_settings,
    pollinations_image,
    profile_media,
    replicate_image,
    service_image_key,
)
from app.services.direct_llm import (
    DirectLlmCallContext,
    DirectLlmError,
    DirectLlmImagePart,
    RunLlmTracker,
    generate_json,
)


POLLINATIONS_IMAGE_TIMEOUT_SECONDS = 90.0
IMAGE_PROMPT_MAX_LENGTH = 1800
LOCAL_API_PROMPT_SAFETY_SUFFIX = (
    "Safe public social illustration. No sexual content, no nudity, no gore, "
    "no hate symbols. No text, no watermark."
)
KLEIN_BODY_STRUCTURE_PROMPT_SUFFIX = (
    "Use a natural relaxed pose with coherent body structure and simple limb "
    "placement. Keep visible limbs consistent with the character's visual identity."
)
SERVICE_IMAGE_ACTIVE_RESERVATION_STATUSES = {
    "reserved",
    "queued",
    "processing",
    "attached",
}
IMAGE_VISUAL_IDENTITY_FIRST_GREETING_MODEL = "gemini-3.1-flash-lite"


class ServiceImageQuotaError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _VisualIdentityPayload(BaseModel):
    usable_identity: bool = True
    identity_prompt: str = Field(default="", max_length=1200)
    reason: str | None = Field(default=None, max_length=300)


class _ImagePromptPayload(BaseModel):
    prompt: str = Field(min_length=1, max_length=1800)
    alt_text: str = Field(min_length=1, max_length=240)


@dataclass(frozen=True)
class _ReferenceImage:
    source: str
    url: str
    source_hash: str
    llm_part: DirectLlmImagePart
    public_url: str | None


@dataclass(frozen=True)
class PreparedPostImage:
    attempt: dict[str, Any]
    content_type: str | None = None
    content: bytes | None = None
    alt_text: str | None = None
    prompt_hash: str | None = None
    model: str | None = None
    key_source: str = "none"
    quota_reservation_id: int | None = None

    @property
    def ready(self) -> bool:
        return (
            self.attempt.get("status") == "ready"
            and self.content_type is not None
            and self.content is not None
            and self.alt_text is not None
            and self.prompt_hash is not None
            and self.model is not None
        )


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
    setting = agent_crud.get_image_generation_setting(db, character.id)
    if setting is None:
        return _skipped("no_image_key")
    key_source = _image_key_source(setting)
    model = _image_model_for_key_source(setting, key_source, db=db)
    provider = "replicate" if image_provider.is_replicate_model(model) else "pollinations"
    base_attempt = {"provider": provider, "model": model}
    if key_source == "disabled":
        return _skipped("disabled", **base_attempt)
    if key_source == "service" and not service_image_key.is_service_image_available_for_model(model):
        return _skipped("service_key_missing", **base_attempt)
    if key_source == "user" and not _has_user_image_key(setting, model):
        return _skipped("replicate_key_missing" if provider == "replicate" else "no_image_key", **base_attempt)
    if model not in IMAGE_MODEL_OPTIONS:
        return _failed("unsupported_model", **base_attempt)
    if key_source == "user" and (
        _daily_image_usage(db, character_id=character.id, at=run_started_at)
        >= setting.max_images_per_day
    ):
        return _skipped("limit_exceeded", **base_attempt)
    reservation: models.PostImageQuotaReservation | None = None
    if key_source == "service":
        try:
            reservation = _reserve_service_image_quota(
                db,
                user_id=character.owner_id,
                character_id=character.id,
                source="resident",
                at=run_started_at,
            )
        except ServiceImageQuotaError as exc:
            return _skipped(exc.reason, **base_attempt)
    reference = _select_reference_image(character, setting)
    reference_source = reference.source if reference is not None else None
    reference_image_url = _reference_image_url(model, reference)
    if _requires_reference(model) and not reference_image_url:
        _finalize_service_image_quota(db, reservation, status="released")
        return _skipped(
            "reference_required",
            reference_source=reference_source,
            **base_attempt,
        )

    prompt = ""
    prompt_hash = ""
    reference_sent = bool(reference_image_url)
    route_mode = "replicate" if provider == "replicate" else operation_settings.get_pollinations_image_route_mode(db)
    try:
        if _requires_reference(model):
            assert reference is not None
            visual_identity = await _ensure_visual_identity(
                db=db,
                setting=setting,
                character=character,
                credential=credential,
                reference=reference,
                tracker=tracker,
                run_id=run_id,
                on_rate_limit_wait=on_rate_limit_wait,
                model_override=_image_llm_model_for_writing_mode(writing_mode),
            )
            if not visual_identity:
                _finalize_service_image_quota(db, reservation, status="released")
                return _skipped(
                    "reference_unusable",
                    reference_source=reference_source,
                    **base_attempt,
                )
        else:
            if key_source == "service":
                if setting.visual_identity_prompt and setting.visual_identity_source_hash is None:
                    visual_identity = setting.visual_identity_prompt.strip()
                elif reference is not None:
                    visual_identity = await _ensure_visual_identity(
                        db=db,
                        setting=setting,
                        character=character,
                        credential=credential,
                        reference=reference,
                        tracker=tracker,
                        run_id=run_id,
                        on_rate_limit_wait=on_rate_limit_wait,
                        model_override=_image_llm_model_for_writing_mode(writing_mode),
                    )
                else:
                    visual_identity = None
            else:
                visual_identity = await _resolve_visual_identity(
                    db=db,
                    setting=setting,
                    character=character,
                    credential=credential,
                    reference=reference,
                    tracker=tracker,
                    run_id=run_id,
                    on_rate_limit_wait=on_rate_limit_wait,
                    model_override=_image_llm_model_for_writing_mode(writing_mode),
                )
            if not visual_identity:
                _finalize_service_image_quota(db, reservation, status="released")
                return _skipped(
                    "visual_identity_required",
                    reference_source=reference_source,
                    **base_attempt,
                )
        refined = await _refine_image_prompt(
            character=character,
            credential=credential,
            tracker=tracker,
            run_id=run_id,
            image_model=model,
            current_time_text=current_time_text,
            post_title=post_title,
            post_body=post_body,
            writing_plan=writing_plan,
            visual_identity=visual_identity,
            on_rate_limit_wait=on_rate_limit_wait,
            model_override=_image_llm_model_for_writing_mode(writing_mode),
        )
        prompt = _compose_pollinations_prompt(refined, model=model)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        image_key = _image_key_for_source(setting, key_source, model, character=character)
        if image_key is None:
            _finalize_service_image_quota(db, reservation, status="released")
            return _skipped(
                "service_key_missing"
                if key_source == "service"
                else ("replicate_key_missing" if provider == "replicate" else "no_image_key"),
                **base_attempt,
            )
        generated = await image_provider.generate_image(
            api_key=image_key,
            model=model,
            prompt=prompt,
            reference_image_url=reference_image_url,
            allow_reference_fallback=_allows_reference_fallback(model),
            timeout_seconds=POLLINATIONS_IMAGE_TIMEOUT_SECONDS,
            prompt_hash=prompt_hash,
            route_mode=route_mode,
            width=640 if provider == "replicate" else 1024,
            height=480 if provider == "replicate" else 768,
            log_context={
                "key_source": key_source,
                "character_id": character.id,
                "run_id": run_id,
                "reference_source": reference_source,
                "route_mode": route_mode,
            },
        )
        return PreparedPostImage(
            attempt={
                "status": "ready",
                "provider": provider,
                "model": model,
                "route_mode": route_mode,
                "reference_source": reference_source,
                "reference_sent": reference_sent,
                "fallback_used": generated.fallback_used,
                "safe_filter": getattr(
                    generated,
                    "safe_filter",
                    pollinations_image.POLLINATIONS_SAFE_FILTER,
                ),
                "relay_elapsed_ms": getattr(generated, "relay_elapsed_ms", None),
                "prompt_hash": prompt_hash,
                "key_source": key_source,
                "quota_reservation_id": reservation.id if reservation is not None else None,
                "provider_prediction_id": getattr(generated, "prediction_id", None),
                "provider_elapsed_ms": getattr(generated, "elapsed_ms", None),
            },
            content_type=generated.content_type,
            content=generated.content,
            alt_text=refined["alt_text"],
            prompt_hash=prompt_hash,
            model=model,
            key_source=key_source,
            quota_reservation_id=reservation.id if reservation is not None else None,
        )
    except DirectLlmError as exc:
        _finalize_service_image_quota(db, reservation, status="failed")
        return _failed(
            type(exc).__name__,
            reference_source=reference_source,
            **base_attempt,
        )
    except pollinations_image.PollinationsImageError as exc:
        _finalize_service_image_quota(db, reservation, status="failed")
        return _pollinations_failed(
            exc,
            key_source=key_source,
            reference_source=reference_source,
            reference_sent=reference_sent,
            prompt_hash=prompt_hash,
            prompt_length=len(prompt),
            quota_reservation_id=reservation.id if reservation is not None else None,
            route_mode=route_mode,
            **base_attempt,
        )
    except replicate_image.ReplicateImageError as exc:
        _finalize_service_image_quota(db, reservation, status="failed")
        return _replicate_failed(
            exc,
            key_source=key_source,
            reference_source=reference_source,
            prompt_hash=prompt_hash,
            prompt_length=len(prompt),
            quota_reservation_id=reservation.id if reservation is not None else None,
            route_mode=route_mode,
            **base_attempt,
        )
    except Exception as exc:
        _finalize_service_image_quota(db, reservation, status="failed")
        return _failed(
            type(exc).__name__,
            reference_source=reference_source,
            **base_attempt,
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
    setting = agent_crud.get_image_generation_setting(db, character.id)
    key_source = _image_key_source(setting)
    model = _image_model_for_key_source(setting, key_source, db=db)
    skip_reason = _local_api_image_skip_reason(
        db=db,
        setting=setting,
        character=character,
        image_prompt=image_prompt,
        requested_at=requested_at,
        key_source=key_source,
    )
    if skip_reason is not None:
        if skip_reason == "unsafe_prompt":
            _log_local_api_image_rejected(
                db=db,
                user_id=user_id,
                character_id=character.id,
                post_id=post_id,
                local_key_prefix=local_key_prefix,
            )
        job = community_crud.create_post_image_generation_job(
            db,
            post_id=post_id,
            user_id=user_id,
            character_id=character.id,
            source="local_api",
            status="skipped",
            key_source=key_source if key_source != "disabled" else "none",
            image_model=model,
            image_prompt=image_prompt,
            skip_reason=skip_reason,
        )
        return schemas.BotImageRequestRead(
            status="skipped",
            job_id=job.id,
            skip_reason=skip_reason,
        )
    if model not in IMAGE_MODEL_OPTIONS:
        job = community_crud.create_post_image_generation_job(
            db,
            post_id=post_id,
            user_id=user_id,
            character_id=character.id,
            source="local_api",
            status="failed",
            key_source=key_source if key_source != "disabled" else "none",
            image_model=model,
            image_prompt=image_prompt,
            failure_class="unsupported_model",
        )
        return schemas.BotImageRequestRead(
            status="failed",
            job_id=job.id,
            failure_class="unsupported_model",
        )
    reservation: models.PostImageQuotaReservation | None = None
    if key_source == "service":
        try:
            reservation = _reserve_service_image_quota(
                db,
                user_id=user_id,
                character_id=character.id,
                source="local_api",
                at=requested_at,
                status="queued",
                post_id=post_id,
            )
        except ServiceImageQuotaError as exc:
            job = community_crud.create_post_image_generation_job(
                db,
                post_id=post_id,
                user_id=user_id,
                character_id=character.id,
                source="local_api",
                status="skipped",
                key_source="service",
                image_model=model,
                image_prompt=image_prompt,
                skip_reason=exc.reason,
            )
            return schemas.BotImageRequestRead(
                status="skipped",
                job_id=job.id,
                skip_reason=exc.reason,
            )
    job = community_crud.create_post_image_generation_job(
        db,
        post_id=post_id,
        user_id=user_id,
        character_id=character.id,
        source="local_api",
        status="queued",
        key_source=key_source,
        quota_reservation_id=reservation.id if reservation is not None else None,
        image_model=model,
        image_prompt=image_prompt,
    )
    if reservation is not None:
        community_crud.update_post_image_quota_reservation(
            db, reservation, status="queued", post_id=post_id, job_id=job.id
        )
        db.commit()
    return schemas.BotImageRequestRead(status="queued", job_id=job.id)


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
    setting = agent_crud.get_image_generation_setting(db, character.id)
    if setting is None:
        return _skipped("no_image_key")
    key_source = key_source if key_source in {"service", "user"} else _image_key_source(setting)
    model = _image_model_for_key_source(setting, key_source, db=db)
    provider = "replicate" if image_provider.is_replicate_model(model) else "pollinations"
    base_attempt = {"provider": provider, "model": model}
    if key_source == "disabled":
        return _skipped("disabled", **base_attempt)
    if key_source == "service" and not service_image_key.is_service_image_available_for_model(model):
        return _skipped("service_key_missing", **base_attempt)
    if key_source == "user" and not _has_user_image_key(setting, model):
        return _skipped("replicate_key_missing" if provider == "replicate" else "no_image_key", **base_attempt)
    if model not in IMAGE_MODEL_OPTIONS:
        return _failed("unsupported_model", **base_attempt)
    visual_identity = (setting.visual_identity_prompt or "").strip()
    if not visual_identity or setting.visual_identity_source_hash is not None:
        return _skipped("visual_identity_required", **base_attempt)
    if (
        key_source == "user"
        and _daily_image_usage(db, character_id=character.id, at=run_started_at)
        >= setting.max_images_per_day
    ):
        return _skipped("limit_exceeded", **base_attempt)
    if _unsafe_image_text_reason(image_prompt) or _unsafe_image_text_reason(visual_identity):
        return _skipped("unsafe_prompt", **base_attempt)
    reference = _select_reference_image(character, setting)
    reference_source = reference.source if reference is not None else None
    reference_image_url = _reference_image_url(model, reference)
    if _requires_reference(model) and not reference_image_url:
        return _skipped(
            "reference_required",
            reference_source=reference_source,
            **base_attempt,
        )
    prompt = _compose_local_api_pollinations_prompt(
        visual_identity=visual_identity,
        image_prompt=image_prompt,
        model=model,
    )
    if _unsafe_image_text_reason(prompt):
        return _skipped("unsafe_prompt", reference_source=reference_source, **base_attempt)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    reference_sent = bool(reference_image_url)
    route_mode = "replicate" if provider == "replicate" else operation_settings.get_pollinations_image_route_mode(db)
    try:
        image_key = _image_key_for_source(setting, key_source, model, character=character)
        if image_key is None:
            return _skipped(
                "service_key_missing"
                if key_source == "service"
                else ("replicate_key_missing" if provider == "replicate" else "no_image_key"),
                **base_attempt,
            )
        generated = await image_provider.generate_image(
            api_key=image_key,
            model=model,
            prompt=prompt,
            reference_image_url=reference_image_url,
            allow_reference_fallback=_allows_reference_fallback(model),
            timeout_seconds=POLLINATIONS_IMAGE_TIMEOUT_SECONDS,
            prompt_hash=prompt_hash,
            route_mode=route_mode,
            width=640 if provider == "replicate" else 1024,
            height=480 if provider == "replicate" else 768,
            log_context={
                "key_source": key_source,
                "character_id": character.id,
                "post_id": post_id,
                "job_id": job_id,
                "reference_source": reference_source,
                "source": "local_api",
                "route_mode": route_mode,
            },
        )
    except pollinations_image.PollinationsImageError as exc:
        return _pollinations_failed(
            exc,
            key_source=key_source,
            reference_source=reference_source,
            reference_sent=reference_sent,
            prompt_hash=prompt_hash,
            prompt_length=len(prompt),
            quota_reservation_id=quota_reservation_id,
            route_mode=route_mode,
            **base_attempt,
        )
    except replicate_image.ReplicateImageError as exc:
        return _replicate_failed(
            exc,
            key_source=key_source,
            reference_source=reference_source,
            prompt_hash=prompt_hash,
            prompt_length=len(prompt),
            quota_reservation_id=quota_reservation_id,
            route_mode=route_mode,
            **base_attempt,
        )
    except Exception as exc:
        return _failed(
            type(exc).__name__,
            reference_source=reference_source,
            **base_attempt,
        )
    return PreparedPostImage(
        attempt={
            "status": "ready",
            "provider": provider,
            "model": model,
            "route_mode": route_mode,
            "reference_source": reference_source,
            "reference_sent": reference_sent,
            "fallback_used": generated.fallback_used,
            "safe_filter": getattr(
                generated,
                "safe_filter",
                pollinations_image.POLLINATIONS_SAFE_FILTER,
            ),
            "relay_elapsed_ms": getattr(generated, "relay_elapsed_ms", None),
            "prompt_hash": prompt_hash,
            "key_source": key_source,
            "quota_reservation_id": quota_reservation_id,
            "provider_prediction_id": getattr(generated, "prediction_id", None),
            "provider_elapsed_ms": getattr(generated, "elapsed_ms", None),
        },
        content_type=generated.content_type,
        content=generated.content,
        alt_text=f"{character.name}의 게시글에 첨부된 AI 생성 이미지",
        prompt_hash=prompt_hash,
        model=model,
        key_source=key_source,
        quota_reservation_id=quota_reservation_id,
    )


def attach_prepared_post_image(
    *,
    db: Session,
    post_id: str,
    prepared: PreparedPostImage,
) -> dict[str, Any]:
    if not prepared.ready:
        return prepared.attempt
    assert prepared.content is not None
    assert prepared.content_type is not None
    assert prepared.alt_text is not None
    assert prepared.prompt_hash is not None
    assert prepared.model is not None
    try:
        saved = profile_media.save_generated_post_image_bytes(
            post_id=post_id,
            content_type=prepared.content_type,
            content=prepared.content,
            target_size=POST_IMAGE_TARGET_SIZE,
            max_bytes=POST_IMAGE_TARGET_MAX_BYTES,
            quality_steps=POST_IMAGE_WEBP_QUALITY_STEPS,
        )
        media = community_crud.create_post_media(
            db,
            post_id=post_id,
            url=str(saved["url"]),
            alt_text=prepared.alt_text,
            model=prepared.model,
            prompt_hash=prepared.prompt_hash,
            byte_size=int(saved["byte_size"]),
            width=int(saved["width"]),
            height=int(saved["height"]),
            key_source=prepared.key_source if prepared.key_source != "none" else "user",
        )
    except Exception as exc:
        reservation = community_crud.get_post_image_quota_reservation(
            db, prepared.quota_reservation_id
        )
        _finalize_service_image_quota(db, reservation, status="failed", post_id=post_id)
        return {
            **prepared.attempt,
            "status": "failed",
            "failure_class": type(exc).__name__,
        }
    reservation = community_crud.get_post_image_quota_reservation(
        db, prepared.quota_reservation_id
    )
    _finalize_service_image_quota(db, reservation, status="attached", post_id=post_id)
    return {
        **prepared.attempt,
        "status": "attached",
        "media_url": media.url,
        "byte_size": media.byte_size,
    }


def release_prepared_post_image_quota(
    *,
    db: Session,
    prepared: PreparedPostImage | None,
    status: str = "released",
) -> None:
    if prepared is None or prepared.quota_reservation_id is None:
        return
    reservation = community_crud.get_post_image_quota_reservation(
        db, prepared.quota_reservation_id
    )
    _finalize_service_image_quota(db, reservation, status=status)


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


def _visual_identity_system_prompt(*, character: models.Character) -> str:
    return f"""
You describe visual identity for an Angmoo autonomous character.
Return JSON only with keys: usable_identity, identity_prompt, reason.

Rules:
- If the image is mainly a landscape, logo, abstract banner, object, or empty background, set usable_identity=false.
- If a character/person is clearly visible, describe a stable visual contract useful for future image generation.
- Do not name copyrighted franchises or real people. Describe visual traits instead.
- Write identity_prompt in English, concise and concrete.
- Prefer this structure when usable_identity=true:
  Rendering style: ...
  Do not render as: ...
  Character identity: ...
  Stable traits: ...
- Rendering style must describe the durable art direction visible in the reference image, such as Japanese TV anime-inspired 2D cel-shaded illustration, polished toon-shaded 3D animation, stylized cartoon, semi-realistic digital painting, or photorealistic portrait.
- Separate physical traits from rendering style. Put face, hair, outfit, colors, species or body form, and props under Character identity or Stable traits, not under Rendering style.
- If the reference image is photographic or realistic, keep that as Rendering style only when it appears to be the intended character art direction; otherwise preserve the physical traits without forcing a photographic rendering style.
- Use Do not render as to name conflicting rendering styles that would break the visual identity.

Character:
- name: {character.name}
- one_liner: {character.one_liner}
- personality: {character.personality}
""".strip()


def _image_prompt_system_prompt(*, character: models.Character, image_model: str) -> str:
    if image_model == POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN:
        return _klein_image_prompt_system_prompt(character=character)
    if image_model == POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL:
        return _flux_schnell_image_prompt_system_prompt(character=character)
    if image_model in {POLLINATIONS_IMAGE_MODEL_ZIMAGE, REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA}:
        return _zimage_image_prompt_system_prompt(character=character)
    if image_model == POLLINATIONS_IMAGE_MODEL_SANA:
        return _sana_image_prompt_system_prompt(character=character)
    if image_model in {
        POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
        REPLICATE_IMAGE_MODEL_PRUNA_EDIT,
    }:
        return _pruna_edit_image_prompt_system_prompt(character=character)
    return _default_image_prompt_system_prompt(character=character)


def _default_image_prompt_system_prompt(*, character: models.Character) -> str:
    return f"""
You convert an Angmoo social post into one image-generation prompt.
Return JSON only with keys: prompt, alt_text.

Rules:
- Write prompt in English.
- Create a concrete 4:3 scene that fits the post context and current time.
- Treat post_title and post_body as the final source of truth; use writing_brief and active_step only as background, and do not copy time cues from them when they conflict with post_body or current_time.
- Preserve the provided visual identity, but do not copy the exact profile image pose or composition.
- Avoid text, speech bubbles, UI, logos, watermarks, gore, sexual content, and real-person claims.
- alt_text must be Korean and describe the generated image in one short sentence.

Character:
- name: {character.name}
- personality: {character.personality}
- speech_style: {character.speech_style}
- worldview: {character.worldview}
- topic_preferences: {character.topic_preferences}
- safety_rules: {character.safety_rules}
""".strip()


def _klein_image_prompt_system_prompt(*, character: models.Character) -> str:
    return f"""
You convert an Angmoo social post into one image-generation prompt for the klein image model.
Return JSON only with keys: prompt, alt_text.

Rules:
- Write prompt in English.
- FLUX.2 [klein] does not add prompt upsampling, so make the final prompt detailed and descriptive.
- Put important elements first: rendering style from visual_identity, main subject, key action or pose, essential context, then secondary details.
- If visual_identity includes a Rendering style line, start the final prompt with Style: followed by that rendering style.
- Create a concrete 4:3 scene that fits the post context and current time.
- Treat post_title and post_body as the final source of truth; use writing_brief and active_step only as background, and do not copy time cues from them when they conflict with post_body or current_time.
- Use natural-language prose that clearly describes subject, action, context, lighting, materials, composition, and spatial relationships.
- Preserve the provided visual identity's Rendering style, Do not render as constraints, physical traits, and reference image traits, but do not copy the exact profile image pose or composition.
- Do not mix conflicting rendering styles in the same prompt; for example, do not combine photorealistic rendering with toon-shaded 3D unless visual_identity explicitly defines that hybrid style.
- Describe the desired scene positively instead of using negative-prompt phrasing.
- If visible text is truly necessary, keep the exact wording in double quotes and describe its position, size, style, and color.
- If color is important, tie color names or hex colors to the exact object they modify.
- Avoid close-up hands, feet, or complex crossed limb poses unless essential to the post.
- Prefer simple limb placement that stays consistent with the provided visual identity.
- Avoid text, speech bubbles, UI, logos, watermarks, gore, sexual content, and real-person claims.
- alt_text must be Korean and describe the generated image in one short sentence.

Character:
- name: {character.name}
- personality: {character.personality}
- speech_style: {character.speech_style}
- worldview: {character.worldview}
- topic_preferences: {character.topic_preferences}
- safety_rules: {character.safety_rules}
""".strip()


def _flux_schnell_image_prompt_system_prompt(*, character: models.Character) -> str:
    return f"""
You convert an Angmoo social post into one image-generation prompt for the Flux Schnell image model.
Return JSON only with keys: prompt, alt_text.

Rules:
- Write prompt in English.
- Flux Schnell is a fast text-to-image model; use concise, concrete natural-language scene descriptions instead of quality-tag lists.
- If visual_identity includes a Rendering style line, start the final prompt with Style: followed by that rendering style.
- If visual_identity does not include an explicit Rendering style, start the prompt with: Style: anime-inspired 2D illustration or polished toon-shaded 3D animation.
- After the style phrase, continue in this order: main subject, action, setting, composition, lighting, color palette, key details.
- Create a concrete 4:3 visual scene that fits the post context and current time.
- Treat post_title and post_body as the final source of truth; use writing_brief and active_step only as background, and do not copy time cues from them when they conflict with post_body or current_time.
- Preserve the provided visual identity's Rendering style, Do not render as constraints, and physical traits, including face, hair, outfit, colors, species or body form, and props.
- If visual_identity contains realistic, photo, portrait, studio lighting, or camera lighting wording outside an explicit Rendering style line, preserve the physical traits only and do not follow those words as the rendering style.
- If a portrait is necessary, write animated character portrait or character portrait illustration.
- Use visible details: subject placement, materials, color palette, spatial depth, mood, and environmental context.
- Do not use quality tags or meta labels such as 8K, masterpiece, best quality, ultra detailed, or photorealistic.
- Do not write photo, photorealistic, realistic skin, shot on, camera, lens, studio photography, film grain, or live-action in the final prompt unless visual_identity explicitly uses those words in its Rendering style line.
- Do not mix conflicting rendering styles in the same prompt; for example, do not combine photorealistic rendering with toon-shaded 3D unless visual_identity explicitly defines that hybrid style.
- Prefer positive style wording such as clean animated character art, stylized illustrated rendering, soft illustrated lighting, and expressive character design.
- Avoid metaphorical, emotional, or subjective phrases that cannot be directly seen.
- Avoid text, speech bubbles, UI, logos, watermarks, gore, sexual content, and real-person claims.
- If visible text is truly necessary, keep the exact wording in double quotes and describe its position, size, and layout.
- alt_text must be Korean and describe the generated image in one short sentence.

Character:
- name: {character.name}
- personality: {character.personality}
- speech_style: {character.speech_style}
- worldview: {character.worldview}
- topic_preferences: {character.topic_preferences}
- safety_rules: {character.safety_rules}
""".strip()


def _zimage_image_prompt_system_prompt(*, character: models.Character) -> str:
    return f"""
You convert an Angmoo social post into one image-generation prompt for the zimage image model.
Return JSON only with keys: prompt, alt_text.

Rules:
- Write prompt in English.
- Z-Image is used as a text-only image model in Angmoo; do not rely on reference images or provider-side style parameters.
- If visual_identity includes a Rendering style line, start the final prompt with Style: followed by that rendering style.
- After the Style phrase, continue with the subject, action, setting, composition, lighting, color palette, and key stable traits.
- Create a concrete 4:3 visual scene that fits the post context and current time.
- Treat post_title and post_body as the final source of truth; use writing_brief and active_step only as background, and do not copy time cues from them when they conflict with post_body or current_time.
- Preserve the post's core elements: intent, subject, count, action, state, specified colors, and any exact requested wording.
- Turn abstract ideas into a specific visible scene with clear subject placement, composition, lighting, materials, color palette, and spatial depth.
- Preserve the provided visual identity's Rendering style, Do not render as constraints, and stable physical traits, but do not copy the exact profile image pose or composition.
- Do not mix conflicting rendering styles in the same prompt; for example, do not combine photorealistic rendering with toon-shaded 3D unless visual_identity explicitly defines that hybrid style.
- Avoid text, speech bubbles, UI, logos, watermarks, gore, sexual content, and real-person claims.
- If visible text is truly necessary, keep the exact wording in double quotes and describe its position, size, and layout.
- Do not use quality tags or meta labels such as 8K, masterpiece, best quality, ultra detailed, or photorealistic.
- Avoid metaphorical, emotional, or subjective phrases that cannot be directly seen.
- alt_text must be Korean and describe the generated image in one short sentence.

Character:
- name: {character.name}
- personality: {character.personality}
- speech_style: {character.speech_style}
- worldview: {character.worldview}
- topic_preferences: {character.topic_preferences}
- safety_rules: {character.safety_rules}
""".strip()


def _sana_image_prompt_system_prompt(*, character: models.Character) -> str:
    return f"""
You convert an Angmoo social post into one image-generation prompt for the Sana Sprint 1.6B image model.
Return JSON only with keys: prompt, alt_text.

Rules:
- Write one natural-language prompt in English.
- Sana is a text-only text-to-image model; do not refer to or depend on a reference image, image editing, or provider-side image parameters.
- If visual_identity includes a Rendering style line, start the prompt with Style: followed by that rendering style.
- Build the prompt in this order: rendering style, character identity and stable traits, main subject and action, setting and time, composition and spatial relationships, lighting, color palette, materials, and textures.
- Create a concrete 4:3 visual scene that fits the post context and current time.
- Treat post_title and post_body as the final source of truth; use writing_brief and active_step only as background, and do not copy time cues from them when they conflict with post_body or current_time.
- Preserve the provided visual identity's Rendering style, Do not render as constraints, Character identity, and Stable traits without copying the exact profile image pose or composition.
- If the scene is simple, add visible specifics about colors, shapes, sizes, textures, materials, lighting, and spatial relationships to make it concrete. If it is already detailed, refine it lightly without overcomplicating it.
- Describe the scene positively with observable details instead of negative-prompt lists or vague quality claims.
- Do not use quality tags or meta labels such as 8K, masterpiece, best quality, ultra detailed, or photorealistic.
- Do not include an Enhanced prompt prefix or commentary outside the requested scene description.
- Avoid text, speech bubbles, UI, logos, watermarks, gore, sexual content, and real-person claims.
- If visible text is truly necessary, keep the exact wording in double quotes and describe its position, size, and layout.
- alt_text must be Korean and describe the generated image in one short sentence.

Character:
- name: {character.name}
- personality: {character.personality}
- speech_style: {character.speech_style}
- worldview: {character.worldview}
- topic_preferences: {character.topic_preferences}
- safety_rules: {character.safety_rules}
""".strip()


def _pruna_edit_image_prompt_system_prompt(*, character: models.Character) -> str:
    return f"""
You convert an Angmoo social post into image editing instructions for the Pruna p-image-edit model.
Return JSON only with keys: prompt, alt_text.

Rules:
- Write prompt in English.
- Write editing instructions for the reference image, not a standalone text-to-image prompt.
- Use this structure in the prompt: [Modification] [Change Target] [Preservation].
- Modification: describe how to change the background, pose, lighting, mood, and situation to fit the post context and current time.
- Treat post_title and post_body as the final source of truth; use writing_brief and active_step only as background, and do not copy time cues from them when they conflict with post_body or current_time.
- Change Target: explicitly name "the character from the reference image" and avoid vague pronouns such as it or they.
- Preservation: preserve the character's face, hairstyle, outfit identity, character identity, and art style from the reference image.
- If visual_identity includes a Rendering style line that does not conflict with the reference image's style, preserve that style too.
- If visual_identity's Rendering style conflicts with the reference image's style, prioritize the reference image's style and stable character traits instead of blending contradictory styles.
- Keep the same character recognizable while changing only the scene elements needed for the post.
- Do not copy the exact reference image pose or composition unless the post requires it.
- Avoid UI, logos, watermarks, gore, sexual content, and real-person claims.
- If visible text is truly necessary, keep the exact wording in double quotes and describe its position, size, and style.
- alt_text must be Korean and describe the edited image in one short sentence.

Character:
- name: {character.name}
- personality: {character.personality}
- speech_style: {character.speech_style}
- worldview: {character.worldview}
- topic_preferences: {character.topic_preferences}
- safety_rules: {character.safety_rules}
""".strip()


def _compose_pollinations_prompt(refined: dict[str, str], *, model: str) -> str:
    prompt = refined["prompt"].strip()
    if model != POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN:
        return prompt
    return _append_prompt_suffix(
        prompt,
        KLEIN_BODY_STRUCTURE_PROMPT_SUFFIX,
        max_length=IMAGE_PROMPT_MAX_LENGTH,
    )


def _append_prompt_suffix(prompt: str, suffix: str, *, max_length: int) -> str:
    separator = "\n\n"
    if len(prompt) + len(separator) + len(suffix) <= max_length:
        return f"{prompt}{separator}{suffix}" if prompt else suffix
    base_limit = max_length - len(separator) - len(suffix)
    if base_limit <= 0:
        return suffix[:max_length].strip()
    base = prompt[:base_limit].rstrip()
    return f"{base}{separator}{suffix}" if base else suffix[:max_length].strip()


def _compose_local_api_pollinations_prompt(
    *,
    visual_identity: str,
    image_prompt: str,
    model: str,
) -> str:
    prompt = (
        "Visual identity:\n"
        f"{visual_identity.strip()}\n\n"
        "Requested scene:\n"
        f"{image_prompt.strip()}"
    )
    prompt = _append_prompt_suffix(
        prompt,
        LOCAL_API_PROMPT_SAFETY_SUFFIX,
        max_length=IMAGE_PROMPT_MAX_LENGTH,
    )
    if model == POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN:
        prompt = _append_prompt_suffix(
            prompt,
            KLEIN_BODY_STRUCTURE_PROMPT_SUFFIX,
            max_length=IMAGE_PROMPT_MAX_LENGTH,
        )
    return prompt


def _fallback_visual_identity(character: models.Character) -> str:
    parts = [
        f"Character name: {character.name}",
        f"One-line identity: {character.one_liner}",
        f"Personality: {character.personality}",
        f"Worldview/background: {character.worldview}",
    ]
    return "\n".join(part for part in parts if part.split(":", 1)[-1].strip())[:1200]


def _pollinations_reference_url(
    model: str,
    reference: _ReferenceImage | None,
) -> str | None:
    if not _accepts_pollinations_reference(model) or reference is None:
        return None
    return reference.public_url


def _reference_image_url(
    model: str,
    reference: _ReferenceImage | None,
) -> str | None:
    if reference is None:
        return None
    if model == REPLICATE_IMAGE_MODEL_PRUNA_EDIT:
        return reference.public_url
    return _pollinations_reference_url(model, reference)


def _accepts_pollinations_reference(model: str) -> bool:
    return model in {
        POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN,
        POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
    }


def _requires_pollinations_reference(model: str) -> bool:
    return model == POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT


def _requires_reference(model: str) -> bool:
    return model in {
        POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
        REPLICATE_IMAGE_MODEL_PRUNA_EDIT,
    }


def _allows_reference_fallback(model: str) -> bool:
    return model == POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN


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
            path = profile_media.media_url_to_path(url)
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


def _daily_image_count(db: Session, *, character_id: str, at: datetime) -> int:
    return _daily_image_window_count(db, character_id=character_id, at=at)


def _daily_image_usage(db: Session, *, character_id: str, at: datetime) -> int:
    start_at, end_at = _daily_image_window(at)
    return community_crud.count_post_media_for_character_between(
        db,
        character_id=character_id,
        start_at=start_at,
        end_at=end_at,
    ) + community_crud.count_active_post_image_jobs_for_character_between(
        db,
        character_id=character_id,
        start_at=start_at,
        end_at=end_at,
    )


def _daily_image_window_count(db: Session, *, character_id: str, at: datetime) -> int:
    start_at, end_at = _daily_image_window(at)
    return community_crud.count_post_media_for_character_between(
        db,
        character_id=character_id,
        start_at=start_at,
        end_at=end_at,
    )


def _daily_image_window(at: datetime) -> tuple[datetime, datetime]:
    tz = agent_activity_policy.APP_TIMEZONE
    local_at = at.astimezone(tz) if at.tzinfo else at.replace(tzinfo=UTC).astimezone(tz)
    local_start = datetime.combine(local_at.date(), time.min, tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(UTC), local_end.astimezone(UTC)


def _image_key_source(setting: models.AgentImageGenerationSetting | None) -> str:
    if setting is None:
        return "disabled"
    mode = (getattr(setting, "image_key_mode", "") or "").strip()
    if mode in {"service", "user", "disabled"}:
        return mode
    return "user" if setting.image_generation_enabled else "disabled"


def _has_user_image_key(setting: models.AgentImageGenerationSetting, model: str) -> bool:
    if image_provider.is_replicate_model(model):
        return bool(setting.encrypted_replicate_api_token)
    return bool(setting.encrypted_pollinations_api_key)


def _image_model_for_key_source(
    setting: models.AgentImageGenerationSetting | None,
    key_source: str,
    *,
    db: Session | None = None,
) -> str:
    if key_source == "service":
        return operation_settings.get_pollinations_free_image_model(db)
    if setting is None:
        return DEFAULT_POLLINATIONS_IMAGE_MODEL
    return setting.pollinations_image_model


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


def _service_failure_class(failure_class: str, *, key_source: str) -> str:
    if key_source != "service":
        return failure_class
    if failure_class == "http_402":
        return "service_key_budget_exhausted"
    if failure_class == "http_429":
        return "service_rate_limited"
    return failure_class


def _service_quota_date(at: datetime) -> date:
    local_at = (
        at.astimezone(agent_activity_policy.APP_TIMEZONE)
        if at.tzinfo
        else at.replace(tzinfo=UTC).astimezone(agent_activity_policy.APP_TIMEZONE)
    )
    return local_at.date()


def _reserve_service_image_quota(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    source: str,
    at: datetime,
    status: str = "reserved",
    post_id: str | None = None,
) -> models.PostImageQuotaReservation:
    limit = settings.pollinations_service_free_images_per_user_day
    quota_date = _service_quota_date(at)
    if limit <= 0:
        raise ServiceImageQuotaError("free_quota_exceeded")
    community_crud.lock_service_image_quota(
        db,
        user_id=user_id,
        quota_date=quota_date,
    )
    used = community_crud.count_service_image_quota_used(
        db,
        user_id=user_id,
        quota_date=quota_date,
    )
    if used >= limit:
        raise ServiceImageQuotaError("free_quota_exceeded")
    global_cap = settings.pollinations_service_max_images_per_day
    if global_cap > 0:
        global_used = community_crud.count_service_image_global_used(
            db, quota_date=quota_date
        )
        if global_used >= global_cap:
            raise ServiceImageQuotaError("service_limit_exceeded")
    reservation = community_crud.create_post_image_quota_reservation(
        db,
        user_id=user_id,
        character_id=character_id,
        quota_date=quota_date,
        source=source,
        status=status,
        post_id=post_id,
    )
    db.commit()
    db.refresh(reservation)
    return reservation


def _finalize_service_image_quota(
    db: Session,
    reservation: models.PostImageQuotaReservation | None,
    *,
    status: str,
    post_id: str | None = None,
) -> None:
    if reservation is None:
        return
    community_crud.update_post_image_quota_reservation(
        db,
        reservation,
        status=status,
        post_id=post_id,
    )
    db.commit()


def _image_llm_model_for_writing_mode(writing_mode: str) -> str | None:
    return (
        IMAGE_VISUAL_IDENTITY_FIRST_GREETING_MODEL
        if writing_mode in {"owner_feed_cue", "first_greeting"}
        else None
    )


def _local_api_image_skip_reason(
    *,
    db: Session,
    setting: models.AgentImageGenerationSetting | None,
    character: models.Character,
    image_prompt: str,
    requested_at: datetime,
    key_source: str,
) -> str | None:
    if setting is None:
        return "disabled"
    if key_source == "disabled":
        return "disabled"
    model = _image_model_for_key_source(setting, key_source, db=db)
    provider = "replicate" if image_provider.is_replicate_model(model) else "pollinations"
    if key_source == "service" and not service_image_key.is_service_image_available_for_model(model):
        return "service_key_missing"
    if key_source == "user" and not _has_user_image_key(setting, model):
        return "replicate_key_missing" if provider == "replicate" else "no_image_key"
    visual_identity = (setting.visual_identity_prompt or "").strip()
    if not visual_identity or setting.visual_identity_source_hash is not None:
        return "visual_identity_required"
    if model not in IMAGE_MODEL_OPTIONS:
        return None
    if (
        key_source == "user"
        and _daily_image_usage(db, character_id=character.id, at=requested_at)
        >= setting.max_images_per_day
    ):
        return "limit_exceeded"
    if _unsafe_image_text_reason(image_prompt) or _unsafe_image_text_reason(visual_identity):
        return "unsafe_prompt"
    reference = _select_reference_image(character, setting)
    reference_image_url = _reference_image_url(model, reference)
    if _requires_reference(model) and not reference_image_url:
        return "reference_required"
    prompt = _compose_local_api_pollinations_prompt(
        visual_identity=visual_identity,
        image_prompt=image_prompt,
        model=model,
    )
    if _unsafe_image_text_reason(prompt):
        return "unsafe_prompt"
    return None


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


def json_safe_prompt(payload: dict[str, Any]) -> str:
    return "Input JSON:\n" + json_dumps(payload)


def json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, default=str)


def _pollinations_failed(
    exc: pollinations_image.PollinationsImageError,
    *,
    key_source: str,
    reference_source: str | None,
    reference_sent: bool,
    prompt_hash: str,
    prompt_length: int,
    quota_reservation_id: int | None,
    **extra: Any,
) -> PreparedPostImage:
    return _failed(
        _service_failure_class(exc.failure_class, key_source=key_source),
        reference_source=reference_source,
        reference_sent=(
            exc.reference_sent if exc.reference_sent is not None else reference_sent
        ),
        key_source=key_source,
        prompt_hash=prompt_hash,
        prompt_length=exc.prompt_length if exc.prompt_length is not None else prompt_length,
        pollinations_status_code=exc.status_code,
        pollinations_response_body_preview=exc.response_body_preview,
        pollinations_content_type=exc.response_content_type,
        pollinations_url_length=exc.request_url_length,
        safe_filter=exc.safe_filter,
        diagnostic_hint=exc.diagnostic_hint,
        relay_elapsed_ms=exc.relay_elapsed_ms,
        quota_reservation_id=quota_reservation_id,
        **extra,
    )


def _replicate_failed(
    exc: replicate_image.ReplicateImageError,
    *,
    key_source: str,
    reference_source: str | None,
    prompt_hash: str,
    prompt_length: int,
    quota_reservation_id: int | None,
    **extra: Any,
) -> PreparedPostImage:
    return _failed(
        _service_failure_class(exc.failure_class, key_source=key_source),
        reference_source=reference_source,
        reference_sent=False,
        key_source=key_source,
        prompt_hash=prompt_hash,
        prompt_length=prompt_length,
        provider_status_code=exc.status_code,
        provider_response_body_preview=exc.response_body_preview,
        provider_prediction_id=exc.prediction_id,
        quota_reservation_id=quota_reservation_id,
        **extra,
    )


def _skipped(skip_reason: str, **extra: Any) -> PreparedPostImage:
    return PreparedPostImage(
        attempt={"status": "skipped", "skip_reason": skip_reason, **extra}
    )


def _failed(failure_class: str, **extra: Any) -> PreparedPostImage:
    return PreparedPostImage(
        attempt={"status": "failed", "failure_class": failure_class, **extra}
    )
