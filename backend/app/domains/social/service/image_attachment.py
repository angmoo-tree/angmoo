"""Persist an accepted generated image and finalize its Social quota reservation."""
from __future__ import annotations
from typing import Any
from sqlalchemy.orm import Session
from app.domains.social.contracts.image_generation import PreparedPostImage
from app.domains.social.service import media_storage as profile_media
from app.domains.social.repository import media as community_crud
from app.domains.social.service.image_quota import _finalize_service_image_quota
from app.core.image_generation import POST_IMAGE_TARGET_SIZE, POST_IMAGE_TARGET_MAX_BYTES, POST_IMAGE_WEBP_QUALITY_STEPS


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
