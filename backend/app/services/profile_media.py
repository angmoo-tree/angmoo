"""Temporary media compatibility surface; actual implementations have role owners.

Character/preview callers are being migrated in AR-B3; Social job consumers end
their bridge in AR-B5. The historical World helper is closed with Worlds storage.
"""
from uuid import uuid4

from app.config import settings
from app.domains.media.contracts import InvalidProfileMediaError
from app.integrations.media.images import (
    CONTENT_TYPES,
    MEDIA_TARGET_SIZES,
    WEBP_QUALITY,
    SEED_IMAGE_TARGET_SIZE,
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_FRAMES,
    decode_profile_media,
    validate_profile_media_content,
    encode_profile_media_webp,
    encode_image_webp_preserve_ratio,
    encode_generated_post_webp,
    _assert_image_signature,
    _assert_decodable_image,
    _assert_safe_image_geometry,
    _content_type_from_suffix,
    _flatten_for_webp,
)
from app.integrations.media.files import (
    PrivateMediaCleanupError,
    PrivateMediaQuarantine,
    quarantine_private_media,
    media_url_to_path,
    resolve_private_media_file,
    delete_media_url,
    _media_url_to_path,
)
from app.domains.characters.service.media_storage import (
    save_profile_media,
    save_profile_media_bytes,
    save_seed_image,
    save_seed_image_bytes,
    save_draft_profile_media,
    save_draft_profile_media_bytes,
    save_profile_image_candidate_bytes,
    promote_draft_profile_media,
    promote_profile_image_candidate,
    delete_profile_image_candidate,
    delete_draft_media,
)
from app.domains.social.service.media_storage import (
    save_generated_post_image_bytes,
)


def save_world_banner(
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
