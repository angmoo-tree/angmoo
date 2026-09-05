"""Temporary media compatibility surface; actual implementations have role owners.

All production consumers use their actual role owner. Existing imported names
remain the same objects until the frozen compatibility tests retire in B8.
"""
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
from app.domains.worlds.storage import save_legacy_world_banner as save_world_banner
