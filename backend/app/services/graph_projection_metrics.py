from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Literal


MetricKind = Literal["counter", "gauge", "observation"]


_LABELS: dict[str, tuple[str, ...]] = {
    "graph_projection_claimed_total": ("projection_type",),
    "graph_projection_succeeded_total": ("projection_type", "result_class"),
    "graph_projection_retry_total": ("error_class",),
    "graph_projection_dead_total": ("error_class",),
    "graph_projection_pending_count": (),
    "graph_projection_oldest_pending_age_seconds": (),
    "graph_projection_duration_seconds": ("projection_type",),
    "graph_query_total": ("template", "status"),
    "graph_query_duration_seconds": ("template", "status"),
    "graph_query_timeout_total": ("template",),
    "graph_query_fallback_total": ("reason",),
    "graph_query_stale_edge_total": (),
    "graph_replay_total": ("mode", "status"),
    "graph_replay_duration_seconds": ("mode", "status"),
}


@dataclass(frozen=True)
class GraphMetricSample:
    name: str
    kind: MetricKind
    labels: tuple[tuple[str, str], ...]
    value: float
    count: int = 0


class GraphMetricRegistry:
    """Bounded in-process P7 metrics with an exporter-neutral snapshot API."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[
            tuple[str, MetricKind, tuple[tuple[str, str], ...]], tuple[float, int]
        ] = {}

    def _key(
        self,
        name: str,
        kind: MetricKind,
        labels: dict[str, str],
    ) -> tuple[str, MetricKind, tuple[tuple[str, str], ...]]:
        expected = _LABELS.get(name)
        if expected is None or set(labels) != set(expected):
            raise ValueError("graph_metric_contract_invalid")
        normalized = tuple((label, str(labels[label])[:80]) for label in expected)
        return name, kind, normalized

    def increment(self, name: str, amount: float = 1.0, **labels: str) -> None:
        if amount < 0:
            raise ValueError("graph_metric_counter_negative")
        key = self._key(name, "counter", labels)
        with self._lock:
            value, count = self._values.get(key, (0.0, 0))
            self._values[key] = (value + amount, count + 1)

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        key = self._key(name, "gauge", labels)
        with self._lock:
            self._values[key] = (float(value), 1)

    def observe(self, name: str, value: float, **labels: str) -> None:
        if value < 0:
            raise ValueError("graph_metric_observation_negative")
        key = self._key(name, "observation", labels)
        with self._lock:
            total, count = self._values.get(key, (0.0, 0))
            self._values[key] = (total + value, count + 1)

    def snapshot(self) -> tuple[GraphMetricSample, ...]:
        with self._lock:
            items = tuple(self._values.items())
        return tuple(
            GraphMetricSample(
                name=key[0],
                kind=key[1],
                labels=key[2],
                value=value,
                count=count,
            )
            for key, (value, count) in sorted(items)
        )

    def reset_for_tests(self) -> None:
        with self._lock:
            self._values.clear()


graph_metrics = GraphMetricRegistry()
