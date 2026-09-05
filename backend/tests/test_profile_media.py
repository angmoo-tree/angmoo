from io import BytesIO

import pytest
from PIL import Image

from app.config import settings
from app.services import profile_media


def _image_bytes(
    *,
    fmt: str,
    size: tuple[int, int] = (32, 32),
    mode: str = "RGB",
    color=(120, 80, 200),
) -> bytes:
    image = Image.new(mode, size, color)
    output = BytesIO()
    image.save(output, format=fmt)
    return output.getvalue()


def _assert_webp(path) -> None:
    content = path.read_bytes()
    assert content.startswith(b"RIFF")
    assert content[8:12] == b"WEBP"


@pytest.fixture()
def media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    return tmp_path


def test_save_profile_media_stores_jpeg_as_webp(media_root):
    url = profile_media.save_profile_media_bytes(
        character_id="char-1",
        media_type="avatar",
        content_type="image/jpeg",
        content=_image_bytes(fmt="JPEG", size=(1200, 1200)),
    )

    assert url.endswith(".webp")
    path = media_root / url.removeprefix("/media/")
    _assert_webp(path)
    with Image.open(path) as image:
        assert image.format == "WEBP"
        assert image.size == (768, 768)


def test_save_draft_media_stores_png_as_webp_without_upscale(media_root):
    url = profile_media.save_draft_profile_media_bytes(
        draft_id="draft-1",
        media_type="banner",
        content_type="image/png",
        content=_image_bytes(fmt="PNG", size=(500, 200)),
    )

    assert url.endswith(".webp")
    path = media_root / url.removeprefix("/media/")
    _assert_webp(path)
    with Image.open(path) as image:
        assert image.format == "WEBP"
        assert image.size == (500, 200)


def test_save_profile_media_flattens_transparent_webp(media_root):
    url = profile_media.save_profile_media_bytes(
        character_id="char-1",
        media_type="avatar",
        content_type="image/webp",
        content=_image_bytes(
            fmt="WEBP", size=(64, 64), mode="RGBA", color=(0, 0, 0, 0)
        ),
    )

    path = media_root / url.removeprefix("/media/")
    with Image.open(path) as image:
        assert image.mode == "RGB"


def test_promote_legacy_draft_media_reencodes_as_webp(media_root):
    draft_dir = media_root / "drafts" / "draft-1"
    draft_dir.mkdir(parents=True)
    source = draft_dir / "avatar-legacy.jpg"
    source.write_bytes(_image_bytes(fmt="JPEG", size=(64, 64)))

    url = profile_media.promote_draft_profile_media(
        character_id="char-1",
        media_type="avatar",
        draft_media_url="/media/drafts/draft-1/avatar-legacy.jpg",
    )

    assert url.endswith(".webp")
    path = media_root / url.removeprefix("/media/")
    _assert_webp(path)


def test_rejects_mismatched_mime(media_root):
    with pytest.raises(profile_media.InvalidProfileMediaError):
        profile_media.save_profile_media_bytes(
            character_id="char-1",
            media_type="avatar",
            content_type="image/png",
            content=_image_bytes(fmt="JPEG"),
        )


def test_rejects_corrupt_image_payload(media_root):
    with pytest.raises(profile_media.InvalidProfileMediaError):
        profile_media.save_profile_media_bytes(
            character_id="char-1",
            media_type="avatar",
            content_type="image/jpeg",
            content=b"\xff\xd8\xffnot-an-image",
        )


def test_rejects_oversized_image_payload(media_root, monkeypatch):
    content = _image_bytes(fmt="JPEG")
    monkeypatch.setattr(settings, "MEDIA_UPLOAD_MAX_BYTES", len(content) - 1)

    with pytest.raises(profile_media.InvalidProfileMediaError):
        profile_media.save_profile_media_bytes(
            character_id="char-1",
            media_type="avatar",
            content_type="image/jpeg",
            content=content,
        )


def test_rejects_image_dimension_above_limit_before_write(media_root):
    content = _image_bytes(fmt="PNG", size=(4097, 1))

    with pytest.raises(
        profile_media.InvalidProfileMediaError,
        match="dimensions",
    ):
        profile_media.save_profile_media_bytes(
            character_id="char-1",
            media_type="avatar",
            content_type="image/png",
            content=content,
        )

    assert not (media_root / "characters" / "char-1").exists()


def test_rejects_animated_webp_before_write(media_root):
    first = Image.new("RGB", (32, 32), (20, 40, 60))
    second = Image.new("RGB", (32, 32), (60, 40, 20))
    output = BytesIO()
    first.save(
        output,
        format="WEBP",
        save_all=True,
        append_images=[second],
        duration=100,
        loop=0,
    )

    with pytest.raises(
        profile_media.InvalidProfileMediaError,
        match="Animated",
    ):
        profile_media.save_profile_media_bytes(
            character_id="char-1",
            media_type="avatar",
            content_type="image/webp",
            content=output.getvalue(),
        )

    assert not (media_root / "characters" / "char-1").exists()


def test_private_media_quarantine_can_restore_after_database_rollback(media_root):
    character_dir = media_root / "characters" / "char-1"
    character_dir.mkdir(parents=True)
    source = character_dir / "avatar.webp"
    source.write_bytes(b"private-avatar")

    quarantine = profile_media.quarantine_private_media([character_dir])

    assert not source.exists()
    assert quarantine.root is not None
    assert quarantine.root.parent == media_root.parent / f".{media_root.name}-deletion-quarantine"
    quarantine.restore()

    assert source.read_bytes() == b"private-avatar"
    assert not quarantine.root.exists()


def test_private_media_quarantine_purges_after_database_commit(media_root):
    draft_dir = media_root / "drafts" / "draft-1"
    draft_dir.mkdir(parents=True)
    (draft_dir / "avatar.webp").write_bytes(b"private-draft")

    quarantine = profile_media.quarantine_private_media([draft_dir])
    quarantine.purge()

    assert not draft_dir.exists()
    assert quarantine.root is not None
    assert not quarantine.root.exists()


def test_private_media_quarantine_rejects_paths_outside_media_root(
    media_root, tmp_path
):
    outside = tmp_path.parent / "outside-private-media"
    outside.mkdir(exist_ok=True)

    with pytest.raises(
        profile_media.PrivateMediaCleanupError,
        match="private_media_path_outside_root",
    ):
        profile_media.quarantine_private_media([outside])
