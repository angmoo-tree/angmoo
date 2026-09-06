"""Proposal workflow construction for existing runtime callers."""
from __future__ import annotations
from datetime import date, datetime
from sqlalchemy.orm import Session
from app.domains.relationships import models
from app.domains.relationships.contracts.proposals import ProposalEligibility, ResolvedSchedule, ProposalResponseResult, ProposalPreview, ProposalPost, ProposalCharacter
from app.domains.relationships.exceptions import ActivityProposalRuntimeError
from app.domains.relationships.repository.proposals import find_open_proposal_for_source_post
from app.domains.relationships.service import proposals as proposal_service
from app.runtime.activity_proposals.references import SqlAlchemyProposalReferences


def proposal_eligibility(
    db: Session,
    *,
    actor_world_character_id: str,
    target_post_id: str,
    now: datetime,
) -> ProposalEligibility:
    return proposal_service.proposal_eligibility(
        db, references=SqlAlchemyProposalReferences(db),
        actor_world_character_id=actor_world_character_id,
        target_post_id=target_post_id,
        now=now,
    )


def validate_preview(
    db: Session,
    *,
    preview: ProposalPreview,
    world_id: str,
    proposer_world_character_id: str,
    target_post_id: str,
    now: datetime,
) -> tuple[ProposalCharacter, ProposalCharacter]:
    return proposal_service.validate_preview(
        db, references=SqlAlchemyProposalReferences(db),
        preview=preview,
        world_id=world_id,
        proposer_world_character_id=proposer_world_character_id,
        target_post_id=target_post_id,
        now=now,
    )


def create_published_proposal(
    db: Session,
    *,
    preview: ProposalPreview,
    proposal_comment: ProposalPost,
    proposal_event: models.SocialEvent,
    proposer_world_character_id: str,
    now: datetime,
) -> models.ActivityProposal:
    return proposal_service.create_published_proposal(
        db, references=SqlAlchemyProposalReferences(db),
        preview=preview,
        proposal_comment=proposal_comment,
        proposal_event=proposal_event,
        proposer_world_character_id=proposer_world_character_id,
        now=now,
    )


def resolve_acceptance_schedule(
    db: Session,
    *,
    proposal_id: str,
    now: datetime,
) -> ResolvedSchedule:
    return proposal_service.resolve_acceptance_schedule(
        db, references=SqlAlchemyProposalReferences(db),
        proposal_id=proposal_id,
        now=now,
    )


def apply_response(
    db: Session,
    *,
    proposal_id: str,
    response_event: models.SocialEvent,
    decision: str,
    now: datetime,
    resolved_schedule: ResolvedSchedule | None = None,
    counter_activity_seed: str | None = None,
    counter_place_key: str | None = None,
    counter_target_daypart: str | None = None,
    counter_date_policy: str | None = None,
    counter_target_date: date | None = None,
) -> ProposalResponseResult:
    return proposal_service.apply_response(
        db, references=SqlAlchemyProposalReferences(db),
        proposal_id=proposal_id,
        response_event=response_event,
        decision=decision,
        now=now,
        resolved_schedule=resolved_schedule,
        counter_activity_seed=counter_activity_seed,
        counter_place_key=counter_place_key,
        counter_target_daypart=counter_target_daypart,
        counter_date_policy=counter_date_policy,
        counter_target_date=counter_target_date,
    )
