import app.runtime.social.agent_tool_authorization as social_agent_tool_authorization_runtime
from datetime import datetime
import inspect
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.runtime.resident import writing as agent_writing
from app.domains.social import exceptions as community
from app.runtime.resident import execution as agent_runs


KST = ZoneInfo("Asia/Seoul")








def test_v6_state_recovery_uses_run_scoped_scratch_session() -> None:
    source = inspect.getsource(agent_runs._run_resident_individual_tool_flow)

    assert "state_recovery_attempted" in source
    assert "state_recovery_applied" in source
    assert "state_recovery_lane" in source
    assert "f\"{run_id}-v6-state-recovery\"" in source
    assert 'lane="state-recovery"' in source
    assert 'lane="state_recovery"' in source
    assert "session_key=recovery_session_key" in source
    assert "session_key=main_run_session_key" in source


def test_writing_composition_prefers_run_tool_auth_key() -> None:
    source = inspect.getsource(agent_writing._run_composition_gateway)

    assert "tool_auth_key=run.tool_auth_key" in source
    assert "tool_auth_key=run.tool_auth_key or session_key" not in source


def test_agent_tool_auth_rejects_daypart_session_key(monkeypatch) -> None:
    import app.domains.social.exceptions as community
    def fail_session_lookup(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("daypart session key must not fall back to session lookup")

    monkeypatch.setattr(
        social_agent_tool_authorization_runtime.agent_run_crud,
        "get_active_run_for_tool_auth_key",
        lambda db, key: None,
    )
    monkeypatch.setattr(
        social_agent_tool_authorization_runtime.agent_run_crud,
        "get_active_run_for_session",
        fail_session_lookup,
    )

    with pytest.raises(community.AgentRunAuthorizationError) as exc:
        social_agent_tool_authorization_runtime._get_agent_tool_run(
            None,
            session_key="agent:angmoo-8:resident-daypart:char-a:2026-06-09:afternoon",
            action="post",
            requested_character_id="char-a",
        )

    assert "reason=daypart_session_key_not_authorized" in str(exc.value)


def test_agent_tool_auth_keeps_run_scoped_session_fallback(monkeypatch) -> None:
    run = SimpleNamespace(
        id="run-1",
        status="running",
        post_id=None,
        character_id="char-a",
    )

    monkeypatch.setattr(
        social_agent_tool_authorization_runtime.agent_run_crud,
        "get_active_run_for_tool_auth_key",
        lambda db, key: None,
    )
    monkeypatch.setattr(
        social_agent_tool_authorization_runtime.agent_run_crud,
        "get_active_run_for_session",
        lambda db, key: run if key == "agent:angmoo-8:resident-tick:user-a:char-a:run-1" else None,
    )

    resolved = social_agent_tool_authorization_runtime._get_agent_tool_run(
        None,
        session_key=(
            "agent:angmoo-8:resident-tick:user-a:char-a:run-1"
            ":run-main:run-1"
        ),
        action="post",
        requested_character_id="char-a",
    )

    assert resolved is run
