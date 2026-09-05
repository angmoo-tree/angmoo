"""Same-Session continuity reads and date admission through actual runtime wiring."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, literal, select
from sqlalchemy.orm import Session

from app.services import langgraph_resident as resident


def _context(db):
    return SimpleNamespace(
        db=db,
        run_id="topic-arc-run",
        character=SimpleNamespace(id="topic-character"),
        run_started_at=datetime(2026, 9, 6, 3, 0, tzinfo=UTC),
    )


def _payload(ctx):
    payload = resident._build_topic_arc_payload(
        ctx,
        draft={
            "arc_title": "기록을 이어 쓰기",
            "steps": [
                {"role": "setup", "brief": "처음 발견한 것을 기록한다"},
                {"role": "conclusion", "brief": "경험을 돌아본다"},
            ],
        },
        arc_source="independent",
        topic_key="experience",
        source_post_id=None,
    )
    assert payload is not None
    payload["last_post_id"] = "previous-post"
    return payload


def test_topic_arc_continuity_keeps_read_order_and_same_session(monkeypatch):
    engine = create_engine("sqlite://")
    with Session(engine) as db:
        ctx = _context(db)
        payload = _payload(ctx)
        calls = []
        commits = []
        event.listen(db, "after_commit", lambda session: commits.append(session))
        previous_at = ctx.run_started_at - timedelta(minutes=90)
        old_event = SimpleNamespace(provided_at=ctx.run_started_at - timedelta(days=1))

        def last_post(actual, post_id):
            assert actual is ctx
            assert actual.db is db
            assert post_id == "previous-post"
            assert actual.db.scalar(select(literal(1))) == 1
            calls.append("post")
            return previous_at

        def latest_event(actual, arc_id):
            assert actual is ctx
            assert actual.db is db
            assert arc_id == payload["arc_id"]
            assert actual.db.scalar(select(literal(2))) == 2
            calls.append("event")
            return old_event

        monkeypatch.setattr(resident, "_topic_arc_last_post_created_at", last_post)
        monkeypatch.setattr(resident, "_latest_topic_arc_event", latest_event)
        result = resident._topic_arc_recovery_decision(ctx, payload, old_event)
        assert result["continue"] is True
        assert result["reason"] == "continuity_near"
        assert calls == ["post", "event"]
        assert db.in_transaction()
        assert commits == []
    engine.dispose()


@pytest.mark.parametrize(
    ("days", "expected", "continues"),
    [
        (0, "due_today", True),
        (-1, "past_target_date", False),
        (1, "future_target_date", False),
    ],
)
def test_topic_arc_date_admission_skips_unneeded_reads(
    monkeypatch, days, expected, continues
):
    engine = create_engine("sqlite://")
    with Session(engine) as db:
        ctx = _context(db)
        payload = _payload(ctx)
        payload["steps"][0]["target_date"] = (
            resident._current_kst_date(ctx) + timedelta(days=days)
        ).isoformat()

        def unexpected_read(*args):
            raise AssertionError("date admission must finish before continuity reads")

        monkeypatch.setattr(
            resident, "_topic_arc_last_post_created_at", unexpected_read
        )
        monkeypatch.setattr(resident, "_latest_topic_arc_event", unexpected_read)
        result = resident._topic_arc_recovery_decision(ctx, payload, None)
        assert result["continue"] is continues
        assert result["reason"] == expected
        assert not db.in_transaction()
    engine.dispose()
