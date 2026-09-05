"""Character profile, draft, candidate and seed file placement.

The caller owns authentication, candidate expiry and the database transaction.
These operations retain the existing write/delete order and return managed URLs.
"""
from io import BytesIO
import shutil
from uuid import uuid4

from PIL import Image

from app.config import settings
from app.domains.media.contracts import InvalidProfileMediaError
from app.integrations.media.files import _media_url_to_path
from app.integrations.media.images import (
    CONTENT_TYPES,
    SEED_IMAGE_TARGET_SIZE,
    WEBP_QUALITY,
    _content_type_from_suffix,
    decode_profile_media,
    encode_image_webp_preserve_ratio,
    encode_profile_media_webp,
    validate_profile_media_content,
)


def save_profile_media(
    *,
    character_id: str,
    media_type: str,
    content_type: str,
    data_base64: str,
) -> str:
    content = decode_profile_media(content_type=content_type, data_base64=data_base64)
    return save_profile_media_bytes(
        character_id=character_id,
        media_type=media_type,
        content_type=content_type,
        content=content,
    )


def save_profile_media_bytes(
    *,
    character_id: str,
    media_type: str,
    content_type: str,
    content: bytes,
) -> str:
    if media_type not in {"avatar", "banner"}:
        raise InvalidProfileMediaError("Unsupported media type")

    normalized_content_type = content_type.strip().lower()
    type_info = CONTENT_TYPES.get(normalized_content_type)
    if type_info is None:
        raise InvalidProfileMediaError("Only jpg, png, and webp images are allowed")
    validate_profile_media_content(normalized_content_type, content)
    encoded = encode_profile_media_webp(media_type=media_type, content=content)

    character_dir = settings.media_root_path / "characters" / character_id
    character_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{media_type}-{uuid4().hex}.webp"
    path = character_dir / filename
    path.write_bytes(encoded)

    return f"{settings.media_url_path}/characters/{character_id}/{filename}"


def save_seed_image(
    *,
    character_id: str,
    content_type: str,
    data_base64: str,
) -> str:
    content = decode_profile_media(content_type=content_type, data_base64=data_base64)
    return save_seed_image_bytes(
        character_id=character_id,
        content_type=content_type,
        content=content,
    )


def save_seed_image_bytes(
    *,
    character_id: str,
    content_type: str,
    content: bytes,
) -> str:
    normalized_content_type = content_type.strip().lower()
    if normalized_content_type not in CONTENT_TYPES:
        raise InvalidProfileMediaError("Only jpg, png, and webp images are allowed")
    validate_profile_media_content(normalized_content_type, content)
    encoded = encode_image_webp_preserve_ratio(
        content=content,
        max_size=SEED_IMAGE_TARGET_SIZE,
        quality=WEBP_QUALITY,
    )
    character_dir = settings.media_root_path / "characters" / character_id
    character_dir.mkdir(parents=True, exist_ok=True)
    filename = f"image-seed-{uuid4().hex}.webp"
    path = character_dir / filename
    path.write_bytes(encoded)
    return f"{settings.media_url_path}/characters/{character_id}/{filename}"


def save_draft_profile_media(
    *,
    draft_id: str,
    media_type: str,
    content_type: str,
    data_base64: str,
) -> str:
    content = decode_profile_media(content_type=content_type, data_base64=data_base64)
    return save_draft_profile_media_bytes(
        draft_id=draft_id,
        media_type=media_type,
        content_type=content_type,
        content=content,
    )


def save_draft_profile_media_bytes(
    *,
    draft_id: str,
    media_type: str,
    content_type: str,
    content: bytes,
) -> str:
    if media_type not in {"avatar", "banner"}:
        raise InvalidProfileMediaError("Unsupported media type")

    normalized_content_type = content_type.strip().lower()
    type_info = CONTENT_TYPES.get(normalized_content_type)
    if type_info is None:
        raise InvalidProfileMediaError("Only jpg, png, and webp images are allowed")
    validate_profile_media_content(normalized_content_type, content)
    encoded = encode_profile_media_webp(media_type=media_type, content=content)

    draft_dir = settings.media_root_path / "drafts" / draft_id
    draft_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{media_type}-{uuid4().hex}.webp"
    path = draft_dir / filename
    path.write_bytes(encoded)

    return f"{settings.media_url_path}/drafts/{draft_id}/{filename}"


