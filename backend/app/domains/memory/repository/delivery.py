"""Persist source admission and consent epochs in the caller's transaction.

The existing SQLAlchemy connection and its commit/rollback owner are retained;
runtime dispatch supplies source identity from successful SNS/Chat changes.
"""
from datetime import datetime
from uuid import uuid4
from sqlalchemy import insert, select, update

from app.domains.memory.models.batch import MemoryActivationEpoch, MemorySourceDelivery
from app.domains.memory.models.items import MemoryScopeSettingModel


def sync_epoch(connection, setting_id: str, *, now: datetime) -> None:
    settings, epochs = (
        MemoryScopeSettingModel.__table__,
        MemoryActivationEpoch.__table__,
    )
    setting = (
        connection.execute(select(settings).where(settings.c.id == setting_id))
        .mappings()
        .one_or_none()
    )
    if setting is None:
        return
    connection.execute(
        update(epochs)
        .where(
            epochs.c.scope_setting_id == setting_id,
            epochs.c.closed_at.is_(None),
            epochs.c.scope_version != setting["version"],
        )
        .values(closed_at=now)
    )
    if (
        setting["enabled"]
        and connection.execute(
            select(epochs.c.id).where(
                epochs.c.scope_setting_id == setting_id,
                epochs.c.scope_version == setting["version"],
            )
        ).first()
        is None
    ):
        connection.execute(
            insert(epochs).values(
                id=str(uuid4()),
                scope_setting_id=setting_id,
                scope_version=setting["version"],
                opened_at=now,
            )
        )



def capture_delivery(connection, *, world_id, subjects, source_type, source_id, now):
    if not world_id or not source_id or not subjects:
        return
    settings, epochs, deliveries = (
        MemoryScopeSettingModel.__table__,
        MemoryActivationEpoch.__table__,
        MemorySourceDelivery.__table__,
    )
    scopes = (
        connection.execute(
            select(settings).where(
                settings.c.world_id == world_id,
                settings.c.subject_world_character_id.in_(subjects),
                settings.c.enabled.is_(True),
            )
        )
        .mappings()
        .all()
    )
    for scope in scopes:
        if connection.execute(
            select(deliveries.c.sequence).where(
                deliveries.c.scope_setting_id == scope["id"],
                deliveries.c.source_type == source_type,
                deliveries.c.source_id == str(source_id),
            )
        ).first():
            continue
        sync_epoch(connection, scope["id"], now=now)
        epoch = connection.execute(
            select(epochs.c.id).where(
                epochs.c.scope_setting_id == scope["id"],
                epochs.c.closed_at.is_(None),
                epochs.c.scope_version == scope["version"],
            )
        ).scalar_one()
        connection.execute(
            insert(deliveries).values(
                scope_setting_id=scope["id"],
                epoch_id=epoch,
                source_type=source_type,
                source_id=str(source_id),
                state="pending",
                captured_at=now,
            )
        )

