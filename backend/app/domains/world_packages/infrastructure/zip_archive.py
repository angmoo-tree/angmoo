"""Byte-reproducible ZIP writer and self-validator for World Package v1."""

from __future__ import annotations

from io import BytesIO
import hashlib
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from app.domains.world_packages.domain.canonical import (
    canonical_entry_index_digest,
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
    WORLD_PACKAGE_MIN_READER_VERSION,
    WORLD_PACKAGE_PRODUCER_NAME,
    WORLD_PACKAGE_PRODUCER_VERSION,
    WorldPackageBuiltArchive,
    WorldPackageResolvedAssets,
    WorldPackageSourceIdentity,
    world_package_seed_digest,
)
from app.domains.world_packages.domain.manifest import (
    WorldPackageCompatibility,
    WorldPackageEntry,
    WorldPackageLicense,
    WorldPackageManifest,
    WorldPackageProducer,
)
from app.domains.world_packages.domain.package_policy import (
    ArchiveEntryDescriptor,
    WorldPackagePolicy,
)


_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_FILE_MODE = 0o100644 << 16


class DeterministicWorldPackageZipArchive:
    def build(
        self,
        *,
        identity: WorldPackageSourceIdentity,
        package_version: int,
        world: PortableWorldDefinition,
        characters: CharactersDocument,
        world_characters: WorldCharactersDocument,
        asset_index: AssetIndexDocument,
        resolved_assets: WorldPackageResolvedAssets,
        license: WorldPackageLicense,
        license_text: str | None,
    ) -> WorldPackageBuiltArchive:
        payloads: dict[str, bytes] = {
            "content/world.json": canonical_json_bytes(world),
            "content/characters.json": canonical_json_bytes(characters),
            "content/world-characters.json": canonical_json_bytes(world_characters),
            "assets/index.json": canonical_json_bytes(asset_index),
        }
        asset_content: dict[str, bytes] = {}
        for resolved in resolved_assets.assets:
            prior = asset_content.get(resolved.asset.ref)
            if prior is not None and prior != resolved.content:
                raise WorldPackageContractError(
                    WorldPackageReasonCode.INTEGRITY_MISMATCH
                )
            asset_content[resolved.asset.ref] = resolved.content
        payloads.update(asset_content)
        if license.license_text_path is not None:
            if license_text is None:
                raise WorldPackageContractError(
                    WorldPackageReasonCode.LICENSE_MISSING
                )
            payloads[license.license_text_path] = license_text.encode("utf-8")
        elif license_text is not None:
            raise WorldPackageContractError(WorldPackageReasonCode.ARCHIVE_INVALID)

        entries = [self._entry(path, content) for path, content in payloads.items()]
        entries.sort(key=lambda item: item.path)
        manifest = WorldPackageManifest(
            format="angmoo-world-package",
            format_version=1,
            schema_version="world-package-v1",
            package_id=identity.package_id,
            package_version=package_version,
            created_at=identity.created_at,
            producer=WorldPackageProducer(
                name=WORLD_PACKAGE_PRODUCER_NAME,
                version=WORLD_PACKAGE_PRODUCER_VERSION,
            ),
            compatibility=WorldPackageCompatibility(
                min_reader_version=WORLD_PACKAGE_MIN_READER_VERSION,
                world_contract_version=world.source_world_contract_version,
            ),
            license=license,
            entries=entries,
            content_digest=canonical_entry_index_digest(entries),
        )
        manifest_bytes = canonical_json_bytes(manifest)
        if len(manifest_bytes) > WorldPackagePolicy.MAX_MANIFEST_BYTES:
            raise WorldPackageContractError(
                WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED
            )
        ordered_payloads = {"manifest.json": manifest_bytes, **payloads}
        stream = BytesIO()
        with ZipFile(stream, "w", compression=ZIP_STORED, allowZip64=False) as archive:
            for path in sorted(ordered_payloads):
                info = ZipInfo(path, date_time=_FIXED_ZIP_TIME)
                info.compress_type = ZIP_STORED
                info.create_system = 3
                info.external_attr = _FILE_MODE
                archive.writestr(info, ordered_payloads[path])
        content = stream.getvalue()
        if len(content) > WorldPackagePolicy.MAX_COMPRESSED_BYTES:
            raise WorldPackageContractError(
                WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED
            )
        self._self_validate(content, manifest, ordered_payloads)
        seed_digest = world_package_seed_digest(
            world=world,
            characters=characters,
            world_characters=world_characters,
            asset_index=asset_index,
            license=license,
            license_text=license_text,
        )
        return WorldPackageBuiltArchive(
            content=content,
            manifest=manifest,
            seed_digest=seed_digest,
            manifest_digest=canonical_sha256(manifest),
            archive_digest=hashlib.sha256(content).hexdigest(),
        )

    @staticmethod
    def _entry(path: str, content: bytes) -> WorldPackageEntry:
        if path.endswith(".json"):
            media_type = "application/json"
        elif path.endswith(".webp"):
            media_type = "image/webp"
        else:
            media_type = "text/plain"
        return WorldPackageEntry(
            path=path,
            sha256=hashlib.sha256(content).hexdigest(),
            bytes=len(content),
            media_type=media_type,
        )

    @staticmethod
    def _self_validate(
        content: bytes,
        manifest: WorldPackageManifest,
        expected: dict[str, bytes],
    ) -> None:
        try:
            with ZipFile(BytesIO(content), "r") as archive:
                infos = archive.infolist()
                descriptors = [
                    ArchiveEntryDescriptor(
                        path=item.filename,
                        compressed_bytes=item.compress_size,
                        uncompressed_bytes=item.file_size,
                        encrypted=bool(item.flag_bits & 0x1),
                    )
                    for item in infos
                ]
                WorldPackagePolicy.validate_archive_entries(descriptors)
                if [item.filename for item in infos] != sorted(expected):
                    raise WorldPackageContractError(
                        WorldPackageReasonCode.ARCHIVE_INVALID
                    )
                for path, expected_content in expected.items():
                    if archive.read(path) != expected_content:
                        raise WorldPackageContractError(
                            WorldPackageReasonCode.INTEGRITY_MISMATCH
                        )
                parsed = WorldPackageManifest.model_validate_json(
                    archive.read("manifest.json")
                )
                if parsed != manifest:
                    raise WorldPackageContractError(
                        WorldPackageReasonCode.INTEGRITY_MISMATCH
                    )
        except WorldPackageContractError:
            raise
        except Exception as exc:
            raise WorldPackageContractError(
                WorldPackageReasonCode.ARCHIVE_INVALID
            ) from exc


__all__ = ["DeterministicWorldPackageZipArchive"]
