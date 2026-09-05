"""World banner placement and World-specific errors over shared media IO.

The legacy upload entry preserves the former profile_media exception contract;
its compatibility export has no production consumer and is retired with B8.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.config import settings
from app.domains.media.contracts import InvalidProfileMediaError
from app.integrations.media import files, images
from app.integrations.media.images import (
    CONTENT_TYPES, decode_profile_media, encode_profile_media_webp,
    validate_profile_media_content,
)


class InvalidWorldBannerMediaError(Exception):
    """Raised when a World banner payload is unsafe or unsupported."""


def save_world_banner(
    *,
    world_id: str,
    content_type: str,
    data_base64: str,
) -> str:
    normalized_content_type = content_type.strip().lower()
    content = _decode_banner_media(
        content_type=normalized_content_type,
        data_base64=data_base64,
    )
    encoded = _encode_banner_webp(content)

    world_dir = settings.media_root_path / "worlds" / world_id
    world_dir.mkdir(parents=True, exist_ok=True)
    filename = f"banner-{uuid4().hex}.webp"
    path = world_dir / filename
    path.write_bytes(encoded)
    return f"{settings.media_url_path}/worlds/{world_id}/{filename}"


def delete_media_url(media_url: str | None) -> None:
    if not media_url:
        return
    try:
        path = _media_url_to_path(media_url)
    except InvalidWorldBannerMediaError:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _decode_banner_media(*, content_type: str, data_base64: str) -> bytes:
    try:
        return images.decode_profile_media(
            content_type=content_type, data_base64=data_base64,
        )
    except InvalidProfileMediaError as exc:
        raise InvalidWorldBannerMediaError(str(exc)) from exc


def _encode_banner_webp(content: bytes) -> bytes:
    try:
        return images.encode_profile_media_webp(media_type="banner", content=content)
    except InvalidProfileMediaError as exc:
        raise InvalidWorldBannerMediaError(str(exc)) from exc


def _media_url_to_path(media_url: str) -> Path:
    try:
        return files.media_url_to_path(media_url)
    except InvalidProfileMediaError as exc:
        raise InvalidWorldBannerMediaError(str(exc)) from exc


def save_legacy_world_banner(
    *,
    world_id: str,
    content_type: str,
    data_base64: str,
) -> str:
    content = decode_profile_media(content_type=content_type, data_base64=data_base64)
    normalized_content_type = content_type.strip().lower()
    if normalized_content_type not in CONTENT_TYPES:
        raise InvalidProfileMediaError("Only jpg, png, and webp images are allowed")
    validate_profile_media_content(normalized_content_type, content)
    encoded = encode_profile_media_webp(
        media_type="banner",
        content=content,
    )

    world_dir = settings.media_root_path / "worlds" / world_id
    world_dir.mkdir(parents=True, exist_ok=True)
    filename = f"banner-{uuid4().hex}.webp"
    path = world_dir / filename
    path.write_bytes(encoded)
    return f"{settings.media_url_path}/worlds/{world_id}/{filename}"
