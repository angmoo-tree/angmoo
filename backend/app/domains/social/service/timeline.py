"""Post, reply, reaction, report and deletion workflows."""
from datetime import UTC, datetime
from uuid import uuid4
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models
from app.domains.social.schemas import community as schemas
from app.domains.social.contracts.actors import SocialUser, SocialCharacter
from app.domains.social.contracts.timeline import SocialWriteWorkflows
from app.domains.social.exceptions import (PostNotFoundError, PostReportNotAllowedError, CommunityQuotaExceeded, CommunityRateLimitedError, CharacterOwnershipError, CharacterNotFoundError, CharacterSuspendedError, PostWorldScopeError, LegacyCommentsDisabledError)
from app.domains.social.repository import posts as post_repository, reactions
from app.domains.social.service import source_posts
from app.domains.social.service.activity_results import build_post_created_activity_result
from app.domains.social.service.presentation import _post_detail
from app.domains.social.service.visibility import _is_post_public_context_visible
from app.domains.social.service.notifications import _notify_post_owner, _notify_mentioned_characters
from app.domains.characters.service import profile as character_profile
from app.domains.world_characters.service import social_scope


def _resolve_author_character(
    db: Session, user: SocialUser, character_id: str | None
) -> SocialCharacter | None:
    if character_id is None:
        return None
    character = character_profile.get_character(db, character_id)
    if character is None:
        raise CharacterNotFoundError(character_id)
    if character.deleted_at is not None:
        raise CharacterNotFoundError(character_id)
    if character.owner_id != user.id:
        raise CharacterOwnershipError(
            f"user {user.id} cannot act as character {character.id}"
        )
    if character.moderation_status == "suspended":
        raise CharacterSuspendedError("character_suspended")
    return character


def _can_delete_post(db: Session, user: SocialUser, post: models.Post) -> bool:
    if post.author_character_id is not None:
        character = character_profile.get_character(db, post.author_character_id)
        return character is not None and character.owner_id == user.id
    return post.author_user_id == user.id


def _reply_title(title: str) -> str:
    return f"Re: {title}"[:160]


def _quote_title(title: str) -> str:
    return f"Quote: {title}"[:160]


def _timeline_world_scope(
    db: Session,
    *,
    target: models.Post,
    character: SocialCharacter | None,
) -> tuple[str | None, str | None]:
    if target.world_id is None:
        return None, None
    if character is None:
        raise PostWorldScopeError("world_scope_requires_character")
    try:
        world_character_id = social_scope.resolve_social_target_scope(
            db, target_world_id=target.world_id, character=character,
        )
    except social_scope.WorldCharacterSocialScopeError as exc:
        raise PostWorldScopeError(str(exc)) from exc
    return target.world_id, world_character_id


def create_comment(
    db: Session, post_id: str, data: schemas.CommentCreate
) -> schemas.CommentRead:
    raise LegacyCommentsDisabledError(
        "Legacy comments are disabled. Use /posts/{post_id}/replies."
    )


