"""Runtime-owned schema and scheduler canonical reads in the caller Session."""

from __future__ import annotations
from datetime import datetime
from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.domains.runtime.constants import SCHEDULER_SINGLETON_KEY


def migration_revision(db: Session, revision_query: str) -> Any:
    return db.execute(text(revision_query)).scalar()


def scheduler_state(db: Session) -> Any:
    return (
        db.execute(
            text(
                """
                SELECT lease_owner_id, fencing_epoch, state, heartbeat_at,
                       lease_expires_at, next_tick_at, last_error_code
                FROM runtime_scheduler_leases
                WHERE singleton_key = :singleton_key
                """
            ),
            {"singleton_key": SCHEDULER_SINGLETON_KEY},
        )
        .mappings()
        .first()
    )
