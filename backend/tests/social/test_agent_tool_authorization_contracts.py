import hashlib
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from model_fixture_support import models
from app.domains.social.exceptions import AgentRunAuthorizationError
from app.domains.social.service import agent_tool_authorization as service
from app.runtime.social.agent_tool_authorization import RuntimeAgentToolReferences
from relationships.test_social_event_runtime import _engine, _seed


def test_tool_authorization_keeps_attached_run_pending_status_and_caller_rollback():
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        run = models.AgentRun(
            id="tool-auth-contract",
            user_id=fixture.actor.owner_id,
            character_id=fixture.actor.id,
            agent_id="resident-contract",
            session_key="resident:tick",
            tool_auth_key="private-tool-key",
            status="running",
        )
        db.add(run)
        db.commit()
        calls = []
        event.listen(engine, "before_cursor_execute", lambda *args: calls.append("sql"))
        event.listen(db, "before_commit", lambda *args: calls.append("commit"))
        references = RuntimeAgentToolReferences()
        assert calls == []
        actual = service._get_agent_tool_run(
            db, references=references, session_key=run.tool_auth_key, action="post"
        )
        assert actual is run
        assert calls == ["sql"]
        assert service._agent_tool_user(
            db, run, references=references, action="post", session_key=run.tool_auth_key
        ) is db.get(models.User, run.user_id)
        run.status = "completed"
        with pytest.raises(AgentRunAuthorizationError) as exc:
            service._get_agent_tool_run(
                db, references=references, session_key=run.tool_auth_key, action="post"
            )
        assert "reason=no_active_run" in str(exc.value)
        assert "run_status=completed" in str(exc.value)
        assert run.tool_auth_key not in str(exc.value)
        assert "commit" not in calls
        db.rollback()
        assert run.status == "running"
        assert (
            service._get_agent_tool_run(
                db, references=references, session_key=run.tool_auth_key, action="post"
            )
            is run
        )
    engine.dispose()


def test_tool_authorization_preserves_short_circuit_and_exact_denial_translation():
    calls = []
    db = object()
    run = SimpleNamespace(
        id="r", user_id="u", character_id="c", post_id=None, status="running"
    )

    class Denied(Exception):
        pass

    class References:
        activity_policy_denied = Denied
        active = run

        def get_active_run_for_tool_auth_key(self, session, key):
            assert session is db
            calls.append("auth")
            return self.active

        def get_active_run_for_session(self, session, key):
            raise AssertionError("daypart cannot fall back to a session")

        def assert_action_allowed(self, session, *, run, action):
            assert session is db
            calls.append((run, action))
            raise self.failure

    references = References()
    key = "secret:resident-daypart:window"
    assert (
        service._get_agent_tool_run(
            db, references=references, session_key=key, action="like"
        )
        is run
    )
    assert calls == ["auth"]
    references.active = None
    with pytest.raises(AgentRunAuthorizationError) as exc:
        service._get_agent_tool_run(
            db, references=references, session_key=key, action="like"
        )
    assert "reason=daypart_session_key_not_authorized" in str(exc.value)
    assert hashlib.sha256(key.encode()).hexdigest()[:12] in str(exc.value)
    assert key not in str(exc.value)
    assert calls == ["auth", "auth"]
    references.failure = Denied("outside active hours")
    with pytest.raises(AgentRunAuthorizationError, match="reason=outside active hours"):
        service._ensure_tick_action_allowed(
            db, references=references, session_key=key, run=run, action="like"
        )
    references.failure = RuntimeError("unexpected storage failure")
    with pytest.raises(RuntimeError) as exc:
        service._ensure_tick_action_allowed(
            db, references=references, session_key=key, run=run, action="like"
        )
    assert exc.value is references.failure
