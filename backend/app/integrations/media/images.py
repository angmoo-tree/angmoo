"""Bounded image decoding and WebP conversion; no owner or publication decisions."""
import base64
from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings
from app.domains.media.contracts import InvalidProfileMediaError


CONTENT_TYPES = {
    "image/jpeg": ("jpg", b"\xff\xd8\xff"),
    "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
    "image/webp": ("webp", b"RIFF"),
}


MEDIA_TARGET_SIZES = {
    "avatar": (768, 768),
    "banner": (1024, 384),
}


WEBP_QUALITY = 80


SEED_IMAGE_TARGET_SIZE = (1024, 1024)


MAX_IMAGE_DIMENSION = 4096


MAX_IMAGE_PIXELS = 16_777_216


MAX_IMAGE_FRAMES = 1


def decode_profile_media(*, content_type: str, data_base64: str) -> bytes:
    normalized_content_type = content_type.strip().lower()
    if normalized_content_type not in CONTENT_TYPES:
        raise InvalidProfileMediaError("Only jpg, png, and webp images are allowed")
    try:
        content = base64.b64decode(data_base64, validate=True)
    except ValueError as exc:
        raise InvalidProfileMediaError("Invalid image payload") from exc
    validate_profile_media_content(normalized_content_type, content)
    return content


def validate_profile_media_content(content_type: str, content: bytes) -> None:
    if not content:
        raise InvalidProfileMediaError("Image payload is empty")
    if len(content) > settings.media_upload_max_bytes:
        raise InvalidProfileMediaError("Image file is too large")
    _assert_image_signature(content_type, content)
    _assert_decodable_image(content)


def encode_profile_media_webp(*, media_type: str, content: bytes) -> bytes:
    if media_type not in MEDIA_TARGET_SIZES:
        raise InvalidProfileMediaError("Unsupported media type")
    try:
        with Image.open(BytesIO(content)) as image:
            _assert_safe_image_geometry(image)
            image = ImageOps.exif_transpose(image)
            image.load()
            image = _flatten_for_webp(image)
            image.thumbnail(MEDIA_TARGET_SIZES[media_type], Image.Resampling.LANCZOS)
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
        raise InvalidProfileMediaError("Invalid image payload") from exc
    if not encoded:
        raise InvalidProfileMediaError("Image payload is empty")
    return encoded


def encode_image_webp_preserve_ratio(
    *, content: bytes, max_size: tuple[int, int], quality: int
) -> bytes:
    try:
        with Image.open(BytesIO(content)) as image:
            _assert_safe_image_geometry(image)
            image = ImageOps.exif_transpose(image)
            image.load()
            image = _flatten_for_webp(image)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="WEBP", quality=quality, method=6)
            encoded = output.getvalue()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ) as exc:
        raise InvalidProfileMediaError("Invalid image payload") from exc
    if not encoded:
        raise InvalidProfileMediaError("Image payload is empty")
    return encoded


def encode_generated_post_webp(
    *,
    content: bytes,
    target_size: tuple[int, int],
    max_bytes: int,
    quality_steps: tuple[int, ...],
) -> bytes:
    try:
        with Image.open(BytesIO(content)) as image:
            _assert_safe_image_geometry(image)
            image = ImageOps.exif_transpose(image)
            image.load()
            image = _flatten_for_webp(image)
            image.thumbnail(target_size, Image.Resampling.LANCZOS)
            for quality in quality_steps:
                output = BytesIO()
                image.save(output, format="WEBP", quality=quality, method=6)
                encoded = output.getvalue()
                if encoded and len(encoded) <= max_bytes:
                    return encoded
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ) as exc:
        raise InvalidProfileMediaError("Invalid image payload") from exc
    raise InvalidProfileMediaError("Encoded image is too large")


def _assert_image_signature(content_type: str, content: bytes) -> None:
    if content_type == "image/webp":
        if not (content.startswith(b"RIFF") and content[8:12] == b"WEBP"):
            raise InvalidProfileMediaError("Invalid webp image")
        return

    signature = CONTENT_TYPES[content_type][1]
    if not content.startswith(signature):
        raise InvalidProfileMediaError("Image content does not match its type")


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
        raise InvalidProfileMediaError("Invalid image payload") from exc


def _assert_safe_image_geometry(image: Image.Image) -> None:
    width, height = image.size
    if (
        width <= 0
        or height <= 0
        or width > MAX_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise InvalidProfileMediaError("Image dimensions are too large")
    frame_count = int(getattr(image, "n_frames", 1))
    if frame_count > MAX_IMAGE_FRAMES:
        raise InvalidProfileMediaError("Animated images are not supported")


def _content_type_from_suffix(suffix: str) -> str:
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    raise InvalidProfileMediaError("Unsupported draft media extension")


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
