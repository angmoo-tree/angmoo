"""Application-supplied construction callbacks for shared-session Package work.

The opaque argument is the existing SQLAlchemy Session or its factory. This
contract neither creates a Session nor introduces a framework dependency into
portable format definitions; concrete runtime constructors annotate Session.
"""
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from app.domains.world_packages.contracts.interfaces import WorldPackageSourceSnapshotPort, WorldPackagePreviewProbePort, WorldPackageImportCommitPort

class WorldPackageRuntimeCommitter(WorldPackageImportCommitPort, Protocol):
    def recover_media(self) -> None: ...
    def list_imported_world_ids(self) -> tuple[str, ...]: ...

@dataclass(frozen=True, slots=True)
class WorldPackageRuntimeFactories:
    source_snapshot: Callable[[Any], WorldPackageSourceSnapshotPort]
    preview_probe: Callable[[Any], WorldPackagePreviewProbePort]
    import_committer: Callable[..., WorldPackageRuntimeCommitter]
