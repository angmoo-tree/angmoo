"""Digest-bound approval and canonical World Package import commit."""

from __future__ import annotations

from app.domains.world_packages.domain.errors import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.domain.import_commit import (
    WorldPackageDuplicateStrategy,
    WorldPackageImportCommitRequest,
    WorldPackageImportCommitResult,
)
from app.domains.world_packages.domain.preview import (
    ValidatedWorldPackage,
    WorldPackageImportPreview,
)
from app.domains.world_packages.ports.import_commit import (
    WorldPackageImportCommitPort,
)
from app.domains.world_packages.ports.import_preview import (
    WorldPackageArchiveValidationPort,
)
from app.domains.world_packages.ports.package_staging import (
    WorldPackageStagingPort,
)


class CommitWorldPackageImport:
    def __init__(
        self,
        *,
        staging: WorldPackageStagingPort,
        validator: WorldPackageArchiveValidationPort,
        committer: WorldPackageImportCommitPort,
    ) -> None:
        self._staging = staging
        self._validator = validator
        self._committer = committer

    def commit(
        self,
        *,
        operation_id: str,
        local_owner_id: str,
        preview_token: str,
        expected_content_digest: str,
        idempotency_key: str,
        duplicate_strategy: WorldPackageDuplicateStrategy,
    ) -> WorldPackageImportCommitResult:
        replay = self._committer.find_replay(
            local_owner_id=local_owner_id,
            idempotency_key=idempotency_key,
            expected_content_digest=expected_content_digest,
        )
        if replay is not None:
            return replay

        approved = self._staging.begin_commit(
            operation_id=operation_id,
            owner_id=local_owner_id,
            preview_token=preview_token,
            expected_content_digest=expected_content_digest,
        )
        try:
            package = self._validator.validate(operation_id=operation_id)
            _validate_digest_bound_preview(approved, package)
            result = self._committer.execute(
                WorldPackageImportCommitRequest(
                    local_owner_id=local_owner_id,
                    idempotency_key=idempotency_key,
                    duplicate_strategy=duplicate_strategy,
                    approved_preview=approved,
                    package=package,
                )
            )
        except BaseException:
            self._staging.restore_preview(
                operation_id=operation_id,
                owner_id=local_owner_id,
            )
            raise
        self._staging.complete_commit(
            operation_id=operation_id,
            owner_id=local_owner_id,
        )
        return result


def _validate_digest_bound_preview(
    preview: WorldPackageImportPreview,
    package: ValidatedWorldPackage,
) -> None:
    manifest = package.manifest
    if (
        preview.operation_id != package.operation_id
        or preview.archive_digest != package.archive_digest
        or preview.content_digest != manifest.content_digest
        or preview.package_id != str(manifest.package_id)
        or preview.package_version != manifest.package_version
        or preview.world_contract_version
        != manifest.compatibility.world_contract_version
        or preview.license != manifest.license
        or preview.world_name != package.world.name
        or preview.world_tagline != package.world.tagline
        or preview.character_names
        != tuple(item.display_name for item in package.characters.characters)
        or preview.normalized_assets != package.normalized_assets
    ):
        raise WorldPackageContractError(
            WorldPackageReasonCode.PREVIEW_CHANGED
        )


__all__ = ["CommitWorldPackageImport"]
