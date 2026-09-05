from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.service import activity_evidence as evidence
from routines.test_activity_persistence import _file_engine
from routine_posts.test_runtime import _seed


def _log(db, fixture, *, log_id, action_type, created_at, result):
    log = models.AgentActivityLog(
        id=log_id, user_id=fixture.user.id, character_id=fixture.character.id,
        action_type=action_type, created_at=created_at, result=result,
        reason="recorded evidence", target_post_id=None,
    )
    db.add(log)
    return log


def test_latest_evidence_keeps_same_session_order_defaults_and_rollback(tmp_path):
    engine = _file_engine(tmp_path)
    since = datetime(2026, 9, 6, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        character_id = fixture.character.id
        first = _log(db, fixture, log_id=1, action_type="feed_interests_noted",
                     created_at=since, result=json.dumps({"interests": ["older-id"]}))
        _log(db, fixture, log_id=2, action_type="feed_interests_noted",
             created_at=since, result=json.dumps({"interests": ["newer-id"]}))
        _log(db, fixture, log_id=3, action_type="inbox_reviewed",
             created_at=since, result="not valid json")
        _log(db, fixture, log_id=4, action_type="feed_history_sanitized",
             created_at=since, result="[]")
        commits = []

        @event.listens_for(db, "after_commit")
        def committed(_session):
            commits.append(True)

        assert evidence._latest_v6_feed_interest_payload(
            db, character_id=character_id, since=since,
        ) == {"interests": ["newer-id"]}
        assert evidence._latest_v6_inbox_review_payload(
            db, character_id=character_id, since=since,
        ) == {"candidate_notification_id": None}
        assert evidence._latest_v6_feed_history_sanitize_payload(
            db, character_id=character_id, since=since,
            action_type="feed_history_sanitized",
        ) is None
        assert evidence._latest_v6_feed_interest_payload(
            db, character_id="another-character", since=since,
        ) == {"interests": [], "post_seed": "", "no_relevant_signal": True}
        assert commits == []
        with Session(engine) as observer:
            assert observer.get(models.AgentActivityLog, first.id) is None
        db.rollback()
        assert evidence._latest_v6_feed_interest_payload(
            db, character_id=character_id, since=since,
        ) == {"interests": [], "post_seed": "", "no_relevant_signal": True}
    engine.dispose()


def test_tick_evidence_preserves_expire_before_read_and_pending_new_log(tmp_path):
    engine = _file_engine(tmp_path)
    since = datetime(2026, 9, 6, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        character_id = fixture.character.id
        saved = _log(db, fixture, log_id=1, action_type="state_saved",
                     created_at=since, result="Saved original state")
        db.commit()
        saved.action_type = "unflushed replacement must be expired"
        commits = []

        @event.listens_for(db, "after_commit")
        def committed(_session):
            commits.append(True)

        assert evidence._has_state_saved_since(db, character_id=character_id, since=since)
        assert saved.action_type == "state_saved"
        assert not evidence._has_state_saved_since(
            db, character_id=character_id, since=since + timedelta(seconds=1),
        )
        assert not evidence._has_thread_viewed_since(db, character_id=character_id, since=since)
        tick = _log(db, fixture, log_id=2, action_type="tick_completed",
                    created_at=since, result="pending tick")
        assert evidence._has_tick_completed_since(db, character_id=character_id, since=since)
        assert commits == []
        with Session(engine) as observer:
            assert observer.get(models.AgentActivityLog, tick.id) is None
        db.rollback()
        assert not evidence._has_tick_completed_since(db, character_id=character_id, since=since)
    engine.dispose()


def test_formatted_evidence_keeps_query_limits_hidden_actions_and_truthful_observation(tmp_path):
    engine = _file_engine(tmp_path)
    since = datetime(2026, 9, 6, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        character_id = fixture.character.id
        for index in range(22):
            _log(db, fixture, log_id=index+1, action_type="liked",
                 created_at=since + timedelta(seconds=index), result=f"like evidence {index:02d}")
        _log(db, fixture, log_id=30, action_type="feed_perception_debug",
             created_at=since, result="hidden debug")
        _log(db, fixture, log_id=31, action_type="observation_note_saved",
             created_at=since, result="커뮤니티의 차분한 분위기를 살펴봤어요.")
        _log(db, fixture, log_id=32, action_type="observation_note_saved",
             created_at=since + timedelta(seconds=1), result="좋아요를 눌렀어요.")
        db.commit()
        ledger = evidence._format_tick_public_action_ledger_since(
            db, character_id=character_id, since=since,
        )
        assert "like evidence 00" in ledger
        assert "like evidence 19" in ledger
        assert "like evidence 20" not in ledger
        assert ledger.index("like evidence 00") < ledger.index("like evidence 19")
        activity = evidence._format_tick_activity_since(
            db, character_id=character_id, since=since,
        )
        assert len(activity.splitlines()) == 20
        assert "hidden debug" not in activity
        assert "like evidence 20" not in activity
        assert evidence._format_tick_observation_context_since(
            db, character_id=character_id, since=since,
        ) == "- none"
        assert evidence._format_observation_result(
            db, character_id=character_id, since=since,
        ) == "커뮤니티의 차분한 분위기를 살펴봤어요."
    engine.dispose()
