"""Actual Social tool writes, authorization order and successful activity bookkeeping."""

from sqlalchemy.orm import Session
from app.domains.social.schemas import community as schemas
from app.domains.social.contracts.agent_tools import AgentToolActionWorkflows
from app.domains.social.exceptions import (
    AgentRunAuthorizationError,
    LegacyCommentsDisabledError,
    PostNotFoundError,
)
from app.domains.social.repository import (
    posts as post_repository,
    profiles as profile_repository,
)
from app.domains.social.repository.resident_affordances import (
    _character_already_liked_post,
    _character_already_reposted_post,
)
from app.domains.social.service.agent_tool_authorization import (
    _agent_tool_lookup_session_key,
    _raise_agent_tool_authorization_error,
    _get_agent_tool_run,
    _agent_tool_character_id,
    _agent_tool_user,
    _ensure_tick_action_allowed,
)
from app.domains.social.service.activity_results import (
    build_post_created_activity_result,
)
from app.domains.social.service.topic_metadata import (
    _topic_metadata_from_result,
    _store_post_topic_metadata,
)
from app.domains.social.service.visibility import _is_post_public_context_visible
from app.domains.social.service.resident_affordances import (
    _ensure_agent_can_reply_to_thread,
)
from app.domains.social.service.profiles import (
    _resolve_target_profile,
    follow_profile,
    unfollow_profile,
)
from app.domains.social.service.timeline import SocialTimelineService
from app.domains.characters.service import profile as character_profile


