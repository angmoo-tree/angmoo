from __future__ import annotations

from app.runtime.activity_proposals import composition as activity_proposal_runtime

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy.orm import Session

from app.domains.relationships.models import ActivityProposal, SocialEvent
from app.domains.routines.models import AgentPublicActionExecution
from app.domains.world_characters.models import WorldCharacter
from app.domains.social.models.posts import Notification
from app.domains.social.exceptions import LangGraphSocialApplyError
from app.domains.social.service import (
    action_sources,
    action_notifications,
    action_event_types,
)
from app.domains.relationships.contracts.action_response import (
    ProposalResponseInput,
    PreparedProposalResponse,
)
from app.domains.relationships.service import action_response as action_response_service
from app.domains.routines.service import public_action_executions
from app.runtime.activity_proposals.references import SqlAlchemyProposalReferences
from app.runtime.social.action_scope import RuntimeActionScopeReferences
from app.runtime.relationships import (
    sqlalchemy_social_event as social_event_runtime,
)


@dataclass(frozen=True)
class LangGraphSocialApplyResult:
    event: SocialEvent
    proposal_result: activity_proposal_runtime.ProposalResponseResult | None


def apply_successful_root_post(
    db: Session,
    *,
    actor_character_id: str,
    post_id: str,
    execution: AgentPublicActionExecution,
    occurred_at: datetime,
) -> LangGraphSocialApplyResult:
    """Attach a LangGraph root post to its World and canonical SocialEvent."""

    actor = active_world_character(db, character_id=actor_character_id)
    post = action_sources.prepare_root_post(db, actor=actor, post_id=post_id)
    public_action_executions.set_social_scope(
        execution, world_id=actor.world_id, actor_world_character_id=actor.id
    )
    db.flush()
    event = social_event_runtime.record_successful_social_event(
        db,
        world_id=actor.world_id,
        actor_world_character_id=actor.id,
        target_world_character_id=None,
        event_type="post_published",
        occurred_at=occurred_at,
        idempotency_key=sha256(
            f"langgraph|{execution.signature}|post_published".encode("utf-8")
        ).hexdigest(),
        evidence=social_event_runtime.EvidenceInput(
            evidence_kind="post",
            source_object_type="post",
            source_object_id=post.id,
            root_post_id=post.id,
            source_post_id=post.id,
            target_post_id=post.id,
            agent_run_id=execution.run_id,
            public_action_execution_id=execution.id,
            source_text="\n".join(part for part in (post.title, post.body) if part),
            source_visibility_at_event=post.visibility,
            source_author_id_at_event=actor.id,
        ),
    ).event
    public_action_executions.set_social_event_id(execution, social_event_id=event.id)
    db.flush()
    return LangGraphSocialApplyResult(event, None)


def active_world_character(db: Session, *, character_id: str) -> WorldCharacter:
    return RuntimeActionScopeReferences(db).active_world_character(
        character_id=character_id
    )


def proposal_for_notification(
    db: Session,
    *,
    recipient_character_id: str,
    source_post_id: str,
) -> ActivityProposal | None:
    try:
        world_character = active_world_character(
            db, character_id=recipient_character_id
        )
    except LangGraphSocialApplyError:
        return None
    source = action_sources.proposal_notification_source(
        db, source_post_id=source_post_id, world_id=world_character.world_id
    )
    if source is None:
        return None
    return activity_proposal_runtime.find_open_proposal_for_source_post(
        db,
        world_id=world_character.world_id,
        target_world_character_id=world_character.id,
        source_post_id=source_post_id,
    )


def prepare_proposal_response(
    db: Session, *, character_id: str, response: ProposalResponseInput, now: datetime
) -> PreparedProposalResponse:
    actor = active_world_character(db, character_id=character_id)
    return action_response_service.prepare_proposal_response(
        db,
        actor=actor,
        references=SqlAlchemyProposalReferences(db),
        error_type=LangGraphSocialApplyError,
        response=response,
        now=now,
    )


