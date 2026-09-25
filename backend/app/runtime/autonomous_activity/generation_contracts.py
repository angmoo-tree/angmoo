"""Version two envelopes convert into the existing canonical decision/draft DTOs."""
import json
from copy import deepcopy
from dataclasses import asdict

from app.contracts.activity_thought_output import extract_activity_thought, thought_response_schema
from app.domains.routine_posts.schemas import RoutinePostDraft
from app.providers.contracts import StructuredOutputValidationError
from app.providers.gemini import build_gemini_developer_response_schema
from app.runtime.autonomous_activity.provider import WriterOutput, parse_writer_output


def draft_schema(lane):
    if lane == "routine":
        return thought_response_schema(build_gemini_developer_response_schema(RoutinePostDraft), include_thought=True)
    schema = deepcopy(build_gemini_developer_response_schema(WriterOutput))
    item = schema["properties"]["replies"]["items"]
    item["properties"].pop("task_id")
    # A conversation identity is not a canonical writer task ID and can be
    # longer. The exact supplied ID set bounds it below.
    item["properties"]["target_id"] = {"type": "string"}
    item["required"] = ["target_id" if key == "task_id" else key for key in item.get("required", [])]
    if "body" not in item["required"]:
        item["required"].append("body")
    item["properties"]["body"] = {"type": "string", "minLength": 1, "maxLength": 500 if lane == "feed" else 1000}
    if lane == "feed":
        schema["properties"]["replies"]["maxItems"] = 1
        item["properties"]["body"]["maxLength"] = 500
    return schema


def envelope_schema(decision_schema, lane):
    draft = draft_schema(lane)
    if lane != "routine":
        targets = decision_schema["properties"]["decisions"]["items"]["properties"]["target_id"].get("enum")
        if targets:
            draft["properties"]["replies"]["items"]["properties"]["target_id"]["enum"] = list(targets)
    return {"type": "object", "properties": {
        "decision": decision_schema, "draft": draft},
        "required": ["decision", "draft"]}


def parse_envelope(value, validate_decision):
    # A usable decision survives a missing/invalid draft. An invalid decision
    # never becomes no_action and cannot authorize any public expression.
    if not isinstance(value, dict) or not isinstance(value.get("decision"), dict):
        raise StructuredOutputValidationError("decision_missing", "decision")
    decision = validate_decision(value["decision"])
    return {**decision, "provisional_draft": value.get("draft")}


def parse_social_draft(raw, *, lane, assignments):
    if not isinstance(raw, dict) or not isinstance(raw.get("replies"), list):
        raise ValueError("combined_draft_missing")
    tasks = {a["source"]["target_id"]: a["task_id"] for a in assignments}
    replies, seen = [], set()
    for row in raw["replies"]:
        if not isinstance(row, dict):
            raise ValueError("combined_draft_shape")
        target = row.get("target_id")
        if not isinstance(target, str) or target not in tasks or target in seen:
            raise ValueError("combined_draft_target_mismatch")
        if "task_id" in row:
            raise ValueError("combined_draft_task_id_forbidden")
        seen.add(target)
        body = row.get("body")
        if not isinstance(body, str) or not body.strip() or (lane == "feed" and len(body) > 500):
            raise ValueError("combined_draft_body_invalid")
        replies.append({k: v for k, v in row.items() if k != "target_id"} | {"task_id": tasks[target]})
    if seen != set(tasks):
        raise ValueError("combined_draft_target_mismatch")
    return parse_writer_output({"replies": replies}, lane=lane, assignments=assignments)


def parse_routine_draft(payload):
    if not isinstance(payload, dict):
        raise ValueError("combined_routine_draft_missing")
    value, thought = extract_activity_thought(payload, include_thought=True)
    draft = RoutinePostDraft.model_validate(value)
    return {**draft.model_dump(mode="json"), "_thought": asdict(thought)}


async def generation_mode(state):
    # This node is checkpointed before any generation request. A resume never
    # switches modes based on the response size or a changed context.
    size = len(json.dumps({"context": state.get("decision_context"),
        "targets": state.get("candidates")}, ensure_ascii=False, default=str))
    return {"generation_mode": "split" if size > 40000 else "combined"}
