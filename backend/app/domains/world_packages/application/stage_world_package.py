"""Bounded staging and read-only preview orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, Callable
from datetime import UTC, datetime, timedelta

from app.domains.world_packages.domain.collision_policy import (
    WorldPackageDuplicateState,
)
from app.domains.world_packages.domain.errors import WorldPackageContractError
from app.domains.world_packages.domain.import_state import WorldPackageImportState
from app.domains.world_packages.domain.preview import (
    IMPORT_PREVIEW_SCHEMA_VERSION,
    IMPORT_PREVIEW_TOKEN_TTL_SECONDS,
    WorldPackageImportPreview,
    WorldPackagePreparedPreview,
)
from app.domains.world_packages.ports.import_preview import (
    WorldPackageArchiveValidationPort,
    WorldPackagePreviewProbePort,
)
from app.domains.world_packages.ports.package_staging import (
    WorldPackageStagingPort,
)


class StageWorldPackage:
    def __init__(
        self,
        *,
        staging: WorldPackageStagingPort,
        validator: WorldPackageArchiveValidationPort,
        preview_probe: WorldPackagePreviewProbePort,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._staging = staging
        self._validator = validator
        self._preview_probe = preview_probe
        self._clock = clock

    async def stage(
        self,
        *,
        operation_id: str,
        local_owner_id: str,
        chunks: AsyncIterable[bytes],
    ) -> WorldPackagePreparedPreview:
        try:
            await self._staging.receive(
                operation_id=operation_id,
                owner_id=local_owner_id,
                chunks=chunks,
            )
            self._staging.transition(
                operation_id=operation_id,
                owner_id=local_owner_id,
                state=WorldPackageImportState.VALIDATING,
            )
            package = await asyncio.to_thread(
                self._validator.validate,
                operation_id=operation_id,
            )
            assessment = self._preview_probe.assess(
                local_owner_id=local_owner_id,
                package=package,
            )
            expires_at = _aware_utc(self._clock()) + timedelta(
                seconds=IMPORT_PREVIEW_TOKEN_TTL_SECONDS
            )
            blocking_issues = (
                ("world_package_duplicate",)
                if assessment.collision_plan.duplicate_state
                is WorldPackageDuplicateState.ALREADY_IMPORTED
                else ()
            )
            warnings = tuple(
                dict.fromkeys(
                    (
                        *package.license_assessment.warnings,
                        *assessment.warnings,
                    )
                )
            )
            preview = WorldPackageImportPreview(
                schema_version=IMPORT_PREVIEW_SCHEMA_VERSION,
                state=WorldPackageImportState.PREVIEW_READY,
                operation_id=operation_id,
                archive_digest=package.archive_digest,
                content_digest=package.manifest.content_digest,
                package_id=str(package.manifest.package_id),
                package_version=package.manifest.package_version,
                producer_name=package.manifest.producer.name,
                producer_version=package.manifest.producer.version,
                min_reader_version=(
                    package.manifest.compatibility.min_reader_version
                ),
                world_contract_version=(
                    package.manifest.compatibility.world_contract_version
                ),
                trust_state=assessment.trust_state,
                license=package.manifest.license,
                world_name=package.world.name,
                world_tagline=package.world.tagline,
                character_names=tuple(
                    item.display_name for item in package.characters.characters
                ),
                role_count=len(package.world.roles),
                place_count=len(package.world.places),
                rule_count=len(package.world.rules),
                glossary_count=len(package.world.glossary),
                asset_count=len(package.normalized_assets),
                asset_bytes=sum(
                    item.normalized_bytes for item in package.normalized_assets
                ),
                total_decoded_pixels=sum(
                    item.width * item.height
                    for item in package.normalized_assets
                ),
                excluded_owner_controlled_characters=0,
                excluded_runtime_records=0,
                collision_plan=assessment.collision_plan,
                normalized_assets=package.normalized_assets,
                warnings=warnings,
                blocking_issues=blocking_issues,
                expires_at=expires_at,
            )
            return self._staging.publish_preview(
                owner_id=local_owner_id,
                preview=preview,
            )
        except WorldPackageContractError:
            self._staging.reject(
                operation_id=operation_id,
                owner_id=local_owner_id,
            )
            raise
        except BaseException:
            self._staging.reject(
                operation_id=operation_id,
                owner_id=local_owner_id,
            )
            raise

    def read_preview(
        self,
        *,
        operation_id: str,
        local_owner_id: str,
        preview_token: str,
    ) -> WorldPackageImportPreview:
        return self._staging.read_preview(
            operation_id=operation_id,
            owner_id=local_owner_id,
            preview_token=preview_token,
        )

    def discard(
        self,
        *,
        operation_id: str,
        local_owner_id: str,
        preview_token: str,
    ) -> None:
        self._staging.discard(
            operation_id=operation_id,
            owner_id=local_owner_id,
            preview_token=preview_token,
        )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = ["StageWorldPackage"]
