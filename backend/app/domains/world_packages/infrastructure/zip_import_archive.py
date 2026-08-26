"""Fail-closed ZIP reader for bounded World Package import previews."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
import hashlib
import json
from pathlib import Path
import stat
import struct
from typing import Any
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, ZipInfo

from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from app.domains.world_packages.domain.canonical import (
    canonical_json_bytes,
    canonical_sha256,
)
from app.domains.world_packages.domain.content import (
    AssetIndexDocument,
    CharactersDocument,
    PortableWorldDefinition,
    WorldCharactersDocument,
)
from app.domains.world_packages.domain.errors import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.domain.export import (
    WORLD_PACKAGE_PRODUCER_VERSION,
)
from app.domains.world_packages.domain.license_policy import (
    validate_world_package_license,
)
from app.domains.world_packages.domain.manifest import WorldPackageManifest
from app.domains.world_packages.domain.package_policy import (
    ArchiveEntryDescriptor,
    WorldPackagePolicy,
)
from app.domains.world_packages.domain.preview import (
    ValidatedWorldPackage,
    WorldPackageNormalizedAsset,
)
from app.domains.world_packages.infrastructure.filesystem_staging import (
    FilesystemWorldPackageStaging,
)
from app.domains.worlds.public import (
    WORLD_CONTRACT_VERSION,
)


_EOCD_SIGNATURE = b"PK\x05\x06"
_LOCAL_FILE_SIGNATURE = b"PK\x03\x04"
_EOCD_BYTES = 22
_READ_CHUNK_BYTES = 64 * 1024
_JSON_MAX_DEPTH = 64


@dataclass(frozen=True, slots=True)
class _ExtractedEntry:
    path: Path
    size: int
    sha256: str


class ZipWorldPackageImportValidator:
    """Validate and normalize an archive without touching canonical storage."""

    def __init__(self, staging: FilesystemWorldPackageStaging) -> None:
        self._staging = staging

    def validate(self, *, operation_id: str) -> ValidatedWorldPackage:
        upload = self._staging.upload_path(operation_id)
        extracted = self._staging.extracted_path(operation_id)
        try:
            archive_digest = _sha256_file(upload)
            _validate_outer_zip(upload)
            with ZipFile(upload, "r", allowZip64=False) as archive:
                infos = archive.infolist()
                _validate_zip_metadata(infos)
                payloads = _extract_bounded(archive, infos, extracted)
            return _validate_payloads(
                operation_id=operation_id,
                archive_digest=archive_digest,
                payloads=payloads,
                extracted=extracted,
            )
        except WorldPackageContractError:
            raise
        except (BadZipFile, OSError, UnicodeError, ValidationError, ValueError) as exc:
            raise WorldPackageContractError(
                WorldPackageReasonCode.ARCHIVE_INVALID
            ) from exc


def _validate_outer_zip(path: Path) -> None:
    size = path.stat().st_size
    if size <= _EOCD_BYTES or size > WorldPackagePolicy.MAX_COMPRESSED_BYTES:
        _fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)
    with path.open("rb") as source:
        if source.read(4) != _LOCAL_FILE_SIGNATURE:
            _fail(WorldPackageReasonCode.ARCHIVE_INVALID)
        source.seek(-_EOCD_BYTES, 2)
        eocd_offset = source.tell()
        eocd = source.read(_EOCD_BYTES)
    if len(eocd) != _EOCD_BYTES or eocd[:4] != _EOCD_SIGNATURE:
        _fail(WorldPackageReasonCode.ARCHIVE_INVALID)
    (
        _signature,
        disk_number,
        central_disk,
        entries_on_disk,
        total_entries,
        central_bytes,
        central_offset,
        comment_bytes,
    ) = struct.unpack("<4s4H2LH", eocd)
    if (
        disk_number != 0
        or central_disk != 0
        or entries_on_disk != total_entries
        or total_entries in {0, 0xFFFF}
        or central_bytes == 0xFFFFFFFF
        or central_offset == 0xFFFFFFFF
        or comment_bytes != 0
        or central_offset + central_bytes != eocd_offset
    ):
        _fail(WorldPackageReasonCode.ARCHIVE_INVALID)


def _validate_zip_metadata(infos: list[ZipInfo]) -> None:
    if not infos or min(item.header_offset for item in infos) != 0:
        _fail(WorldPackageReasonCode.ARCHIVE_INVALID)
    if len({item.header_offset for item in infos}) != len(infos):
        _fail(WorldPackageReasonCode.ARCHIVE_INVALID)
    descriptors: list[ArchiveEntryDescriptor] = []
    for item in infos:
        if item.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
            _fail(WorldPackageReasonCode.ARCHIVE_INVALID)
        kind = _zip_entry_kind(item)
        descriptors.append(
            ArchiveEntryDescriptor(
                path=item.filename,
                compressed_bytes=item.compress_size,
                uncompressed_bytes=item.file_size,
                kind=kind,
                encrypted=bool(item.flag_bits & 0x1),
            )
        )
    WorldPackagePolicy.validate_archive_entries(descriptors)


def _zip_entry_kind(info: ZipInfo) -> str:
    if info.is_dir():
        return "directory"
    if info.create_system != 3:
        return "file"
    mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    if file_type in {0, stat.S_IFREG}:
        return "file"
    if file_type == stat.S_IFDIR:
        return "directory"
    if file_type == stat.S_IFLNK:
        return "symlink"
    return "device"


def _extract_bounded(
    archive: ZipFile,
    infos: list[ZipInfo],
    extracted: Path,
) -> dict[str, _ExtractedEntry]:
    entries: dict[str, _ExtractedEntry] = {}
    total = 0
    for info in infos:
        destination = (extracted / info.filename).resolve()
        try:
            destination.relative_to(extracted)
        except ValueError:
            _fail(WorldPackageReasonCode.PATH_UNSAFE)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        digest = hashlib.sha256()
        received = 0
        with archive.open(info, "r") as source, destination.open("xb") as target:
            while chunk := source.read(_READ_CHUNK_BYTES):
                received += len(chunk)
                total += len(chunk)
                if (
                    received > info.file_size
                    or total > WorldPackagePolicy.MAX_UNCOMPRESSED_BYTES
                ):
                    _fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)
                digest.update(chunk)
                target.write(chunk)
        if received != info.file_size:
            _fail(WorldPackageReasonCode.INTEGRITY_MISMATCH)
        entries[info.filename] = _ExtractedEntry(
            path=destination,
            size=received,
            sha256=digest.hexdigest(),
        )
    return entries


def _validate_payloads(
    *,
    operation_id: str,
    archive_digest: str,
    payloads: Mapping[str, _ExtractedEntry],
    extracted: Path,
) -> ValidatedWorldPackage:
    manifest_payload = _strict_json(
        _read_entry(
            payloads["manifest.json"],
            max_bytes=WorldPackagePolicy.MAX_MANIFEST_BYTES,
        )
    )
    if manifest_payload.get("format") != "angmoo-world-package":
        _fail(WorldPackageReasonCode.FORMAT_UNSUPPORTED)
    if manifest_payload.get("format_version") != 1:
        _fail(WorldPackageReasonCode.FORMAT_UNSUPPORTED)
    try:
        manifest = WorldPackageManifest.model_validate(manifest_payload)
    except ValidationError as exc:
        raise WorldPackageContractError(
            WorldPackageReasonCode.ARCHIVE_INVALID
        ) from exc

    expected_paths = {entry.path for entry in manifest.entries}
    actual_paths = set(payloads) - {"manifest.json"}
    if expected_paths != actual_paths:
        _fail(WorldPackageReasonCode.INTEGRITY_MISMATCH)
    entry_by_path = {entry.path: entry for entry in manifest.entries}
    for path, payload in payloads.items():
        if path == "manifest.json":
            continue
        entry = entry_by_path[path]
        if payload.size != entry.bytes or payload.sha256 != entry.sha256:
            _fail(WorldPackageReasonCode.INTEGRITY_MISMATCH)
        expected_media_type = _media_type_for(path)
        if entry.media_type != expected_media_type:
            _fail(WorldPackageReasonCode.INTEGRITY_MISMATCH)

    if _version_tuple(manifest.compatibility.min_reader_version) > _version_tuple(
        WORLD_PACKAGE_PRODUCER_VERSION
    ):
        _fail(WorldPackageReasonCode.APP_VERSION_UNSUPPORTED)
    WorldPackagePolicy.validate_required_extensions(manifest.required_extensions)

    world = _model(
        PortableWorldDefinition,
        _read_json_entry(payloads["content/world.json"]),
    )
    characters = _model(
        CharactersDocument,
        _read_json_entry(payloads["content/characters.json"]),
    )
    world_characters = _model(
        WorldCharactersDocument,
        _read_json_entry(payloads["content/world-characters.json"]),
    )
    asset_index = _model(
        AssetIndexDocument,
        _read_json_entry(payloads["assets/index.json"]),
    )
    if (
        manifest.compatibility.world_contract_version != WORLD_CONTRACT_VERSION
        or world.source_world_contract_version != WORLD_CONTRACT_VERSION
    ):
        _fail(WorldPackageReasonCode.CONTRACT_UNSUPPORTED)

    license_text = _license_text(manifest, payloads)
    license_assessment = validate_world_package_license(
        manifest.license,
        license_text,
    )
    _validate_references(
        world=world,
        characters=characters,
        world_characters=world_characters,
        asset_index=asset_index,
    )
    normalized_assets = _validate_and_normalize_assets(
        asset_index=asset_index,
        payloads=payloads,
        extracted=extracted,
    )
    return ValidatedWorldPackage(
        operation_id=operation_id,
        archive_digest=archive_digest,
        manifest_digest=canonical_sha256(manifest),
        manifest=manifest,
        world=world,
        characters=characters,
        world_characters=world_characters,
        asset_index=asset_index,
        normalized_assets=normalized_assets,
        license_text=license_text,
        license_assessment=license_assessment,
    )


def _read_json_entry(entry: _ExtractedEntry) -> bytes:
    return _read_entry(
        entry,
        max_bytes=WorldPackagePolicy.MAX_JSON_ENTRY_BYTES,
    )


def _read_entry(entry: _ExtractedEntry, *, max_bytes: int) -> bytes:
    if entry.size > max_bytes:
        _fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)
    with entry.path.open("rb") as source:
        payload = source.read(max_bytes + 1)
    if len(payload) > max_bytes:
        _fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)
    if (
        len(payload) != entry.size
        or hashlib.sha256(payload).hexdigest() != entry.sha256
    ):
        _fail(WorldPackageReasonCode.INTEGRITY_MISMATCH)
    return payload


def _strict_json(payload: bytes) -> dict[str, Any]:
    if payload.startswith(b"\xef\xbb\xbf"):
        _fail(WorldPackageReasonCode.ARCHIVE_INVALID)

    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    def reject_constant(_value: str) -> None:
        raise ValueError("non-finite JSON number")

    try:
        decoded = payload.decode("utf-8", errors="strict")
        value = json.loads(
            decoded,
            object_pairs_hook=reject_duplicate,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise WorldPackageContractError(
            WorldPackageReasonCode.ARCHIVE_INVALID
        ) from exc
    if not isinstance(value, dict) or _json_depth(value) > _JSON_MAX_DEPTH:
        _fail(WorldPackageReasonCode.ARCHIVE_INVALID)
    if canonical_json_bytes(value) != payload:
        _fail(WorldPackageReasonCode.ARCHIVE_INVALID)
    return value


def _json_depth(value: Any) -> int:
    if isinstance(value, dict):
        return 1 + max((_json_depth(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_json_depth(item) for item in value), default=0)
    return 0


def _model(model: Any, payload: bytes) -> Any:
    try:
        return model.model_validate(_strict_json(payload))
    except ValidationError as exc:
        raise WorldPackageContractError(
            WorldPackageReasonCode.ARCHIVE_INVALID
        ) from exc


def _license_text(
    manifest: WorldPackageManifest,
    payloads: Mapping[str, _ExtractedEntry],
) -> str | None:
    if manifest.license.license_text_path is None:
        return None
    entry = payloads.get(manifest.license.license_text_path)
    if entry is None:
        _fail(WorldPackageReasonCode.LICENSE_MISSING)
    try:
        return _read_entry(
            entry,
            max_bytes=WorldPackagePolicy.MAX_LICENSE_TEXT_BYTES,
        ).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise WorldPackageContractError(
            WorldPackageReasonCode.LICENSE_MISSING
        ) from exc


def _validate_references(
    *,
    world: PortableWorldDefinition,
    characters: CharactersDocument,
    world_characters: WorldCharactersDocument,
    asset_index: AssetIndexDocument,
) -> None:
    if any(
        len(refs) != len(set(refs))
        for refs in (
            [item.ref for item in world.places],
            [item.ref for item in world.roles],
            [item.ref for item in world.rules],
            [item.ref for item in world.glossary],
            [item.daypart for item in world.daypart_profiles],
        )
    ):
        _fail(WorldPackageReasonCode.REFERENCE_INVALID)
    character_refs = {item.ref for item in characters.characters}
    seed_refs = {item.character_ref for item in world_characters.characters}
    role_refs = {item.ref for item in world.roles}
    if character_refs != seed_refs:
        _fail(WorldPackageReasonCode.REFERENCE_INVALID)
    if any(item.role_ref not in role_refs for item in world_characters.characters):
        _fail(WorldPackageReasonCode.REFERENCE_INVALID)
    if any(
        role_ref not in role_refs
        for place in world.places
        for role_ref in place.access_role_refs
    ):
        _fail(WorldPackageReasonCode.REFERENCE_INVALID)

    referenced_assets = {
        reference
        for reference in (
            world.banner_asset_ref,
            *(
                item.avatar_asset_ref
                for item in characters.characters
            ),
            *(
                item.banner_asset_ref
                for item in characters.characters
            ),
        )
        if reference is not None
    }
    indexed_assets = {item.ref for item in asset_index.assets}
    if referenced_assets != indexed_assets:
        _fail(WorldPackageReasonCode.REFERENCE_INVALID)


def _validate_and_normalize_assets(
    *,
    asset_index: AssetIndexDocument,
    payloads: Mapping[str, _ExtractedEntry],
    extracted: Path,
) -> tuple[WorldPackageNormalizedAsset, ...]:
    normalized_root = extracted / "normalized"
    normalized_root.mkdir(mode=0o700, exist_ok=False)
    results: list[WorldPackageNormalizedAsset] = []
    total_pixels = 0
    for asset in asset_index.assets:
        entry = payloads.get(asset.ref)
        if entry is None:
            _fail(WorldPackageReasonCode.ASSET_MISSING)
        raw = _read_entry(
            entry,
            max_bytes=WorldPackagePolicy.MAX_IMAGE_BYTES,
        )
        if (
            len(raw) != asset.bytes
            or hashlib.sha256(raw).hexdigest() != asset.sha256
            or not _looks_like_exact_webp(raw)
        ):
            _fail(WorldPackageReasonCode.INTEGRITY_MISMATCH)
        try:
            with Image.open(BytesIO(raw)) as image:
                if (
                    image.format != "WEBP"
                    or getattr(image, "n_frames", 1) != 1
                    or image.width != asset.width
                    or image.height != asset.height
                    or image.width > WorldPackagePolicy.MAX_IMAGE_DIMENSION
                    or image.height > WorldPackagePolicy.MAX_IMAGE_DIMENSION
                ):
                    _fail(WorldPackageReasonCode.ASSET_UNSUPPORTED)
                total_pixels += image.width * image.height
                if total_pixels > WorldPackagePolicy.MAX_TOTAL_PIXELS:
                    _fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)
                image.load()
                normalized_image = image.convert(
                    "RGBA" if "A" in image.getbands() else "RGB"
                )
                output = BytesIO()
                normalized_image.save(
                    output,
                    format="WEBP",
                    lossless=True,
                    quality=100,
                    method=6,
                    exact=True,
                    exif=b"",
                    xmp=b"",
                    icc_profile=b"",
                )
        except WorldPackageContractError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise WorldPackageContractError(
                WorldPackageReasonCode.ASSET_UNSUPPORTED
            ) from exc
        normalized = output.getvalue()
        if len(normalized) > WorldPackagePolicy.MAX_IMAGE_BYTES:
            _fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)
        digest = hashlib.sha256(normalized).hexdigest()
        normalized_ref = f"assets/sha256-{digest}.webp"
        destination = normalized_root / f"sha256-{digest}.webp"
        if destination.exists() and destination.read_bytes() != normalized:
            _fail(WorldPackageReasonCode.INTEGRITY_MISMATCH)
        destination.write_bytes(normalized)
        results.append(
            WorldPackageNormalizedAsset(
                source_ref=asset.ref,
                normalized_ref=normalized_ref,
                normalized_sha256=digest,
                normalized_bytes=len(normalized),
                width=asset.width,
                height=asset.height,
                alt_text=asset.alt_text,
            )
        )
    return tuple(results)


def _looks_like_exact_webp(payload: bytes) -> bool:
    if len(payload) < 12 or payload[:4] != b"RIFF" or payload[8:12] != b"WEBP":
        return False
    declared = int.from_bytes(payload[4:8], "little") + 8
    return declared == len(payload)


def _media_type_for(path: str) -> str:
    if path.endswith(".json"):
        return "application/json"
    if path.endswith(".webp"):
        return "image/webp"
    if path == "LICENSE.txt":
        return "text/plain"
    _fail(WorldPackageReasonCode.ARCHIVE_INVALID)
    raise AssertionError("unreachable")


def _version_tuple(value: str) -> tuple[int, ...]:
    normalized = value.replace("-", ".")
    parts = normalized.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        _fail(WorldPackageReasonCode.APP_VERSION_UNSUPPORTED)
    return tuple(int(part) for part in parts)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(_READ_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _fail(reason: WorldPackageReasonCode) -> None:
    raise WorldPackageContractError(reason)


__all__ = ["ZipWorldPackageImportValidator"]
