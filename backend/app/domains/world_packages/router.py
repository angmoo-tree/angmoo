"""Owner-only deterministic World Package export routes."""

from __future__ import annotations

from app.domains.world_packages.dependencies import _artifacts, _staging, _exporter, _stager, _delivery_session_factory, _import_committer
from app.domains.world_packages.service.delivery import (
    _stream_pending_native_delivery,
    _stream_and_record_delivery,
    preview_export,
    prepare_export,
    acknowledge_export_delivery,
)

from collections.abc import AsyncIterator
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
from sqlalchemy.orm import Session

from app.api.identity_dependencies import get_current_user
from app.api.identity_dependencies import browser_session
from app.core.db import get_db
from app.core.ids import uuid7_string
from app.domains.world_packages.schemas.http import (
    WorldPackageExportPreviewRead,
    WorldPackageExportRequest,
    WorldPackageImportPreviewRead,
    WorldPackageImportCommitRequestRead,
    WorldPackageImportCommitResultRead,
    WorldPackagePreparedExportRead,
    WorldPackagePreparedImportPreviewRead,
)
from app.domains.world_packages.service.import_approval import (
    CommitWorldPackageImport,
)
from app.domains.world_packages.exceptions import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.policies.archive import WorldPackagePolicy
from app.domains.world_packages.archive.validation import (
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
        preview = preview_export(
            db=db,
            exporter=_exporter(request, db),
            source_world_id=world_id,
            local_owner_id=current_user.id,
            license=data.domain_license(),
            license_text=data.license_text,
        )
        return WorldPackageExportPreviewRead.from_domain(preview)
    except WorldPackageContractError as exc:
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
        preview, archive, artifact, token, replayed = prepare_export(
            db=db,
            exporter=_exporter(request, db),
            artifact_store=artifact_store,
            operation_id=operation_id,
            source_world_id=world_id,
            local_owner_id=current_user.id,
            license=data.domain_license(),
            license_text=data.license_text,
            idempotency_key=normalized_key,
        )
    except WorldPackageContractError as exc:
        _raise_contract_error(exc)
        raise AssertionError("unreachable")

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
        acknowledge_export_delivery(
            db=db,
            artifact_store=artifact_store,
            operation_id=operation_id,
            owner_id=current_user.id,
            token=download_token,
        )
    except WorldPackageContractError as exc:
        _raise_contract_error(exc)
        raise AssertionError("unreachable")
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


__all__ = ["router"]