class AgentToolActionService:
    def __init__(
        self, workflows: AgentToolActionWorkflows, timeline: SocialTimelineService
    ) -> None:
        self.workflows = workflows
        self.timeline = timeline

    def create_agent_tool_comment(
        self, db: Session, session_key: str, post_id: str, data: schemas.CommentCreate
    ) -> schemas.CommentRead:
        raise LegacyCommentsDisabledError(
            "Legacy comments are disabled. Use /posts/{post_id}/replies."
        )

    def create_agent_tool_post(
        self,
        db: Session,
        session_key: str,
        data: schemas.PostCreate,
        *,
        topic_signature: str | None = None,
        novelty_basis: str | None = None,
        lore_chunk_ids: list[str] | None = None,
        retrieval_mode: str | None = None,
        lore_query_mode: str | None = None,
        consume_pending_feed_cue: bool = False,
        feed_cue_id: int | None = None,
        world_id: str | None = None,
        author_world_character_id: str | None = None,
    ) -> schemas.PostDetail:
        lookup_session_key = _agent_tool_lookup_session_key(session_key)
        run = self.workflows.get_active_run_for_session(db, lookup_session_key)
        if run is None:
            latest_run = self.workflows.get_latest_run_for_session(
                db, lookup_session_key
            )
            _raise_agent_tool_authorization_error(
                action="post",
                reason="no_active_run",
                session_key=session_key,
                run=latest_run,
                requested_character_id=data.author_character_id,
            )
        author_character_id = data.author_character_id or run.character_id
        if run.character_id != author_character_id:
            _raise_agent_tool_authorization_error(
                action="post",
                reason="character_mismatch",
                session_key=session_key,
                run=run,
                requested_character_id=author_character_id,
            )
        user = self.workflows.get_user(db, run.user_id)
        if user is None:
            _raise_agent_tool_authorization_error(
                action="post",
                reason="user_missing",
                session_key=session_key,
                run=run,
                requested_character_id=author_character_id,
            )
        _ensure_tick_action_allowed(
            db,
            session_key=session_key,
            run=run,
            action="post",
            references=self.workflows,
        )
        post = self.timeline.create_post(
            db,
            user,
            schemas.PostCreate(
                title=data.title,
                body=data.body,
                author_character_id=author_character_id,
            ),
            log_manual_activity=False,
            world_id=world_id,
            author_world_character_id=author_world_character_id,
        )
        result = build_post_created_activity_result(
            post_id=post.id,
            title=post.title,
            body=post.body,
            topic_signature=topic_signature,
            novelty_basis=novelty_basis,
            lore_chunk_ids=lore_chunk_ids,
            retrieval_mode=retrieval_mode,
            lore_query_mode=lore_query_mode,
            message=f"Created post {post.id}.",
        )
        topic_metadata = _topic_metadata_from_result(result)
        _store_post_topic_metadata(
            db,
            post_id=post.id,
            topic_signature=topic_metadata["topic_signature"],
            novelty_basis=topic_metadata["novelty_basis"],
        )
        self.workflows.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="post_created",
            target_post_id=post.id,
            reason="agent_tool_post",
            result=result,
        )
        self.workflows.maybe_log_feed_seed_consumed_for_created_post(
            db, run=run, created_post_id=post.id
        )
        if consume_pending_feed_cue:
            cue = self.workflows.get_pending_feed_cue(db, run.character_id)
            if feed_cue_id is None or (cue is not None and cue.id == feed_cue_id):
                self.workflows.mark_pending_feed_cue_used(
                    db, character_id=run.character_id, run_id=run.id, post_id=post.id
                )
        return post

    def like_agent_tool_post(
        self, db: Session, session_key: str, post_id: str, data: schemas.PostLikeCreate
    ) -> schemas.PostDetail:
        run = _get_agent_tool_run(
            db,
            session_key=session_key,
            action="like",
            requested_post_id=post_id,
            requested_character_id=data.character_id,
            references=self.workflows,
        )
        character_id = _agent_tool_character_id(
            run,
            data.character_id,
            action="like",
            session_key=session_key,
            post_id=post_id,
        )
        user = _agent_tool_user(
            db, run, action="like", session_key=session_key, references=self.workflows
        )
        _ensure_tick_action_allowed(
            db,
            session_key=session_key,
            run=run,
            action="like",
            references=self.workflows,
        )
        if _character_already_liked_post(
            db, character_id=character_id, post_id=post_id
        ):
            raise AgentRunAuthorizationError("like is already recorded for this post")
        return self.timeline.like_post(
            db,
            user,
            post_id,
            schemas.PostLikeCreate(character_id=character_id),
            activity_reason="agent_tool_like",
        )

    def reply_agent_tool_post(
        self,
        db: Session,
        session_key: str,
        post_id: str,
        data: schemas.TimelineReplyCreate,
    ) -> schemas.PostDetail:
        run = _get_agent_tool_run(
            db,
            session_key=session_key,
            action="reply",
            requested_post_id=post_id,
            requested_character_id=data.author_character_id,
            references=self.workflows,
        )
        character_id = _agent_tool_character_id(
            run,
            data.author_character_id,
            action="reply",
            session_key=session_key,
            post_id=post_id,
        )
        user = _agent_tool_user(
            db, run, action="reply", session_key=session_key, references=self.workflows
        )
        _ensure_tick_action_allowed(
            db,
            session_key=session_key,
            run=run,
            action="reply",
            references=self.workflows,
        )
        target_post = post_repository.get_post(db, post_id)
        if target_post is None or not _is_post_public_context_visible(db, target_post):
            raise PostNotFoundError(post_id)
        if target_post.author_character_id == character_id:
            raise AgentRunAuthorizationError(
                "reply target is self-authored. Reply to another character's post in the viewed thread instead."
            )
        _ensure_agent_can_reply_to_thread(
            db, post_id=post_id, character_id=character_id
        )
        return self.timeline.create_reply(
            db,
            user,
            post_id,
            schemas.TimelineReplyCreate(
                body=data.body, author_character_id=character_id
            ),
            activity_reason="agent_tool_reply",
            enforce_user_quota=False,
        )

    def quote_agent_tool_post(
        self,
        db: Session,
        session_key: str,
        post_id: str,
        data: schemas.TimelineQuoteCreate,
    ) -> schemas.PostDetail:
        raise AgentRunAuthorizationError("Quote is disabled for agent activity")

    def unlike_agent_tool_post(
        self, db: Session, session_key: str, post_id: str, data: schemas.PostLikeCreate
    ) -> schemas.PostDetail:
        run = _get_agent_tool_run(
            db,
            session_key=session_key,
            action="unlike",
            requested_post_id=post_id,
            requested_character_id=data.character_id,
            references=self.workflows,
        )
        character_id = _agent_tool_character_id(
            run,
            data.character_id,
            action="unlike",
            session_key=session_key,
            post_id=post_id,
        )
        user = _agent_tool_user(
            db, run, action="unlike", session_key=session_key, references=self.workflows
        )
        return self.timeline.unlike_post(
            db, user, post_id, schemas.PostLikeCreate(character_id=character_id)
        )

    def repost_agent_tool_post(
        self, db: Session, session_key: str, post_id: str, data: schemas.PostLikeCreate
    ) -> schemas.PostDetail:
        run = _get_agent_tool_run(
            db,
            session_key=session_key,
            action="repost",
            requested_post_id=post_id,
            requested_character_id=data.character_id,
            references=self.workflows,
        )
        character_id = _agent_tool_character_id(
            run,
            data.character_id,
            action="repost",
            session_key=session_key,
            post_id=post_id,
        )
        user = _agent_tool_user(
            db, run, action="repost", session_key=session_key, references=self.workflows
        )
        _ensure_tick_action_allowed(
            db,
            session_key=session_key,
            run=run,
            action="repost",
            references=self.workflows,
        )
        if _character_already_reposted_post(
            db, character_id=character_id, post_id=post_id
        ):
            raise AgentRunAuthorizationError("repost is already recorded for this post")
        return self.timeline.repost_post(
            db,
            user,
            post_id,
            schemas.PostLikeCreate(character_id=character_id),
            activity_reason="agent_tool_repost",
        )

    def unrepost_agent_tool_post(
        self, db: Session, session_key: str, post_id: str, data: schemas.PostLikeCreate
    ) -> schemas.PostDetail:
        run = _get_agent_tool_run(
            db,
            session_key=session_key,
            action="unrepost",
            requested_post_id=post_id,
            requested_character_id=data.character_id,
            references=self.workflows,
        )
        character_id = _agent_tool_character_id(
            run,
            data.character_id,
            action="unrepost",
            session_key=session_key,
            post_id=post_id,
        )
        user = _agent_tool_user(
            db,
            run,
            action="unrepost",
            session_key=session_key,
            references=self.workflows,
        )
        return self.timeline.unrepost_post(
            db, user, post_id, schemas.PostLikeCreate(character_id=character_id)
        )

    def follow_agent_tool_profile(
        self, db: Session, session_key: str, data: schemas.FollowCreate
    ) -> schemas.FollowRead:
        run = _get_agent_tool_run(
            db,
            session_key=session_key,
            action="follow",
            requested_character_id=data.follower_character_id,
            references=self.workflows,
        )
        follower_character_id = _agent_tool_character_id(
            run, data.follower_character_id, action="follow", session_key=session_key
        )
        user = _agent_tool_user(
            db, run, action="follow", session_key=session_key, references=self.workflows
        )
        _ensure_tick_action_allowed(
            db,
            session_key=session_key,
            run=run,
            action="follow",
            references=self.workflows,
        )
        follower_character = character_profile.get_character(db, follower_character_id)
        target_user, target_character = _resolve_target_profile(
            db, data.target_type, data.target_id
        )
        already_following = profile_repository.profile_follow_exists(
            db,
            follower_user=None,
            follower_character=follower_character,
            target_user=target_user,
            target_character=target_character,
        )
        if already_following:
            raise AgentRunAuthorizationError(
                "follow is already recorded for this profile"
            )
        follow = follow_profile(
            db,
            user,
            schemas.FollowCreate(
                target_type=data.target_type,
                target_id=data.target_id,
                follower_character_id=follower_character_id,
            ),
        )
        if not already_following:
            self.workflows.log_activity(
                db,
                user_id=run.user_id,
                character_id=run.character_id,
                action_type="followed",
                target_post_id=None,
                reason="agent_tool_follow",
                result=f"Followed {data.target_type}:{data.target_id}.",
            )
        return follow

    def unfollow_agent_tool_profile(
        self, db: Session, session_key: str, data: schemas.FollowCreate
    ) -> None:
        run = _get_agent_tool_run(
            db,
            session_key=session_key,
            action="unfollow",
            requested_character_id=data.follower_character_id,
            references=self.workflows,
        )
        follower_character_id = _agent_tool_character_id(
            run, data.follower_character_id, action="unfollow", session_key=session_key
        )
        user = _agent_tool_user(
            db,
            run,
            action="unfollow",
            session_key=session_key,
            references=self.workflows,
        )
        _ensure_tick_action_allowed(
            db,
            session_key=session_key,
            run=run,
            action="unfollow",
            references=self.workflows,
        )
        unfollow_profile(
            db,
            user,
            schemas.FollowCreate(
                target_type=data.target_type,
                target_id=data.target_id,
                follower_character_id=follower_character_id,
            ),
        )
        self.workflows.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="unfollowed",
            target_post_id=None,
            reason="agent_tool_unfollow",
            result=f"Unfollowed {data.target_type}:{data.target_id}.",
        )
