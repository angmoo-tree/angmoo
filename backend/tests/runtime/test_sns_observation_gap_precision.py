"""Report the same elapsed gap that made recorder coverage incomplete."""
from datetime import UTC, datetime, timedelta
import json

import pytest

from app.runtime.diagnostics.sns_observation_report import export_session, start_session
from tests.runtime.test_sns_observation import data_root


@pytest.mark.parametrize("gap", [150.0, 150.1, 150.49])
def test_gap_report_preserves_threshold_precision(data_root, tmp_path, gap):
    started = datetime(2026, 10, 5, tzinfo=UTC)
    manifest = start_session(data_root, world_id="world-1", minutes=10,
                             tail_minutes=0, now=started)
    directory = data_root / "diagnostics" / "sns" / manifest["session_id"]
    event = {"schema_version": manifest["event_schema_version"],
             "session_id": manifest["session_id"], "event_id": "heartbeat-boundary",
             "occurred_at": (started + timedelta(seconds=gap)).isoformat(),
             "event_type": "heartbeat", "actor_id": None, "activity_id": None,
             "details": {}}
    (directory / "events-boundary-0001.jsonl").write_text(
        json.dumps(event) + "\n", encoding="utf-8")
    coverage = export_session(data_root, manifest["session_id"],
                              destination=tmp_path / "export",
                              now=started + timedelta(seconds=gap + 1))
    assert coverage["heartbeat_gap_seconds"] == ([gap] if gap > 150 else [])
    assert all(value > 150 for value in coverage["heartbeat_gap_seconds"])
