from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.services import lore_parser_quota


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.LoreParserLease.__table__.create(engine)
    return engine


def test_parser_lease_enforces_per_user_and_global_limits() -> None:
    engine = _engine()
    with (
        Session(engine) as first_db,
        Session(engine) as second_db,
        Session(engine) as rejected_db,
    ):
        with lore_parser_quota.parser_lease(first_db, user_id="user-1"):
            with pytest.raises(lore_parser_quota.LoreParserCapacityError):
                with lore_parser_quota.parser_lease(
                    rejected_db,
                    user_id="user-1",
                ):
                    pass
            with lore_parser_quota.parser_lease(second_db, user_id="user-2"):
                with pytest.raises(lore_parser_quota.LoreParserCapacityError):
                    with lore_parser_quota.parser_lease(
                        rejected_db,
                        user_id="user-3",
                    ):
                        pass


def test_parser_lease_recovers_stale_rows_and_stores_only_hashes() -> None:
    engine = _engine()
    now = datetime(2026, 7, 26, 9, 0, tzinfo=UTC)
    with Session(engine) as db:
        db.add(
            models.LoreParserLease(
                id="stale-lease",
                subject_hash="synthetic-stale-hash",
                created_at=now - timedelta(minutes=1),
                lease_expires_at=now - timedelta(seconds=1),
            )
        )
        db.commit()

        with lore_parser_quota.parser_lease(
            db,
            user_id="fresh-user",
            now=now,
        ) as lease_id:
            active = db.get(models.LoreParserLease, lease_id)
            assert active is not None
            assert "fresh-user" not in active.subject_hash

        released = db.get(models.LoreParserLease, lease_id)
        assert released is not None
        assert released.released_at is not None
        assert len(list(db.scalars(select(models.LoreParserLease)))) == 2
