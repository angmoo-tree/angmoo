"""Install concrete multi-domain projections/UoWs at the app boundary."""
from typing import Any
from app.domains.world_packages.contracts.runtime import WorldPackageRuntimeFactories
from app.runtime.world_packages.export_source import SqlAlchemyWorldPackageSourceSnapshot
from app.runtime.world_packages.preview_probe import SqlAlchemyWorldPackagePreviewProbe
from app.runtime.world_packages.import_commit import SqlAlchemyWorldPackageImportCommitter

def configure_world_package_runtime(app: Any) -> None:
    app.state.world_package_factories = WorldPackageRuntimeFactories(
        source_snapshot=SqlAlchemyWorldPackageSourceSnapshot,
        preview_probe=SqlAlchemyWorldPackagePreviewProbe,
        import_committer=SqlAlchemyWorldPackageImportCommitter,
    )
