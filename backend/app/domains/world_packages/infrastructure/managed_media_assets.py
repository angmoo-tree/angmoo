"""Fail-closed managed media resolver for deterministic package export."""

from __future__ import annotations

import hashlib
from io import BytesIO
import os
from pathlib import Path
from pathlib import PurePosixPath

from PIL import Image, UnidentifiedImageError

from app.domains.world_packages.schemas.content import ManagedImageAsset
from app.domains.world_packages.exceptions import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.contracts.export import (
    WorldPackageMediaCandidate,
    WorldPackageResolvedAsset,
    WorldPackageResolvedAssets,
)
from app.domains.world_packages.policies.archive import WorldPackagePolicy


class ManagedMediaPackageAssets:
    """Resolve only Angmoo-owned WebP paths; never fetch remote media."""

    def __init__(self, *, media_root: Path, media_url_path: str = "/media") -> None:
        self._media_root = media_root.resolve()
        self._url_prefix = "/" + media_url_path.strip("/") + "/"

    def resolve_export_assets(
        self, *, candidates: tuple[WorldPackageMediaCandidate, ...]
    ) -> WorldPackageResolvedAssets:
        resolved: list[WorldPackageResolvedAsset] = []
        external: list[str] = []
        by_digest: dict[str, ManagedImageAsset] = {}
        total_bytes = 0
        total_pixels = 0
        for candidate in sorted(candidates, key=lambda item: item.candidate_key):
            source_url = (candidate.source_url or "").strip()
            if not source_url:
                continue
            if source_url.startswith(("http://", "https://")):
                external.append(candidate.candidate_key)
                continue
            path = self._resolve_managed_path(candidate)
            try:
                with path.open("rb") as source:
                    before = os.fstat(source.fileno())
                    content = source.read(WorldPackagePolicy.MAX_IMAGE_BYTES + 1)
                    after = os.fstat(source.fileno())
                current = path.stat()
            except (FileNotFoundError, OSError) as exc:
                raise WorldPackageContractError(
                    WorldPackageReasonCode.ASSET_MISSING
                ) from exc
            if (
                before.st_size < 1
                or before.st_size > WorldPackagePolicy.MAX_IMAGE_BYTES
                or len(content) != before.st_size
            ):
                raise WorldPackageContractError(
                    WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED
                )
            before_identity = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            )
            if before_identity != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ) or before_identity != (
                current.st_dev,
                current.st_ino,
                current.st_size,
                current.st_mtime_ns,
            ):
                raise WorldPackageContractError(
                    WorldPackageReasonCode.SOURCE_CHANGED
                )
            width, height = self._validate_webp(content)
            total_bytes += len(content)
            total_pixels += width * height
            if (
                total_bytes > WorldPackagePolicy.MAX_UNCOMPRESSED_BYTES
                or total_pixels > WorldPackagePolicy.MAX_TOTAL_PIXELS
            ):
                raise WorldPackageContractError(
                    WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED
                )
            digest = hashlib.sha256(content).hexdigest()
            relative = source_url[len(self._url_prefix) :]
            portable = PurePosixPath(relative)
            if portable.parts[0] == "world-package-imports" and (
                portable.parts[-1] != f"sha256-{digest}.webp"
            ):
                raise WorldPackageContractError(
                    WorldPackageReasonCode.INTEGRITY_MISMATCH
                )
            asset = by_digest.get(digest)
            if asset is None:
                asset = ManagedImageAsset(
                    ref=f"assets/sha256-{digest}.webp",
                    sha256=digest,
                    bytes=len(content),
                    media_type="image/webp",
                    width=width,
                    height=height,
                    alt_text=candidate.alt_text,
                )
                by_digest[digest] = asset
            resolved.append(
                WorldPackageResolvedAsset(
                    candidate_key=candidate.candidate_key,
                    asset=asset,
                    content=content,
                )
            )
        return WorldPackageResolvedAssets(
            assets=tuple(resolved),
            excluded_external_candidate_keys=tuple(sorted(external)),
        )

    def stage_verified_asset(
        self, *, content: bytes, sha256: str, media_type: str
    ) -> str:
        del content, sha256, media_type
        raise NotImplementedError("import asset staging belongs to PR D/E")

    def promote_staged_assets(self, *, import_id: str) -> tuple[str, ...]:
        del import_id
        raise NotImplementedError("import asset promotion belongs to PR E")

    def discard_staged_assets(self, *, import_id: str) -> None:
        del import_id
        raise NotImplementedError("import asset cleanup belongs to PR D/E")

    def _resolve_managed_path(self, candidate: WorldPackageMediaCandidate) -> Path:
        source_url = (candidate.source_url or "").strip()
        if not source_url.startswith(self._url_prefix):
            raise WorldPackageContractError(
                WorldPackageReasonCode.ASSET_UNSUPPORTED
            )
        relative = source_url[len(self._url_prefix) :]
        if "\\" in relative or ":" in relative:
            raise WorldPackageContractError(WorldPackageReasonCode.PATH_UNSAFE)
        portable = PurePosixPath(relative)
        if (
            portable.is_absolute()
            or not portable.parts
            or any(part in {"", ".", ".."} for part in portable.parts)
        ):
            raise WorldPackageContractError(WorldPackageReasonCode.PATH_UNSAFE)
        expected_group = (
            "worlds" if candidate.slot == "world_banner" else "characters"
        )
        if portable.parts[0] == "world-package-imports":
            if (
                len(portable.parts) != 3
                or any(
                    character not in "0123456789abcdef-"
                    for character in portable.parts[1]
                )
                or not portable.parts[2].startswith("sha256-")
                or not portable.parts[2].endswith(".webp")
            ):
                raise WorldPackageContractError(
                    WorldPackageReasonCode.PATH_UNSAFE
                )
            expected_root = (
                self._media_root
                / "world-package-imports"
                / portable.parts[1]
            ).resolve()
        else:
            if portable.parts[:2] != (
                expected_group,
                candidate.source_entity_id,
            ):
                raise WorldPackageContractError(
                    WorldPackageReasonCode.PATH_UNSAFE
                )
            expected_root = (
                self._media_root / expected_group / candidate.source_entity_id
            ).resolve()
        lexical = self._media_root.joinpath(*portable.parts)
        cursor = self._media_root
        for part in portable.parts:
            cursor = cursor / part
            if cursor.is_symlink() or (
                hasattr(cursor, "is_junction") and cursor.is_junction()
            ):
                raise WorldPackageContractError(
                    WorldPackageReasonCode.PATH_UNSAFE
                )
        resolved = lexical.resolve()
        try:
            resolved.relative_to(expected_root)
            resolved.relative_to(self._media_root)
        except ValueError as exc:
            raise WorldPackageContractError(
                WorldPackageReasonCode.PATH_UNSAFE
            ) from exc
        if not resolved.is_file() or resolved.suffix.casefold() != ".webp":
            raise WorldPackageContractError(
                WorldPackageReasonCode.ASSET_UNSUPPORTED
            )
        return resolved

    @staticmethod
    def _validate_webp(content: bytes) -> tuple[int, int]:
        try:
            with Image.open(BytesIO(content)) as image:
                if image.format != "WEBP" or getattr(image, "n_frames", 1) != 1:
                    raise WorldPackageContractError(
                        WorldPackageReasonCode.ASSET_UNSUPPORTED
                    )
                width, height = image.size
                if (
                    width < 1
                    or height < 1
                    or width > WorldPackagePolicy.MAX_IMAGE_DIMENSION
                    or height > WorldPackagePolicy.MAX_IMAGE_DIMENSION
                ):
                    raise WorldPackageContractError(
                        WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED
                    )
                image.verify()
                return width, height
        except WorldPackageContractError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise WorldPackageContractError(
                WorldPackageReasonCode.ASSET_UNSUPPORTED
            ) from exc


__all__ = ["ManagedMediaPackageAssets"]
