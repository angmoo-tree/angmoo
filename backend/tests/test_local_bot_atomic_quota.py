from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app import schemas
from app.services import local_bot
from app.services import local_bot_quota


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.LocalBotActionQuotaBucket.__table__.create(engine)
    models.LocalBotReadQuotaBucket.__table__.create(engine)
    return Session(engine)


def test_action_quota_resets_daily_count_and_keeps_cooldown() -> None:
    db = _session()
    now = datetime(2026, 7, 26, 3, 0, tzinfo=UTC)

    quota = local_bot_quota.lock_action_quota(
        db,
        character_id="char-quota",
        labels=("post",),
        now=now,
    )
    quota.ensure_allowed(
        "post",
        cooldown=timedelta(minutes=30),
        max_per_day=1,
        message="post limited",
    )
    quota.consume(("post",))
    db.commit()

    row = db.scalar(
        select(models.LocalBotActionQuotaBucket).where(
            models.LocalBotActionQuotaBucket.character_id == "char-quota",
            models.LocalBotActionQuotaBucket.action_label == "post",
        )
    )
    assert row is not None
    assert row.used_count == 1

    next_day = now + timedelta(days=1)
    quota = local_bot_quota.lock_action_quota(
        db,
        character_id="char-quota",
        labels=("post",),
        now=next_day,
    )
    quota.ensure_allowed(
        "post",
        cooldown=timedelta(minutes=30),
        max_per_day=1,
        message="post limited",
    )
    assert quota.rows["post"].used_count == 0


def test_action_quota_rejects_daily_limit_without_consuming_more() -> None:
    db = _session()
    now = datetime(2026, 7, 26, 3, 0, tzinfo=UTC)
    quota = local_bot_quota.lock_action_quota(
        db,
        character_id="char-quota",
        labels=("reply",),
        now=now,
    )
    quota.ensure_allowed(
        "reply",
        cooldown=timedelta(minutes=2),
        max_per_day=1,
        message="reply limited",
    )
    quota.consume(("reply",))
    db.commit()

    quota = local_bot_quota.lock_action_quota(
        db,
        character_id="char-quota",
        labels=("reply",),
        now=now + timedelta(minutes=3),
    )
    with pytest.raises(local_bot_quota.QuotaExceeded) as exc:
        quota.ensure_allowed(
            "reply",
            cooldown=timedelta(minutes=2),
            max_per_day=1,
            message="reply limited",
        )
    assert exc.value.label == "reply"
    assert quota.rows["reply"].used_count == 1


def test_reaction_daily_bucket_and_action_cooldown_are_independent() -> None:
    db = _session()
    now = datetime(2026, 7, 26, 3, 0, tzinfo=UTC)
    quota = local_bot_quota.lock_action_quota(
        db,
        character_id="char-reaction",
        labels=("reaction", "like"),
        now=now,
    )
    quota.ensure_allowed(
        "reaction",
        cooldown=timedelta(0),
        max_per_day=1,
        message="reaction limited",
    )
    quota.ensure_allowed(
        "like",
        cooldown=timedelta(seconds=30),
        max_per_day=None,
        message="like limited",
    )
    quota.consume(("reaction", "like"))
    db.commit()

    quota = local_bot_quota.lock_action_quota(
        db,
        character_id="char-reaction",
        labels=("reaction", "repost"),
        now=now + timedelta(seconds=31),
    )
    with pytest.raises(local_bot_quota.QuotaExceeded) as exc:
        quota.ensure_allowed(
            "reaction",
            cooldown=timedelta(0),
            max_per_day=1,
            message="reaction limited",
        )
    assert exc.value.label == "reaction"
    assert quota.rows["reaction"].used_count == 1
    assert quota.rows["repost"].used_count == 0


