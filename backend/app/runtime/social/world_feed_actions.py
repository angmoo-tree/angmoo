from __future__ import annotations

from app.runtime.activity_proposals import composition as activity_proposal_runtime

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from sqlalchemy.orm import Session

from app.domains.relationships.models import ActivityProposal, SocialEvent
from app.domains.routines.models import AgentPublicActionExecution
from app.domains.social.models.posts import Post
from app.domains.social.schemas import feed as schemas
from app.domains.social.exceptions import WorldFeedSocialApplyError
from app.domains.social.service import (
    action_sources,
    action_notifications,
    action_event_types,
)
from app.domains.routines.service import public_action_executions
from app.runtime.relationships import (
    sqlalchemy_social_event as social_event_runtime,
)

from app.domains.social.contracts.action_scope import WorldFeedActionProfile


@dataclass(frozen=True)
class WorldFeedSocialApplyResult:
    event: SocialEvent
    proposal: ActivityProposal | None


def apply_successful_world_feed_action(
    db: Session,
    *,
    profile: WorldFeedActionProfile,
    candidate: schemas.WorldFeedCandidateRead,
    decision: schemas.FeedReactionDecision,
    draft: schemas.FeedCommentDraft | schemas.JointActivityProposalPreview | None,
    action_result: dict[str, object],
    execution: AgentPublicActionExecution,
    occurred_at: datetime,
) -> WorldFeedSocialApplyResult:
    action = str(decision.selected_action or "")
    source, evidence_kind, source_type, source_id = action_sources._source_row(
        db,
        action=action,
        actor_character_id=profile.character.id,
        target_character_id=candidate.author_character_id,
        target_post_id=candidate.post_id,
        action_result=action_result,
    )
    action_sources.attach_world_feed_source(
        source,
        world_id=profile.world.id,
        actor_world_character_id=profile.world_character.id,
        target_world_character_id=candidate.author_world_character_id,
    )
    db.flush()

    proposal_preview = (
        draft if isinstance(draft, schemas.JointActivityProposalPreview) else None
    )
    event_type = action_event_types.world_feed_event_type(
        action, has_proposal=proposal_preview is not None
    )
    source_text = draft.text if draft is not None else None
    event = social_event_runtime.record_successful_social_event(
        db,
        world_id=profile.world.id,
        actor_world_character_id=profile.world_character.id,
        target_world_character_id=candidate.author_world_character_id,
        event_type=event_type,
        occurred_at=occurred_at,
        idempotency_key=sha256(
            f"p5|{execution.signature}|{event_type}".encode("utf-8")
        ).hexdigest(),
        evidence=social_event_runtime.EvidenceInput(
            evidence_kind=evidence_kind,
            source_object_type=source_type,
            source_object_id=source_id,
            root_post_id=candidate.post_id,
            source_post_id=(
                source.id if isinstance(source, Post) else candidate.post_id
            ),
            target_post_id=candidate.post_id,
            agent_run_id=execution.run_id,
            public_action_execution_id=execution.id,
            interaction_intent=decision.interaction_intent,
            comment_purpose=decision.comment_purpose,
            source_text=source_text,
            source_visibility_at_event="public",
            source_author_id_at_event=candidate.author_world_character_id,
        ),
    ).event
    proposal = None
    if proposal_preview is not None:
        action_sources.require_proposal_comment(source)
        proposal = activity_proposal_runtime.create_published_proposal(
            db,
            preview=proposal_preview,
            proposal_comment=source,
            proposal_event=event,
            proposer_world_character_id=profile.world_character.id,
            now=occurred_at,
        )
    action_notifications.link_world_feed_notification(
        db,
        action=action,
        source=source,
        world_id=profile.world.id,
        actor_character_id=profile.character.id,
        target_character_id=candidate.author_character_id,
        actor_world_character_id=profile.world_character.id,
        target_world_character_id=candidate.author_world_character_id,
        target_post_id=candidate.post_id,
        social_event_id=event.id,
        proposal_id=proposal.id if proposal is not None else None,
    )
    action_result["social_event_id"] = event.id
    public_action_executions.set_social_event_id(execution, social_event_id=event.id)
    if proposal is not None:
        action_result["proposal_id"] = proposal.id
    db.flush()
    return WorldFeedSocialApplyResult(event, proposal)
