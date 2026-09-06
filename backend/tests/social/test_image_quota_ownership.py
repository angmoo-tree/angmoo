from datetime import UTC, date, datetime

import pytest
from sqlalchemy import event
from sqlalchemy.orm import object_session

from app.domains.social.exceptions import ServiceImageQuotaError
from app.domains.social.repository.media import count_service_image_quota_used
from app.domains.social.service import image_quota
from social.test_l4_social_write_uow import _session_factory


def test_image_quota_keeps_day_window_commit_and_release_accounting(monkeypatch, tmp_path):
    factory = _session_factory(tmp_path)
    monkeypatch.setattr(image_quota.settings, "POLLINATIONS_SERVICE_FREE_IMAGES_PER_USER_DAY", 1)
    monkeypatch.setattr(image_quota.settings, "POLLINATIONS_SERVICE_MAX_IMAGES_PER_DAY", 0)
    at = datetime(2026, 9, 5, 15, 0, tzinfo=UTC)
    assert image_quota._service_quota_date(at) == date(2026, 9, 6)
    assert image_quota._daily_image_window(at) == (
        at, datetime(2026, 9, 6, 15, 0, tzinfo=UTC),
    )
    assert image_quota._daily_image_window(at.replace(tzinfo=None)) == image_quota._daily_image_window(at)
    with factory() as db:
        commits = []
        event.listen(db, "before_commit", lambda *_: commits.append("commit"))
        first = image_quota._reserve_service_image_quota(
            db, user_id="social-uow-owner", character_id="social-uow-autonomous-character",
            source="resident", at=at,
        )
        assert object_session(first) is db
        assert first.status == "reserved" and first.quota_date == date(2026, 9, 6)
        assert commits == ["commit"]
        with pytest.raises(ServiceImageQuotaError, match="free_quota_exceeded"):
            image_quota._reserve_service_image_quota(
                db, user_id="social-uow-owner", character_id="social-uow-owner-character",
                source="local_api", at=at,
            )
        assert commits == ["commit"]
        image_quota._finalize_service_image_quota(db, first, status="released")
        assert commits == ["commit", "commit"]
        assert count_service_image_quota_used(db, user_id="social-uow-owner", quota_date=first.quota_date) == 0
        second = image_quota._reserve_service_image_quota(
            db, user_id="social-uow-owner", character_id="social-uow-autonomous-character",
            source="resident", at=at,
        )
        image_quota._finalize_service_image_quota(db, second, status="attached")
        assert count_service_image_quota_used(db, user_id="social-uow-owner", quota_date=first.quota_date) == 1
        assert commits == ["commit"] * 4
