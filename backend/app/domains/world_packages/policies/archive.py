"""Fail-closed archive metadata policy for World Package v1.

This module performs no file I/O. Archive adapters supply bounded metadata
descriptors and enforce the same policy while streaming bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import ClassVar, Iterable, Literal

from app.domains.world_packages.exceptions import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)


@dataclass(frozen=True, slots=True)
class ArchiveEntryDescriptor:
    path: str
    compressed_bytes: int
    uncompressed_bytes: int
    kind: Literal["file", "directory", "symlink", "hardlink", "device"] = "file"
    encrypted: bool = False


class WorldPackagePolicy:
    FORMAT_EXTENSION: ClassVar[str] = ".angmoo-world"
    MEDIA_TYPE: ClassVar[str] = "application/vnd.angmoo.world+zip"
    MAX_COMPRESSED_BYTES: ClassVar[int] = 128 * 1024 * 1024
    MAX_UNCOMPRESSED_BYTES: ClassVar[int] = 256 * 1024 * 1024
    MAX_ARCHIVE_ENTRIES: ClassVar[int] = 256
    MAX_MANIFEST_BYTES: ClassVar[int] = 256 * 1024
    MAX_LICENSE_TEXT_BYTES: ClassVar[int] = 256 * 1024
    MAX_JSON_ENTRY_BYTES: ClassVar[int] = 2 * 1024 * 1024
    MAX_IMAGE_BYTES: ClassVar[int] = 5 * 1024 * 1024
    MAX_CHARACTERS: ClassVar[int] = 50
    MAX_ASSETS: ClassVar[int] = 100
    MAX_IMAGE_DIMENSION: ClassVar[int] = 4096
    MAX_TOTAL_PIXELS: ClassVar[int] = 200_000_000
    MAX_COMPRESSION_RATIO: ClassVar[int] = 100
    MAX_PATH_DEPTH: ClassVar[int] = 5
    MAX_PATH_UTF8_BYTES: ClassVar[int] = 240

    REQUIRED_PATHS: ClassVar[frozenset[str]] = frozenset(
        {
            "manifest.json",
            "content/world.json",
            "content/characters.json",
            "content/world-characters.json",
            "assets/index.json",
        }
    )
    OPTIONAL_PATHS: ClassVar[frozenset[str]] = frozenset({"LICENSE.txt"})
    _ASSET_PATH = re.compile(r"^assets/sha256-[0-9a-f]{64}\.webp$")
    _WINDOWS_DEVICE = re.compile(
        r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$", re.IGNORECASE
    )

    @classmethod
    def validate_required_extensions(
        cls,
        required_extensions: Iterable[str],
        *,
        supported_extensions: frozenset[str] = frozenset(),
    ) -> None:
        if any(item not in supported_extensions for item in required_extensions):
            raise WorldPackageContractError(
                WorldPackageReasonCode.CONTRACT_UNSUPPORTED
            )

    @classmethod
    def validate_archive_entries(
        cls,
        entries: Iterable[ArchiveEntryDescriptor],
    ) -> tuple[ArchiveEntryDescriptor, ...]:
        audited = tuple(entries)
        if not audited or len(audited) > cls.MAX_ARCHIVE_ENTRIES:
            cls._fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)

        total_compressed = sum(item.compressed_bytes for item in audited)
        total_uncompressed = sum(item.uncompressed_bytes for item in audited)
        if (
            total_compressed > cls.MAX_COMPRESSED_BYTES
            or total_uncompressed > cls.MAX_UNCOMPRESSED_BYTES
            or total_compressed < 0
            or total_uncompressed < 0
        ):
            cls._fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)
        if (
            total_compressed
            and total_uncompressed
            > total_compressed * cls.MAX_COMPRESSION_RATIO
        ):
            cls._fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)

        cls.validate_path_collisions(item.path for item in audited)
        paths: set[str] = set()
        for entry in audited:
            cls._validate_path(entry.path)
            if entry.kind != "file" or entry.encrypted:
                cls._fail(WorldPackageReasonCode.ARCHIVE_INVALID)
            if entry.compressed_bytes < 0 or entry.uncompressed_bytes < 0:
                cls._fail(WorldPackageReasonCode.ARCHIVE_INVALID)
            if entry.uncompressed_bytes and entry.compressed_bytes == 0:
                cls._fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)
            if (
                entry.compressed_bytes
                and entry.uncompressed_bytes
                > entry.compressed_bytes * cls.MAX_COMPRESSION_RATIO
            ):
                cls._fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)
            cls._validate_entry_size(entry)
            paths.add(entry.path)

        if not cls.REQUIRED_PATHS.issubset(paths):
            reason = (
                WorldPackageReasonCode.MANIFEST_MISSING
                if "manifest.json" not in paths
                else WorldPackageReasonCode.ARCHIVE_INVALID
            )
            cls._fail(reason)
        return audited

    @classmethod
    def validate_path_collisions(cls, paths: Iterable[str]) -> None:
        seen: dict[str, str] = {}
        for path in paths:
            collision_key = unicodedata.normalize("NFC", path).casefold()
            if collision_key in seen:
                cls._fail(WorldPackageReasonCode.PATH_UNSAFE)
            seen[collision_key] = path

    @classmethod
    def _validate_entry_size(cls, entry: ArchiveEntryDescriptor) -> None:
        if entry.path == "manifest.json" and entry.uncompressed_bytes > cls.MAX_MANIFEST_BYTES:
            cls._fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)
        if entry.path.endswith(".json") and entry.uncompressed_bytes > cls.MAX_JSON_ENTRY_BYTES:
            cls._fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)
        if entry.path.startswith("assets/") and entry.uncompressed_bytes > cls.MAX_IMAGE_BYTES:
            cls._fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)
        if (
            entry.path == "LICENSE.txt"
            and entry.uncompressed_bytes > cls.MAX_LICENSE_TEXT_BYTES
        ):
            cls._fail(WorldPackageReasonCode.ARCHIVE_LIMIT_EXCEEDED)

    @classmethod
    def _validate_path(cls, path: str) -> None:
        if not path or len(path.encode("utf-8")) > cls.MAX_PATH_UTF8_BYTES:
            cls._fail(WorldPackageReasonCode.PATH_UNSAFE)
        nfc = unicodedata.normalize("NFC", path)
        if nfc != path or not path.isascii():
            cls._fail(WorldPackageReasonCode.PATH_UNSAFE)
        if (
            path.startswith(("/", "\\"))
            or "\\" in path
            or ":" in path
            or any(ord(character) < 32 or ord(character) == 127 for character in path)
        ):
            cls._fail(WorldPackageReasonCode.PATH_UNSAFE)
        segments = path.split("/")
        if (
            len(segments) > cls.MAX_PATH_DEPTH
            or any(segment in {"", ".", ".."} for segment in segments)
            or any(cls._WINDOWS_DEVICE.fullmatch(segment) for segment in segments)
        ):
            cls._fail(WorldPackageReasonCode.PATH_UNSAFE)

        allowed = (
            path in cls.REQUIRED_PATHS
            or path in cls.OPTIONAL_PATHS
            or cls._ASSET_PATH.fullmatch(path) is not None
        )
        if not allowed:
            cls._fail(WorldPackageReasonCode.ARCHIVE_INVALID)

    @staticmethod
    def _fail(reason: WorldPackageReasonCode) -> None:
        raise WorldPackageContractError(reason)
