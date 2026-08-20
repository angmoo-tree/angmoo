"""Framework-neutral ports implemented by local-runtime adapters."""

from app.domains.runtime.ports.application_runtime_probe import (
    ApplicationRuntimeProbe,
)
from app.domains.runtime.ports.migration_source import (
    MigrationRevision,
    MigrationSourcePort,
)
from app.domains.runtime.ports.offline_migration import (
    OfflineCanonicalMigrationPort,
    OfflineMigrationManifest,
    OfflineMigrationReport,
    OfflineMigrationTableParity,
)
from app.domains.runtime.ports.runtime_data_path import (
    RuntimeDataPathPort,
    RuntimeDataPaths,
)
from app.domains.runtime.ports.scheduler_lease_repository import (
    ClaimLeasePort,
    SchedulerLeaseRepository,
)
from app.domains.runtime.ports.search_index import (
    SearchIndexDocument,
    SearchIndexHit,
    SearchIndexPort,
)
from app.domains.runtime.ports.unit_of_work import UnitOfWorkPort

__all__ = [
    "ApplicationRuntimeProbe",
    "ClaimLeasePort",
    "MigrationRevision",
    "MigrationSourcePort",
    "OfflineCanonicalMigrationPort",
    "OfflineMigrationManifest",
    "OfflineMigrationReport",
    "OfflineMigrationTableParity",
    "RuntimeDataPathPort",
    "RuntimeDataPaths",
    "SchedulerLeaseRepository",
    "SearchIndexDocument",
    "SearchIndexHit",
    "SearchIndexPort",
    "UnitOfWorkPort",
]
