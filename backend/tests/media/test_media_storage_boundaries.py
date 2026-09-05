from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.config import settings
from app.domains.characters.service import media_storage as character_media
from app.domains.media.contracts import InvalidProfileMediaError
from app.domains.social.service import media_storage as post_media
from app.integrations.media import files, images
from app.services import profile_media


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGBA", (12, 8), (100, 30, 20, 90)).save(output, format="PNG")
    return output.getvalue()


def test_character_upload_limit_does_not_replace_post_encoded_size_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "MEDIA_UPLOAD_MAX_BYTES", 8)
    content = _png_bytes()
    with pytest.raises(InvalidProfileMediaError, match="Image file is too large"):
        character_media.save_profile_media_bytes(
            character_id="character", media_type="avatar", content_type="image/png", content=content
        )
    result = post_media.save_generated_post_image_bytes(
        post_id="post", content_type="image/png", content=content,
        target_size=(8, 8), max_bytes=2048, quality_steps=(80, 60),
    )
    path = files.media_url_to_path(result["url"])
    assert path.is_file()
    assert result["byte_size"] == path.stat().st_size
    assert result["byte_size"] <= 2048
    assert (result["width"], result["height"]) == (8, 5)


def test_quarantine_partial_move_failure_restores_preceding_file(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(media_root))
    first = media_root / "first.webp"
    second = media_root / "second.webp"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    replace = Path.replace
    moved_sources = []

    def fail_second_source(source, target):
        if source.parent == media_root:
            moved_sources.append(source)
            if len(moved_sources) == 2:
                raise OSError("simulated move failure")
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_second_source)
    with pytest.raises(files.PrivateMediaCleanupError, match="private_media_quarantine_failed"):
        files.quarantine_private_media([first, second])
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"
    assert not any((tmp_path / ".media-deletion-quarantine").rglob("*.webp"))


def test_compatibility_exports_use_owner_implementations_and_same_error_classes():
    assert profile_media.save_profile_media is character_media.save_profile_media
    assert profile_media.save_generated_post_image_bytes is post_media.save_generated_post_image_bytes
    assert profile_media.encode_profile_media_webp is images.encode_profile_media_webp
    assert profile_media.quarantine_private_media is files.quarantine_private_media
    assert profile_media.PrivateMediaCleanupError is files.PrivateMediaCleanupError
    assert profile_media.InvalidProfileMediaError is InvalidProfileMediaError
