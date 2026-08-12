from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.services import activity_proposal_runtime, social_event_runtime
from app.services.world_feed_search import ReadySearchProfile


class WorldFeedSocialApplyError(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class WorldFeedSocialApplyResult:
    event: models.SocialEvent
    proposal: models.ActivityProposal | None


def _source_row(
    db: Session,
    *,
    action: str,
    actor_character_id: str,
    target_character_id: str,
    target_post_id: str,
    action_result: dict[str, object],
) -> tuple[object, str, str, str]:
    if action == "comment":
        reply_id = str(action_result.get("post_id") or "")
        row = db.get(models.Post, reply_id)
        if row is None or row.reply_to_post_id != target_post_id:
            raise WorldFeedSocialApplyError("comment_evidence_missing")
        return row, "reply_post", "post", row.id
    if action == "like":
        row = db.scalar(
            select(models.PostLike).where(
                models.PostLike.post_id == target_post_id,
                models.PostLike.character_id == actor_character_id,
            )
        )
        if row is None:
            raise WorldFeedSocialApplyError("like_evidence_missing")
        return row, "like", "post_like", str(row.id)
    if action == "repost":
        row = db.scalar(
            select(models.PostRepost).where(
                models.PostRepost.post_id == target_post_id,
                models.PostRepost.character_id == actor_character_id,
            )
        )
        if row is None:
            raise WorldFeedSocialApplyError("repost_evidence_missing")
        return row, "repost", "post_repost", str(row.id)
    if action == "follow":
        row = db.scalar(
            select(models.ProfileFollow).where(
                models.ProfileFollow.follower_character_id == actor_character_id,
                models.ProfileFollow.target_character_id == target_character_id,
            )
        )
        if row is None:
            raise WorldFeedSocialApplyError("follow_evidence_missing")
        return row, "follow", "profile_follow", str(row.id)
    raise WorldFeedSocialApplyError("unsupported_feed_action")


def apply_successful_world_feed_action(
    db: Session,
    *,
    profile: ReadySearchProfile,
    candidate: schemas.WorldFeedCandidateRead,
    decision: schemas.FeedReactionDecision,
    draft: schemas.FeedCommentDraft | schemas.JointActivityProposalPreview | None,
    action_result: dict[str, object],
    execution: models.AgentPublicActionExecution,
    occurred_at: datetime,
) -> WorldFeedSocialApplyResult:
    action = str(decision.selected_action or "")
    source, evidence_kind, source_type, source_id = _source_row(
        db,
        action=action,
        actor_character_id=profile.character.id,
        target_character_id=candidate.author_character_id,
        target_post_id=candidate.post_id,
        action_result=action_result,
    )
    if isinstance(source, (models.PostLike, models.PostRepost)):
        source.world_id = profile.world.id
        source.actor_world_character_id = profile.world_character.id
        source.target_world_character_id = candidate.author_world_character_id
    elif isinstance(source, models.ProfileFollow):
        source.world_id = profile.world.id
        source.follower_world_character_id = profile.world_character.id
        source.target_world_character_id = candidate.author_world_character_id
    elif isinstance(source, models.Post):
        if (
            source.world_id != profile.world.id
            or source.author_world_character_id != profile.world_character.id
        ):
            raise WorldFeedSocialApplyError("comment_world_scope_invalid")
    db.flush()

    proposal_preview = (
        draft if isinstance(draft, schemas.JointActivityProposalPreview) else None
    )
    event_type = {
        "comment": "joint_proposed" if proposal_preview is not None else "comment_created",
        "like": "like_added",
        "repost": "repost_added",
        "follow": "follow_added",
    }[action]
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
                source.id if isinstance(source, models.Post) else candidate.post_id
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
        if not isinstance(source, models.Post):
            raise WorldFeedSocialApplyError("proposal_comment_missing")
        proposal = activity_proposal_runtime.create_published_proposal(
            db,
            preview=proposal_preview,
            proposal_comment=source,
            proposal_event=event,
            proposer_world_character_id=profile.world_character.id,
            now=occurred_at,
        )
    notification_type = {
        "comment": "reply",
        "like": "like",
        "repost": "repost",
        "follow": "follow",
    }[action]
    notification_query = select(models.Notification).where(
        models.Notification.notification_type == notification_type,
        models.Notification.recipient_character_id == candidate.author_character_id,
        models.Notification.actor_character_id == profile.character.id,
    )
    if isinstance(source, models.Post):
        notification_query = notification_query.where(
            models.Notification.source_post_id == source.id
        )
    elif action in {"like", "repost"}:
        notification_query = notification_query.where(
            models.Notification.post_id == candidate.post_id
        )
    notification = db.scalar(
        notification_query.order_by(models.Notification.id.desc()).limit(1)
    )
    if notification is not None:
        notification.world_id = profile.world.id
        notification.recipient_world_character_id = (
            candidate.author_world_character_id
        )
        notification.actor_world_character_id = profile.world_character.id
        notification.source_social_event_id = event.id
        if proposal is not None:
            notification.data = (
                '{"kind":"activity_proposal","proposal_id":"'
                + proposal.id
                + '"}'
            )
    action_result["social_event_id"] = event.id
    if proposal is not None:
        action_result["proposal_id"] = proposal.id
    db.flush()
    return WorldFeedSocialApplyResult(event, proposal)