def apply_successful_public_action(
    db: Session,
    *,
    actor_character_id: str,
    action_type: str,
    target_post_id: str | None,
    target_character_id: str | None,
    action_result: dict[str, object],
    execution: AgentPublicActionExecution,
    occurred_at: datetime,
    notification_id: int | None = None,
    source_text: str | None = None,
    proposal_response: PreparedProposalResponse | None = None,
) -> LangGraphSocialApplyResult:
    actor = active_world_character(db, character_id=actor_character_id)
    target, target_post = action_sources._target_scope(
        db,
        references=RuntimeActionScopeReferences(db),
        actor=actor,
        action_type=action_type,
        target_post_id=target_post_id,
        target_character_id=target_character_id,
    )
    if proposal_response is not None:
        action_response_service.validate_public_response_scope(
            action_type=action_type,
            actor=actor,
            target=target,
            proposal_response=proposal_response,
            error_type=LangGraphSocialApplyError,
        )
    source, evidence_kind, source_type, source_id, source_post = (
        action_sources._source_evidence(
            db,
            references=RuntimeActionScopeReferences(db),
            action_type=action_type,
            actor=actor,
            target=target,
            target_post=target_post,
            action_result=action_result,
            execution=execution,
        )
    )
    public_action_executions.set_social_scope(
        execution, world_id=actor.world_id, actor_world_character_id=actor.id
    )
    public_action_executions.set_interaction_intent(
        execution,
        interaction_intent=(
            "proposal_response"
            if proposal_response is not None
            else execution.interaction_intent
        ),
    )
    db.flush()

    event_type = action_event_types._event_type(action_type, proposal_response)
    root_post_id = (
        action_sources._root_post_id(db, target_post)
        if target_post is not None
        else None
    )
    event = social_event_runtime.record_successful_social_event(
        db,
        world_id=actor.world_id,
        actor_world_character_id=actor.id,
        target_world_character_id=target.id,
        event_type=event_type,
        occurred_at=occurred_at,
        idempotency_key=sha256(
            f"langgraph|{execution.signature}|{event_type}".encode("utf-8")
        ).hexdigest(),
        evidence=social_event_runtime.EvidenceInput(
            evidence_kind=evidence_kind,
            source_object_type=source_type,
            source_object_id=source_id,
            root_post_id=root_post_id,
            source_post_id=(
                source_post.id if source_post is not None else target_post_id
            ),
            target_post_id=target_post_id,
            source_notification_id=notification_id,
            agent_run_id=execution.run_id,
            public_action_execution_id=execution.id,
            interaction_intent=execution.interaction_intent,
            comment_purpose=execution.comment_purpose,
            proposal_decision=(
                proposal_response.response.decision
                if proposal_response is not None
                else None
            ),
            source_text=source_text,
            source_visibility_at_event=(
                "public" if target_post is not None else "not_applicable"
            ),
            source_author_id_at_event=target.id,
        ),
    ).event
    public_action_executions.set_social_event_id(execution, social_event_id=event.id)

    proposal_result = None
    if proposal_response is not None:
        response = proposal_response.response
        proposal_result = activity_proposal_runtime.apply_response(
            db,
            proposal_id=proposal_response.proposal.id,
            response_event=event,
            decision=response.decision,
            now=occurred_at,
            resolved_schedule=proposal_response.resolved_schedule,
            counter_activity_seed=response.counter_activity_seed,
            counter_place_key=response.counter_place_key,
            counter_target_daypart=response.counter_target_daypart,
            counter_date_policy=response.counter_date_policy,
            counter_target_date=response.counter_target_date,
        )
        action_result["proposal_id"] = proposal_result.proposal.id
        if proposal_result.child_proposal is not None:
            action_result["counter_proposal_id"] = proposal_result.child_proposal.id
        if proposal_result.joint_activity is not None:
            action_result["joint_activity_id"] = proposal_result.joint_activity.id

    action_result["social_event_id"] = event.id
    action_notifications._link_notifications(
        db,
        input_notification_id=notification_id,
        actor=actor,
        target=target,
        source_post=source_post,
        target_post=target_post,
        event=event,
        occurred_at=occurred_at.astimezone(UTC),
        handling_outcome=(
            f"proposal_{proposal_response.response.decision}"
            if proposal_response is not None
            else action_type
        ),
        joint_activity_id=(
            proposal_result.joint_activity.id
            if proposal_result is not None
            and proposal_result.joint_activity is not None
            else None
        ),
    )
    db.flush()
    return LangGraphSocialApplyResult(event, proposal_result)


def mark_notification_handled_without_public_action(
    db: Session,
    *,
    actor_character_id: str,
    notification_id: int,
    handling_outcome: str,
    occurred_at: datetime,
) -> Notification:
    return action_notifications.mark_notification_handled_without_public_action(
        db,
        references=RuntimeActionScopeReferences(db),
        actor_character_id=actor_character_id,
        notification_id=notification_id,
        handling_outcome=handling_outcome,
        occurred_at=occurred_at,
    )