class SocialTimelineService:
    def __init__(self, workflows: SocialWriteWorkflows) -> None:
        self.workflows = workflows

    def report_post(self,
        db: Session, user: SocialUser, post_id: str, data: schemas.PostReportCreate
    ) -> schemas.PostReportRead:
        post = post_repository.get_post_including_report_hidden(db, post_id)
        if post is None:
            raise PostNotFoundError(post_id)
        if post_repository.is_report_hidden(post):
            raise PostNotFoundError(post_id)
        if _can_delete_post(db, user, post):
            raise PostReportNotAllowedError("cannot report your own post")
        try:
            self.workflows.consume_quota(
                db,
                user_id=user.id,
                action="report",
            )
        except CommunityQuotaExceeded as exc:
            raise CommunityRateLimitedError(exc.retry_after_seconds) from exc

        _report, created = reactions.create_post_report(
            db, post=post, reporter_user=user, data=data
        )
        if not created:
            return schemas.PostReportRead(
                status="already_reported",
                already_reported=True,
                report_hidden=post_repository.is_report_hidden(post),
            )

        report_count = post_repository.count_post_reports(db, post.id)
        post.report_count = report_count
        db.commit()
        db.refresh(post)
        return schemas.PostReportRead(
            status="reported",
            already_reported=False,
            report_hidden=post_repository.is_report_hidden(post),
        )

    def delete_post(self, db: Session, user: SocialUser, post_id: str) -> None:
        post = post_repository.get_post(db, post_id)
        if post is None:
            raise PostNotFoundError(post_id)
        if not _can_delete_post(db, user, post):
            raise CharacterOwnershipError(f"user {user.id} cannot delete post {post.id}")

        deleted_at = datetime.now(UTC)
        if post.post_type == "repost":
            post_repository.delete_repost_event_for_timeline_post(db, post=post)

        deleted_posts = post_repository.soft_delete_post_tree(
            db, post=post, deleted_at=deleted_at
        )
        index = 0
        while index < len(deleted_posts):
            deleted_post = deleted_posts[index]
            post_repository.delete_repost_events_for_post(db, post=deleted_post)
            timeline_reposts = post_repository.soft_delete_timeline_reposts_for_source(
                db, post=deleted_post, deleted_at=deleted_at
            )
            for timeline_repost in timeline_reposts:
                deleted_posts.extend(
                    post_repository.soft_delete_post_tree(
                        db, post=timeline_repost, deleted_at=deleted_at
                    )
                )
            index += 1

        self.workflows.exclude_events_for_posts(
            db,
            post_ids=[deleted_post.id for deleted_post in deleted_posts],
            reason="source_deleted",
            invalidated_at=deleted_at,
        )
        db.commit()

    def create_post(self,
        db: Session,
        user: SocialUser,
        data: schemas.PostCreate,
        *,
        log_manual_activity: bool = True,
        post_info: schemas.PostInfoMetadata | None = None,
        world_id: str | None = None,
        author_world_character_id: str | None = None,
    ) -> schemas.PostDetail:
        character = None
        if data.author_character_id:
            character = character_profile.get_character(db, data.author_character_id)
            if character is None or character.deleted_at is not None:
                raise CharacterNotFoundError(data.author_character_id)
            if character.owner_id != user.id:
                raise CharacterOwnershipError(
                    f"user {user.id} cannot post as character {character.id}"
                )
            if character.moderation_status == "suspended":
                raise CharacterSuspendedError("character_suspended")
        if (world_id is None) != (author_world_character_id is None):
            raise PostWorldScopeError("world_scope_pair_required")
        if world_id is not None and author_world_character_id is not None:
            if character is None:
                raise PostWorldScopeError("world_scope_requires_character")
            try:
                social_scope.validate_social_author_scope(
                    db, world_id=world_id, author_world_character_id=author_world_character_id, character=character,
                )
            except social_scope.WorldCharacterSocialScopeError as exc:
                raise PostWorldScopeError(str(exc)) from exc
        post = source_posts.create_post(
            db,
            post_id=f"post-{uuid4().hex[:12]}",
            user=user,
            character=character,
            data=data,
            post_info=post_info,
            world_id=world_id,
            author_world_character_id=author_world_character_id,
        )
        if character is not None and log_manual_activity:
            result = build_post_created_activity_result(
                post_id=post.id,
                title=post.title,
                body=post.body,
                message=f"Created post {post.id}.",
            )
            self.workflows.log_activity(
                db,
                user_id=user.id,
                character_id=character.id,
                action_type="post_created",
                target_post_id=post.id,
                reason="manual_post",
                result=result,
            )
        _notify_mentioned_characters(
            db,
            post=post,
            actor_user_id=user.id if character is None else None,
            actor_character_id=character.id if character else None,
        )
        return _post_detail(db, post)

    def create_reply(self,
        db: Session,
        user: SocialUser,
        post_id: str,
        data: schemas.TimelineReplyCreate,
        *,
        activity_reason: str = "manual_reply",
        enforce_user_quota: bool = True,
    ) -> schemas.PostDetail:
        parent = post_repository.get_post(db, post_id)
        if parent is None or not _is_post_public_context_visible(db, parent):
            raise PostNotFoundError(post_id)
        if enforce_user_quota:
            try:
                self.workflows.consume_quota(
                    db,
                    user_id=user.id,
                    action="reply",
                )
            except CommunityQuotaExceeded as exc:
                raise CommunityRateLimitedError(exc.retry_after_seconds) from exc
        character = _resolve_author_character(db, user, data.author_character_id)
        world_id, author_world_character_id = _timeline_world_scope(
            db,
            target=parent,
            character=character,
        )
        reply = source_posts.create_timeline_post(
            db,
            post_id=f"post-{uuid4().hex[:12]}",
            user=user,
            character=character,
            title=_reply_title(parent.title),
            body=data.body,
            post_type="reply",
            reply_to_post_id=parent.id,
            world_id=world_id,
            author_world_character_id=author_world_character_id,
        )
        if character is not None:
            self.workflows.log_activity(
                db,
                user_id=user.id,
                character_id=character.id,
                action_type="replied",
                target_post_id=parent.id,
                reason=activity_reason,
                result=f"Created reply {reply.id}.",
            )
        _notify_post_owner(
            db,
            notification_type="reply",
            post=parent,
            source_post_id=reply.id,
            actor_user_id=user.id if character is None else None,
            actor_character_id=character.id if character else None,
        )
        _notify_mentioned_characters(
            db,
            post=reply,
            actor_user_id=user.id if character is None else None,
            actor_character_id=character.id if character else None,
            skip_character_ids=[parent.author_character_id],
        )
        return _post_detail(db, reply)

    def create_quote(self,
        db: Session,
        user: SocialUser,
        post_id: str,
        data: schemas.TimelineQuoteCreate,
        *,
        activity_reason: str = "manual_quote",
    ) -> schemas.PostDetail:
        quoted = post_repository.get_post(db, post_id)
        if quoted is None or not _is_post_public_context_visible(db, quoted):
            raise PostNotFoundError(post_id)
        character = _resolve_author_character(db, user, data.author_character_id)
        world_id, author_world_character_id = _timeline_world_scope(
            db,
            target=quoted,
            character=character,
        )
        quote = source_posts.create_timeline_post(
            db,
            post_id=f"post-{uuid4().hex[:12]}",
            user=user,
            character=character,
            title=(data.title or _quote_title(quoted.title)),
            body=data.body,
            post_type="quote",
            quote_post_id=quoted.id,
            world_id=world_id,
            author_world_character_id=author_world_character_id,
        )
        if character is not None:
            self.workflows.log_activity(
                db,
                user_id=user.id,
                character_id=character.id,
                action_type="quoted",
                target_post_id=quoted.id,
                reason=activity_reason,
                result=f"Created quote {quote.id}.",
            )
        _notify_post_owner(
            db,
            notification_type="quote",
            post=quoted,
            source_post_id=quote.id,
            actor_user_id=user.id if character is None else None,
            actor_character_id=character.id if character else None,
        )
        _notify_mentioned_characters(
            db,
            post=quote,
            actor_user_id=user.id if character is None else None,
            actor_character_id=character.id if character else None,
            skip_character_ids=[quoted.author_character_id],
        )
        return _post_detail(db, quote)

    def like_post(self,
        db: Session,
        user: SocialUser,
        post_id: str,
        data: schemas.PostLikeCreate,
        *,
        activity_reason: str = "manual_like",
    ) -> schemas.PostDetail:
        post = post_repository.get_post(db, post_id)
        if post is None or not _is_post_public_context_visible(db, post):
            raise PostNotFoundError(post_id)
        character = _resolve_author_character(db, user, data.character_id)
        _like, created = reactions.like_post(
            db, post=post, user=user, character=character
        )
        if character is not None and created:
            self.workflows.log_activity(
                db,
                user_id=user.id,
                character_id=character.id,
                action_type="liked",
                target_post_id=post.id,
                reason=activity_reason,
                result=f"Liked post {post.id}.",
            )
        if created:
            _notify_post_owner(
                db,
                notification_type="like",
                post=post,
                source_post_id=None,
                actor_user_id=user.id if character is None else None,
                actor_character_id=character.id if character else None,
            )
        return _post_detail(db, post)

    def unlike_post(self,
        db: Session, user: SocialUser, post_id: str, data: schemas.PostLikeCreate
    ) -> schemas.PostDetail:
        post = post_repository.get_post(db, post_id)
        if post is None or not _is_post_public_context_visible(db, post):
            raise PostNotFoundError(post_id)
        character = _resolve_author_character(db, user, data.character_id)
        reactions.unlike_post(db, post=post, user=user, character=character)
        return _post_detail(db, post)

    def repost_post(self,
        db: Session,
        user: SocialUser,
        post_id: str,
        data: schemas.PostLikeCreate,
        *,
        activity_reason: str = "manual_repost",
    ) -> schemas.PostDetail:
        post = post_repository.get_post(db, post_id)
        if post is None or not _is_post_public_context_visible(db, post):
            raise PostNotFoundError(post_id)
        character = _resolve_author_character(db, user, data.character_id)
        world_id, author_world_character_id = _timeline_world_scope(
            db,
            target=post,
            character=character,
        )
        existing_timeline_repost = reactions.get_timeline_repost(
            db, post=post, user=user, character=character
        )
        _repost, created = reactions.create_repost(
            db, post=post, user=user, character=character
        )
        if existing_timeline_repost is not None:
            return _post_detail(db, existing_timeline_repost)
        timeline_repost = source_posts.create_timeline_post(
            db,
            post_id=f"post-{uuid4().hex[:12]}",
            user=user,
            character=character,
            title=f"Repost: {post.title}"[:160],
            body="",
            post_type="repost",
            repost_of_post_id=post.id,
            world_id=world_id,
            author_world_character_id=author_world_character_id,
        )
        if character is not None and created:
            self.workflows.log_activity(
                db,
                user_id=user.id,
                character_id=character.id,
                action_type="reposted",
                target_post_id=post.id,
                reason=activity_reason,
                result=f"Reposted post {post.id} as {timeline_repost.id}.",
            )
        if created:
            _notify_post_owner(
                db,
                notification_type="repost",
                post=post,
                source_post_id=timeline_repost.id,
                actor_user_id=user.id if character is None else None,
                actor_character_id=character.id if character else None,
            )
        return _post_detail(db, timeline_repost)

    def unrepost_post(self,
        db: Session, user: SocialUser, post_id: str, data: schemas.PostLikeCreate
    ) -> schemas.PostDetail:
        post = post_repository.get_post(db, post_id)
        if post is None or not _is_post_public_context_visible(db, post):
            raise PostNotFoundError(post_id)
        character = _resolve_author_character(db, user, data.character_id)
        reactions.delete_repost(db, post=post, user=user, character=character)
        reactions.delete_timeline_reposts(db, post=post, user=user, character=character)
        return _post_detail(db, post)
