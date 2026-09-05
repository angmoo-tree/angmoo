from app.domains.media.contracts import (
    InvalidProfileMediaError,
)
import base64
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import shutil
from typing import Iterable
from uuid import uuid4
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings


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




class PrivateMediaCleanupError(Exception):
    pass


@dataclass
class PrivateMediaQuarantine:
    root: Path | None = None
    entries: list[tuple[Path, Path]] = field(default_factory=list)

    def restore(self) -> None:
        errors: list[OSError] = []
        for source, quarantined in reversed(self.entries):
            if not quarantined.exists():
                continue
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                quarantined.replace(source)
            except OSError as exc:
                errors.append(exc)
        if errors:
            raise PrivateMediaCleanupError("private_media_restore_failed") from errors[0]
        self._remove_empty_root()

    def purge(self) -> None:
        if self.root is None or not self.root.exists():
            return
        try:
            shutil.rmtree(self.root)
        except OSError as exc:
            raise PrivateMediaCleanupError("private_media_purge_failed") from exc

    def _remove_empty_root(self) -> None:
        if self.root is None or not self.root.exists():
            return
        try:
            shutil.rmtree(self.root)
        except OSError:
            return


def quarantine_private_media(paths: Iterable[Path]) -> PrivateMediaQuarantine:
    media_root = settings.media_root_path.resolve()
    candidates: list[Path] = []
    for path in paths:
        if path.is_symlink():
            raise PrivateMediaCleanupError("private_media_symlink_not_allowed")
        resolved = path.resolve()
        try:
            resolved.relative_to(media_root)
        except ValueError as exc:
            raise PrivateMediaCleanupError("private_media_path_outside_root") from exc
        if resolved == media_root or not resolved.exists():
            continue
        candidates.append(resolved)

    selected: list[Path] = []
    for candidate in sorted(set(candidates), key=lambda item: len(item.parts)):
        if any(candidate == parent or parent in candidate.parents for parent in selected):
            continue
        selected.append(candidate)

    if not selected:
        return PrivateMediaQuarantine()

    quarantine_root = (
        media_root.parent
        / f".{media_root.name}-deletion-quarantine"
        / uuid4().hex
    )
    result = PrivateMediaQuarantine(root=quarantine_root)
    try:
        for source in selected:
            relative = source.relative_to(media_root)
            destination = quarantine_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination)
            result.entries.append((source, destination))
    except OSError as exc:
        try:
            result.restore()
        except PrivateMediaCleanupError:
            pass
        raise PrivateMediaCleanupError("private_media_quarantine_failed") from exc
    return result


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


def save_generated_post_image_bytes(
    *,
    post_id: str,
    content_type: str,
    content: bytes,
    target_size: tuple[int, int],
    max_bytes: int,
    quality_steps: tuple[int, ...],
) -> dict[str, object]:
    normalized_content_type = content_type.strip().lower()
    if normalized_content_type not in CONTENT_TYPES:
        raise InvalidProfileMediaError("Only jpg, png, and webp images are allowed")
    if not content:
        raise InvalidProfileMediaError("Image payload is empty")
    _assert_image_signature(normalized_content_type, content)
    _assert_decodable_image(content)
    encoded = encode_generated_post_webp(
        content=content,
        target_size=target_size,
        max_bytes=max_bytes,
        quality_steps=quality_steps,
    )
    with Image.open(BytesIO(encoded)) as image:
        width, height = image.size
    post_dir = settings.media_root_path / "posts" / post_id
    post_dir.mkdir(parents=True, exist_ok=True)
    filename = f"image-{uuid4().hex}.webp"
    path = post_dir / filename
    path.write_bytes(encoded)
    return {
        "url": f"{settings.media_url_path}/posts/{post_id}/{filename}",
        "byte_size": len(encoded),
        "width": width,
        "height": height,
    }


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


def media_url_to_path(media_url: str):
    return _media_url_to_path(media_url)


def resolve_private_media_file(
    media_url: str,
    *,
    expected_directory: str,
) -> tuple[Path, str]:
    url_prefix = f"{settings.media_url_path}/"
    if not media_url.startswith(url_prefix):
        raise InvalidProfileMediaError("Invalid private media URL")
    relative = media_url[len(url_prefix):]
    lexical_path = settings.media_root_path / Path(relative)
    expected_root = settings.media_root_path / expected_directory
    try:
        lexical_path.relative_to(expected_root)
    except ValueError as exc:
        raise InvalidProfileMediaError("Invalid private media path") from exc
    current = lexical_path
    while current != expected_root:
        if current.is_symlink():
            raise InvalidProfileMediaError("Private media symlinks are not allowed")
        current = current.parent
    resolved = lexical_path.resolve()
    try:
        resolved.relative_to(expected_root.resolve())
    except ValueError as exc:
        raise InvalidProfileMediaError("Invalid private media path") from exc
    if not resolved.is_file():
        raise InvalidProfileMediaError("Private media was not found")
    return resolved, _content_type_from_suffix(resolved.suffix.lower())


def delete_media_url(media_url: str | None) -> None:
    if not media_url:
        return
    try:
        path = _media_url_to_path(media_url)
    except InvalidProfileMediaError:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _media_url_to_path(media_url: str):
    url_prefix = f"{settings.media_url_path}/"
    if not media_url.startswith(url_prefix):
        raise InvalidProfileMediaError("Invalid media URL")
    relative = media_url[len(url_prefix):]
    path = (settings.media_root_path / relative).resolve()
    root = settings.media_root_path.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise InvalidProfileMediaError("Invalid media path") from exc
    return path


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
