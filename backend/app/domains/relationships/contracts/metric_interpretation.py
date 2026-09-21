"""Bounded AI interpretation of experience, independent of action execution."""

from dataclasses import dataclass
from typing import Literal

Direction = Literal["increase", "keep", "decrease"]
DIRECTIONS = frozenset({"increase", "keep", "decrease"})


@dataclass(frozen=True, slots=True)
class MetricInterpretation:
    target_ref: str
    affinity: Direction
    trust: Direction
    tension: Direction
    new_evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MetricInterpretationResult:
    status: Literal["valid", "missing", "invalid"]
    interpretations: tuple[MetricInterpretation, ...] = ()


def parse_metric_interpretations(
    value: object, *, max_targets: int = 20
) -> MetricInterpretationResult:
    """Invalid optional metadata must not invalidate the generated text.

    Scope and evidence membership are validated by the applying service, never
    inferred from model-produced names. Empty output is valid, not missing.
    """
    if value is None:
        return MetricInterpretationResult("missing")
    if not isinstance(value, list) or len(value) > max_targets:
        return MetricInterpretationResult("invalid")
    parsed: list[MetricInterpretation] = []
    targets: set[str] = set()
    for row in value:
        if not isinstance(row, dict):
            return MetricInterpretationResult("invalid")
        target = row.get("target_ref")
        refs = row.get("new_evidence_refs")
        directions = [row.get(axis) for axis in ("affinity", "trust", "tension")]
        if (
            not isinstance(target, str) or not 1 <= len(target) <= 128
            or target in targets
            or any(not isinstance(d, str) or d not in DIRECTIONS for d in directions)
            or not isinstance(refs, list) or not 1 <= len(refs) <= 3
            or any(not isinstance(ref, str) or not 1 <= len(ref) <= 128 for ref in refs)
            or len(set(refs)) != len(refs)
        ):
            return MetricInterpretationResult("invalid")
        targets.add(target)
        parsed.append(MetricInterpretation(target, *directions, tuple(refs)))
    return MetricInterpretationResult("valid", tuple(parsed))
