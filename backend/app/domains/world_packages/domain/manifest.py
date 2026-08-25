"""Pydantic manifest contract for World Package v1."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, UUID7, field_validator, model_validator

from app.domains.world_packages.domain.canonical import canonical_entry_index_digest


SHA256_PATTERN = r"^[0-9a-f]{64}$"
PACKAGE_PATH_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,239}$"
EXTENSION_PATTERN = r"^[a-z][a-z0-9.-]{0,79}$"


class WorldPackageSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WorldPackageProducer(WorldPackageSchema):
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=40)


class WorldPackageCompatibility(WorldPackageSchema):
    min_reader_version: str = Field(min_length=1, max_length=40)
    world_contract_version: str = Field(min_length=1, max_length=120)


class WorldPackageLicense(WorldPackageSchema):
    expression: str = Field(min_length=1, max_length=160)
    attribution: str = Field(default="", max_length=1000)
    source_url: str | None = Field(default=None, max_length=2048)
    license_text_path: Literal["LICENSE.txt"] | None = None

    @model_validator(mode="after")
    def _license_ref_requires_text(self) -> "WorldPackageLicense":
        if self.expression.startswith("LicenseRef-") and self.license_text_path is None:
            raise ValueError("LicenseRef expressions require LICENSE.txt")
        if self.source_url is not None and not self.source_url.startswith("https://"):
            raise ValueError("license source_url must use https")
        return self


class WorldPackageEntry(WorldPackageSchema):
    path: str = Field(pattern=PACKAGE_PATH_PATTERN, max_length=240)
    sha256: str = Field(pattern=SHA256_PATTERN)
    bytes: int = Field(ge=0, le=5 * 1024 * 1024)
    media_type: Literal["application/json", "image/webp", "text/plain"]


class WorldPackageManifest(WorldPackageSchema):
    format: Literal["angmoo-world-package"]
    format_version: Literal[1]
    schema_version: Literal["world-package-v1"]
    package_id: UUID7
    package_version: int = Field(ge=1, le=2_147_483_647)
    created_at: datetime
    producer: WorldPackageProducer
    compatibility: WorldPackageCompatibility
    license: WorldPackageLicense
    entries: list[WorldPackageEntry] = Field(min_length=4, max_length=255)
    content_digest: str = Field(pattern=SHA256_PATTERN)
    required_extensions: list[str] = Field(default_factory=list, max_length=32)
    optional_extensions: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("created_at")
    @classmethod
    def _created_at_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("created_at must be RFC3339 UTC")
        return value

    @field_validator("required_extensions", "optional_extensions")
    @classmethod
    def _extensions(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("extension names must be unique")
        if any(re.fullmatch(EXTENSION_PATTERN, value) is None for value in values):
            raise ValueError("extension names use the frozen lowercase namespace")
        return values

    @model_validator(mode="after")
    def _entry_index_is_complete_and_digest_matches(self) -> "WorldPackageManifest":
        paths = [entry.path for entry in self.entries]
        required = {
            "content/world.json",
            "content/characters.json",
            "content/world-characters.json",
            "assets/index.json",
        }
        if len(paths) != len(set(paths)) or not required.issubset(paths):
            raise ValueError("entry index must contain unique required v1 content paths")
        if self.license.license_text_path and self.license.license_text_path not in paths:
            raise ValueError("LICENSE.txt must be indexed when referenced")
        if canonical_entry_index_digest(self.entries) != self.content_digest:
            raise ValueError("content_digest does not match the canonical entry index")
        return self
