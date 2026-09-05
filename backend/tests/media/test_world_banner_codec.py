"""World errors and file placement stay distinct over the common image codec."""
import base64
from io import BytesIO

from PIL import Image
import pytest

from app.config import settings
from app.domains.media.contracts import InvalidProfileMediaError
from app.domains.worlds import storage
from app.integrations.media import images
from app.services import profile_media


@pytest.mark.parametrize(
    "content_type,payload,message",
    [
        ("image/gif", "", "Only jpg, png, and webp images are allowed"),
        ("image/png", "!", "Invalid image payload"),
        ("image/png", "", "Image payload is empty"),
        ("image/png", "YWJj", "Image content does not match its type"),
        ("image/webp", "YWJj", "Invalid webp image"),
        ("image/png", "iVBORw0KGgo=", "Invalid image payload"),
    ],
)
def test_world_upload_keeps_world_error_and_writes_no_file(
    tmp_path, monkeypatch, content_type, payload, message,
):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    with pytest.raises(storage.InvalidWorldBannerMediaError) as result:
        storage.save_world_banner(
            world_id="world", content_type=content_type, data_base64=payload,
        )
    assert str(result.value) == message
    assert not isinstance(result.value, InvalidProfileMediaError)
    assert list(tmp_path.iterdir()) == []


def test_world_banner_uses_shared_sanitized_bytes_and_legacy_exception_contract(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    output = BytesIO()
    Image.new("RGBA", (1600, 800), (50, 90, 140, 0)).save(output, format="PNG")
    content = output.getvalue()
    url = storage.save_world_banner(
        world_id="world", content_type=" IMAGE/PNG ",
        data_base64=base64.b64encode(content).decode("ascii"),
    )
    path = tmp_path / url.removeprefix("/media/")
    assert path.parent == tmp_path / "worlds" / "world"
    assert path.read_bytes() == images.encode_profile_media_webp(
        media_type="banner", content=content,
    )
    with Image.open(path) as image:
        assert image.size == (768, 384)
        assert image.mode == "RGB"
        assert image.getpixel((0, 0)) == (255, 255, 255)
    assert profile_media.save_world_banner is storage.save_legacy_world_banner
    with pytest.raises(InvalidProfileMediaError, match="Invalid image payload"):
        profile_media.save_world_banner(
            world_id="world", content_type="image/png", data_base64="!",
        )


def test_world_delete_ignores_paths_outside_the_configured_media_root(tmp_path, monkeypatch):
    root = tmp_path / "media"
    root.mkdir()
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(root))
    outside = tmp_path / "outside.webp"
    outside.write_bytes(b"outside")
    storage.delete_media_url("/media/../outside.webp")
    assert outside.read_bytes() == b"outside"
