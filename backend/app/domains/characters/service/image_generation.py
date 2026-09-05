"""Character image-generation admission, quota and candidate persistence.

Provider transport is shared; model settings, service-key access and translation
are supplied by runtime without taking over the caller's Session.
"""
from datetime import UTC, datetime
import logging
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import settings
from app.core import security
from app.domains.characters import models as character_models, schemas, exceptions as errors
from app.domains.characters.contracts import CharacterOwner, CreatorWorkflows, CharacterImageGenerationWorkflows
from app.domains.characters.exceptions import AgentCreationDraftMediaError, AgentProfileImageQuotaExceededError
from app.domains.characters.service import drafts as draft_lifecycle, profile as character_profile
from app.domains.characters.service import media_storage as profile_media
from app.domains.characters.service.creator import DRAFT_COOLDOWN, PROFILE_IMAGE_CANDIDATE_TTL, _ensure_not_in_cooldown, _draft_read
from app.domains.characters.service.image_quota import (
    _profile_image_usage_status, _reserve_profile_image_quota,
    _finalize_profile_image_quota, _profile_image_bucket,
)
from app.domains.characters.service.media import _cleanup_expired_profile_image_candidates
from app.integrations import image_provider, pollinations_image, replicate_image

logger = logging.getLogger("app.runtime.characters.creator")


POLLINATIONS_MAX_SEED = 2_147_483_647


STYLE_PROMPTS = {
    "기본": "polished character illustration",
    "애니메풍": "cinematic anime style",
    "리얼풍": "realistic digital art style",
    "3D풍": "stylized 3D character render",
}


async def generate_media(
    db: Session,
    user: CharacterOwner,
    draft_id: str,
    data: schemas.AgentCreationDraftGenerateMediaCreate,
    *, workflows: CharacterImageGenerationWorkflows,
    creator_workflows: CreatorWorkflows,
) -> schemas.AgentCreationDraftMediaGenerationRead:
    draft = draft_lifecycle._get_owned_draft(db, user, draft_id, workflows=creator_workflows)
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
    image_model = workflows.get_model(db)
    route_mode = workflows.get_route_mode(db)
    if image_provider.is_replicate_model(image_model):
        route_mode = "replicate"
    generation_seed = uuid4().hex
    profile_image_key_available = workflows.image_key_available(image_model)
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
        workflows.translate_prompt(draft.appearance_prompt)
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
                workflows=workflows,
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
    user: CharacterOwner,
    character_id: str,
    data: schemas.AgentProfileMediaGenerateCreate,
    *, workflows: CharacterImageGenerationWorkflows,
) -> schemas.AgentProfileMediaGenerationRead:
    character = character_profile.get_character(db, character_id)
    if (
        character is None
        or character.owner_id != user.id
        or character.deleted_at is not None
    ):
        raise errors.AgentNotFoundError(character_id)
    _cleanup_expired_profile_image_candidates(db, user.id)

    results: list[schemas.AgentCreationDraftMediaResult] = []
    media_type = data.media_type
    width, height = _pollinations_image_size(media_type)
    try:
        image_model = workflows.get_model(db)
        route_mode = workflows.get_route_mode(db)
        profile_image_key_available = workflows.image_key_available(image_model)
        usage_status = _profile_image_usage_status(
            db,
            user=user,
            scope="profile",
            media_type=media_type,
        )
        appearance_prompt = (
            workflows.translate_prompt(data.appearance_prompt.strip())
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
            workflows=workflows,
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


async def _generate_profile_image_candidate(
    db: Session,
    *,
    user: CharacterOwner,
    scope: str,
    media_type: str,
    prompt: str,
    seed: int,
    model: str,
    route_mode: str,
    draft_id: str | None,
    character_id: str | None,
    workflows: CharacterImageGenerationWorkflows,
) -> tuple[character_models.ProfileImageCandidate, schemas.AgentProfileImageUsageStatusRead]:
    api_key = workflows.resolve_api_key(model)
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
        candidate = character_models.ProfileImageCandidate(
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


def _pollinations_image_size(
    media_type: str, size: tuple[int, int] | None = None
) -> tuple[int, int]:
    return size or ((768, 768) if media_type == "avatar" else (1024, 384))


def _draft_media_seed(draft_id: str, media_type: str) -> int:
    return int(security.hash_token(f"{draft_id}:{media_type}")[:8], 16) & POLLINATIONS_MAX_SEED
