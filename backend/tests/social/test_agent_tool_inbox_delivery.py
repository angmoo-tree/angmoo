import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import event
from sqlalchemy.orm import Session

from model_fixture_support import models
from app.domains.social.service.agent_tool_authorization import _session_fingerprint
from app.runtime.social.agent_tool_reads import (
    RuntimeAgentToolReadWorkflows,
    agent_tool_reads,
)
from relationships.test_social_event_runtime import _engine, _seed


def test_inbox_delivery_keeps_run_scope_order_payload_rules_and_caller_rollback():
    engine = _engine()
    now = datetime.now(UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        run = models.AgentRun(
            id="inbox-delivery-contract",
            user_id=fixture.actor.owner_id,
            character_id=fixture.actor.id,
            agent_id="delivery-contract",
            session_key="inbox-contract",
            status="running",
            created_at=now,
        )
        db.add(run)
        db.flush()

        def log(payload, *, character_id=None, created_at=now):
            row = models.AgentActivityLog(
                user_id=run.user_id,
                character_id=character_id or run.character_id,
                action_type="inbox_notifications_provided",
                target_post_id=None,
                reason="fixture",
                result=payload,
                created_at=created_at,
            )
            db.add(row)
            return row

        fingerprint = _session_fingerprint(run.session_key)
        valid = log(
            json.dumps(
                {
                    "session_fingerprint": fingerprint,
                    "notification_ids": [True, "12", "invalid", 13],
                }
            )
        )
        malformed = log("{invalid json")
        foreign = log(
            json.dumps({"session_fingerprint": fingerprint, "notification_ids": [99]}),
            character_id=fixture.target.id,
        )
        older = log(
            json.dumps({"session_fingerprint": fingerprint, "notification_ids": [88]}),
            created_at=now - timedelta(seconds=1),
        )
        db.commit()
        calls = []
        event.listen(engine, "before_cursor_execute", lambda *args: calls.append("sql"))
        event.listen(db, "before_commit", lambda *args: calls.append("commit"))
        references = RuntimeAgentToolReadWorkflows()
        assert calls == []
        rows = references.inbox_delivery_logs(db, run=run)
        assert rows == [malformed, valid]
        assert all(row is not foreign and row is not older for row in rows)
        assert agent_tool_reads._latest_inbox_delivery_notification_ids(
            db, run=run, session_key=run.session_key
        ) == [12, 13]
        pending = log(
            json.dumps(
                {"session_fingerprint": fingerprint, "notification_ids": "wrong type"}
            )
        )
        assert (
            agent_tool_reads._latest_inbox_delivery_notification_ids(
                db, run=run, session_key=run.session_key
            )
            == []
        )
        assert pending.id is not None
        assert "commit" not in calls
        db.rollback()
        assert agent_tool_reads._latest_inbox_delivery_notification_ids(
            db, run=run, session_key=run.session_key
        ) == [12, 13]
        assert "commit" not in calls
    engine.dispose()
