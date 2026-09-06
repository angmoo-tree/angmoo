"""Exercise runtime-to-policy budget binding on one caller-owned Session."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, literal, select
from sqlalchemy.orm import Session

from app.runtime.resident import langgraph as resident


@pytest.mark.parametrize("reply_limit", [None, 5])
def test_action_budget_binding_keeps_session_timestamp_and_read_order(
    monkeypatch, reply_limit
):
    engine = create_engine("sqlite://")
    with Session(engine) as db:
        now = datetime(2026, 9, 6, 5, 0, tzinfo=UTC)
        ctx = SimpleNamespace(
            db=db,
            character=SimpleNamespace(id="budget-character"),
            run_started_at=now,
            activity_policy=SimpleNamespace(allowed_actions=("reply", "post")),
        )
        setting = SimpleNamespace(
            allow_reply=True,
            allow_post=True,
            max_comments_per_day=reply_limit,
            max_posts_per_day=3,
        )
        calls = []
        commits = []
        event.listen(db, "after_commit", lambda session: commits.append(session))

        def ensure_setting(actual_db, character_id):
            assert actual_db is db
            assert character_id == "budget-character"
            calls.append("setting")
            return setting

        def count_today(actual_db, *, character_id, action, now):
            assert actual_db is db
            assert character_id == "budget-character"
            assert now is ctx.run_started_at
            calls.append(action)
            return actual_db.scalar(select(literal(2)))

        monkeypatch.setattr(
            resident.activity_settings, "ensure_setting", ensure_setting
        )
        monkeypatch.setattr(
            resident.agent_activity_policy, "count_action_today", count_today
        )
        budget = resident._daily_action_budgets(ctx)
        assert calls == (
            ["setting", "post"] if reply_limit is None else ["setting", "reply", "post"]
        )
        assert budget["reply"]["remaining_before_plan"] == (
            None if reply_limit is None else 3
        )
        assert budget["post"]["remaining_before_plan"] == 1
        assert commits == []
        assert db.in_transaction()
    engine.dispose()
