from __future__ import annotations

import pytest

from app.services.graph_projection_metrics import GraphMetricRegistry


def test_graph_metrics_keep_only_declared_low_cardinality_labels() -> None:
    registry = GraphMetricRegistry()
    registry.increment(
        "graph_projection_claimed_total",
        projection_type="relationship_state",
    )
    registry.increment(
        "graph_projection_claimed_total",
        projection_type="relationship_state",
    )
    registry.observe(
        "graph_query_duration_seconds",
        0.125,
        template="direct_relationship",
        status="succeeded",
    )
    samples = registry.snapshot()
    claimed = next(
        sample
        for sample in samples
        if sample.name == "graph_projection_claimed_total"
    )
    assert claimed.value == 2
    assert claimed.labels == (("projection_type", "relationship_state"),)
    with pytest.raises(ValueError, match="graph_metric_contract_invalid"):
        registry.increment(
            "graph_projection_claimed_total",
            projection_type="relationship_state",
            world_id="not-allowed",
        )


def test_observations_are_aggregated_without_unbounded_samples() -> None:
    registry = GraphMetricRegistry()
    for value in (0.1, 0.2, 0.3):
        registry.observe(
            "graph_projection_duration_seconds",
            value,
            projection_type="social_event",
        )
    sample = registry.snapshot()[0]
    assert sample.count == 3
    assert sample.value == pytest.approx(0.6)
