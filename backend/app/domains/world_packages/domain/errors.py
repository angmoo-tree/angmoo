"""Stable, non-sensitive World Package error contract."""

from __future__ import annotations

from enum import StrEnum


class WorldPackageReasonCode(StrEnum):
    OWNER_REQUIRED = "world_package_owner_required"
    WORLD_NOT_EXPORTABLE = "world_package_world_not_exportable"
    SOURCE_CHANGED = "world_package_source_changed"
    UPLOAD_TOO_LARGE = "world_package_upload_too_large"
    ARCHIVE_INVALID = "world_package_archive_invalid"
    PATH_UNSAFE = "world_package_path_unsafe"
    ARCHIVE_LIMIT_EXCEEDED = "world_package_archive_limit_exceeded"
    MANIFEST_MISSING = "world_package_manifest_missing"
    FORMAT_UNSUPPORTED = "world_package_format_unsupported"
    APP_VERSION_UNSUPPORTED = "world_package_app_version_unsupported"
    CONTRACT_UNSUPPORTED = "world_package_contract_unsupported"
    INTEGRITY_MISMATCH = "world_package_integrity_mismatch"
    LICENSE_MISSING = "world_package_license_missing"
    ASSET_UNSUPPORTED = "world_package_asset_unsupported"
    ASSET_MISSING = "world_package_asset_missing"
    REFERENCE_INVALID = "world_package_reference_invalid"
    DUPLICATE = "world_package_duplicate"
    TAMPERED_VERSION = "world_package_tampered_version"
    STAGE_EXPIRED = "world_package_stage_expired"
    PREVIEW_CHANGED = "world_package_preview_changed"
    COMMIT_CONFLICT = "world_package_commit_conflict"
    COMMIT_FAILED = "world_package_commit_failed"
    DELIVERY_EXPIRED = "world_package_delivery_expired"
    DELIVERY_FORBIDDEN = "world_package_delivery_forbidden"


class WorldPackageContractError(ValueError):
    """Fail-closed contract error that exposes only a stable reason code."""

    def __init__(self, reason_code: WorldPackageReasonCode) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code.value)
