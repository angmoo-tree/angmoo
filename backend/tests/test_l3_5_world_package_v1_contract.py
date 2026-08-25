from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any

import pytest
from pydantic import ValidationError

from app.domains.world_packages.public import (
    ArchiveEntryDescriptor,
    AssetIndexDocument,
    CharactersDocument,
    PortableWorldDefinition,
    WorldCharactersDocument,
    WorldPackageContractError,
    WorldPackageManifest,
    WorldPackagePolicy,
    WorldPackageReasonCode,
    WorldPackageTrustState,
    canonical_entry_index_digest,
    canonical_json_bytes,
    canonical_sha256,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
APP_ROOT = BACKEND_ROOT / "app"
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "world_packages" / "v1"
VALID_ROOT = FIXTURE_ROOT / "valid"
SCHEMA_ROOT = APP_ROOT / "domains" / "world_packages" / "schemas" / "v1"
GENERATOR_PATH = REPO_ROOT / "scripts" / "ci" / "generate_world_package_schemas.py"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _valid_descriptors() -> list[ArchiveEntryDescriptor]:
    manifest_path = VALID_ROOT / "manifest.json"
    manifest = WorldPackageManifest.model_validate(_json(manifest_path))
    return [
        ArchiveEntryDescriptor(
            path="manifest.json",
            compressed_bytes=manifest_path.stat().st_size,
            uncompressed_bytes=manifest_path.stat().st_size,
        ),
        *[
            ArchiveEntryDescriptor(
                path=entry.path,
                compressed_bytes=max(1, entry.bytes),
                uncompressed_bytes=entry.bytes,
            )
            for entry in manifest.entries
        ],
    ]


def _malicious_archive_metadata_corpus() -> list[tuple[str, list[ArchiveEntryDescriptor], WorldPackageReasonCode]]:
    valid = _valid_descriptors()
    return [
        (
            "path_traversal",
            [*valid, ArchiveEntryDescriptor("../escape.json", 1, 1)],
            WorldPackageReasonCode.PATH_UNSAFE,
        ),
        (
            "backslash_path",
            [*valid, ArchiveEntryDescriptor(r"assets\\escape.webp", 1, 1)],
            WorldPackageReasonCode.PATH_UNSAFE,
        ),
        (
            "windows_casefold_collision",
            [*valid, ArchiveEntryDescriptor("Manifest.json", 1, 1)],
            WorldPackageReasonCode.PATH_UNSAFE,
        ),
        (
            "symlink",
            [
                ArchiveEntryDescriptor(
                    item.path,
                    item.compressed_bytes,
                    item.uncompressed_bytes,
                    kind="symlink" if item.path == "manifest.json" else item.kind,
                )
                for item in valid
            ],
            WorldPackageReasonCode.ARCHIVE_INVALID,
        ),
        (
            "encrypted",
            [
                ArchiveEntryDescriptor(
                    item.path,
                    item.compressed_bytes,
                    item.uncompressed_bytes,
                    encrypted=item.path == "manifest.json",
                )
                for item in valid
            ],
            WorldPackageReasonCode.ARCHIVE_INVALID,
        ),
        (
            "compression_bomb",
            [
                ArchiveEntryDescriptor(
                    item.path,
                    1 if item.path == "content/world.json" else item.compressed_bytes,
                    101 if item.path == "content/world.json" else item.uncompressed_bytes,
                )
                for item in valid
            ],
            WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED,
        ),
        (
            "unknown_root_entry",
            [*valid, ArchiveEntryDescriptor("unexpected.txt", 1, 1)],
            WorldPackageReasonCode.ARCHIVE_INVALID,
        ),
    ]


def test_checked_in_json_schemas_are_deterministic_goldens() -> None:
    spec = importlib.util.spec_from_file_location("world_package_schema_generator", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = generator
    spec.loader.exec_module(generator)

    expected = generator.expected_outputs()
    observed_hashes: dict[str, str] = {}
    for path, payload in expected.items():
        assert path.read_text(encoding="utf-8") == payload
        observed_hashes[path.name] = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    assert observed_hashes == _json(FIXTURE_ROOT / "schema-golden.json")


def test_synthetic_fixture_validates_and_entry_digests_match() -> None:
    manifest = WorldPackageManifest.model_validate(_json(VALID_ROOT / "manifest.json"))
    documents = {
        "content/world.json": (
            PortableWorldDefinition,
            VALID_ROOT / "content" / "world.json",
        ),
        "content/characters.json": (
            CharactersDocument,
            VALID_ROOT / "content" / "characters.json",
        ),
        "content/world-characters.json": (
            WorldCharactersDocument,
            VALID_ROOT / "content" / "world-characters.json",
        ),
        "assets/index.json": (
            AssetIndexDocument,
            VALID_ROOT / "assets" / "index.json",
        ),
    }
    indexed = {entry.path: entry for entry in manifest.entries}

    for path, (model, fixture_path) in documents.items():
        value = _json(fixture_path)
        model.model_validate(value)
        assert canonical_sha256(value) == indexed[path].sha256
        assert len(canonical_json_bytes(value)) == indexed[path].bytes

    assert canonical_entry_index_digest(manifest.entries) == manifest.content_digest


def test_canonical_json_digest_is_order_independent_and_nfc_normalized() -> None:
    composed = {"name": "é", "items": [3, 2, 1]}
    decomposed_reordered = {"items": [3, 2, 1], "name": "e\u0301"}

    assert canonical_json_bytes(composed) == canonical_json_bytes(decomposed_reordered)
    assert canonical_sha256(composed) == canonical_sha256(decomposed_reordered)
    assert canonical_sha256(composed) == canonical_sha256(composed)

    with pytest.raises(ValueError, match="NaN and Infinity"):
        canonical_json_bytes({"unsafe": math.nan})


def test_unknown_required_extension_fails_closed() -> None:
    with pytest.raises(WorldPackageContractError) as exc_info:
        WorldPackagePolicy.validate_required_extensions(["angmoo.future-feature"])

    assert exc_info.value.reason_code is WorldPackageReasonCode.CONTRACT_UNSUPPORTED
    assert str(exc_info.value) == "world_package_contract_unsupported"


def test_optional_unknown_extension_does_not_change_v1_required_gate() -> None:
    manifest_payload = _json(VALID_ROOT / "manifest.json")
    manifest_payload["optional_extensions"] = ["angmoo.future-hint"]

    manifest = WorldPackageManifest.model_validate(manifest_payload)
    WorldPackagePolicy.validate_required_extensions(manifest.required_extensions)


def test_archive_metadata_policy_accepts_the_synthetic_fixture() -> None:
    audited = WorldPackagePolicy.validate_archive_entries(_valid_descriptors())

    assert len(audited) == 5
    assert {entry.path for entry in audited} == WorldPackagePolicy.REQUIRED_PATHS


@pytest.mark.parametrize(
    ("case_id", "entries", "expected_reason"),
    _malicious_archive_metadata_corpus(),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_malicious_archive_metadata_corpus_fails_closed(
    case_id: str,
    entries: list[ArchiveEntryDescriptor],
    expected_reason: WorldPackageReasonCode,
) -> None:
    del case_id
    with pytest.raises(WorldPackageContractError) as exc_info:
        WorldPackagePolicy.validate_archive_entries(entries)

    assert exc_info.value.reason_code is expected_reason


def test_unicode_nfc_and_casefold_path_collisions_fail_closed() -> None:
    collision_sets = [
        ["manifest.json", "Manifest.json"],
        ["assets/é.webp", "assets/e\u0301.webp"],
    ]

    for paths in collision_sets:
        with pytest.raises(WorldPackageContractError) as exc_info:
            WorldPackagePolicy.validate_path_collisions(paths)
        assert exc_info.value.reason_code is WorldPackageReasonCode.PATH_UNSAFE


def test_manifest_rejects_unknown_fields_and_tampered_digest() -> None:
    payload = _json(VALID_ROOT / "manifest.json")
    payload["source_world_id"] = "must-not-cross-package-boundary"
    with pytest.raises(ValidationError):
        WorldPackageManifest.model_validate(payload)

    payload = _json(VALID_ROOT / "manifest.json")
    payload["content_digest"] = "0" * 64
    with pytest.raises(ValidationError, match="content_digest"):
        WorldPackageManifest.model_validate(payload)


def test_portable_schemas_exclude_runtime_private_and_source_identity_fields() -> None:
    forbidden = {
        "api_key",
        "app_secret",
        "autonomous_enabled",
        "character_id",
        "control_mode",
        "credential",
        "owner_id",
        "owner_user_id",
        "relationship_state",
        "source_world_id",
        "world_character_id",
        "world_id",
    }
    models = (
        PortableWorldDefinition,
        CharactersDocument,
        WorldCharactersDocument,
        AssetIndexDocument,
    )

    for model in models:
        schema_text = json.dumps(model.model_json_schema(), sort_keys=True).casefold()
        assert not {field for field in forbidden if f'"{field}"' in schema_text}


def test_v1_trust_labels_do_not_claim_a_verified_author() -> None:
    assert {state.value for state in WorldPackageTrustState} == {
        "locally_exported",
        "checksum_verified_unsigned",
    }


def test_world_package_domain_has_no_route_provider_or_framework_dependency() -> None:
    root = APP_ROOT / "domains" / "world_packages"
    forbidden_imports = (
        "app.api",
        "app.integrations",
        "app.providers",
        "app.runtime",
        "fastapi",
        "pathlib",
        "sqlalchemy",
    )
    violations: dict[str, list[str]] = {}

    pure_paths = [
        root / "public.py",
        *sorted((root / "domain").rglob("*.py")),
        *sorted((root / "ports").rglob("*.py")),
    ]
    for path in pure_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        forbidden = [
            item
            for item in imports
            if item in forbidden_imports
            or item.startswith(tuple(f"{prefix}." for prefix in forbidden_imports))
        ]
        if forbidden:
            violations[path.relative_to(APP_ROOT).as_posix()] = forbidden

    assert violations == {}
    assert not (root / "api" / "routes.py").exists()


def test_public_boundary_exports_only_world_package_domain_modules() -> None:
    public = APP_ROOT / "domains" / "world_packages" / "public.py"
    tree = ast.parse(public.read_text(encoding="utf-8"), filename=str(public))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert imported
    assert all(name.startswith("app.domains.world_packages.domain") for name in imported)
