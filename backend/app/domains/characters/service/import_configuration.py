"""Immutable, secret-free configuration values owned by Characters import origins."""
from __future__ import annotations

import re
from ipaddress import ip_address
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "ImportProfile",
    "ImportSettings",
    "ImportConfiguration",
    "safe_configuration_media",
    "import_digest",
]


def _is_loopback_host(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return host is not None and ip_address(host).is_loopback
    except ValueError:
        return False


def safe_configuration_media(value: str | None) -> str | None:
    """Public reference only; query credentials and executable URLs never persist."""
    if value is None:
        return None
    if not isinstance(value, str) or any(ord(char) < 32 for char in value) or "\\" in value:
        raise ValueError("configuration_media_invalid")
    parts = urlsplit(value)
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("configuration_media_invalid") from exc
    if port == 0:
        raise ValueError("configuration_media_invalid")
    if parts.username or parts.password or parts.query or parts.fragment or ".." in parts.path.split("/"):
        raise ValueError("configuration_media_invalid")
    managed_path = parts.path.startswith("/media/") or bool(
        re.fullmatch(r"/api/v1/media/assets/[A-Za-z0-9-]+/content", parts.path)
    )
    relative = not parts.scheme and not parts.netloc and managed_path
    # Old local profiles retained absolute public asset references. Reading the
    # immutable basis preserves their bytes, rather than rewriting their digest.
    legacy_local = parts.scheme == "http" and _is_loopback_host(parts.hostname) and (
        managed_path or parts.path == "/icon.svg"
    )
    if not relative and not legacy_local and not (parts.scheme == "https" and parts.hostname):
        raise ValueError("configuration_media_invalid")
    return value


class ImportProfile(BaseModel):
    """Immutable, secret-free profile stored at a permanent import origin."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    display_name: str = Field(min_length=1, max_length=80)
    handle: str = Field(min_length=1, max_length=80)
    avatar_url: str | None = None
    banner_url: str | None = None
    intro: str = ""

    @field_validator("avatar_url", "banner_url")
    @classmethod
    def _media(cls, value):
        return safe_configuration_media(value)


class ImportSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    personality: str = ""
    speech_style: str = ""
    worldview: str = ""
    character_background: str = ""
    topic_preferences: str = ""
    safety_rules: str = ""
    active_hours_start: str = "09:00"
    active_hours_end: str = "02:00"
    activity_interval_minutes: int = Field(default=60, ge=1, le=1440)
    max_posts_per_day: int = Field(default=30, ge=0, le=1000)
    max_comments_per_day: int = Field(default=30, ge=0, le=1000)
    allow_post: bool = True
    allow_reply: bool = True
    allow_like: bool = True
    allow_repost: bool = True
    allow_follow: bool = True
    allow_unfollow: bool = True
    generation_model: str | None = None
    image_model: str | None = None
    image_style: str = ""
    appearance_prompt: str = ""


class ImportConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    profile: ImportProfile
    settings: ImportSettings


def import_digest(payload: dict) -> str:
    import hashlib
    import json
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
