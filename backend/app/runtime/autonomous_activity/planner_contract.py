"""Pure ActionPlanner output schema and validation contract."""

from typing import Literal, get_args

from pydantic import BaseModel, Field, ValidationError

from app.domains.routines.schemas.resident_planning import _ReplyTaskText
from app.domains.social.schemas.feed import JointActivityProposalPreview
from app.domains.world_characters.schemas.activity_state import StateUpdate
from app.providers.contracts import StructuredOutputValidationError
from app.providers.gemini import build_gemini_developer_response_schema


ActionName = Literal["no_action", "comment", "like", "repost", "follow"]
ACTIVE_ACTIONS = tuple(action for action in get_args(ActionName) if action != "no_action")


class ProposalDecision(_ReplyTaskText):
    task_id: str = "planner"
    body: None = None


class ProposalPlan(JointActivityProposalPreview):
    text: str = "Planner proposal"


class ActionChoice(BaseModel):
    target_id: str
    action: ActionName
    interaction_intent: Literal["ordinary_comment", "joint_activity_proposal", "proposal_response"] | None = None
    comment_purpose: Literal["question", "advice", "empathy", "encouragement", "information", "humor", "disagreement", "competition", "observation"] | None = None
    proposal: ProposalPlan | None = None
    proposal_response: ProposalDecision | None = None
    brief: str = Field(default="", max_length=280,
                       description="Required non-blank direction for every actual action; optional for no_action.")
    thought: str | None = Field(default=None, max_length=280)


class ActionOutput(BaseModel):
    decisions: list[ActionChoice]
    state_update: StateUpdate | None
    state_source_refs: list[str] = Field(default_factory=list)


def planner_response_schema(candidates: list[dict]) -> dict:
    """Add a Planner-only conditional without replacing the shared converter."""
    schema = build_gemini_developer_response_schema(ActionOutput)
    decisions = schema["properties"]["decisions"]
    decisions["maxItems"] = len(candidates)
    item = decisions["items"]
    item["properties"]["target_id"]["enum"] = [c["target_id"] for c in candidates]
    item["anyOf"] = [
        {"properties": {"action": {"type": "string", "enum": ["no_action"]}},
         "required": ["action"]},
        {"properties": {"action": {"type": "string", "enum": list(ACTIVE_ACTIONS)}},
         "required": ["action", "brief"]},
    ]
    return schema


def parse_action(payload: dict, candidates: list[dict]) -> dict:
    """Validate core decisions while isolating malformed optional state."""
    body = dict(payload)
    metrics = body.pop("relationship_metrics", None)
    state_present = "state_update" in body
    proposed = body.pop("state_update", None)
    refs = body.pop("state_source_refs", [])
    state_status = "valid"
    try:
        if not state_present:
            raise ValueError("missing_state_update")
        state = StateUpdate.model_validate(proposed).model_dump() if proposed is not None else None
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            raise ValueError("invalid_state_refs")
    except (ValidationError, ValueError):
        state, refs, state_status = None, [], "invalid"
    parsed = ActionOutput.model_validate({**body, "state_update": None})
    by_id = {c["target_id"]: c for c in candidates}
    seen = set()
    for index, decision in enumerate(parsed.decisions):
        path = f"decisions.{index}"
        if decision.target_id in seen or decision.target_id not in by_id:
            raise StructuredOutputValidationError("decision_target_invalid", f"{path}.target_id")
        seen.add(decision.target_id)
        if decision.action != "no_action" and decision.action not in by_id[decision.target_id]["allowed_actions"]:
            raise StructuredOutputValidationError("decision_action_not_allowed", f"{path}.action")
        if decision.action != "comment":
            if decision.interaction_intent in {"joint_activity_proposal", "proposal_response"} or decision.proposal_response is not None or decision.proposal is not None:
                raise StructuredOutputValidationError("non_comment_proposal_invalid", f"{path}.interaction_intent")
            decision.interaction_intent = decision.comment_purpose = None
        elif decision.interaction_intent is None or (decision.interaction_intent == "ordinary_comment" and decision.comment_purpose is None):
            raise StructuredOutputValidationError("comment_intent_missing", f"{path}.interaction_intent")
        if decision.interaction_intent == "joint_activity_proposal":
            if not by_id[decision.target_id].get("proposal_eligible") or decision.proposal is None:
                raise StructuredOutputValidationError("proposal_not_eligible", f"{path}.proposal")
            if decision.proposal.source_post_id != decision.target_id or decision.proposal.target_world_character_id != by_id[decision.target_id].get("counterpart_id"):
                raise StructuredOutputValidationError("proposal_target_mismatch", f"{path}.proposal")
        elif decision.proposal is not None:
            raise StructuredOutputValidationError("unexpected_proposal", f"{path}.proposal")
        if decision.interaction_intent == "proposal_response":
            if not by_id[decision.target_id].get("activity_proposal") or decision.proposal_response is None or decision.proposal_response.proposal_decision is None:
                raise StructuredOutputValidationError("proposal_response_missing", f"{path}.proposal_response")
        elif decision.proposal_response is not None:
            raise StructuredOutputValidationError("unexpected_proposal_response", f"{path}.proposal_response")
        if decision.action != "no_action" and not decision.brief.strip():
            raise StructuredOutputValidationError("action_brief_missing", f"{path}.brief")
    allowed_refs = {ref for c in candidates for ref in c["source_ids"]}
    if not set(refs) <= allowed_refs:
        state, refs, state_status = None, [], "invalid"
    return {"decisions": [d.model_dump() for d in parsed.decisions], "relationship_metrics": metrics,
            "state_update": state, "state_source_refs": refs, "state_status": state_status}
