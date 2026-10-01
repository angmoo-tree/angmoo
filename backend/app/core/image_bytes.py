"""Bounded image-byte inspection shared by transport and domain validation.

This leaf module has no domain, credential, settings or ownership dependencies.
Domain callers translate its value-free errors to their supported HTTP contract.
"""
from dataclasses import dataclass
from io import BytesIO
import warnings

from PIL import Image, UnidentifiedImageError


CONTENT_TYPES = {
    "image/jpeg": ("jpg", b"\xff\xd8\xff"),
    "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
    "image/webp": ("webp", b"RIFF"),
}


MAX_IMAGE_DIMENSION = 4096


MAX_IMAGE_PIXELS = 16_777_216


MAX_IMAGE_FRAMES = 1


@dataclass(frozen=True)
class ImageInspection:
    format: str
    content_type: str
    extension: str
    width: int
    height: int
    byte_size: int


class ImageBytesError(Exception):
    """Value-free inspection stage, safe for provider diagnostics."""
    def __init__(self, stage: str):
        super().__init__(f"image_{stage}_invalid")
        self.stage = stage


def inspect_image_bytes(content: bytes, *, max_bytes: int, declared_mime: str | None = None) -> ImageInspection:
    if not isinstance(content, bytes) or not content or len(content) > max_bytes:
        raise ImageBytesError("size")
    if declared_mime is not None and not isinstance(declared_mime, str):
        raise ImageBytesError("mime")
    mime = declared_mime.split(";", 1)[0].strip().lower() if declared_mime else ""
    if mime and mime not in CONTENT_TYPES:
        raise ImageBytesError("mime")
    detected = next((kind for kind, (_, signature) in CONTENT_TYPES.items()
        if content.startswith(signature) and (kind != "image/webp" or content[8:12] == b"WEBP")), None)
    if detected is None:
        raise ImageBytesError("format")
    if mime and mime != detected:
        raise ImageBytesError("mime")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content), formats=("PNG", "JPEG", "WEBP")) as image:
                if Image.MIME.get(image.format) != detected:
                    raise ImageBytesError("format")
                width, height = image.size
                if not (0 < width <= MAX_IMAGE_DIMENSION and 0 < height <= MAX_IMAGE_DIMENSION
                        and width * height <= MAX_IMAGE_PIXELS):
                    raise ImageBytesError("geometry")
                if getattr(image, "n_frames", 1) != MAX_IMAGE_FRAMES:
                    raise ImageBytesError("frames")
                format = image.format
                image.verify()
            # verify does not decode pixels (notably JPEG). Reopen before load.
            with Image.open(BytesIO(content), formats=("PNG", "JPEG", "WEBP")) as image:
                image.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageBytesError("geometry") from exc
    except (OSError, UnidentifiedImageError, ValueError, SyntaxError) as exc:
        raise ImageBytesError("decode") from exc
    return ImageInspection(format, detected, CONTENT_TYPES[detected][0], width, height, len(content))
