"""Social image request admission and resident/local generation workflow."""
from __future__ import annotations
from collections.abc import Awaitable, Callable
from datetime import datetime
import hashlib
from app.domains.social.models import posts as models
from app.domains.social.schemas import community as schemas
from app.domains.social.repository import media as community_crud
from app.domains.social.contracts.image_generation import ImageCharacter, PreparedPostImage
from app.domains.social.contracts.image_workflows import ImageCredential, ImageSetting, ImageReference, ImageGenerationWorkflows
from app.domains.social.constants import POLLINATIONS_IMAGE_TIMEOUT_SECONDS
from app.domains.social.exceptions import ServiceImageQuotaError
from app.domains.social.service.image_quota import _daily_image_usage, _reserve_service_image_quota, _finalize_service_image_quota
from app.domains.social.service.image_prompts import _image_llm_model_for_writing_mode, _compose_pollinations_prompt, _compose_local_api_pollinations_prompt
from app.domains.social.service.image_reference_policy import _reference_image_url, _requires_reference, _allows_reference_fallback
from app.domains.social.service.image_attempts import _skipped, _failed, _pollinations_failed, _replicate_failed
from app.core.image_generation import DEFAULT_POLLINATIONS_IMAGE_MODEL, IMAGE_MODEL_OPTIONS
from app.integrations import image_provider, pollinations_image, replicate_image
from sqlalchemy.orm import Session


async def prepare_post_image(
    *,
    workflows: ImageGenerationWorkflows,
    db: Session,
    character: ImageCharacter,
    credential: ImageCredential,
    run_id: str,
    tracker: object,
    writing_mode: str,
    post_title: str,
    post_body: str,
    writing_plan: dict[str, Any],
    current_time_text: str,
    run_started_at: datetime,
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None = None,
) -> PreparedPostImage:
    setting = workflows.get_image_generation_setting(db, character.id)
    if setting is None:
        return _skipped("no_image_key")
    key_source = _image_key_source(setting)
    model = _image_model_for_key_source(setting, key_source, workflows=workflows, db=db)
    provider = "replicate" if image_provider.is_replicate_model(model) else "pollinations"
    base_attempt = {"provider": provider, "model": model}
    if key_source == "disabled":
        return _skipped("disabled", **base_attempt)
    if key_source == "service" and not workflows.service_image_available(model):
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
    reference = workflows.select_reference_image(character, setting)
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
    route_mode = "replicate" if provider == "replicate" else workflows.image_route_mode(db)
    try:
        if _requires_reference(model):
            assert reference is not None
            visual_identity = await workflows.ensure_visual_identity(
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
                    visual_identity = await workflows.ensure_visual_identity(
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
                visual_identity = await workflows.resolve_visual_identity(
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
        refined = await workflows.refine_image_prompt(
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
        image_key = workflows.image_key_for_source(setting, key_source, model, character=character)
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
    except workflows.llm_error as exc:
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
    workflows: ImageGenerationWorkflows,
    db: Session,
    user_id: str,
    local_key_prefix: str,
    character: ImageCharacter,
    post_id: str,
    image_prompt: str,
    requested_at: datetime,
) -> schemas.BotImageRequestRead:
    setting = workflows.get_image_generation_setting(db, character.id)
    key_source = _image_key_source(setting)
    model = _image_model_for_key_source(setting, key_source, workflows=workflows, db=db)
    skip_reason = _local_api_image_skip_reason(workflows=workflows,
        db=db,
        setting=setting,
        character=character,
        image_prompt=image_prompt,
        requested_at=requested_at,
        key_source=key_source,
    )
    if skip_reason is not None:
        if skip_reason == "unsafe_prompt":
            workflows.log_local_api_image_rejected(
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
    workflows: ImageGenerationWorkflows,
    db: Session,
    character: ImageCharacter,
    image_prompt: str,
    run_started_at: datetime,
    key_source: str = "user",
    quota_reservation_id: int | None = None,
    post_id: str | None = None,
    job_id: int | None = None,
) -> PreparedPostImage:
    setting = workflows.get_image_generation_setting(db, character.id)
    if setting is None:
        return _skipped("no_image_key")
    key_source = key_source if key_source in {"service", "user"} else _image_key_source(setting)
    model = _image_model_for_key_source(setting, key_source, workflows=workflows, db=db)
    provider = "replicate" if image_provider.is_replicate_model(model) else "pollinations"
    base_attempt = {"provider": provider, "model": model}
    if key_source == "disabled":
        return _skipped("disabled", **base_attempt)
    if key_source == "service" and not workflows.service_image_available(model):
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
    if workflows.unsafe_image_text_reason(image_prompt) or workflows.unsafe_image_text_reason(visual_identity):
        return _skipped("unsafe_prompt", **base_attempt)
    reference = workflows.select_reference_image(character, setting)
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
    if workflows.unsafe_image_text_reason(prompt):
        return _skipped("unsafe_prompt", reference_source=reference_source, **base_attempt)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    reference_sent = bool(reference_image_url)
    route_mode = "replicate" if provider == "replicate" else workflows.image_route_mode(db)
    try:
        image_key = workflows.image_key_for_source(setting, key_source, model, character=character)
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


def _image_key_source(setting: ImageSetting | None) -> str:
    if setting is None:
        return "disabled"
    mode = (getattr(setting, "image_key_mode", "") or "").strip()
    if mode in {"service", "user", "disabled"}:
        return mode
    return "user" if setting.image_generation_enabled else "disabled"


def _has_user_image_key(setting: ImageSetting, model: str) -> bool:
    if image_provider.is_replicate_model(model):
        return bool(setting.encrypted_replicate_api_token)
    return bool(setting.encrypted_pollinations_api_key)


def _image_model_for_key_source(
    setting: ImageSetting | None,
    key_source: str,
    *,
    workflows: ImageGenerationWorkflows,
    db: Session | None = None,
) -> str:
    if key_source == "service":
        return workflows.free_image_model(db)
    if setting is None:
        return DEFAULT_POLLINATIONS_IMAGE_MODEL
    return setting.pollinations_image_model


def _local_api_image_skip_reason(
    *,
    workflows: ImageGenerationWorkflows,
    db: Session,
    setting: ImageSetting | None,
    character: ImageCharacter,
    image_prompt: str,
    requested_at: datetime,
    key_source: str,
) -> str | None:
    if setting is None:
        return "disabled"
    if key_source == "disabled":
        return "disabled"
    model = _image_model_for_key_source(setting, key_source, workflows=workflows, db=db)
    provider = "replicate" if image_provider.is_replicate_model(model) else "pollinations"
    if key_source == "service" and not workflows.service_image_available(model):
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
    if workflows.unsafe_image_text_reason(image_prompt) or workflows.unsafe_image_text_reason(visual_identity):
        return "unsafe_prompt"
    reference = workflows.select_reference_image(character, setting)
    reference_image_url = _reference_image_url(model, reference)
    if _requires_reference(model) and not reference_image_url:
        return "reference_required"
    prompt = _compose_local_api_pollinations_prompt(
        visual_identity=visual_identity,
        image_prompt=image_prompt,
        model=model,
    )
    if workflows.unsafe_image_text_reason(prompt):
        return "unsafe_prompt"
    return None
