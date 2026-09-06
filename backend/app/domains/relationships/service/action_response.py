"""Admission of proposed accept/reject/counter responses before public action."""

from collections.abc import Callable
from datetime import datetime
from sqlalchemy.orm import Session
from app.domains.relationships import models
from app.domains.relationships.contracts.action_response import (
    ProposalResponseInput,
    PreparedProposalResponse,
    ProposalResponseActor,
)
from app.domains.relationships.contracts.proposals import ProposalReferences
from app.domains.relationships.service.proposals import resolve_acceptance_schedule


def prepare_proposal_response(
    db: Session,
    *,
    actor: ProposalResponseActor,
    references: ProposalReferences,
    error_type: Callable[[str], Exception],
    response: ProposalResponseInput,
    now: datetime,
) -> PreparedProposalResponse:
    proposal = db.get(models.ActivityProposal, response.proposal_id)
    if (
        proposal is None
        or proposal.status != "proposed"
        or proposal.world_id != actor.world_id
        or proposal.target_world_character_id != actor.id
    ):
        raise error_type("proposal_response_not_allowed")
    if response.decision not in {"accept", "reject", "counter"}:
        raise error_type("proposal_decision_invalid")
    resolved = None
    if response.decision == "accept":
        resolved = resolve_acceptance_schedule(
            db, references=references, proposal_id=proposal.id, now=now
        )
    elif response.decision == "counter":
        if (
            not response.counter_activity_seed
            or response.counter_target_daypart
            not in {"dawn", "morning", "afternoon", "evening"}
            or response.counter_date_policy not in {"exact", "earliest_available"}
            or (
                response.counter_date_policy == "exact"
                and response.counter_target_date is None
            )
        ):
            raise error_type("proposal_counter_invalid")
    return PreparedProposalResponse(proposal, response, resolved)


def validate_public_response_scope(
    *,
    action_type: str,
    actor: ProposalResponseActor,
    target: ProposalResponseActor,
    proposal_response: PreparedProposalResponse,
    error_type: Callable[[str], Exception],
) -> None:
    proposal = proposal_response.proposal
    if (
        action_type != "reply"
        or proposal.world_id != actor.world_id
        or proposal.target_world_character_id != actor.id
        or proposal.proposer_world_character_id != target.id
    ):
        raise error_type("proposal_response_scope_invalid")
