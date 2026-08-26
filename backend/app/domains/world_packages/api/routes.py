"""Owner-only deterministic World Package export routes."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.deps import get_current_user
from app.core import browser_session
from app.core.db import get_db
from app.core.ids import uuid7_string
from app.domains.world_packages.api.schemas import (
    WorldPackageExportPreviewRead,
    WorldPackageExportRequest,
    WorldPackageImportPreviewRead,
    WorldPackageImportCommitRequestRead,
    WorldPackageImportCommitResultRead,
    WorldPackagePreparedExportRead,
    WorldPackagePreparedImportPreviewRead,
)
from app.domains.world_packages.application.export_world_package import (
    ExportWorldPackage,
)
from app.domains.world_packages.application.stage_world_package import (
    StageWorldPackage,
)
from app.domains.world_packages.application.commit_world_package import (
    CommitWorldPackageImport,
)
from app.domains.world_packages.domain.errors import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.domain.export import (
    WorldPackageExportRegistryRecord,
)
from app.domains.world_packages.domain.package_policy import WorldPackagePolicy
from app.domains.world_packages.infrastructure.filesystem_export_artifacts import (
    ExportArtifact,
    FilesystemWorldPackageExportArtifacts,
)
from app.domains.world_packages.infrastructure.filesystem_staging import (
    FilesystemWorldPackageStaging,
)
from app.domains.world_packages.infrastructure.filesystem_import_media import (
    FilesystemWorldPackageImportMedia,
)
from app.domains.world_packages.infrastructure.managed_media_assets import (
    ManagedMediaPackageAssets,
)
from app.domains.world_packages.infrastructure.sqlalchemy_registry import (
    SqlAlchemyWorldPackageRegistry,
)
from app.domains.world_packages.infrastructure.sqlalchemy_preview_probe import (
    SqlAlchemyWorldPackagePreviewProbe,
)
from app.domains.world_packages.infrastructure.sqlalchemy_source_snapshot import (
    SqlAlchemyWorldPackageSourceSnapshot,
)
from app.domains.world_packages.infrastructure.sqlalchemy_import_commit import (
    SqlAlchemyWorldPackageImportCommitter,
)
from app.domains.world_packages.infrastructure.zip_archive import (
    DeterministicWorldPackageZipArchive,
)
from app.domains.world_packages.infrastructure.zip_import_archive import (
    ZipWorldPackageImportValidator,
)


router = APIRouter(tags=["world-packages"])
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]
DownloadToken = Annotated[
    str,
    Header(alias="X-World-Package-Download-Token", min_length=32, max_length=128),
]
PreviewToken = Annotated[
    str,
    Header(alias="X-World-Package-Preview-Token", min_length=32, max_length=128),
]
_STORE_LOCK = threading.Lock()


def _paths(request: Request) -> tuple[Path, Path, str]:
    runtime_config = getattr(request.app.state, "runtime_config", None)
    runtime_settings = request.app.state.runtime_settings
    if runtime_config is not None:
        return (
            runtime_config.data_paths.media,
            runtime_config.data_paths.runtime,
            runtime_settings.media_url_path,
        )
    media_root = runtime_settings.media_root_path
    return media_root, media_root.parent / "runtime", runtime_settings.media_url_path


def _artifacts(request: Request) -> FilesystemWorldPackageExportArtifacts:
    existing = getattr(
        request.app.state, "world_package_export_artifacts", None
    )
    if existing is not None:
        return existing
    with _STORE_LOCK:
        existing = getattr(
            request.app.state, "world_package_export_artifacts", None
        )
        if existing is None:
            _media_root, runtime_root, _media_url_path = _paths(request)
            existing = FilesystemWorldPackageExportArtifacts(runtime_root)
            request.app.state.world_package_export_artifacts = existing
    return existing


def _staging(request: Request) -> FilesystemWorldPackageStaging:
    existing = getattr(request.app.state, "world_package_import_staging", None)
    if existing is not None:
        return existing
    with _STORE_LOCK:
        existing = getattr(
            request.app.state,
            "world_package_import_staging",
            None,
        )
        if existing is None:
            _media_root, runtime_root, _media_url_path = _paths(request)
            existing = FilesystemWorldPackageStaging(runtime_root)
            request.app.state.world_package_import_staging = existing
    return existing


def _exporter(request: Request, db: Session) -> ExportWorldPackage:
    media_root, _runtime_root, media_url_path = _paths(request)
    return ExportWorldPackage(
        source=SqlAlchemyWorldPackageSourceSnapshot(db),
        assets=ManagedMediaPackageAssets(
            media_root=media_root,
            media_url_path=media_url_path,
        ),
        registry=SqlAlchemyWorldPackageRegistry(db),
        archive=DeterministicWorldPackageZipArchive(),
    )


def _stager(request: Request, db: Session) -> StageWorldPackage:
    staging = _staging(request)
    return StageWorldPackage(
        staging=staging,
        validator=ZipWorldPackageImportValidator(staging),
        preview_probe=SqlAlchemyWorldPackagePreviewProbe(db),
    )


def _delivery_session_factory(
    request: Request, db: Session
) -> Callable[[], Session]:
    composition = getattr(request.app.state, "runtime_composition", None)
    if composition is not None:
        return composition.session_factory
    return sessionmaker(bind=db.get_bind(), expire_on_commit=False)


def _import_committer(
    request: Request, db: Session
) -> SqlAlchemyWorldPackageImportCommitter:
    existing = getattr(
        request.app.state, "world_package_import_committer", None
    )
    if existing is not None:
        return existing
    with _STORE_LOCK:
        existing = getattr(
            request.app.state, "world_package_import_committer", None
        )
        if existing is None:
            media_root, runtime_root, media_url_path = _paths(request)
            existing = SqlAlchemyWorldPackageImportCommitter(
                _delivery_session_factory(request, db),
                media=FilesystemWorldPackageImportMedia(
                    media_root=media_root,
                    runtime_root=runtime_root,
                    media_url_path=media_url_path,
                ),
            )
            existing.recover_media()
            request.app.state.world_package_import_committer = existing
    return existing


def _raise_contract_error(exc: WorldPackageContractError) -> None:
    reason = exc.reason_code
    if reason in {
        WorldPackageReasonCode.OWNER_REQUIRED,
        WorldPackageReasonCode.DELIVERY_FORBIDDEN,
        WorldPackageReasonCode.STAGE_FORBIDDEN,
    }:
        code = status.HTTP_403_FORBIDDEN
    elif reason in {
        WorldPackageReasonCode.DELIVERY_EXPIRED,
        WorldPackageReasonCode.STAGE_EXPIRED,
    }:
        code = status.HTTP_410_GONE
    elif reason is WorldPackageReasonCode.UPLOAD_TOO_LARGE:
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    elif reason in {
        WorldPackageReasonCode.SOURCE_CHANGED,
        WorldPackageReasonCode.COMMIT_CONFLICT,
        WorldPackageReasonCode.WORLD_NOT_EXPORTABLE,
        WorldPackageReasonCode.DUPLICATE,
        WorldPackageReasonCode.TAMPERED_VERSION,
        WorldPackageReasonCode.PREVIEW_CHANGED,
        WorldPackageReasonCode.COMMIT_FAILED,
    }:
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=code, detail=reason.value) from exc


@router.post(
    "/world-package-imports/stage",
    response_model=WorldPackagePreparedImportPreviewRead,
    status_code=status.HTTP_201_CREATED,
)
async def stage_world_package_import(
    request: Request,
    package: Annotated[UploadFile, File(...)],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WorldPackagePreparedImportPreviewRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    operation_id = uuid7_string()

    async def chunks() -> AsyncIterator[bytes]:
        while chunk := await package.read(64 * 1024):
            yield chunk

    try:
        prepared = await _stager(request, db).stage(
            operation_id=operation_id,
            local_owner_id=current_user.id,
            chunks=chunks(),
        )
        return WorldPackagePreparedImportPreviewRead.from_domain(prepared)
    except WorldPackageContractError as exc:
        _raise_contract_error(exc)
        raise AssertionError("unreachable")
    finally:
        await package.close()


@router.get(
    "/world-package-imports/{operation_id}/preview",
    response_model=WorldPackageImportPreviewRead,
)
def read_world_package_import_preview(
    operation_id: str,
    request: Request,
    preview_token: PreviewToken,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WorldPackageImportPreviewRead:
    browser_session.require_local_frontend_request(request, mutation=False)
    try:
        preview = _stager(request, db).read_preview(
            operation_id=operation_id,
            local_owner_id=current_user.id,
            preview_token=preview_token,
        )
        return WorldPackageImportPreviewRead.from_domain(preview)
    except WorldPackageContractError as exc:
        _raise_contract_error(exc)
        raise AssertionError("unreachable")


@router.delete(
    "/world-package-imports/{operation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def discard_world_package_import_preview(
    operation_id: str,
    request: Request,
    preview_token: PreviewToken,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        _stager(request, db).discard(
            operation_id=operation_id,
            local_owner_id=current_user.id,
            preview_token=preview_token,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except WorldPackageContractError as exc:
        _raise_contract_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/world-package-imports/{operation_id}/commit",
    response_model=WorldPackageImportCommitResultRead,
    status_code=status.HTTP_201_CREATED,
)
def commit_world_package_import(
    operation_id: str,
    data: WorldPackageImportCommitRequestRead,
    request: Request,
    preview_token: PreviewToken,
    idempotency_key: IdempotencyKey,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WorldPackageImportCommitResultRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    normalized_key = idempotency_key.strip()
    if len(normalized_key) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="idempotency_key_invalid",
        )
    try:
        staging = _staging(request)
        result = CommitWorldPackageImport(
            staging=staging,
            validator=ZipWorldPackageImportValidator(staging),
            committer=_import_committer(request, db),
        ).commit(
            operation_id=operation_id,
            local_owner_id=current_user.id,
            preview_token=preview_token,
            expected_content_digest=data.expected_content_digest,
            idempotency_key=normalized_key,
            duplicate_strategy=data.duplicate_strategy,
        )
        return WorldPackageImportCommitResultRead.from_domain(result)
    except WorldPackageContractError as exc:
        _raise_contract_error(exc)
        raise AssertionError("unreachable")
    except (IntegrityError, OperationalError) as exc:
        _raise_contract_error(
            WorldPackageContractError(WorldPackageReasonCode.COMMIT_FAILED)
        )
        raise AssertionError("unreachable") from exc


@router.post(
    "/worlds/{world_id}/package-exports/preview",
    response_model=WorldPackageExportPreviewRead,
)
def preview_world_package_export(
    world_id: str,
    data: WorldPackageExportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WorldPackageExportPreviewRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    try:
        preview = _exporter(request, db).preview(
            source_world_id=world_id,
            local_owner_id=current_user.id,
            license=data.domain_license(),
            license_text=data.license_text,
        )
        db.commit()
        return WorldPackageExportPreviewRead.from_domain(preview)
    except WorldPackageContractError as exc:
        db.rollback()
        _raise_contract_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/worlds/{world_id}/package-exports",
    response_model=WorldPackagePreparedExportRead,
    status_code=status.HTTP_201_CREATED,
)
def prepare_world_package_export(
    world_id: str,
    data: WorldPackageExportRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WorldPackagePreparedExportRead:
    browser_session.require_local_frontend_request(request, mutation=True)
    normalized_key = idempotency_key.strip()
    if len(normalized_key) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="idempotency_key_invalid",
        )
    operation_id = uuid7_string()
    artifact_store = _artifacts(request)
    try:
        preview, archive = _exporter(request, db).build(
            source_world_id=world_id,
            local_owner_id=current_user.id,
            license=data.domain_license(),
            license_text=data.license_text,
        )
        artifact, token, replayed = artifact_store.create(
            operation_id=operation_id,
            owner_id=current_user.id,
            filename=preview.recommended_filename,
            content=archive.content,
            package_id=preview.package_id,
            package_version=preview.package_version,
            source_world_id=world_id,
            seed_digest=preview.seed_digest,
            manifest_digest=archive.manifest_digest,
            license_expression=preview.license.expression,
            request_digest=archive.archive_digest,
            idempotency_key=normalized_key,
        )
        db.commit()
    except WorldPackageContractError as exc:
        db.rollback()
        _raise_contract_error(exc)
        raise AssertionError("unreachable")
    except IntegrityError as exc:
        db.rollback()
        artifact_store.discard(operation_id)
        _raise_contract_error(
            WorldPackageContractError(WorldPackageReasonCode.COMMIT_CONFLICT)
        )
        raise AssertionError("unreachable") from exc
    except BaseException:
        db.rollback()
        artifact_store.discard(operation_id)
        raise

    return WorldPackagePreparedExportRead(
        operation_id=artifact.operation_id,
        download_token=token,
        download_path=(
            f"/api/v1/world-package-exports/{artifact.operation_id}/download"
        ),
        expires_at=artifact.expires_at,
        preview=WorldPackageExportPreviewRead.from_domain(preview),
        manifest_digest=artifact.manifest_digest,
        archive_digest=archive.archive_digest,
        archive_bytes=len(archive.content),
        replayed_request=replayed,
    )


@router.get("/world-package-exports/{operation_id}/download")
def download_world_package_export(
    operation_id: str,
    request: Request,
    download_token: DownloadToken,
    delivery_mode: Literal["browser_download", "tauri_save_as"] = Header(
        default="browser_download",
        alias="X-World-Package-Delivery-Mode",
    ),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> StreamingResponse:
    browser_session.require_local_frontend_request(request, mutation=False)
    artifact_store = _artifacts(request)
    try:
        artifact = artifact_store.claim(
            operation_id=operation_id,
            owner_id=current_user.id,
            token=download_token,
        )
    except WorldPackageContractError as exc:
        _raise_contract_error(exc)
        raise AssertionError("unreachable")

    session_factory = _delivery_session_factory(request, db)
    stream = (
        _stream_and_record_delivery(
            artifact=artifact,
            artifact_store=artifact_store,
            session_factory=session_factory,
        )
        if delivery_mode == "browser_download"
        else _stream_pending_native_delivery(artifact=artifact)
    )
    response = StreamingResponse(
        stream,
        media_type=WorldPackagePolicy.MEDIA_TYPE,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": (
                "attachment; filename=angmoo-world.angmoo-world; "
                f"filename*=UTF-8''{quote(artifact.filename)}"
            ),
            "Content-Length": str(artifact.path.stat().st_size),
            "X-Content-Type-Options": "nosniff",
        },
    )
    return response


@router.post(
    "/world-package-exports/{operation_id}/delivery-ack",
    status_code=status.HTTP_204_NO_CONTENT,
)
def acknowledge_world_package_export_delivery(
    operation_id: str,
    request: Request,
    download_token: DownloadToken,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    """Commit a native Save As only after the host reports a durable write."""

    browser_session.require_local_frontend_request(request, mutation=True)
    artifact_store = _artifacts(request)
    try:
        artifact = artifact_store.claim(
            operation_id=operation_id,
            owner_id=current_user.id,
            token=download_token,
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
    except WorldPackageContractError as exc:
        db.rollback()
        _raise_contract_error(exc)
        raise AssertionError("unreachable")
    except BaseException:
        db.rollback()
        raise
    artifact_store.discard(operation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/world-package-exports/{operation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def discard_world_package_export(
    operation_id: str,
    request: Request,
    download_token: DownloadToken,
    current_user=Depends(get_current_user),
) -> Response:
    """Discard a prepared artifact after Save As cancellation or failure."""

    browser_session.require_local_frontend_request(request, mutation=True)
    artifact_store = _artifacts(request)
    try:
        artifact_store.claim(
            operation_id=operation_id,
            owner_id=current_user.id,
            token=download_token,
        )
    except WorldPackageContractError as exc:
        _raise_contract_error(exc)
        raise AssertionError("unreachable")
    artifact_store.discard(operation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


__all__ = ["router"]
