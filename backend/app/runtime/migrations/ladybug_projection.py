"""Versioned LadybugDB reuse and canonical-replay generation upgrades."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from app.domains.runtime.ports.runtime_data_path import RuntimeDataPathPort
from app.integrations.ladybug_projection import (
    LADYBUG_PROJECTION_SCHEMA_VERSION,
    LadybugRelationshipProjection,
    inspect_ladybug_projection_schema_version,
)
from app.runtime.migrations.generation import (
    EmbeddedGenerationController,
    write_json_atomic,
)
from app.runtime.migrations.ladybug_versions.registry import (
    LadybugVersionManifest,
    rebuild_for_version,
    validate_latest_ladybug_contract,
)
from app.runtime.graph_projection.sqlalchemy_outbox import (
    SqlAlchemyProjectionReplaySource,
)


GRAPH_MANIFEST_NAME = "projection-manifest.json"


class LadybugProjectionUpgradeError(RuntimeError):
    """Privacy-safe graph upgrade failure."""


@dataclass(frozen=True)
class LadybugProjectionUpgradeResult:
    database_root: Path
    source_version: int | None
    target_version: int
    rebuilt: bool
    degraded: bool
    manifest_sha256: str
    error_code: str | None = None


class LadybugProjectionUpgradeCoordinator:
    def __init__(
        self,
        data_paths: RuntimeDataPathPort,
        *,
        session_factory: sessionmaker[Session],
    ) -> None:
        self._paths = data_paths.resolve()
        self._replay_source = SqlAlchemyProjectionReplaySource(session_factory)
        self._controller = EmbeddedGenerationController(
            self._paths.graph,
            artifact_relative_path="relationships.lbdb",
        )

    def upgrade(self) -> LadybugProjectionUpgradeResult:
        latest = validate_latest_ladybug_contract()
        relative = self._controller.selected_relative_path("ladybug")
        current_root = (self._paths.graph / relative).resolve()
        version = inspect_ladybug_projection_schema_version(current_root)
        if version is None:
            return self._create_clean(current_root, relative, latest)
        if version > LADYBUG_PROJECTION_SCHEMA_VERSION:
            raise LadybugProjectionUpgradeError(
                "ladybug_schema_newer_than_runtime"
            )
        if version == LADYBUG_PROJECTION_SCHEMA_VERSION:
            self._validate_or_register_manifest(current_root, latest)
            with LadybugRelationshipProjection(database_root=current_root) as graph:
                graph.verify_connectivity()
                if graph.projection_schema_version() != version:
                    raise LadybugProjectionUpgradeError(
                        "ladybug_schema_manifest_mismatch"
                    )
            current_marker = self._controller.current()
            if (
                current_marker is None
                or current_marker.get("relative_path") != Path(relative).as_posix()
                or current_marker.get("manifest_sha256")
                != latest.manifest_sha256
            ):
                self._controller.promote(
                    relative,
                    manifest_sha256=latest.manifest_sha256,
                    data_version=latest.projection_schema_version,
                )
            return LadybugProjectionUpgradeResult(
                database_root=current_root,
                source_version=version,
                target_version=latest.projection_schema_version,
                rebuilt=False,
                degraded=False,
                manifest_sha256=latest.manifest_sha256,
            )
        return self._rebuild(current_root, version, latest)

    def _create_clean(
        self,
        root: Path,
        relative: str,
        manifest: LadybugVersionManifest,
    ) -> LadybugProjectionUpgradeResult:
        with LadybugRelationshipProjection(database_root=root) as graph:
            graph.verify_connectivity()
        self._write_manifest(root, manifest)
        self._controller.promote(
            relative,
            manifest_sha256=manifest.manifest_sha256,
            data_version=manifest.projection_schema_version,
        )
        return LadybugProjectionUpgradeResult(
            database_root=root,
            source_version=None,
            target_version=manifest.projection_schema_version,
            rebuilt=False,
            degraded=False,
            manifest_sha256=manifest.manifest_sha256,
        )

    def _rebuild(
        self,
        previous_root: Path,
        source_version: int,
        manifest: LadybugVersionManifest,
    ) -> LadybugProjectionUpgradeResult:
        builder = rebuild_for_version(manifest.projection_schema_version)
        previous_artifact = previous_root / "relationships.lbdb"
        previous_fingerprint = _file_sha256(previous_artifact)
        previous_marker = self._controller.current()
        previous_manifest_sha256 = (
            str(previous_marker["manifest_sha256"])
            if previous_marker is not None
            else previous_fingerprint
        )
        previous_data_version = (
            int(previous_marker.get("data_version", source_version))
            if previous_marker is not None
            else source_version
        )
        previous_relative = (
            None
            if previous_marker is not None
            else previous_root.relative_to(self._paths.graph).as_posix()
        )
        final_name = f"ladybug-v{manifest.projection_schema_version}"
        final_relative = f"generations/{final_name}"
        if (self._paths.graph / final_relative).exists():
            final_name = f"{final_name}-{uuid4().hex[:8]}"
            final_relative = f"generations/{final_name}"
        staging = (
            self._controller.generations
            / f".{final_name}.tmp-{uuid4().hex[:8]}"
        )
        staging.mkdir(parents=True, exist_ok=False)
        try:
            builder(
                database_root=staging,
                replay_source=self._replay_source,
            )
            with LadybugRelationshipProjection(database_root=staging) as graph:
                graph.verify_connectivity()
                if (
                    graph.projection_schema_version()
                    != manifest.projection_schema_version
                ):
                    raise LadybugProjectionUpgradeError(
                        "ladybug_schema_manifest_mismatch"
                    )
            self._write_manifest(staging, manifest)
            if _file_sha256(previous_artifact) != previous_fingerprint:
                raise LadybugProjectionUpgradeError(
                    "ladybug_rebuild_previous_generation_changed"
                )
            final = self._controller.finalize_staging(staging, final_relative)
            self._controller.promote(
                final_relative,
                manifest_sha256=manifest.manifest_sha256,
                data_version=manifest.projection_schema_version,
                previous_relative_path=previous_relative,
                previous_manifest_sha256=(
                    None
                    if previous_marker is not None
                    else previous_manifest_sha256
                ),
                previous_data_version=(
                    None if previous_marker is not None else previous_data_version
                ),
            )
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise
        return LadybugProjectionUpgradeResult(
            database_root=final,
            source_version=source_version,
            target_version=manifest.projection_schema_version,
            rebuilt=True,
            degraded=False,
            manifest_sha256=manifest.manifest_sha256,
        )

    def _validate_or_register_manifest(
        self,
        root: Path,
        manifest: LadybugVersionManifest,
    ) -> None:
        path = root / GRAPH_MANIFEST_NAME
        if not path.is_file():
            self._write_manifest(root, manifest)
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LadybugProjectionUpgradeError(
                "ladybug_schema_manifest_mismatch"
            ) from exc
        if payload != manifest.as_dict():
            raise LadybugProjectionUpgradeError(
                "ladybug_schema_manifest_mismatch"
            )

    @staticmethod
    def _write_manifest(root: Path, manifest: LadybugVersionManifest) -> None:
        write_json_atomic(root / GRAPH_MANIFEST_NAME, manifest.as_dict())


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        raise LadybugProjectionUpgradeError(
            "ladybug_rebuild_previous_generation_changed"
        )
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "GRAPH_MANIFEST_NAME",
    "LadybugProjectionUpgradeCoordinator",
    "LadybugProjectionUpgradeError",
    "LadybugProjectionUpgradeResult",
]
