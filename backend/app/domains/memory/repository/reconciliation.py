"""Recover durable Memory deliveries in the caller's transaction.

The bounded epoch scans and anti-join SQL are the original recovery queries.
Only the service commits, after all selected scopes have been scanned.
"""

from sqlalchemy import exists, insert, select
from app.domains.memory.models.batch import MemoryActivationEpoch, MemorySourceDelivery
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.repository.delivery import sync_epoch


def open_missing_epochs(session, *, now):
    epochs = MemoryActivationEpoch.__table__
    missing_epoch = ~exists(
        select(epochs.c.id).where(
            epochs.c.scope_setting_id == MemoryScopeSettingModel.id,
            epochs.c.scope_version == MemoryScopeSettingModel.version,
        )
    )
    for setting in session.scalars(
        select(MemoryScopeSettingModel)
        .where(MemoryScopeSettingModel.enabled.is_(True), missing_epoch)
        .limit(32)
    ):
        sync_epoch(session.connection(), setting.id, now=now)


def scan_enabled_epochs(session):
    return session.scalars(
        select(MemoryActivationEpoch)
        .join(
            MemoryScopeSettingModel,
            MemoryScopeSettingModel.id == MemoryActivationEpoch.scope_setting_id,
        )
        .where(MemoryScopeSettingModel.enabled.is_(True))
        .order_by(
            MemoryActivationEpoch.last_scanned_at.asc().nullsfirst(),
            MemoryActivationEpoch.id,
        )
        .limit(16)
    ).all()


def get_epoch_setting(session, epoch):
    return session.get(MemoryScopeSettingModel, epoch.scope_setting_id)


def recover_catalog(session, *, setting, epoch, catalog):
    source, captured, identity, kinds, predicates, content = catalog
    delivery = MemorySourceDelivery.__table__
    missing = ~exists(
        select(delivery.c.sequence).where(
            delivery.c.scope_setting_id == setting.id,
            delivery.c.source_type.in_(kinds),
            delivery.c.source_id == identity.cast(delivery.c.source_id.type),
        )
    )
    predicates += [captured >= epoch.opened_at, missing]
    if epoch.closed_at is not None:
        predicates.append(captured < epoch.closed_at)
    rows = (
        session.execute(
            select(content, captured.label("admitted_at"))
            .select_from(source)
            .where(*predicates)
            .order_by(captured, identity)
            .limit(32)
        )
        .mappings()
        .all()
    )
    for row in rows:
        kind = (
            ("REPLY" if row["reply_to_post_id"] else "POST")
            if kinds == ("POST", "REPLY")
            else kinds[0]
        )
        # Invalid sources also receive terminal entries via revalidation.
        if (
            session.scalar(
                select(delivery.c.sequence).where(
                    delivery.c.scope_setting_id == setting.id,
                    delivery.c.source_type == kind,
                    delivery.c.source_id == str(row["id"]),
                )
            )
            is None
        ):
            session.execute(
                insert(delivery).values(
                    scope_setting_id=setting.id,
                    epoch_id=epoch.id,
                    source_type=kind,
                    source_id=str(row["id"]),
                    state="pending",
                    captured_at=row["admitted_at"],
                )
            )
