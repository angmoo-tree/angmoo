from datetime import UTC, date, datetime

import pytest

from app.domains.memory.domain.batch_policy import (
    daily_slot,
    next_daily_slot,
    schedule_time,
)
from app.domains.memory.domain.errors import MemoryValidationError
from app.domains.memory.domain.selection import MemorySelectionSource, parse_selection


def test_daily_schedule_future_and_consumed_date():
    assert next_daily_slot(
        after=datetime(2026, 9, 4, 13, tzinfo=UTC),
        local_time="22:30",
        timezone="Asia/Seoul",
    ) == datetime(2026, 9, 4, 13, 30, tzinfo=UTC)
    assert next_daily_slot(
        after=datetime(2026, 9, 4, 14, tzinfo=UTC),
        local_time="22:30",
        timezone="Asia/Seoul",
    ) == datetime(2026, 9, 5, 13, 30, tzinfo=UTC)
    assert next_daily_slot(
        after=datetime(2026, 9, 4, 13, tzinfo=UTC),
        local_time="22:30",
        timezone="Asia/Seoul",
        last_consumed_date=date(2026, 9, 4),
    ) == datetime(2026, 9, 5, 13, 30, tzinfo=UTC)


def test_dst_gap_and_overlap_are_single_instants():
    assert daily_slot(
        date(2026, 3, 8), local_time="02:30", timezone="America/New_York"
    ) == datetime(2026, 3, 8, 7, tzinfo=UTC)
    assert daily_slot(
        date(2026, 11, 1), local_time="01:30", timezone="America/New_York"
    ) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "value", ["24:00", "1:30", "12:60", "22:30:00", " 22:30", None]
)
def test_invalid_daily_times(value):
    with pytest.raises(MemoryValidationError):
        schedule_time(value)


def payload():
    return {
        "version": "memory-selection.v2",
        "batch_ref": "batch-1",
        "decisions": [
            {
                "candidate_ref": "candidate-1",
                "decision": "retain",
                "reason_code": "meaningful_experience",
                "memory": {
                    "summary": "동료의 도움으로 과제를 마쳤다.",
                    "evidence_refs": ["source-1"],
                    "subjective_context_refs": [],
                },
            },
            {
                "candidate_ref": "candidate-2",
                "decision": "skip",
                "reason_code": "routine_low_salience",
                "memory": None,
            },
        ],
    }


SOURCES = (
    MemorySelectionSource(
        "candidate-1", "source-1", "AUTOBIOGRAPHICAL_EVENT", "과제를 마침"
    ),
    MemorySelectionSource(
        "candidate-2", "source-2", "AUTOBIOGRAPHICAL_EVENT", "좋아요"
    ),
)


def test_explicit_retain_and_skip():
    result = parse_selection(payload(), sources=SOURCES)
    assert [item.decision for item in result] == ["retain", "skip"]
    assert result[1].summary is None


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "foreign_source",
        "extra",
        "version",
        "skip_body",
        "long_summary",
    ],
)
def test_selection_fails_closed(mutation):
    value = payload()
    if mutation == "missing":
        value["decisions"].pop()
    if mutation == "duplicate":
        value["decisions"][1] = value["decisions"][0]
    if mutation == "foreign_source":
        value["decisions"][0]["memory"]["evidence_refs"] = ["source-2"]
    if mutation == "extra":
        value["owner_id"] = "untrusted"
    if mutation == "version":
        value["version"] = "old"
    if mutation == "skip_body":
        value["decisions"][1]["memory"] = value["decisions"][0]["memory"]
    if mutation == "long_summary":
        value["decisions"][0]["memory"]["summary"] = "가" * 321
    with pytest.raises(MemoryValidationError):
        parse_selection(value, sources=SOURCES)
