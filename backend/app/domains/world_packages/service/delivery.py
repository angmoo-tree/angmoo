"""Export transfer completion owns lineage persistence and artifact cleanup.

Browser delivery records only after the iterator exhausts; native delivery
retains the artifact until the explicit durable-save acknowledgment.
"""
from __future__ import annotations
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.domains.world_packages.contracts.export import (
    WorldPackageExportRegistryRecord, WorldPackageExportPreview, WorldPackageBuiltArchive,
)
from app.domains.world_packages.schemas.manifest import WorldPackageLicense
from app.domains.world_packages.exceptions import WorldPackageContractError, WorldPackageReasonCode
from app.domains.world_packages.service.export import ExportWorldPackage
from app.domains.world_packages.storage.exports import ExportArtifact, FilesystemWorldPackageExportArtifacts
from app.domains.world_packages.service.registry import SqlAlchemyWorldPackageRegistry

def _stream_pending_native_delivery(*, artifact: ExportArtifact) -> Iterator[bytes]:
    """Stream bytes without consuming the version or removing the artifact."""

    with artifact.path.open("rb") as source:
        while chunk := source.read(64 * 1024):
            yield chunk


def _stream_and_record_delivery(
    *,
    artifact: ExportArtifact,
    artifact_store: FilesystemWorldPackageExportArtifacts,
    session_factory: Callable[[], Session],
) -> Iterator[bytes]:
    try:
        with artifact.path.open("rb") as source:
            while chunk := source.read(64 * 1024):
                yield chunk
        with session_factory() as delivery_db:
            registry = SqlAlchemyWorldPackageRegistry(delivery_db)
            registry.record_export_delivery(
                WorldPackageExportRegistryRecord(
                    export_id=artifact.operation_id,
                    package_id=artifact.package_id,
                    package_version=artifact.package_version,
                    source_world_id=artifact.source_world_id,
                    seed_digest=artifact.seed_digest,
                    manifest_digest=artifact.manifest_digest,
                    license_expression=artifact.license_expression,
                    delivery_mode="browser_download",
                    delivered_at=datetime.now(timezone.utc),
                )
            )
            delivery_db.commit()
    finally:
        artifact_store.discard(artifact.operation_id)



def preview_export(
    *, db: Session, exporter: ExportWorldPackage, source_world_id: str,
    local_owner_id: str, license: WorldPackageLicense, license_text: str | None,
) -> WorldPackageExportPreview:
    """Persist source lineage only after a complete export preview."""
    try:
        preview = exporter.preview(
            source_world_id=source_world_id, local_owner_id=local_owner_id,
            license=license, license_text=license_text,
        )
        db.commit()
        return preview
    except WorldPackageContractError:
        db.rollback()
        raise


def prepare_export(
    *, db: Session, exporter: ExportWorldPackage,
    artifact_store: FilesystemWorldPackageExportArtifacts,
    operation_id: str, source_world_id: str, local_owner_id: str,
    license: WorldPackageLicense, license_text: str | None, idempotency_key: str,
) -> tuple[WorldPackageExportPreview, WorldPackageBuiltArchive, ExportArtifact, str, bool]:
    """Build and retain delivery bytes; compensate a failed lineage commit."""
    try:
        preview, archive = exporter.build(
            source_world_id=source_world_id, local_owner_id=local_owner_id,
            license=license, license_text=license_text,
        )
        artifact, token, replayed = artifact_store.create(
            operation_id=operation_id,
            owner_id=local_owner_id,
            filename=preview.recommended_filename,
            content=archive.content,
            package_id=preview.package_id,
            package_version=preview.package_version,
            source_world_id=source_world_id,
            seed_digest=preview.seed_digest,
            manifest_digest=archive.manifest_digest,
            license_expression=preview.license.expression,
            request_digest=archive.archive_digest,
            idempotency_key=idempotency_key,
        )
        db.commit()
    except WorldPackageContractError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        artifact_store.discard(operation_id)
        raise WorldPackageContractError(WorldPackageReasonCode.COMMIT_CONFLICT) from exc
    except BaseException:
        db.rollback()
        artifact_store.discard(operation_id)
        raise
    return preview, archive, artifact, token, replayed


def acknowledge_export_delivery(
    *, db: Session, artifact_store: FilesystemWorldPackageExportArtifacts,
    operation_id: str, owner_id: str, token: str,
) -> None:
    """Record native delivery only after the caller confirms a durable save."""
    try:
        artifact = artifact_store.claim(
            operation_id=operation_id, owner_id=owner_id, token=token,
        )
        SqlAlchemyWorldPackageRegistry(db).record_export_delivery(
            WorldPackageExportRegistryRecord(
                export_id=artifact.operation_id,
                package_id=artifact.package_id,
                package_version=artifact.package_version,
                source_world_id=artifact.source_world_id,
                seed_digest=artifact.seed_digest,
                manifest_digest=artifact.manifest_digest,
                license_expression=artifact.license_expression,
                delivery_mode="tauri_save_as",
                delivered_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    except BaseException:
        db.rollback()
        raise
    artifact_store.discard(operation_id)
