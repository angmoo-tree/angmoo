"""Detector reports are authenticated observations, never direct locale settings."""
from datetime import datetime
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import langcodes
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EnvironmentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    lease_token: str | None = Field(default=None, max_length=128, repr=False)
    expected_revision: int = Field(ge=0)
    sequence: int = Field(ge=1)
    preferred_language: str | None = Field(default=None, max_length=80)
    timezone: str | None = Field(default=None, max_length=80)

    @field_validator("preferred_language")
    @classmethod
    def language(cls, value):
        if value is None:
            return None
        if not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", value) or not langcodes.tag_is_valid(value):
            raise ValueError("detected_language_invalid")
        normalized = langcodes.standardize_tag(value)
        if langcodes.Language.get(normalized).language in {None, "und"}:
            raise ValueError("detected_language_undefined")
        return normalized

    @field_validator("timezone")
    @classmethod
    def zone(cls, value):
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("detected_timezone_invalid") from None
        return value


class EnvironmentRead(BaseModel):
    installation_id: str | None
    preferred_language: str
    memory_search_locale: str
    timezone: str
    environment_revision: int
    timezone_revision: int
    confirmed_at: datetime | None
    synchronization: str
    lease_expires_at: datetime | None
    lease_token: str | None = Field(default=None, repr=False)
