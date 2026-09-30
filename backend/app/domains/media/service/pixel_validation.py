"""Validate owned attachment pixels before decoding or persisting them."""
from io import BytesIO
import warnings
from PIL import Image, UnidentifiedImageError
from app.domains.media.contracts import InvalidProfileMediaError


def validate_pixels(content_type, content, *, max_bytes):
    signatures = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff", "image/webp": b"RIFF"}
    if not content or len(content) > max_bytes or content_type not in signatures or not content.startswith(signatures[content_type]):
        raise InvalidProfileMediaError("asset_mime_or_size_invalid")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if Image.MIME.get(image.format) != content_type or getattr(image, "n_frames", 1) != 1:
                    raise InvalidProfileMediaError("asset_mime_or_frames_invalid")
                width, height = image.size
                if width < 1 or height < 1 or width > 4096 or height > 4096 or width * height > 16777216:
                    raise InvalidProfileMediaError("asset_geometry_invalid")
                image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise InvalidProfileMediaError("asset_pixels_invalid") from exc
