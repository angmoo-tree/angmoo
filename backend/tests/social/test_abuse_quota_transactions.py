"""Quota owner separation preserves the transaction and public retry interval."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.domains.identity.models import CommunityMutationQuotaBucket
from app.domains.social.exceptions import CommunityQuotaExceeded
from app.domains.social.service import abuse_quota
from app.runtime.persistence.model_registration import register_models


def test_quota_writes_remain_uncommitted_and_rejection_rolls_back_window_reset():
    register_models()
    engine = create_engine("sqlite://")
    CommunityMutationQuotaBucket.__table__.create(engine)
    now = datetime(2026, 9, 6, tzinfo=UTC)
    try:
        with Session(engine) as db:
            abuse_quota.consume(db, user_id="synthetic-subject", action="reply", now=now)
            db.commit()
            rows = {row.scope: row for row in db.scalars(select(CommunityMutationQuotaBucket))}
            abuse_quota.consume(db, user_id="synthetic-subject", action="reply", now=now)
            assert all(row.used_count == 2 for row in rows.values())
            assert all(row in db for row in rows.values())
            db.rollback()
            assert all(row.used_count == 1 for row in rows.values())

            rows["reply_minute"].used_count = 10
            rows["reply_day"].used_count = 100
            db.commit()
            with pytest.raises(CommunityQuotaExceeded) as error:
                abuse_quota.consume(
                    db, user_id="synthetic-subject", action="reply", now=now + timedelta(seconds=61)
                )
            assert error.value.retry_after_seconds == 86_339
            assert rows["reply_minute"].used_count == 10
            assert rows["reply_day"].used_count == 100
            assert rows["reply_minute"].window_started_at.replace(tzinfo=UTC) == now
    finally:
        engine.dispose()


def test_unknown_quota_action_rejects_before_touching_session():
    class UntouchedSession:
        def __getattr__(self, name):
            raise AssertionError(f"Unexpected session access: {name}")

    with pytest.raises(ValueError, match="Unsupported community quota action"):
        abuse_quota.consume(UntouchedSession(), user_id="synthetic-subject", action="unknown")
