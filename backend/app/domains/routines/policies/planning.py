"""Pure daypart boundaries, deterministic candidate choice and snapshots."""
from __future__ import annotations
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from app.domains.routines.constants import (
    DAYPARTS,
    DAYPART_START_HOURS,
    RECENT_EXACT_DAYS,
    SELECTION_CONTRACT_VERSION,
)
from app.domains.routines.exceptions import DailyActivityPlanValidationError
from app.domains.routines.service.scheduling import aware_utc as _aware_utc


def _zone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise DailyActivityPlanValidationError("world_timezone_invalid") from exc


def _resolve_local_boundary(local_naive: datetime, zone: ZoneInfo) -> datetime:
    probe = local_naive
    for _ in range(181):
        candidates: list[datetime] = []
        for fold in (0, 1):
            aware = probe.replace(tzinfo=zone, fold=fold)
            instant = aware.astimezone(UTC)
            round_trip = instant.astimezone(zone).replace(tzinfo=None)
            if round_trip == probe:
                candidates.append(instant)
        if candidates:
            return min(candidates)
        probe += timedelta(minutes=1)
    raise DailyActivityPlanValidationError("world_timezone_invalid")


def daypart_windows(
    local_date: date,
    timezone_name: str,
) -> dict[str, tuple[datetime, datetime]]:
    zone = _zone(timezone_name)
    local_boundaries = [
        datetime.combine(local_date, time(hour=hour))
        for hour in DAYPART_START_HOURS
    ]
    local_boundaries.append(datetime.combine(local_date + timedelta(days=1), time()))
    utc_boundaries = [
        _resolve_local_boundary(boundary, zone) for boundary in local_boundaries
    ]
    if any(
        current >= following
        for current, following in zip(utc_boundaries, utc_boundaries[1:])
    ):
        raise DailyActivityPlanValidationError("world_timezone_invalid")
    return {
        daypart: (utc_boundaries[index], utc_boundaries[index + 1])
        for index, daypart in enumerate(DAYPARTS)
    }


def local_activity_date(now: datetime, timezone_name: str) -> date:
    return _aware_utc(now).astimezone(_zone(timezone_name)).date()


def _select_candidate(
    *,
    world_character_id: str,
    local_date: date,
    daypart: str,
    repertoire: Any,
    candidates: list[Any],
    history: list[tuple[Any, date]],
) -> Any:
    options = [candidate for candidate in candidates if candidate.daypart == daypart]
    recent_cutoff = local_date - timedelta(days=RECENT_EXACT_DAYS)
    recent_signatures = {
        item.candidate_signature
        for item, history_date in history
        if item.daypart == daypart and history_date >= recent_cutoff
    }
    unused = [
        candidate
        for candidate in options
        if candidate.canonical_signature not in recent_signatures
    ]
    pool = unused or options
    usage = Counter(
        item.candidate_signature
        for item, _history_date in history
        if item.daypart == daypart
    )
    minimum_usage = min(usage[candidate.canonical_signature] for candidate in pool)
    pool = [
        candidate
        for candidate in pool
        if usage[candidate.canonical_signature] == minimum_usage
    ]
    previous_kind = next(
        (
            item.activity_kind
            for item, history_date in history
            if item.daypart == daypart
            and history_date == local_date - timedelta(days=1)
        ),
        None,
    )
    different_kind = [
        candidate for candidate in pool if candidate.activity_kind != previous_kind
    ]
    if different_kind:
        pool = different_kind

    base_seed = "|".join(
        (
            world_character_id,
            local_date.isoformat(),
            daypart,
            repertoire.id,
            f"p2-repertoire-v{repertoire.schema_version}",
            SELECTION_CONTRACT_VERSION,
        )
    )
    return min(
        pool,
        key=lambda candidate: sha256(
            f"{base_seed}|{candidate.canonical_signature}".encode("utf-8")
        ).hexdigest(),
    )


def _snapshot(candidate: Any) -> dict[str, object]:
    return {
        "candidate_id": candidate.id,
        "candidate_signature": candidate.canonical_signature,
        "candidate_ordinal": candidate.ordinal,
        "daypart": candidate.daypart,
        "activity_kind": candidate.activity_kind,
        "title": candidate.title,
        "activity_seed": candidate.activity_seed,
        "social_mode": candidate.social_mode,
        "place_key": candidate.place_key,
    }
