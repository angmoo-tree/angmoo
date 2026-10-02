"""Planning policies must be importable without relying on service preload."""
import subprocess
import sys

import pytest


@pytest.mark.parametrize("first", [
    "app.domains.routines.policies.planning",
    "app.domains.routines.service.scheduling",
])
def test_planning_and_scheduling_are_independently_importable(first):
    result = subprocess.run([sys.executable, "-c", f'''
import importlib
importlib.import_module({first!r})
from datetime import UTC, datetime, timedelta, timezone
from app.domains.routines.policies.planning import daypart_windows
from app.domains.routines.service.scheduling import aware_utc as public_clock
from app.domains.routines.utils.clock import aware_utc
assert public_clock is aware_utc
assert aware_utc(datetime(2026, 10, 3)) == datetime(2026, 10, 3, tzinfo=UTC)
assert aware_utc(datetime(2026, 10, 3, 9, tzinfo=timezone(timedelta(hours=9)))) == datetime(2026, 10, 3, tzinfo=UTC)
assert len(daypart_windows(datetime(2026, 10, 3).date(), "Asia/Seoul")) == 4
'''], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
