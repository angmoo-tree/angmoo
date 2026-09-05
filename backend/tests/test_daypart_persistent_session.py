from datetime import datetime
import inspect
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.services import agent_writing
from app.services import community
from app.services import agent_runs


KST = ZoneInfo("Asia/Seoul")


def test_night_daypart_keeps_start_date_across_midnight() -> None:
    daypart, start_date, start_at, end_at = agent_runs._activity_daypart_window(
        datetime(2026, 6, 10, 1, 30, tzinfo=KST)
    )

    assert daypart == "night"
    assert start_date.isoformat() == "2026-06-09"
    assert start_at.isoformat() == "2026-06-09T22:00:00+09:00"
    assert end_at.isoformat() == "2026-06-10T06:00:00+09:00"


def test_daypart_main_session_key_changes_by_window() -> None:
    morning = agent_runs._daypart_main_session_key(
        agent_id="angmoo-1",
        character_id="char-a",
        daypart_start_date=agent_runs._activity_daypart_window(
            datetime(2026, 6, 9, 6, 0, tzinfo=KST)
        )[1],
        activity_daypart="morning",
    )
    afternoon = agent_runs._daypart_main_session_key(
        agent_id="angmoo-1",
        character_id="char-a",
        daypart_start_date=agent_runs._activity_daypart_window(
            datetime(2026, 6, 9, 14, 0, tzinfo=KST)
        )[1],
        activity_daypart="afternoon",
    )

    assert morning != afternoon
    assert morning == "agent:angmoo-1:resident-daypart:char-a:2026-06-09:morning"


def test_daypart_persistent_session_requires_flag_allowlist_and_natural_tick(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_runs.settings,
        "RESIDENT_DAYPART_PERSISTENT_SESSION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        agent_runs.settings,
        "RESIDENT_DAYPART_PERSISTENT_SESSION_CHARACTER_IDS",
        "char-allowed",
    )

    assert agent_runs._daypart_persistent_session_allowed(
        character_id="char-allowed",
        require_public_action=False,
        enforce_activity_policy=True,
    )
    assert not agent_runs._daypart_persistent_session_allowed(
        character_id="char-allowed",
        require_public_action=True,
        enforce_activity_policy=True,
    )
    assert not agent_runs._daypart_persistent_session_allowed(
        character_id="char-other",
        require_public_action=False,
        enforce_activity_policy=True,
    )


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


def test_v6_state_recovery_prompt_is_tool_only_and_compact() -> None:
    character = SimpleNamespace(
        id="char-test",
        name="테스트",
        handle="test",
        persona_summary="quiet observer",
        speech_style="short Korean notes",
    )
    activity_policy = SimpleNamespace(tendency_summary="prefers compact observations")

    prompt = agent_runs._build_v6_state_recovery_prompt(
        character=character,
        state=None,
        activity_policy=activity_policy,
        public_action_ledger="- observed only",
        tick_activity="- feed_viewed; feed_interests_noted",
        observation_context="- semantic_event: someone discussed resting",
    )

    assert "angmoo_save_character_state" in prompt
    assert "Do not call public action, feed, inbox, writing, read, or scan tools." in prompt
    assert "Public action ledger from this tick" in prompt
    assert "Compact observation context from this tick" in prompt
    assert "raw feed" not in prompt.lower()
    assert "thread body" not in prompt.lower()


def test_writing_composition_prefers_run_tool_auth_key() -> None:
    source = inspect.getsource(agent_writing._run_composition_gateway)

    assert "tool_auth_key=run.tool_auth_key" in source
    assert "tool_auth_key=run.tool_auth_key or session_key" not in source


def test_agent_tool_auth_rejects_daypart_session_key(monkeypatch) -> None:
    def fail_session_lookup(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("daypart session key must not fall back to session lookup")

    monkeypatch.setattr(
        community.routine_run_queries,
        "get_active_run_for_tool_auth_key",
        lambda db, key: None,
    )
    monkeypatch.setattr(
        community.routine_run_queries,
        "get_active_run_for_session",
        fail_session_lookup,
    )

    with pytest.raises(community.AgentRunAuthorizationError) as exc:
        community._get_agent_tool_run(
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
        community.routine_run_queries,
        "get_active_run_for_tool_auth_key",
        lambda db, key: None,
    )
    monkeypatch.setattr(
        community.routine_run_queries,
        "get_active_run_for_session",
        lambda db, key: run if key == "agent:angmoo-8:resident-tick:user-a:char-a:run-1" else None,
    )

    resolved = community._get_agent_tool_run(
        None,
        session_key=(
            "agent:angmoo-8:resident-tick:user-a:char-a:run-1"
            ":run-main:run-1"
        ),
        action="post",
        requested_character_id="char-a",
    )

    assert resolved is run
