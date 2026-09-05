"""Persist a generated post image after Social accepts the generation result.

Quota, jobs and attachment/publication policy remain owned by Social's workflow.
"""
from io import BytesIO
from uuid import uuid4

from PIL import Image

from app.config import settings
from app.domains.media.contracts import InvalidProfileMediaError
from app.integrations.media.images import (
    CONTENT_TYPES,
    _assert_decodable_image,
    _assert_image_signature,
    encode_generated_post_webp,
)


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
