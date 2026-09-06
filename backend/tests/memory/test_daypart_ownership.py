from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from model_fixture_support import models
from app.domains.memory.contracts.daypart import DaypartObservationReferences
from app.domains.memory.models.daypart import AgentDaypartMemoryEvent
from app.domains.memory.policies import daypart as policy
from app.domains.memory.service import daypart, daypart_observations


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'daypart.db').as_posix()}")
    AgentDaypartMemoryEvent.__table__.create(engine)
    yield engine
    engine.dispose()


def _event(**changes):
    values = dict(
        character_id="char-a",
        memory_session_key="session-a",
        daypart_start_date=date(2026, 6, 24),
        activity_daypart="morning",
        event_type="observation_feed",
        summary="remembered",
        provided_at=datetime(2026, 6, 24, 0, tzinfo=UTC),
    )
    values.update(changes)
    return AgentDaypartMemoryEvent(**values)


def _context(db, **changes):
    values = dict(
        db=db,
        character=SimpleNamespace(id="char-a"),
        memory_session_key="session-a",
        daypart_start_date=date(2026, 6, 24),
        activity_daypart="afternoon",
        run_id="run-a",
        run_started_at=datetime(2026, 6, 24, 6, tzinfo=UTC),
    )
    values.update(changes)
    return SimpleNamespace(**values)


def test_daypart_writes_keep_commits_action_admission_and_original_fields(engine):
    assert models.AgentDaypartMemoryEvent is AgentDaypartMemoryEvent
    with Session(engine) as db:
        ctx = _context(db)
        daypart.record_event(
            ctx,
            event_type="observation_inbox",
            summary="a" * 2100,
            source_post_id="post-a",
            notification_id=0,
            thread_id="thread-a",
            topic_signature="topic-a",
            payload={"source": "original"},
        )
        db.rollback()
        with Session(engine) as observer:
            row = observer.scalar(select(AgentDaypartMemoryEvent))
            assert row.summary == "a" * 2000
            assert (row.character_id, row.run_id, row.source_post_id) == (
                "char-a",
                "run-a",
                "post-a",
            )
            assert (row.notification_id, row.thread_id, row.topic_signature) == (
                0,
                "thread-a",
                "topic-a",
            )
            assert row.payload == {"source": "original"}

        run = SimpleNamespace(id="run-b", character_id="char-a", gateway_result={})
        daypart.record_action_memory(db, run=run, action_memory={})
        run.gateway_result = {
            "session_context": {
                "daypart_persistent": True,
                "memory_session_key": "session-b",
                "daypart_start_date": "invalid-date",
                "activity_daypart": "night",
            }
        }
        daypart.record_action_memory(db, run=run, action_memory={})
        run.gateway_result["session_context"]["daypart_start_date"] = "2026-06-24"
        action = {
            "action_type": "post",
            "post_id": "created-post",
            "source_post": "source-post",
            "public_result_summary": "b" * 2100,
            "topic": "t" * 350,
        }
        daypart.record_action_memory(db, run=run, action_memory=action)
        db.rollback()
        with Session(engine) as observer:
            rows = list(
                observer.scalars(
                    select(AgentDaypartMemoryEvent).order_by(AgentDaypartMemoryEvent.id)
                )
            )
            assert len(rows) == 2
            assert (
                rows[1].event_type,
                rows[1].source_post_id,
                rows[1].memory_session_key,
            ) == ("action_post", "source-post", "session-b")
            assert rows[1].summary == "b" * 2000
            assert rows[1].topic_signature == "t" * 300
            assert rows[1].payload == action


def test_daypart_reads_keep_scopes_stable_order_limits_and_duplicate_ids(engine):
    with Session(engine) as db:
        # A tied timestamp still orders by identity, not insertion payload text.
        db.add_all(
            [
                _event(
                    id=i, source_post_id=f"post-{i}", notification_id=i, summary=str(i)
                )
                for i in range(1, 68)
            ]
        )
        db.add_all(
            [
                _event(id=68, character_id="other"),
                _event(id=69, memory_session_key="other"),
            ]
        )
        db.commit()
        ctx = _context(db)
        assert [row["summary"] for row in daypart.history(ctx)] == [
            str(i) for i in range(1, 65)
        ]
        assert daypart.seen_feed_post_ids(ctx) == {f"post-{i}" for i in range(1, 68)}
        assert daypart.seen_notification_ids(ctx) == set()
        assert daypart.history(_context(db, memory_session_key=None)) == []
        scope = dict(
            character_id="char-a",
            memory_session_key="session-a",
            daypart_start_date=date(2026, 6, 24),
            activity_daypart="morning",
            event_type="observation_feed",
        )
        assert daypart.event_exists(
            db, **scope, source_post_id="post-1", notification_id=1
        )
        assert not daypart.event_exists(
            db, **scope, source_post_id="post-1", notification_id=2
        )
        assert not daypart.event_exists(db, **scope)
        start = datetime(2026, 6, 24, tzinfo=UTC)
        assert [
            row.id
            for row in daypart.recent_topic_events(
                db, character_id="char-a", event_type="observation_feed", cutoff=start
            )
        ] == [69, *range(67, 48, -1)]
        assert [
            row.id
            for row in daypart.handoff_events(
                db,
                character_id="char-a",
                event_types=["observation_feed"],
                start_utc=start,
                end_utc=start + timedelta(days=1),
            )
        ] == [69, *range(67, 56, -1)]
        assert (
            daypart.handoff_events(
                db,
                character_id="char-a",
                event_types=["observation_feed"],
                start_utc=start - timedelta(days=1),
                end_utc=start,
            )
            == []
        )


