"""Dispatch one validated Social action and preserve its exact source identity."""

from app.domains.social.schemas import feed as schemas
from app.domains.social.schemas.community import (
    PostLikeCreate,
    TimelineReplyCreate,
    FollowCreate,
)
from app.domains.social.contracts.feed_execution import (
    WorldFeedContext,
    FeedPublishingWorkflows,
)
from app.domains.social.exceptions import FeedReactionValidationError


def _publish_action(
    ctx: WorldFeedContext,
    *,
    workflows: FeedPublishingWorkflows,
    candidate: schemas.WorldFeedCandidateRead,
    decision: schemas.FeedReactionDecision,
    draft: schemas.FeedCommentDraft | schemas.JointActivityProposalPreview | None,
) -> dict[str, object]:
    action = decision.selected_action
    if action == "like":
        post = workflows.like_agent_tool_post(
            ctx.db,
            ctx.session_key,
            candidate.post_id,
            PostLikeCreate(character_id=ctx.character.id),
        )
        return {"post_id": post.id, "action": "like"}
    if action == "comment":
        if draft is None:
            raise FeedReactionValidationError("ordinary comment draft is missing")
        reply = workflows.reply_agent_tool_post(
            ctx.db,
            ctx.session_key,
            candidate.post_id,
            TimelineReplyCreate(
                body=draft.text,
                author_character_id=ctx.character.id,
            ),
        )
        return {
            "post_id": reply.id,
            "reply_to_post_id": candidate.post_id,
            "action": "comment",
        }
    if action == "repost":
        repost = workflows.repost_agent_tool_post(
            ctx.db,
            ctx.session_key,
            candidate.post_id,
            PostLikeCreate(character_id=ctx.character.id),
        )
        return {
            "post_id": repost.id,
            "repost_of_post_id": candidate.post_id,
            "action": "repost",
        }
    if action == "follow":
        follow = workflows.follow_agent_tool_profile(
            ctx.db,
            ctx.session_key,
            FollowCreate(
                target_type="character",
                target_id=candidate.author_character_id,
                follower_character_id=ctx.character.id,
            ),
        )
        return {
            "target_character_id": follow.target.id,
            "source_post_id": candidate.post_id,
            "action": "follow",
        }
    raise FeedReactionValidationError("unsupported feed action")