def save_profile_image_candidate_bytes(
    *,
    user_id: str,
    candidate_id: str,
    media_type: str,
    content_type: str,
    content: bytes,
) -> dict[str, object]:
    if media_type not in {"avatar", "banner"}:
        raise InvalidProfileMediaError("Unsupported media type")

    normalized_content_type = content_type.strip().lower()
    if normalized_content_type not in CONTENT_TYPES:
        raise InvalidProfileMediaError("Only jpg, png, and webp images are allowed")
    validate_profile_media_content(normalized_content_type, content)
    encoded = encode_profile_media_webp(media_type=media_type, content=content)
    with Image.open(BytesIO(encoded)) as image:
        width, height = image.size

    candidate_dir = settings.media_root_path / "profile-candidates" / user_id / candidate_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{media_type}.webp"
    path = candidate_dir / filename
    path.write_bytes(encoded)

    return {
        "url": f"{settings.media_url_path}/profile-candidates/{user_id}/{candidate_id}/{filename}",
        "content_type": "image/webp",
        "byte_size": len(encoded),
        "width": width,
        "height": height,
    }


def promote_draft_profile_media(
    *, character_id: str, media_type: str, draft_media_url: str
) -> str:
    if media_type not in {"avatar", "banner"}:
        raise InvalidProfileMediaError("Unsupported media type")
    source = _media_url_to_path(draft_media_url)
    draft_root = (settings.media_root_path / "drafts").resolve()
    try:
        source.resolve().relative_to(draft_root)
    except ValueError as exc:
        raise InvalidProfileMediaError("Invalid draft media path") from exc
    if not source.is_file():
        raise InvalidProfileMediaError("Draft media file is missing")

    content = source.read_bytes()
    content_type = _content_type_from_suffix(source.suffix.lower())
    validate_profile_media_content(content_type, content)
    encoded = encode_profile_media_webp(media_type=media_type, content=content)
    character_dir = settings.media_root_path / "characters" / character_id
    character_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{media_type}-{uuid4().hex}.webp"
    destination = character_dir / filename
    destination.write_bytes(encoded)
    return f"{settings.media_url_path}/characters/{character_id}/{filename}"


def promote_profile_image_candidate(
    *, character_id: str, media_type: str, candidate_media_url: str
) -> str:
    if media_type not in {"avatar", "banner"}:
        raise InvalidProfileMediaError("Unsupported media type")
    source = _media_url_to_path(candidate_media_url)
    candidate_root = (settings.media_root_path / "profile-candidates").resolve()
    try:
        source.resolve().relative_to(candidate_root)
    except ValueError as exc:
        raise InvalidProfileMediaError("Invalid candidate media path") from exc
    if not source.is_file():
        raise InvalidProfileMediaError("Candidate media file is missing")

    content = source.read_bytes()
    content_type = _content_type_from_suffix(source.suffix.lower())
    validate_profile_media_content(content_type, content)
    encoded = encode_profile_media_webp(media_type=media_type, content=content)
    character_dir = settings.media_root_path / "characters" / character_id
    character_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{media_type}-{uuid4().hex}.webp"
    destination = character_dir / filename
    destination.write_bytes(encoded)
    return f"{settings.media_url_path}/characters/{character_id}/{filename}"


def delete_profile_image_candidate(candidate_id: str, user_id: str) -> None:
    candidate_dir = settings.media_root_path / "profile-candidates" / user_id / candidate_id
    if candidate_dir.exists():
        shutil.rmtree(candidate_dir, ignore_errors=True)


def delete_draft_media(draft_id: str) -> None:
    draft_dir = settings.media_root_path / "drafts" / draft_id
    if draft_dir.exists():
        shutil.rmtree(draft_dir, ignore_errors=True)
