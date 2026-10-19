from copy import deepcopy

from app.domains.memory.policies.situation_generation import with_social_situations, TARGET_OUTPUT_REVISION
from app.domains.memory.policies.situation_output import parse_situations
from app.runtime.autonomous_activity.combined_provider import CombinedActivityProvider


def test_targets_are_exact_and_empty_targets_allow_only_empty_array():
    schema = {"type": "object", "properties": {"decision": {}, "draft": {}}}
    original = deepcopy(schema)
    result = with_social_situations(schema, ["routine-post"], locale="en-US")
    assert result["properties"]["situations"]["items"]["properties"]["target_id"]["enum"] == ["routine-post"]
    empty = with_social_situations(schema, [], locale="en-US")
    assert empty["properties"]["situations"]["maxItems"] == 0
    assert "enum" not in empty["properties"]["situations"]["items"]["properties"]["target_id"]
    assert schema == original


def test_wrong_auxiliary_targets_do_not_change_base_action():
    payload = {"decision": {"action": "post"}, "draft": {}, "situations": [{"target_id": "Red", "description": "scene"}]}
    drafts = parse_situations(payload, ("routine-post",))
    assert drafts["routine-post"].status != "valid"
    assert payload["decision"]["action"] == "post"


def test_legacy_output_schema_and_new_target_scope_are_distinct():
    provider = object.__new__(CombinedActivityProvider)
    provider.situation_output_revision = None
    assert provider.situation_targets({}, "routine") is None
    provider.situation_output_revision = TARGET_OUTPUT_REVISION
    assert provider.situation_targets({}, "routine") == ("routine-post",)
    assert provider.situation_targets({"selected_targets": [{"target_id": "post-A"}]}, "inbox") == ("post-A",)
    assert provider.situation_targets({"assignments": [{"source": {"target_id": "post-B"}}]}, "feed", writing=True) == ("post-B",)
