"""Pure ActionPlanner output schema and validation contract."""

from typing import Literal, get_args

from pydantic import BaseModel, Field, ValidationError

from app.domains.routines.contracts.reply_writing import ReplyTaskText
from app.domains.social.schemas.feed import JointActivityProposalPreview
from app.domains.world_characters.schemas.activity_state import StateUpdate
from app.providers.contracts import StructuredOutputValidationError
from app.providers.gemini import build_gemini_developer_response_schema


ActionName = Literal["no_action", "comment", "like", "repost", "follow"]
ACTIVE_ACTIONS = tuple(action for action in get_args(ActionName) if action != "no_action")


class ProposalDecision(ReplyTaskText):
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
    thought: str | None = None


class ActionOutput(BaseModel):
    decisions: list[ActionChoice]
    state_update: StateUpdate | None
    state_source_refs: list[str] = Field(default_factory=list)


def planner_response_schema(candidates: list[dict], *, lane=None, policy=None) -> dict:
    """Add a Planner-only conditional without replacing the shared converter."""
    from app.domains.world_characters.contracts.social_io import LANE_IO
    from app.runtime.autonomous_activity.social_wire import judgement_model
    model = judgement_model(lane, candidates) if policy == LANE_IO else ActionOutput
    schema = build_gemini_developer_response_schema(model)
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


def parse_action(payload: dict, candidates: list[dict], *, lane=None, policy=None) -> dict:
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
    from app.domains.world_characters.contracts.social_io import LANE_IO
    from app.runtime.autonomous_activity.social_wire import judgement_model
    model = judgement_model(lane, candidates) if policy == LANE_IO else ActionOutput
    # Optional authored text is finalized only after the full name/macro pass.
    # Keep strict target/action/state validation independent of its raw type.
    raw_decisions = body.get("decisions")
    validation_body = dict(body)
    if isinstance(raw_decisions, list):
        validation_body["decisions"] = [
            {**row, "thought": None} if isinstance(row, dict) else row
            for row in raw_decisions
        ]
    parsed = model.model_validate({**validation_body, "state_update": None})
    by_id = {c["target_id"]: c for c in candidates}
    seen = set()
    missing_path = None
    brief_path = None
    for index, decision in enumerate(parsed.decisions):
        path = f"decisions.{index}"
        proposal = getattr(decision, "proposal", None)
        response = getattr(decision, "proposal_response", None)
        if decision.target_id in seen or decision.target_id not in by_id:
            raise StructuredOutputValidationError("decision_target_invalid", f"{path}.target_id")
        seen.add(decision.target_id)
        if policy == LANE_IO:
            source, wire = by_id[decision.target_id], body["decisions"][index]
            if ((lane == "feed" and "proposal" in wire and not source.get("proposal_eligible"))
                    or (lane == "inbox" and "proposal_response" in wire and not source.get("activity_proposal"))):
                raise StructuredOutputValidationError("proposal_capability_missing", path)
        if decision.action != "no_action" and decision.action not in by_id[decision.target_id]["allowed_actions"]:
            raise StructuredOutputValidationError("decision_action_not_allowed", f"{path}.action")
        if decision.action != "comment":
            if decision.interaction_intent in {"joint_activity_proposal", "proposal_response"} or response is not None or proposal is not None:
                raise StructuredOutputValidationError("non_comment_proposal_invalid", f"{path}.interaction_intent")
            decision.interaction_intent = decision.comment_purpose = None
        elif decision.interaction_intent is None or (decision.interaction_intent == "ordinary_comment" and decision.comment_purpose is None):
            # Defer recoverable omissions until every canonical target, action
            # and proposal has been checked. A fatal sibling is not repairable.
            if missing_path is None:
                field = "interaction_intent" if decision.interaction_intent is None else "comment_purpose"
                missing_path = f"{path}.{field}"
        if decision.interaction_intent == "joint_activity_proposal":
            if not by_id[decision.target_id].get("proposal_eligible") or proposal is None:
                raise StructuredOutputValidationError("proposal_not_eligible", f"{path}.proposal")
            if proposal.source_post_id != decision.target_id or proposal.target_world_character_id != by_id[decision.target_id].get("counterpart_id"):
                raise StructuredOutputValidationError("proposal_target_mismatch", f"{path}.proposal")
        elif proposal is not None:
            raise StructuredOutputValidationError("unexpected_proposal", f"{path}.proposal")
        if decision.interaction_intent == "proposal_response":
            if not by_id[decision.target_id].get("activity_proposal") or response is None or response.proposal_decision is None:
                raise StructuredOutputValidationError("proposal_response_missing", f"{path}.proposal_response")
        elif response is not None:
            raise StructuredOutputValidationError("unexpected_proposal_response", f"{path}.proposal_response")
        if decision.action != "no_action" and not decision.brief.strip():
            brief_path = brief_path or f"{path}.brief"
    if missing_path is not None:
        raise StructuredOutputValidationError("comment_intent_missing", missing_path)
    if brief_path is not None:
        raise StructuredOutputValidationError("action_brief_missing", brief_path)
    allowed_refs = {ref for c in candidates for ref in c["source_ids"]}
    if not set(refs) <= allowed_refs:
        state, refs, state_status = None, [], "invalid"
    return {"decisions": [{"proposal": None, "proposal_response": None, **d.model_dump(),
                          "thought": body["decisions"][index].get("thought")}
                         for index, d in enumerate(parsed.decisions)], "relationship_metrics": metrics,
            "state_update": state, "state_source_refs": refs, "state_status": state_status}
