"""Validate original posts/reactions and attach successful Social evidence."""

from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models
from app.domains.social.contracts.source_writes import SourceWorldCharacter
from app.domains.social.contracts.subjective_persistence import SubjectiveExecution
from app.domains.social.contracts.action_scope import ActionScopeReferences
from app.domains.social.exceptions import (
    LangGraphSocialApplyError,
    WorldFeedSocialApplyError,
)


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


def _root_post_id(db: Session, post: models.Post) -> str:
    current = post
    seen = {post.id}
    for _ in range(20):
        parent_id = current.reply_to_post_id
        if not parent_id:
            return current.id
        if parent_id in seen:
            raise LangGraphSocialApplyError("post_reply_cycle")
        seen.add(parent_id)
        parent = db.get(models.Post, parent_id)
        if parent is None or parent.world_id != post.world_id:
            raise LangGraphSocialApplyError("post_root_invalid")
        current = parent
    raise LangGraphSocialApplyError("post_reply_depth_exceeded")


def _target_scope(
    db: Session,
    *,
    references: ActionScopeReferences,
    actor: SourceWorldCharacter,
    action_type: str,
    target_post_id: str | None,
    target_character_id: str | None,
) -> tuple[SourceWorldCharacter, models.Post | None]:
    if target_post_id is not None:
        post = db.get(models.Post, target_post_id)
        if (
            post is None
            or post.world_id != actor.world_id
            or post.author_character_id is None
            or post.author_world_character_id is None
        ):
            raise LangGraphSocialApplyError("target_post_world_invalid")
        target = references.get_world_character(post.author_world_character_id)
        if (
            target is None
            or target.world_id != actor.world_id
            or target.character_id != post.author_character_id
        ):
            raise LangGraphSocialApplyError("target_post_author_invalid")
        return target, post
    if action_type not in {"follow", "unfollow"} or not target_character_id:
        raise LangGraphSocialApplyError("target_world_character_required")
    return (
        references.world_character_for_character(
            world_id=actor.world_id,
            character_id=target_character_id,
        ),
        None,
    )


def _source_evidence(
    db: Session,
    *,
    references: ActionScopeReferences,
    action_type: str,
    actor: SourceWorldCharacter,
    target: SourceWorldCharacter,
    target_post: models.Post | None,
    action_result: dict[str, object],
    execution: SubjectiveExecution,
) -> tuple[object, str, str, str, models.Post | None]:
    if action_type == "reply":
        reply_id = str(action_result.get("post_id") or "")
        row = db.get(models.Post, reply_id)
        if (
            row is None
            or target_post is None
            or row.reply_to_post_id != target_post.id
            or row.world_id != actor.world_id
            or row.author_world_character_id != actor.id
        ):
            raise LangGraphSocialApplyError("reply_evidence_missing")
        return row, "reply_post", "post", row.id, row
    if action_type == "like":
        if target_post is None:
            raise LangGraphSocialApplyError("like_target_missing")
        row = db.scalar(
            select(models.PostLike).where(
                models.PostLike.post_id == target_post.id,
                models.PostLike.character_id == actor.character_id,
            )
        )
        if row is None:
            raise LangGraphSocialApplyError("like_evidence_missing")
        row.world_id = actor.world_id
        row.actor_world_character_id = actor.id
        row.target_world_character_id = target.id
        return row, "like", "post_like", str(row.id), None
    if action_type == "repost":
        if target_post is None:
            raise LangGraphSocialApplyError("repost_target_missing")
        row = db.scalar(
            select(models.PostRepost).where(
                models.PostRepost.post_id == target_post.id,
                models.PostRepost.character_id == actor.character_id,
            )
        )
        if row is None:
            raise LangGraphSocialApplyError("repost_evidence_missing")
        row.world_id = actor.world_id
        row.actor_world_character_id = actor.id
        row.target_world_character_id = target.id
        return row, "repost", "post_repost", str(row.id), None
    if action_type == "follow":
        row = db.scalar(
            select(models.ProfileFollow).where(
                models.ProfileFollow.follower_character_id == actor.character_id,
                models.ProfileFollow.target_character_id == target.character_id,
            )
        )
        if row is None:
            raise LangGraphSocialApplyError("follow_evidence_missing")
        row.world_id = actor.world_id
        row.follower_world_character_id = actor.id
        row.target_world_character_id = target.id
        return row, "follow", "profile_follow", str(row.id), None
    if action_type == "unfollow":
        references.set_execution_scope(
            execution, world_id=actor.world_id, actor_world_character_id=actor.id
        )
        db.flush()
        return (
            execution,
            "execution",
            "agent_public_action_execution",
            str(execution.id),
            None,
        )
    raise LangGraphSocialApplyError("unsupported_public_action")


def prepare_root_post(
    db: Session, *, actor: SourceWorldCharacter, post_id: str
) -> models.Post:
    post = db.get(models.Post, post_id)
    if (
        post is None
        or post.author_character_id != actor.character_id
        or post.reply_to_post_id is not None
    ):
        raise LangGraphSocialApplyError("root_post_evidence_invalid")
    if post.world_id not in {
        None,
        actor.world_id,
    } or post.author_world_character_id not in {
        None,
        actor.id,
    }:
        raise LangGraphSocialApplyError("root_post_world_scope_invalid")
    post.world_id = actor.world_id
    post.author_world_character_id = actor.id
    return post


def attach_world_feed_source(
    source: object,
    *,
    world_id: str,
    actor_world_character_id: str,
    target_world_character_id: str,
) -> None:
    if isinstance(source, (models.PostLike, models.PostRepost)):
        source.world_id = world_id
        source.actor_world_character_id = actor_world_character_id
        source.target_world_character_id = target_world_character_id
    elif isinstance(source, models.ProfileFollow):
        source.world_id = world_id
        source.follower_world_character_id = actor_world_character_id
        source.target_world_character_id = target_world_character_id
    elif isinstance(source, models.Post):
        if (
            source.world_id != world_id
            or source.author_world_character_id != actor_world_character_id
        ):
            raise WorldFeedSocialApplyError("comment_world_scope_invalid")


def proposal_notification_source(
    db: Session, *, source_post_id: str, world_id: str
) -> models.Post | None:
    source = db.get(models.Post, source_post_id)
    if source is None or source.world_id != world_id:
        return None
    return source


def require_proposal_comment(source: object) -> models.Post:
    if not isinstance(source, models.Post):
        raise WorldFeedSocialApplyError("proposal_comment_missing")
    return source