def test_state_quota_keeps_cooldown_without_daily_count() -> None:
    db = _session()
    now = datetime(2026, 7, 26, 3, 0, tzinfo=UTC)
    quota = local_bot_quota.lock_action_quota(
        db,
        character_id="char-state",
        labels=("state",),
        now=now,
    )
    quota.ensure_allowed(
        "state",
        cooldown=timedelta(seconds=30),
        max_per_day=None,
        message="state limited",
    )
    quota.consume(("state",))
    db.commit()

    quota = local_bot_quota.lock_action_quota(
        db,
        character_id="char-state",
        labels=("state",),
        now=now + timedelta(seconds=10),
    )
    with pytest.raises(local_bot_quota.QuotaExceeded):
        quota.ensure_allowed(
            "state",
            cooldown=timedelta(seconds=30),
            max_per_day=None,
            message="state limited",
        )
    assert quota.rows["state"].quota_date is None
    assert quota.rows["state"].used_count == 0


def test_read_quota_is_database_backed_and_windowed() -> None:
    db = _session()
    engine = db.get_bind()
    now = datetime(2026, 7, 26, 3, 0, tzinfo=UTC)

    for _ in range(2):
        local_bot_quota.consume_read(
            db,
            local_key_id="key-quota",
            now=now,
            limit=2,
            window=timedelta(minutes=1),
        )

    db.close()
    db = Session(engine)
    with pytest.raises(local_bot_quota.QuotaExceeded) as exc:
        local_bot_quota.consume_read(
            db,
            local_key_id="key-quota",
            now=now,
            limit=2,
            window=timedelta(minutes=1),
        )
    assert exc.value.retry_after_seconds == 60

    local_bot_quota.consume_read(
        db,
        local_key_id="key-quota",
        now=now + timedelta(minutes=1),
        limit=2,
        window=timedelta(minutes=1),
    )
    row = db.get(models.LocalBotReadQuotaBucket, "key-quota")
    assert row is not None
    assert row.used_count == 1


class _FakeTransactionDb:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _FakeQuota:
    def __init__(self) -> None:
        self.consumed: list[tuple[str, ...]] = []

    def consume(self, labels: tuple[str, ...]) -> None:
        self.consumed.append(labels)


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        user=SimpleNamespace(id="user-quota"),
        character=SimpleNamespace(id="char-quota"),
        local_key=SimpleNamespace(id="key-quota", token_prefix="angmoo_local_test"),
    )


def test_failed_domain_write_rolls_back_without_consuming_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeTransactionDb()
    quota = _FakeQuota()
    monkeypatch.setattr(local_bot, "_ensure_post_rate_limit", lambda *_args: quota)
    monkeypatch.setattr(
        local_bot.community_service,
        "create_post",
        lambda *_args, **_kwargs: SimpleNamespace(
            id="post-quota",
            title="title",
            body="body",
        ),
    )

    def fail_activity(*_args, **_kwargs):
        raise RuntimeError("activity write failed")

    monkeypatch.setattr(local_bot.agent_crud, "log_activity", fail_activity)

    with pytest.raises(RuntimeError, match="activity write failed"):
        local_bot.create_post(
            db,
            _context(),
            schemas.BotPostCreate(title="title", body="body"),
        )

    assert quota.consumed == []
    assert db.commits == 0
    assert db.rollbacks == 1


def test_noop_like_commits_without_consuming_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeTransactionDb()
    quota = _FakeQuota()
    marker = object()
    monkeypatch.setattr(
        local_bot,
        "_ensure_reaction_rate_limit",
        lambda *_args, **_kwargs: quota,
    )
    monkeypatch.setattr(local_bot, "_post_like_exists", lambda *_args: True)
    monkeypatch.setattr(
        local_bot.community_service,
        "like_post",
        lambda *_args, **_kwargs: marker,
    )
    monkeypatch.setattr(local_bot, "_bot_post_detail", lambda value: value)

    assert local_bot.like_post(db, _context(), "post-quota") is marker
    assert quota.consumed == []
    assert db.commits == 1
    assert db.rollbacks == 0
