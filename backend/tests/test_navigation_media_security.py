from pathlib import Path

import pytest
from pydantic import ValidationError

from app import schemas


@pytest.mark.parametrize(
    "url",
    [
        "https://tracker.example/avatar.png",
        "//tracker.example/avatar.png",
        "data:image/png;base64,AAAA",
        "javascript:alert(1)",
    ],
)
def test_profile_media_inputs_reject_external_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        schemas.AgentProfileUpdate(avatar_url=url)


def test_profile_media_inputs_allow_managed_media_paths() -> None:
    payload = schemas.AgentProfileUpdate(
        avatar_url="/media/characters/char-1/avatar.png",
        banner_url="",
    )
    assert payload.avatar_url == "/media/characters/char-1/avatar.png"
    assert payload.banner_url == ""


def test_frontend_uses_allowlisted_return_and_profile_media_helpers() -> None:
    root = Path(__file__).parents[2] / "frontend" / "src"
    navigation = (root / "lib" / "safe-navigation.ts").read_text(encoding="utf-8")
    media = (root / "lib" / "safe-media-url.ts").read_text(encoding="utf-8")
    settings = (root / "components" / "settings-client.tsx").read_text(
        encoding="utf-8"
    )
    avatar = (root / "components" / "profile-avatar.tsx").read_text(
        encoding="utf-8"
    )

    assert 'value.startsWith("//")' in navigation
    assert "ALLOWED_RETURN_PATHS" in navigation
    assert "safeSettingsReturnTo(params.get" in settings
    assert "parsed.pathname.startsWith(\"/media/\")" in media
    assert "safeSameOriginMediaUrl(avatarUrl, { allowBlob })" in avatar
