from datetime import UTC, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.domains.routines.service import slot_status as agent_run_service
from app.services import agent_runs


@pytest.mark.parametrize(
    ("next_tick_at", "expected"),
    [
        (None, False),
        (datetime(2026, 8, 29, 4, 59, 59), True),
        (datetime(2026, 8, 29, 5, 0), True),
        (datetime(2026, 8, 29, 5, 0, 1), False),
        (datetime(2026, 8, 29, 4, 59, 59, tzinfo=UTC), True),
        (
            datetime(2026, 8, 29, 14, 0, 1, tzinfo=ZoneInfo("Asia/Seoul")),
            False,
        ),
    ],
)
def test_resident_slot_due_comparison_normalizes_utc_instants(
    next_tick_at: datetime | None,
    expected: bool,
) -> None:
    slot = SimpleNamespace(next_tick_at=next_tick_at)

    assert agent_run_service._resident_slot_is_due(
        slot,
        now=datetime(2026, 8, 29, 5, 0, tzinfo=UTC),
    ) is expected


def test_agent_run_readiness_requires_hidden_feed_seed_criteria() -> None:
    base = {
        "tendency_updated_at": datetime.now(UTC),
        "tendency_summary": "This agent has a saved community tendency profile.",
        "tendency_action_ranges": {
            "post": {
                "min": 0,
                "max": 1,
                "label": "Post",
                "note": "Post only when the topic fits.",
            }
        },
    }
    legacy_profile = SimpleNamespace(**base, planner_tendency_profile={})
    ready_profile = SimpleNamespace(
        **base,
        planner_tendency_profile={
            "feed_seed_interest_criteria": "Prefer feed posts that fit the persona."
        },
    )

    assert not agent_runs._has_tendency_analysis(legacy_profile)
    assert agent_runs._has_tendency_analysis(ready_profile)