def test_provided_observation_commits_before_author_failure_and_keeps_retry_admission(
    engine,
):
    with Session(engine) as db:
        args = dict(
            character_id="char-a",
            memory_session_key="session-a",
            daypart_start_date=date(2026, 6, 24),
            activity_daypart="morning",
            run_id="run-a",
        )
        inbox = [
            {
                "notification_id": "12",
                "root_summary": "inbox",
                "source_post_id": "inbox-post",
                "root_post_id": "root-a",
                "actor_name": "Seen author",
            }
        ]
        feed = {
            "interests": [{"post_id": "feed-post", "summary": "feed"}],
            "topic_signature": "topic",
        }

        def fail_author(session, post_id, missing):
            assert session is db
            assert (post_id, missing) == ("feed-post", None)
            with Session(engine) as observer:
                assert (
                    observer.scalar(select(AgentDaypartMemoryEvent)).event_type
                    == "observation_inbox"
                )
            raise RuntimeError("author read failed")

        references = DaypartObservationReferences(
            post_author=fail_author, clip_text=lambda text, limit: text[:limit]
        )
        with pytest.raises(RuntimeError, match="author read failed"):
            daypart_observations.record_provided_daypart_observations(
                db,
                **args,
                inbox_candidates=inbox,
                feed_interest_payload=feed,
                references=references,
            )
        db.rollback()
        scope = {k: v for k, v in args.items() if k != "run_id"}
        pending_inbox = daypart_observations.filter_daypart_duplicate_inbox_candidates(
            db, **scope, candidates=inbox
        )
        pending_feed = daypart_observations.filter_daypart_duplicate_feed_interest(
            db, **scope, feed_interest_payload=feed
        )
        assert pending_inbox == []
        assert pending_feed is feed
        daypart_observations.record_provided_daypart_observations(
            db,
            **args,
            inbox_candidates=pending_inbox,
            feed_interest_payload=pending_feed,
            references=DaypartObservationReferences(
                post_author=lambda *args: "Feed author", clip_text=references.clip_text
            ),
        )
        with Session(engine) as observer:
            rows = list(
                observer.scalars(
                    select(AgentDaypartMemoryEvent).order_by(AgentDaypartMemoryEvent.id)
                )
            )
            assert [(row.event_type, row.source_post_id) for row in rows] == [
                ("observation_inbox", "inbox-post"),
                ("observation_feed", "feed-post"),
            ]
            assert rows[0].thread_id == "root-a"
            assert rows[1].payload == {
                "source_item_id": "post:feed-post",
                "seen_person": "Feed author",
            }
        filtered = daypart_observations.filter_daypart_duplicate_feed_interest(
            db, **scope, feed_interest_payload=feed
        )
        assert filtered["interests"] == []
        assert filtered["warnings"] == ["daypart_memory_event_already_provided"]


def test_summary_commit_failure_rolls_back_one_group_and_continues_then_retries(engine):
    with Session(engine) as db:
        db.add_all(
            [
                _event(memory_session_key="group-a", source_post_id="post-a"),
                _event(memory_session_key="group-b", source_post_id="post-b"),
            ]
        )
        db.commit()

    class FailFirstSummaryCommit(Session):
        failed = False

        def commit(self):
            if not self.failed:
                self.failed = True
                self.flush()
                raise RuntimeError("summary commit failed")
            super().commit()

    start = policy.daypart_start_utc(
        date(2026, 6, 24), "afternoon", timezone=ZoneInfo("Asia/Seoul")
    )
    assert start == datetime(2026, 6, 24, 5, tzinfo=UTC)
    with FailFirstSummaryCommit(engine) as db:

        def finalize():
            return daypart.finalize_closed_dayparts(
                _context(db),
                current_start=start,
                result={
                    "status": "succeeded",
                    "expired_relationship_points": 2,
                    "summaries_created": 0,
                    "summaries_skipped": 0,
                },
            )

        first = finalize()
        assert first["summaries_created"] == 1
        assert first["expired_relationship_points"] == 2
        assert first["summary_errors"] == [
            {"memory_session_key": "group-a", "failure_class": "RuntimeError"}
        ]
        second = finalize()
        assert (second["summaries_created"], second["summaries_skipped"]) == (1, 1)
    with Session(engine) as observer:
        rows = list(
            observer.scalars(
                select(AgentDaypartMemoryEvent).where(
                    AgentDaypartMemoryEvent.event_type == "daypart_summary"
                )
            )
        )
        assert len(rows) == 2
        assert {row.memory_session_key for row in rows} == {"group-a", "group-b"}
        assert all(
            row.provided_at == (start - timedelta(microseconds=1)).replace(tzinfo=None)
            for row in rows
        )
        assert all(row.payload["finalized_by_run_id"] == "run-a" for row in rows)
