from datetime import datetime
from zoneinfo import ZoneInfo

from app.domains.routines.service import session_keys as agent_runs


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
