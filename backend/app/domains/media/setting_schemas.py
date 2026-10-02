"""HTTP writes contain user preferences; effective state is server-owned."""
from typing import Literal
from pydantic import Field, SecretStr
from app.domains.media.generation_contracts import StrictInput, ImageProvider


class GenerationSettingsWrite(StrictInput):
    expected_revision: int = Field(ge=0)
    provider: ImageProvider
    model: str = Field(min_length=1, max_length=120)
    auto_enabled: bool = False
    daily_limit: int | None = Field(default=None, ge=1, le=10000)
    installation_daily_limit: int | None = Field(default=None, ge=1, le=10000)
    installation_expected_revision: int | None = Field(default=None, ge=0)
    appearance: str = Field(default="", max_length=1200)
    style: str = Field(default="", max_length=1200)
    negative: str = Field(default="", max_length=1800)
    reference_enabled: bool | None = None
    reference_asset_id: str | None = None
    options: dict = Field(default_factory=dict)
    api_key: SecretStr | None = None
    clear_api_key: bool = False
    partner_api_key: SecretStr | None = None
    clear_partner_api_key: bool = False


class InterpretationSettingsWrite(StrictInput):
    expected_revision: int = Field(ge=0)
    enabled: bool = False
    model: Literal["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"] = "gemini-3.1-flash-lite"
    thinking_level: Literal["high", "medium"] = "medium"
    daily_limit: int | None = Field(default=None, ge=1, le=10000)
    api_key: SecretStr | None = None
    clear_api_key: bool = False


class AssetUpload(StrictInput):
    scope_kind: Literal["character", "world", "thread"]
    scope_id: str = Field(min_length=1, max_length=64)
    content_type: Literal["image/png", "image/jpeg", "image/webp"]
    data_base64: str = Field(min_length=1, max_length=13981016)


class InstallationUsageWrite(StrictInput):
    expected_revision: int = Field(ge=0)
    daily_limit: int = Field(ge=1, le=10000)
