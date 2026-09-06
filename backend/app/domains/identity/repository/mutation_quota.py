"""Identity-owned quota rows; preserve locking and nested-insert semantics."""
from datetime import datetime, timedelta

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.identity.models import CommunityMutationQuotaBucket


def ensure_bucket(
    db: Session,
    *,
    scope: str,
    subject_hash: str,
    now: datetime,
) -> None:
    identity = {"scope": scope, "subject_hash": subject_hash}
    if db.get(CommunityMutationQuotaBucket, identity) is not None:
        return
    try:
        with db.begin_nested():
            db.add(
                CommunityMutationQuotaBucket(
                    scope=scope,
                    subject_hash=subject_hash,
                    window_started_at=now,
                    used_count=0,
                    updated_at=now,
                )
            )
            db.flush()
    except IntegrityError:
        pass


def lock_buckets(
    db: Session,
    *,
    policies: tuple[tuple[str, timedelta, int], ...],
    subject_hash: str,
) -> list[CommunityMutationQuotaBucket]:
    return list(
        db.scalars(
            select(CommunityMutationQuotaBucket)
            .where(
                tuple_(
                    CommunityMutationQuotaBucket.scope,
                    CommunityMutationQuotaBucket.subject_hash,
                ).in_(
                    [(scope, subject_hash) for scope, _window, _limit in policies]
                )
            )
            .order_by(CommunityMutationQuotaBucket.scope.asc())
            .with_for_update()
        )
    )
