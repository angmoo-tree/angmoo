import pytest

from app.domains.relationships.contracts.metric_interpretation import parse_metric_interpretations
from app.domains.relationships.contracts.daily_review import validate_review_result
from app.domains.relationships.policies.personalized_metrics import calculate_metric_delta
from app.domains.relationships.policies.daily_review import partition_review_inputs, fits_input


def proposal(**directions):
    return parse_metric_interpretations([{"target_ref": "b", "affinity": "keep", "trust": "increase",
        "tension": "decrease", "new_evidence_refs": ["post:1"], **directions}]).interpretations[0]


def test_optional_metadata_failure_is_distinct_from_keep():
    assert parse_metric_interpretations(None).status == "missing"
    assert parse_metric_interpretations([]).status == "valid"
    assert parse_metric_interpretations([{"trust": 99}]).status == "invalid"


def test_scope_refs_are_bounded_and_duplicates_rejected():
    row = {"target_ref": "b", "affinity": "keep", "trust": "keep", "tension": "keep", "new_evidence_refs": ["p"]}
    assert parse_metric_interpretations([row, row]).status == "invalid"
    assert parse_metric_interpretations([row], max_targets=0).status == "invalid"
    assert parse_metric_interpretations([{**row, "new_evidence_refs": ["p"] * 4}]).status == "invalid"


def test_limits_are_shared_but_directional_not_net():
    current = dict(familiarity=0, affinity=0, trust=0, tension=20)
    usage = {}
    for _ in range(8):
        result = calculate_metric_delta(current, usage, new_contact=True, interpretation=proposal())
        current, usage = result.values, result.usage
    assert current == dict(familiarity=4, affinity=0, trust=2, tension=16)
    for _ in range(8):
        result = calculate_metric_delta(current, usage, new_contact=False, interpretation=proposal(trust="decrease", tension="increase"))
        current, usage = result.values, result.usage
    assert current == dict(familiarity=4, affinity=0, trust=0, tension=20)
    result = calculate_metric_delta(current, usage, new_contact=False, interpretation=proposal())
    assert result.deltas == dict(familiarity=0, affinity=0, trust=0, tension=0)


def test_clamps_do_not_consume_unused_budget():
    result = calculate_metric_delta(dict(familiarity=100, affinity=100, trust=100, tension=0), {},
                                   new_contact=True, interpretation=proposal(affinity="increase"))
    assert result.usage == {}
    assert not any(result.deltas.values())


def test_partition_preserves_full_memories_and_reduces_bounded_outputs():
    entries = [{"memory_id": str(i), "summary": "한" * 2000} for i in range(40)]
    partitions = partition_review_inputs({"actor": "a", "target": "b"}, entries)
    assert len(partitions) > 1
    assert all(fits_input(p) for p in partitions)
    assert [m for p in partitions for m in p["memories"]] == entries
    assert partition_review_inputs({}, []) == []


def test_final_review_cannot_invent_references_or_unbounded_perception():
    with pytest.raises(ValueError):
        validate_review_result({"decision": "update", "relationship_label": "친구", "perception": "신뢰함", "memory_refs": ["other"]}, partial=False, allowed_refs={"m"})
    assert validate_review_result({"decision": "keep", "memory_refs": []}, partial=False, allowed_refs={"m"})["decision"] == "keep"
    with pytest.raises(ValueError):
        validate_review_result({"findings": ["x"] * 13, "memory_refs": ["m"]}, partial=True, allowed_refs={"m"})
