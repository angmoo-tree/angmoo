from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.service import activity_policy, activity_settings
from routines.test_activity_persistence import _file_engine
from routine_posts.test_runtime import _seed


@pytest.mark.parametrize("existing_setting", (False, True))
def test_policy_timezone_reader_preserves_setting_commit_and_caller_transaction(
    tmp_path, existing_setting,
):
    engine = _file_engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        character_id = fixture.character.id
        if existing_setting:
            setting = activity_settings.ensure_setting(db, character_id)
            setting.allow_post = False
        seen = []

        @event.listens_for(db, "after_commit")
        def committed(_session):
            seen.append("commit")

        def timezone_reader(session, *, character_id):
            assert session is db
            assert character_id == fixture.character.id
            current = activity_settings.get_setting(session, character_id)
            assert current is not None
            assert current.allow_post is (not existing_setting)
            seen.append("timezone")
            with Session(engine) as observer:
                stored = activity_settings.get_setting(observer, character_id)
                assert stored is not None
                assert stored.allow_post is True
            return ZoneInfo("UTC")

        result = activity_policy.build_activity_policy(
            db, character_id=character_id,
            now=datetime(2026, 9, 6, 16, tzinfo=UTC),
            timezone_reader=timezone_reader,
        )
        assert seen == (["timezone"] if existing_setting else ["commit", "timezone"])
        assert result.within_active_hours is True
        assert ("post" in result.allowed_actions) is (not existing_setting)
        if existing_setting:
            assert result.blocked_reasons["post"] == "new post writing is disabled"
        db.rollback()
        assert activity_settings.get_setting(db, character_id).allow_post is True
    engine.dispose()


def test_unknown_action_and_non_policy_run_do_not_read_world_scope(tmp_path):
    engine = _file_engine(tmp_path)
    seen = []

    def unexpected_timezone(_db, *, character_id):
        seen.append(character_id)
        raise AssertionError("scope must not be read before these original guards")

    with Session(engine) as db:
        with pytest.raises(KeyError, match="unsupported-action"):
            activity_policy.count_action_today(
                db, character_id="missing-character", action="unsupported-action",
                timezone_reader=unexpected_timezone,
            )
        activity_policy.assert_action_allowed(
            db, run=models.AgentRun(session_key="ordinary-session"),
            action="unsupported-action", timezone_reader=unexpected_timezone,
        )
        assert seen == []
        assert db.in_transaction() is False
    engine.dispose()
