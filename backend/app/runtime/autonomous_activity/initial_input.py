"""Checkpoint integrity for reference content; permissions remain live."""
from app.contracts.relationship_currentness import CURRENTNESS_POLICY_KEY, CURRENTNESS_REVISION
from app.domains.memory.contracts.activity_situation import stable_digest
import json

MAX_INPUT_BYTES = 512 * 1024


def material(state):
    data = state.get("lane_data", {})
    return {"identity": {key: state.get("identity", {}).get(key) for key in (
        "activity_id", "world_id", "actor_id", CURRENTNESS_POLICY_KEY)},
        "context": state.get("shared_context", {}),
        "candidates": [{key: value for key, value in row.items()
            if key not in {"allowed_actions", "proposal_eligible"}} for row in state.get("candidates", [])],
        "sources": data.get("_reference_sources", {}), "metrics": data.get("_metric_sources", []),
        "routine": data.get("prepared")}


def seal(state, update):
    combined = {**state, **update}
    data = dict(combined.get("lane_data", {}))
    data["_initial_input_digest"] = bounded_digest(combined)
    return {**update, "shared_context": combined.get("shared_context", {}), "lane_data": data}


def assert_integrity(state):
    if state.get("identity", {}).get(CURRENTNESS_POLICY_KEY) != CURRENTNESS_REVISION:
        return
    if not state.get("candidates"):
        return  # No reference input has been acquired yet.
    if state.get("lane_data", {}).get("_initial_input_digest") != bounded_digest(state):
        raise ValueError("activity_initial_input_invalid")


def bounded_digest(state):
    value = material(state)
    if len(json.dumps(value, ensure_ascii=False, default=str, allow_nan=False).encode()) > MAX_INPUT_BYTES:
        raise ValueError("activity_initial_input_limit")
    return stable_digest(value)
