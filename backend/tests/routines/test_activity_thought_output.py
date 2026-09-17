import json

from app.integrations.llm.activity_output import resident_thought_payload, resident_thought_schema
from app.domains.routines.schemas.resident_planning import _ReplyWriterOutput, _PostWriterOutput, _FeedActionPlan, _RelationshipActionPlan
from app.domains.routines.policies.writer_outputs import _apply_reply_writer_output
from app.providers.gemini import build_gemini_developer_response_schema


def test_nested_planner_schema_removes_legacy_and_keeps_execution_fields():
    schema = resident_thought_schema(build_gemini_developer_response_schema(_FeedActionPlan), writer=False)
    raw = json.dumps(schema)
    assert "motivation_kind" not in raw
    assert "emotion_intensity" not in raw
    assert "action_type" in raw and "thought" in raw
    result = resident_thought_payload({"feed_actions": [
        {"item_index": 0, "action_type": "like", "thought": "好きだ"},
        {"item_index": 1, "action_type": "reply", "thought": "計画の重複"},
    ]}, _FeedActionPlan, writer=False)
    assert result["feed_actions"][0]["_activity_thought"]["text"] == "好きだ"
    assert "_activity_thought" not in result["feed_actions"][1]
    assert "motivation_kind" not in json.dumps(result)


def test_relationship_decision_has_nontext_thought():
    output = resident_thought_payload({"decision": "follow", "target_character_id": "friend", "thought": "더 알고 싶다."}, _RelationshipActionPlan, writer=False)
    assert output["_activity_thought"]["text"] == "더 알고 싶다."


def test_final_reply_thought_is_task_bound_and_repair_replaces_old_thought():
    tasks = [{"task_id": "reply-1", "scope": "inbox", "action_index": 0, "target_post_id": "post-1"}]
    output = resident_thought_payload({"replies": [{"task_id": "reply-1", "body": "도와줄게.", "thought": "같이하고 싶다."}]}, _ReplyWriterOutput, writer=True)
    writing, _ = _apply_reply_writer_output({}, tasks, output, repair_attempted=False, writer_node="ReplyWriter")
    assert writing["reply_task_results"][0]["_activity_thought"]["text"] == "같이하고 싶다."
    repaired = resident_thought_payload({"replies": [{"task_id": "reply-1", "body": "내일 도와줄게.", "thought": 12}]}, _ReplyWriterOutput, writer=True)
    writing, _ = _apply_reply_writer_output(writing, tasks, repaired, repair_attempted=True, writer_node="ReplyWriterRepair")
    assert writing["reply_task_results"][0]["_activity_thought"]["status"] == "invalid"
    assert writing["reply_task_results"][0]["body"] == "내일 도와줄게."


def test_post_output_keeps_body_when_thought_is_missing():
    result = resident_thought_payload({"task_id": "post", "post_title": "연습", "post_body": "연습했다."}, _PostWriterOutput, writer=True)
    assert result["_activity_thought"]["status"] == "missing"
    assert result["post_body"] == "연습했다."
