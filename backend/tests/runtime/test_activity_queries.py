import pytest
from app.runtime.autonomous_activity.contracts import Candidate, Selection
from app.runtime.autonomous_activity.queries import resolve_query, routine_query, validate_selection


def test_bad_auxiliary_query_preserves_valid_selection_but_bad_target_fails():
    c = Candidate(target_id="p", text="I did not agree to the proposal.", allowed_actions=["comment"])
    selected = validate_selection({"selections": [{"target_id": "p", "memory_query": {"wrong": "type"}}]}, [c], 1)
    query = resolve_query(selected[0], c, lane="inbox")
    assert query.origin == "natural" and "did not agree" in query.query
    with pytest.raises(ValueError):
        validate_selection({"selections": [{"target_id": "other"}]}, [c], 1)
    assert validate_selection({"selections": []}, [c], 1) == []


def test_routine_query_tracks_success_and_retains_fixed_routine_anchor():
    assert routine_query(title="repair", activity_seed="clean tools", previous=None).query == "repair clean tools"
    assert routine_query(title="repair", activity_seed="clean tools", previous={"topic_signature": "fixed handle"}).query == "fixed handle repair"
    assert routine_query(title="repair", activity_seed="clean tools", previous={"topic_signature": " ", "title": "finished", "body": "stored the tools"}).query == "finished stored the tools repair"
