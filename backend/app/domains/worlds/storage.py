"""Filesystem storage adapter for World Creator banner images."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings


CONTENT_TYPES = {
    "image/jpeg": ("jpg", b"\xff\xd8\xff"),
    "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
    "image/webp": ("webp", b"RIFF"),
}
BANNER_TARGET_SIZE = (1024, 384)
WEBP_QUALITY = 80
MAX_IMAGE_DIMENSION = 4096
MAX_IMAGE_PIXELS = 16_777_216
MAX_IMAGE_FRAMES = 1


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
    if content_type not in CONTENT_TYPES:
        raise InvalidWorldBannerMediaError(
            "Only jpg, png, and webp images are allowed"
        )
    try:
        content = base64.b64decode(data_base64, validate=True)
    except ValueError as exc:
        raise InvalidWorldBannerMediaError("Invalid image payload") from exc
    if not content:
        raise InvalidWorldBannerMediaError("Image payload is empty")
    if len(content) > settings.media_upload_max_bytes:
        raise InvalidWorldBannerMediaError("Image file is too large")
    _assert_image_signature(content_type, content)
    _assert_decodable_image(content)
    return content


def _encode_banner_webp(content: bytes) -> bytes:
    try:
        with Image.open(BytesIO(content)) as image:
            _assert_safe_image_geometry(image)
            image = ImageOps.exif_transpose(image)
            image.load()
            image = _flatten_for_webp(image)
            image.thumbnail(BANNER_TARGET_SIZE, Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="WEBP", quality=WEBP_QUALITY, method=6)
            encoded = output.getvalue()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ) as exc:
        raise InvalidWorldBannerMediaError("Invalid image payload") from exc
    if not encoded:
        raise InvalidWorldBannerMediaError("Image payload is empty")
    return encoded


def _media_url_to_path(media_url: str) -> Path:
    url_prefix = f"{settings.media_url_path}/"
    if not media_url.startswith(url_prefix):
        raise InvalidWorldBannerMediaError("Invalid media URL")
    relative = media_url[len(url_prefix) :]
    path = (settings.media_root_path / relative).resolve()
    root = settings.media_root_path.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise InvalidWorldBannerMediaError("Invalid media path") from exc
    return path


def _assert_image_signature(content_type: str, content: bytes) -> None:
    if content_type == "image/webp":
        if not (content.startswith(b"RIFF") and content[8:12] == b"WEBP"):
            raise InvalidWorldBannerMediaError("Invalid webp image")
        return
    signature = CONTENT_TYPES[content_type][1]
    if not content.startswith(signature):
        raise InvalidWorldBannerMediaError(
            "Image content does not match its type"
        )


def _assert_decodable_image(content: bytes) -> None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                _assert_safe_image_geometry(image)
                image.verify()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ) as exc:
        raise InvalidWorldBannerMediaError("Invalid image payload") from exc


def _assert_safe_image_geometry(image: Image.Image) -> None:
    width, height = image.size
    if (
        width <= 0
        or height <= 0
        or width > MAX_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise InvalidWorldBannerMediaError("Image dimensions are too large")
    if int(getattr(image, "n_frames", 1)) > MAX_IMAGE_FRAMES:
        raise InvalidWorldBannerMediaError("Animated images are not supported")


def _flatten_for_webp(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image
