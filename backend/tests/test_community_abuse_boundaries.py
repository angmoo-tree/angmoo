from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models, schemas
from app.services import community as community_service
from app.services import community_abuse_quota


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.User.__table__.create(engine)
    models.Character.__table__.create(engine)
    models.Post.__table__.create(engine)
    models.Comment.__table__.create(engine)
    models.PostReport.__table__.create(engine)
    models.CommunityMutationQuotaBucket.__table__.create(engine)
    return engine


def _user(user_id: str) -> models.User:
    return models.User(
        id=user_id,
        email=f"{user_id}@example.invalid",
        display_name=user_id,
        display_name_normalized=user_id,
        profile_setup_completed=True,
        feed_content_filter="all",
    )


def test_reply_and_report_quotas_persist_only_hashed_subjects() -> None:
    engine = _engine()
    now = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)
    with Session(engine) as db:
        for _ in range(10):
            community_abuse_quota.consume(
                db,
                user_id="quota-user",
                action="reply",
                now=now,
            )
            db.commit()
        with pytest.raises(community_abuse_quota.CommunityQuotaExceeded):
            community_abuse_quota.consume(
                db,
                user_id="quota-user",
                action="reply",
                now=now,
            )

        rows = list(db.scalars(select(models.CommunityMutationQuotaBucket)))
        assert {row.scope for row in rows} == {"reply_minute", "reply_day"}
        assert all("quota-user" not in row.subject_hash for row in rows)


def test_three_reports_do_not_automatically_hide_post() -> None:
    engine = _engine()
    with Session(engine) as db:
        author = _user("report-author")
        reporters = [_user(f"reporter-{index}") for index in range(3)]
        post = models.Post(
            id="post-report-boundary",
            author_user_id=author.id,
            author_name=author.display_name,
            title="report target",
            body="synthetic",
            post_type="text",
        )
        db.add_all([author, *reporters, post])
        db.commit()

        for reporter in reporters:
            result = community_service.report_post(
                db,
                reporter,
                post.id,
                schemas.PostReportCreate(reason="spam"),
            )
            assert result.report_hidden is False

        db.refresh(post)
        assert post.report_count == 3
        assert post.report_hidden_at is None


def test_saved_character_count_is_not_a_community_abuse_quota() -> None:
    from app.services import agents

    assert not hasattr(agents, "_lock_agent_quota")
    assert not hasattr(agents, "_ensure_agent_quota_available")
