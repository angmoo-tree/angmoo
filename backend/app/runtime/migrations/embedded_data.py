"""Canonical-first startup orchestration for all embedded Angmoo runtimes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from app.core.db import create_database_engine, create_session_factory
from app.domains.runtime.ports.runtime_data_path import RuntimeDataPathPort
from app.integrations.ladybug_projection import (
    LADYBUG_PROJECTION_SCHEMA_VERSION,
    LadybugProjectionError,
)
from app.runtime.migrations.embedded_sqlite import (
    SqliteCanonicalUpgradeCoordinator,
    SqliteCanonicalUpgradeResult,
)
from app.runtime.migrations.generation import (
    EmbeddedGenerationController,
    EmbeddedUpgradeLock,
)
from app.runtime.migrations.ladybug_projection import (
    LadybugProjectionUpgradeCoordinator,
    LadybugProjectionUpgradeError,
    LadybugProjectionUpgradeResult,
)
from app.runtime.migrations.ladybug_versions.registry import (
    LadybugVersionContractError,
)
from app.runtime.migrations.ladybug_versions.rebuild import LadybugRebuildError


@dataclass(frozen=True)
class EmbeddedDataUpgradeResult:
    canonical: SqliteCanonicalUpgradeResult
    graph: LadybugProjectionUpgradeResult


class EmbeddedDataUpgradeCoordinator:
    """Upgrade SQLite, then validate/rebuild the derived graph projection."""

    def __init__(
        self,
        data_paths: RuntimeDataPathPort,
        *,
        fallback_generation: str,
    ) -> None:
        self._data_paths = data_paths
        self._paths = data_paths.resolve()
        self._fallback_generation = fallback_generation

    def upgrade(self) -> EmbeddedDataUpgradeResult:
        secret_before = _file_sha256(self._paths.secrets / "app-secret")
        media_before = _tree_fingerprint(self._paths.media)
        with EmbeddedUpgradeLock(
            self._paths.runtime / "embedded-data-migration.lock"
        ):
            canonical = SqliteCanonicalUpgradeCoordinator(
                self._data_paths,
                fallback_generation=self._fallback_generation,
            ).upgrade()
            engine = create_database_engine(
                "sqlite+pysqlite:///" + canonical.database_path.resolve().as_posix()
            )
            session_factory = create_session_factory(engine)
            try:
                graph = LadybugProjectionUpgradeCoordinator(
                    self._data_paths,
                    session_factory=session_factory,
                ).upgrade()
            except (
                LadybugProjectionError,
                LadybugProjectionUpgradeError,
                LadybugRebuildError,
                LadybugVersionContractError,
            ) as exc:
                controller = EmbeddedGenerationController(
                    self._paths.graph,
                    artifact_relative_path="relationships.lbdb",
                )
                try:
                    relative = controller.selected_relative_path("ladybug")
                except Exception:
                    relative = "ladybug"
                graph = LadybugProjectionUpgradeResult(
                    database_root=(self._paths.graph / relative).resolve(),
                    source_version=None,
                    target_version=LADYBUG_PROJECTION_SCHEMA_VERSION,
                    rebuilt=False,
                    degraded=True,
                    manifest_sha256="0" * 64,
                    error_code=_graph_error_code(exc),
                )
            finally:
                engine.dispose()
        if _file_sha256(self._paths.secrets / "app-secret") != secret_before:
            raise RuntimeError("embedded_upgrade_secret_changed")
        if _tree_fingerprint(self._paths.media) != media_before:
            raise RuntimeError("embedded_upgrade_media_changed")
        return EmbeddedDataUpgradeResult(canonical=canonical, graph=graph)


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return "missing"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_fingerprint(root: Path) -> str:
    if not root.exists():
        return "missing"
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("embedded_upgrade_symbolic_link_refused")
        if not path.is_file():
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _graph_error_code(error: Exception) -> str:
    value = str(error).strip()
    if value and all(
        character.isalnum() or character in "._:-" for character in value
    ):
        return value[:120]
    return "ladybug_upgrade_failed"


__all__ = ["EmbeddedDataUpgradeCoordinator", "EmbeddedDataUpgradeResult"]
