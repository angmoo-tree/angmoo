from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CONTRACT_VERSION = "p0-contract-v1"


class FixtureExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["success", "rejected", "deferred", "fallback"]
    code: str = Field(min_length=1, max_length=80)
    writes: list[str] = Field(default_factory=list, max_length=20)
    provider_call_count: int = Field(default=0, ge=0)
    notes: list[str] = Field(default_factory=list, max_length=20)


class ContractFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    contract_version: Literal["p0-contract-v1"]
    required_phase: str = Field(pattern=r"^P(?:[1-9]|1[01])$")
    input: dict[str, Any]
    expected: FixtureExpectation
    variants: list[str] = Field(default_factory=list, min_length=1, max_length=20)


class FixtureManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str
    path: str
    required_phase: str
    expected_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class FixtureManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["p0-contract-v1"]
    schema_path: str
    fixtures: list[FixtureManifestEntry] = Field(min_length=1)


class FixturePackage(BaseModel):
    manifest: FixtureManifest
    fixtures: tuple[ContractFixture, ...]


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_fixture_package(root: Path) -> FixturePackage:
    manifest_path = root / "manifest.json"
    manifest = FixtureManifest.model_validate_json(manifest_path.read_text("utf-8"))
    if not (root / manifest.schema_path).is_file():
        raise ValueError("fixture schema path does not exist")

    seen: set[str] = set()
    fixtures: list[ContractFixture] = []
    for entry in manifest.fixtures:
        if entry.fixture_id in seen:
            raise ValueError(f"duplicate fixture id: {entry.fixture_id}")
        seen.add(entry.fixture_id)

        fixture_path = (root / entry.path).resolve()
        if fixture_path.parent != root.resolve():
            raise ValueError(f"fixture path escapes package: {entry.path}")
        fixture = ContractFixture.model_validate_json(fixture_path.read_text("utf-8"))
        if fixture.fixture_id != entry.fixture_id:
            raise ValueError(f"fixture id mismatch: {entry.fixture_id}")
        if fixture.contract_version != manifest.contract_version:
            raise ValueError(f"fixture contract mismatch: {entry.fixture_id}")
        if fixture.required_phase != entry.required_phase:
            raise ValueError(f"fixture phase mismatch: {entry.fixture_id}")
        expected_hash = canonical_json_sha256(fixture.expected.model_dump(mode="json"))
        if expected_hash != entry.expected_schema_sha256:
            raise ValueError(f"fixture expected hash mismatch: {entry.fixture_id}")
        fixtures.append(fixture)

    json_files = {
        path.name
        for path in root.glob("*.json")
        if path.name not in {"manifest.json", manifest.schema_path}
    }
    manifest_files = {entry.path for entry in manifest.fixtures}
    if json_files != manifest_files:
        raise ValueError("fixture manifest and JSON file set differ")

    return FixturePackage(manifest=manifest, fixtures=tuple(fixtures))
