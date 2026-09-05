"""Repair missed Memory deliveries only inside recorded consent epochs."""

from datetime import datetime
from app.domains.memory.contracts.batch_preparation import MemoryPreparationDependencies
from app.domains.memory.repository import reconciliation as repository


def reconcile_sources(
    session, *, dependencies: MemoryPreparationDependencies, now: datetime
) -> None:
    """Per-source anti-join retains holes; persisted scan order rotates scopes.

    Only source timestamps inside a recorded ON epoch are recoverable. The
    transactional normal path uses commit-time admission, not display time.
    Upgrade opens an epoch now, never retroactively assumes old consent.
    """
    repository.open_missing_epochs(session, now=now)
    scanned = repository.scan_enabled_epochs(session)
    source_catalogs = dependencies.source_catalog_factory()
    for epoch in scanned:
        setting = repository.get_epoch_setting(session, epoch)
        subject = setting.subject_world_character_id
        catalogs = source_catalogs(setting, subject)
        for catalog in catalogs:
            repository.recover_catalog(
                session, setting=setting, epoch=epoch, catalog=catalog
            )
        epoch.last_scanned_at = now
    session.commit()
