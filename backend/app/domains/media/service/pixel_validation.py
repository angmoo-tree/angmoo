"""Validate owned attachment pixels before decoding or persisting them."""
from app.domains.media.contracts import InvalidProfileMediaError
from app.integrations.media.images import ImageBytesError, inspect_image_bytes


def validate_pixels(content_type, content, *, max_bytes):
    if content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise InvalidProfileMediaError("asset_mime_or_size_invalid")
    try:
        return inspect_image_bytes(content, max_bytes=max_bytes, declared_mime=content_type)
    except ImageBytesError as exc:
        code = {"size": "asset_mime_or_size_invalid", "mime": "asset_mime_or_frames_invalid",
            "frames": "asset_mime_or_frames_invalid", "geometry": "asset_geometry_invalid"}.get(exc.stage, "asset_pixels_invalid")
        raise InvalidProfileMediaError(code) from exc
