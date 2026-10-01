"""Shared inspection preserves stage and both supported domain error contracts."""
from io import BytesIO

from PIL import Image
import pytest

from app.core.image_bytes import ImageBytesError, inspect_image_bytes
from app.domains.media.contracts import InvalidProfileMediaError
from app.domains.media.service.pixel_validation import validate_pixels
from app.integrations.media.images import validate_generated_media_content


def test_geometry_error_is_translated_at_the_existing_domain_boundaries():
    output = BytesIO()
    Image.new("RGB", (4097, 1)).save(output, format="PNG")
    content = output.getvalue()

    with pytest.raises(ImageBytesError) as inspection:
        inspect_image_bytes(content, max_bytes=100_000)
    assert inspection.value.stage == "geometry"
    assert not isinstance(inspection.value, InvalidProfileMediaError)

    with pytest.raises(InvalidProfileMediaError, match="^asset_geometry_invalid$"):
        validate_pixels("image/png", content, max_bytes=100_000)

    with pytest.raises(InvalidProfileMediaError, match="^image_geometry_invalid$"):
        validate_generated_media_content("image/png", content, max_bytes=100_000)
