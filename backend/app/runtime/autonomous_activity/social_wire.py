"""Small lane/capability contracts for new model requests, never historical readers."""
from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from app.domains.routines.contracts.reply_writing import ProposalResponseMeaning, RESPONSE_FIELDS
from app.domains.social.contracts.proposal_plan import ActivityProposalPlan
from app.domains.world_characters.schemas.activity_state import StateUpdate


class ResponseMeaning(ProposalResponseMeaning):
    model_config = ConfigDict(extra="forbid")


class ProposalMeaning(ActivityProposalPlan):
    model_config = ConfigDict(extra="forbid")


class OrdinaryAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_id: str
    action: Literal["no_action", "comment", "like", "repost", "follow"]
    interaction_intent: Literal["ordinary_comment"] | None = None
    comment_purpose: Literal["question", "advice", "empathy", "encouragement", "information", "humor",
        "disagreement", "competition", "observation"] | None = None
    brief: str = Field(default="", max_length=280)
    thought: str | None = None


class FeedAction(OrdinaryAction):
    interaction_intent: Literal["ordinary_comment", "joint_activity_proposal"] | None = None
    proposal: ProposalMeaning | None = None


class InboxAction(OrdinaryAction):
    interaction_intent: Literal["ordinary_comment", "proposal_response"] | None = None
    proposal_response: ResponseMeaning | None = None


class SocialJudgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state_update: StateUpdate | None
    state_source_refs: list[str] = Field(default_factory=list)


_OUTPUTS = {
    (lane, capable): create_model(f"{lane.title()}{'Capable' if capable else 'Ordinary'}Judgement",
        __base__=SocialJudgement, decisions=(list[choice], ...))
    for lane, capable, choice in (("feed", False, OrdinaryAction), ("feed", True, FeedAction),
        ("inbox", False, OrdinaryAction), ("inbox", True, InboxAction))
}


def judgement_model(lane, candidates):
    capable = any(candidate.get("proposal_eligible") if lane == "feed"
        else candidate.get("activity_proposal") for candidate in candidates)
    return _OUTPUTS[(lane, capable)]


def target_view(value, lane, *, preview=False):
    """Project a copy only; canonical candidates and opposite lane retain every value."""
    excluded = {"parent_text", "waiting_since", "activity_proposal"} if lane == "feed" else {
        "topic_signature", "proposal_eligible"}
    if preview and lane == "feed":
        excluded.add("parent_text_partial")
    return {key: deepcopy(item) for key, item in value.items() if key not in excluded}


def assignment_view(assignments, lane):
    return [{**deepcopy(task), "source": target_view(task.get("source", {}), lane)} for task in assignments]


def restrict_reply_schema(schema, lane, can_respond):
    result = deepcopy(schema)
    item = result["properties"]["replies"]["items"]
    if lane == "feed" or not can_respond:
        item["properties"] = {key: value for key, value in item["properties"].items() if key not in RESPONSE_FIELDS}
        item["required"] = [key for key in item.get("required", []) if key not in RESPONSE_FIELDS]
    return result


def validate_reply_wire(value, lane, can_respond, *, combined=False, assignments=None):
    """Strict new wire; canonical Writer validation still owns tasks, bodies and counters."""
    if not isinstance(value, dict) or set(value) != {"replies"} or not isinstance(value["replies"], list):
        raise ValueError("social_draft_wire_invalid")
    allowed = {"target_id" if combined else "task_id", "body", "thought"}
    if lane == "inbox" and can_respond:
        allowed.update(RESPONSE_FIELDS)
    for row in value["replies"]:
        if not isinstance(row, dict) or set(row) - allowed:
            raise ValueError("social_draft_field_forbidden")
        if assignments is not None and RESPONSE_FIELDS & set(row):
            key = "target_id" if combined else "task_id"
            tasks = {task["source"]["target_id"] if combined else task["task_id"]: task
                     for task in assignments}
            task = tasks.get(row.get(key))
            if task is None or task.get("proposal_response") is None:
                raise ValueError("social_draft_field_forbidden")
