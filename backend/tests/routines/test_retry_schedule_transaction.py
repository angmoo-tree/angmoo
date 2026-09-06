from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.routines.service import activity_settings, retry_schedule
from routine_posts.test_runtime import _seed
from social.test_resident_context_queries import _engine


def test_retry_schedule_preserves_early_returns_and_caller_pending_setting(tmp_path):
    now = datetime(2026, 9, 6, 5, tzinfo=UTC)
    manual = now + timedelta(minutes=4)

    def unexpected_timezone(*_args, **_kwargs):
        raise AssertionError("An early-return retry must not resolve timezone")

    assert retry_schedule._scheduled_retry_next_tick_at(
        None, setting=None, character_id="actor", retry_at=now,
        manual_next_tick_at=manual, timezone_reader=unexpected_timezone,
    ) is manual
    assert retry_schedule._scheduled_retry_next_tick_at(
        None, setting=None, character_id="", retry_at=now,
        manual_next_tick_at=None, timezone_reader=unexpected_timezone,
    ) is now
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        actor = fixture.character.id
        original_name = fixture.character.name
        setting = activity_settings.ensure_setting(db, actor)
        setting.activity_interval_minutes = 19
        fixture.character.name = "pending-retry-owner"
        seen = []

        def timezone_reader(session, *, character_id):
            seen.append((session, character_id, setting.activity_interval_minutes))
            return ZoneInfo("UTC")

        result = retry_schedule._scheduled_retry_next_tick_at(
            db, setting=setting, character_id=actor, retry_at=now,
            manual_next_tick_at=None, timezone_reader=timezone_reader,
        )
        assert seen == [(db, actor, 19)]
        assert result.tzinfo is not None
        with Session(engine) as observer:
            assert observer.get(Character, actor).name == original_name
        db.rollback()
        assert fixture.character.name == original_name
    engine.dispose()


def test_retry_missing_setting_keeps_original_ensure_commit_before_timezone(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        actor = fixture.character.id
        assert activity_settings.get_setting(db, actor) is None
        fixture.character.name = "original-ensure-commit"
        observations = []

        def timezone_reader(session, *, character_id):
            assert session is db
            with Session(engine) as observer:
                observations.append(observer.get(Character, actor).name)
                assert activity_settings.get_setting(observer, character_id) is not None
            return ZoneInfo("UTC")

        retry_schedule._scheduled_retry_next_tick_at(
            db, setting=None, character_id=actor,
            retry_at=datetime(2026, 9, 6, 5, tzinfo=UTC),
            manual_next_tick_at=None, timezone_reader=timezone_reader,
        )
        assert observations == ["original-ensure-commit"]
        db.rollback()
        assert fixture.character.name == "original-ensure-commit"
    engine.dispose()
