"""HTTP state, caller Session and application-supplied Package composition."""
from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
import threading
from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker
from app.domains.world_packages.contracts.runtime import WorldPackageRuntimeFactories, WorldPackageRuntimeCommitter
from app.domains.world_packages.service.export import ExportWorldPackage
from app.domains.world_packages.service.staging import StageWorldPackage
from app.domains.world_packages.service.registry import SqlAlchemyWorldPackageRegistry
from app.domains.world_packages.storage.exports import FilesystemWorldPackageExportArtifacts
from app.domains.world_packages.storage.staging import FilesystemWorldPackageStaging
from app.domains.world_packages.storage.import_media import FilesystemWorldPackageImportMedia
from app.domains.world_packages.storage.export_assets import ManagedMediaPackageAssets
from app.domains.world_packages.archive.export import DeterministicWorldPackageZipArchive
from app.domains.world_packages.archive.validation import ZipWorldPackageImportValidator

_STORE_LOCK = threading.Lock()

def _runtime_factories(request: Request) -> WorldPackageRuntimeFactories:
    return request.app.state.world_package_factories

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
        source=_runtime_factories(request).source_snapshot(db),
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
        preview_probe=_runtime_factories(request).preview_probe(db),
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
) -> WorldPackageRuntimeCommitter:
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
            existing = _runtime_factories(request).import_committer(
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
