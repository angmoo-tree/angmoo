"""Persist ON admission intervals in the same transaction as scope changes."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update

from app.domains.memory.infrastructure.batch_models import MemoryActivationEpoch


def record_activation(session, setting) -> None:
    now = datetime.now(UTC)
    session.execute(
        update(MemoryActivationEpoch)
        .where(
            MemoryActivationEpoch.scope_setting_id == setting.id,
            MemoryActivationEpoch.closed_at.is_(None),
            MemoryActivationEpoch.scope_version != setting.version,
        )
        .values(closed_at=now)
    )
    if (
        setting.enabled
        and session.scalar(
            select(MemoryActivationEpoch.id).where(
                MemoryActivationEpoch.scope_setting_id == setting.id,
                MemoryActivationEpoch.scope_version == setting.version,
            )
        )
        is None
    ):
        session.add(
            MemoryActivationEpoch(
                id=str(uuid4()),
                scope_setting_id=setting.id,
                scope_version=setting.version,
                opened_at=now,
            )
        )
    session.flush()
