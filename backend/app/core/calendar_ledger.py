"""Conservative period aggregates with original bucket identity, never fake events.

The owner persists this value under its own transaction/lock. Legacy counters
retain their original UTC bounds; overlapping guards count each bucket once.
"""
from copy import deepcopy
from datetime import datetime

from app.contracts.environment import AccountingPeriod
from app.core.calendar import utc_instant


class CalendarLedgerInvalid(ValueError):
    pass


def validated_ledger(value):
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("buckets"), dict):
        raise CalendarLedgerInvalid("calendar_quota_recovery_required")
    result = deepcopy(value)
    for key, bucket in result["buckets"].items():
        if (not isinstance(key, str) or not isinstance(bucket, dict)
            or type(bucket.get("count")) is not int or bucket["count"] < 0):
            raise CalendarLedgerInvalid("calendar_quota_recovery_required")
        try:
            start, end = (utc_instant(datetime.fromisoformat(bucket[name])) for name in ("start", "end"))
        except (ValueError, TypeError, KeyError):
            raise CalendarLedgerInvalid("calendar_quota_recovery_required") from None
        if start >= end:
            raise CalendarLedgerInvalid("calendar_quota_recovery_required")
    return result


def add_bucket(ledger, key, bounds, count=0):
    if type(count) is not int or count < 0:
        raise CalendarLedgerInvalid("calendar_quota_recovery_required")
    result = validated_ledger(ledger)
    start, end = bounds
    bucket = result["buckets"].setdefault(key, {"start": start.isoformat(), "end": end.isoformat(), "count": 0})
    if (bucket["start"], bucket["end"]) != (start.isoformat(), end.isoformat()):
        raise CalendarLedgerInvalid("calendar_quota_recovery_required")
    bucket["count"] += count
    return result


def ledger_usage(ledger, period: AccountingPeriod):
    result = validated_ledger(ledger)
    total = 0
    for bucket in result["buckets"].values():
        start, end = (utc_instant(datetime.fromisoformat(bucket[name])) for name in ("start", "end"))
        if any(start < hi and end > lo for lo, hi in period.ranges):
            total += bucket["count"]
    return total
