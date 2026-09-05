from __future__ import annotations

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
