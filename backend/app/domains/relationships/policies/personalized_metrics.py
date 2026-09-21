"""Numerical policy. Models propose directions; code owns numerical changes."""

from dataclasses import dataclass
from collections.abc import Mapping

from app.domains.relationships.contracts.metric_interpretation import MetricInterpretation

DAILY_LIMITS = {"familiarity_up": 4, "affinity_up": 4, "affinity_down": 4,
                "trust_up": 2, "trust_down": 2, "tension_up": 4, "tension_down": 4}
RANGES = {"familiarity": (0, 100), "affinity": (-100, 100),
          "trust": (-100, 100), "tension": (0, 100)}


@dataclass(frozen=True, slots=True)
class MetricDelta:
    values: dict[str, int]
    deltas: dict[str, int]
    usage: dict[str, int]


def calculate_metric_delta(
    current: Mapping[str, int], usage: Mapping[str, int], *,
    new_contact: bool, interpretation: MetricInterpretation | None,
) -> MetricDelta:
    """Independent upward/downward budgets prevent cancellation-based bypass.

    Charge only an actually applied point (including the state range clamp).
    The caller serializes and persists state, budget and receipt atomically.
    """
    if any(not isinstance(current.get(axis), int) or not low <= current[axis] <= high
           for axis, (low, high) in RANGES.items()):
        raise ValueError("relationship_metric_state_invalid")
    if any(not isinstance(v, int) or v < 0 for v in usage.values()):
        raise ValueError("relationship_metric_budget_invalid")
    proposed = {"familiarity": int(new_contact), "affinity": 0, "trust": 0, "tension": 0}
    if interpretation is not None:
        for axis in ("affinity", "trust", "tension"):
            proposed[axis] = {"increase": 1, "keep": 0, "decrease": -1}[getattr(interpretation, axis)]
    values = dict(current)
    consumed = dict(usage)
    deltas: dict[str, int] = {}
    for axis, delta in proposed.items():
        key = axis + ("_up" if delta > 0 else "_down")
        if delta and consumed.get(key, 0) >= DAILY_LIMITS[key]:
            delta = 0
        low, high = RANGES[axis]
        value = min(high, max(low, current[axis] + delta))
        applied = value - current[axis]
        if applied:
            consumed[key] = consumed.get(key, 0) + abs(applied)
        values[axis] = value
        deltas[axis] = applied
    return MetricDelta(values, deltas, consumed)
