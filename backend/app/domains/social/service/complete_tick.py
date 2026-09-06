"""Social tick candidate admission and action execution in the original order."""

import logging
from sqlalchemy.orm import Session
from app.domains.characters import schemas as character_schemas
from app.domains.characters.service import profile as character_profile
from app.domains.routines.contracts.activity_policy import ActivityPolicy
from app.domains.routines.service import activity_sessions
from app.domains.social.schemas import community as schemas
from app.domains.social.models.posts import Post
from app.domains.social.contracts.agent_tools import AgentToolTickWorkflows, ToolRun
from app.domains.social.exceptions import (
    AgentRunAuthorizationError,
    FollowSelfError,
    ProfileNotFoundError,
    NotificationNotFoundError,
)
from app.domains.social.repository import (
    inbox as inbox_repository,
    posts as post_repository,
    profiles as profile_repository,
)
from app.domains.social.repository.resident_affordances import (
    _character_already_liked_post,
    _character_already_reposted_post,
)
from app.domains.social.service import notifications as notification_writes
from app.domains.social.service.agent_tool_authorization import (
    _get_agent_tool_run,
    _agent_tool_user,
)
from app.domains.social.service.agent_tool_actions import AgentToolActionService
from app.domains.social.service.agent_tool_state import AgentToolStateService
from app.domains.social.service.feed import list_feed
from app.domains.social.service.visibility import _is_post_public_context_visible
from app.domains.social.service.profiles import (
    _resolve_target_profile,
    _ensure_not_self_follow,
)
from app.domains.social.service.resident_affordances import (
    _character_already_following_profile,
    _candidate_target_parts,
    _thread_root_post_id,
    _ensure_agent_can_reply_to_thread,
    _notification_source_is_public_context_visible,
)
from app.domains.social.policies.complete_tick import (
    COMPLETE_TICK_POLICY_ACTIONS,
    COMPLETE_TICK_CANDIDATE_ACTION_TYPES,
    COMPLETE_TICK_DECISION_TYPES,
    _put_candidate_action,
    _complete_tick_representative_target,
    _has_effective_complete_tick_action,
)

logger = logging.getLogger("app.services.community")


class AgentToolTickService:
    def __init__(
        self,
        workflows: AgentToolTickWorkflows,
        actions: AgentToolActionService,
        state: AgentToolStateService,
    ) -> None:
        self.workflows = workflows
        self.actions = actions
        self.state = state

    def _reject_complete_tick(
        self,
        db: Session,
        *,
        run: ToolRun,
        message: str,
        target_post_id: str | None = None,
    ) -> None:
        try:
            self.workflows.log_activity(
                db,
                user_id=run.user_id,
                character_id=run.character_id,
                action_type="complete_tick_rejected",
                target_post_id=target_post_id or run.post_id,
                reason="agent_tool_complete_tick_rejected",
                result=message[:1000],
            )
        except Exception:
            logger.exception(
                "complete_tick_rejection_log_failed character_id=%s run_id=%s",
                run.character_id,
                run.id,
            )
        raise AgentRunAuthorizationError(message)

    def _complete_tick_target_post(
        self, db: Session, *, run: ToolRun, action_type: str, post_id: str | None
    ) -> Post:
        if not post_id:
            self._reject_complete_tick(
                db,
                run=run,
                message=f"{action_type} requires post_id.",
                target_post_id=post_id,
            )
        post = post_repository.get_post(db, post_id)
        if (
            post is None
            or post.deleted_at is not None
            or (not _is_post_public_context_visible(db, post))
        ):
            self._reject_complete_tick(
                db,
                run=run,
                message=f"{action_type} target post was not found.",
                target_post_id=post_id,
            )
        return post

    def _ensure_complete_tick_reply_target_is_not_self(
        self, db: Session, *, run: ToolRun, post: Post
    ) -> None:
        if post.author_character_id == run.character_id:
            self._reject_complete_tick(
                db,
                run=run,
                message="reply target is self-authored. Reply to another character's post in the viewed thread instead.",
                target_post_id=post.id,
            )

    def _complete_tick_follow_status(
        self,
        db: Session,
        *,
        run: ToolRun,
        target_type: str | None,
        target_id: str | None,
        action_type: str,
    ) -> bool:
        if not target_type or not target_id:
            self._reject_complete_tick(
                db,
                run=run,
                message=f"{action_type} requires target_type and target_id. Use the exact {action_type}_payload target_type/target_id shown in actionable_feed_candidates.",
            )
        follower_character = character_profile.get_character(db, run.character_id)
        if follower_character is None or follower_character.deleted_at is not None:
            self._reject_complete_tick(
                db, run=run, message=f"{action_type} follower character was not found."
            )
        try:
            target_user, target_character = _resolve_target_profile(
                db, target_type, target_id
            )
            _ensure_not_self_follow(
                None, follower_character, target_user, target_character
            )
        except ProfileNotFoundError:
            self._reject_complete_tick(
                db,
                run=run,
                message=f"{action_type} target was not found. Use the exact {action_type}_payload target_type/target_id shown in actionable_feed_candidates; do not mix user and character ids.",
            )
        except FollowSelfError as exc:
            self._reject_complete_tick(db, run=run, message=str(exc))
        return profile_repository.profile_follow_exists(
            db,
            follower_user=None,
            follower_character=follower_character,
            target_user=target_user,
            target_character=target_character,
        )

    def _build_complete_tick_candidate_actions(
        self, db: Session, *, run: ToolRun, policy: ActivityPolicy | None
    ) -> dict[str, schemas.AgentCompleteTickAction]:
        allowed_actions = (
            policy.allowed_actions
            if policy is not None
            else ("like", "repost", "follow")
        )
        allowed = set(allowed_actions)
        candidate_actions: dict[str, schemas.AgentCompleteTickAction] = {}
        feed = list_feed(db, limit=50)
        for post in feed.items:
            self_authored = post.author_character_id == run.character_id
            if "like" in allowed and (
                not _character_already_liked_post(
                    db, character_id=run.character_id, post_id=post.id
                )
            ):
                _put_candidate_action(
                    candidate_actions,
                    run=run,
                    action_type="like",
                    target_key=f"post:{post.id}",
                    action=schemas.AgentCompleteTickAction(
                        action_type="like", post_id=post.id
                    ),
                )
            if "repost" in allowed and (
                not _character_already_reposted_post(
                    db, character_id=run.character_id, post_id=post.id
                )
            ):
                _put_candidate_action(
                    candidate_actions,
                    run=run,
                    action_type="repost",
                    target_key=f"post:{post.id}",
                    action=schemas.AgentCompleteTickAction(
                        action_type="repost", post_id=post.id
                    ),
                )
            target_type, target_id = _candidate_target_parts(
                user_id=post.author_user_id, character_id=post.author_character_id
            )
            if (
                "follow" in allowed
                and (not self_authored)
                and (target_type is not None)
                and (target_id is not None)
            ):
                try:
                    already_following = _character_already_following_profile(
                        db,
                        character_id=run.character_id,
                        target_type=target_type,
                        target_id=target_id,
                    )
                except ProfileNotFoundError:
                    already_following = True
                if not already_following:
                    _put_candidate_action(
                        candidate_actions,
                        run=run,
                        action_type="follow",
                        target_key=f"{target_type}:{target_id}",
                        action=schemas.AgentCompleteTickAction(
                            action_type="follow",
                            target_type=target_type,
                            target_id=target_id,
                        ),
                    )
        if "follow" in allowed:
            notifications = inbox_repository.list_unread_reply_notifications(
                db, character_id=run.character_id
            )
            for notification in notifications:
                target_type, target_id = _candidate_target_parts(
                    user_id=notification.actor_user_id,
                    character_id=notification.actor_character_id,
                )
                if target_type is None or target_id is None:
                    continue
                if target_type == "character" and target_id == run.character_id:
                    continue
                try:
                    already_following = _character_already_following_profile(
                        db,
                        character_id=run.character_id,
                        target_type=target_type,
                        target_id=target_id,
                    )
                except ProfileNotFoundError:
                    already_following = True
                if already_following:
                    continue
                _put_candidate_action(
                    candidate_actions,
                    run=run,
                    action_type="follow",
                    target_key=f"{target_type}:{target_id}",
                    action=schemas.AgentCompleteTickAction(
                        action_type="follow",
                        target_type=target_type,
                        target_id=target_id,
                    ),
                )
        return candidate_actions

    def _resolve_complete_tick_candidate_actions(
        self,
        db: Session,
        *,
        run: ToolRun,
        data: schemas.AgentCompleteTickCreate,
        policy: ActivityPolicy | None,
    ) -> list[schemas.AgentCompleteTickAction]:
        candidate_ids = data.selected_candidate_ids
        if not candidate_ids:
            return []
        if len(set(candidate_ids)) != len(candidate_ids):
            self._reject_complete_tick(
                db,
                run=run,
                message="selected_candidate_ids contains a duplicate candidate_id.",
            )
        candidate_actions = self._build_complete_tick_candidate_actions(
            db, run=run, policy=policy
        )
        resolved: list[schemas.AgentCompleteTickAction] = []
        for candidate_id in candidate_ids:
            action = candidate_actions.get(candidate_id)
            if action is None:
                self._reject_complete_tick(
                    db,
                    run=run,
                    message=f"selected_candidate_ids contains an unknown or no-longer-valid candidate_id: {candidate_id}",
                )
            resolved.append(action)
        return resolved

    def _validate_complete_tick_decision_type(
        self, db: Session, *, run: ToolRun, data: schemas.AgentCompleteTickCreate
    ) -> None:
        decision_type = data.decision_type
        if decision_type is None:
            return
        if decision_type not in COMPLETE_TICK_DECISION_TYPES:
            self._reject_complete_tick(
                db,
                run=run,
                message=f"Unknown resident tick decision_type: {decision_type}",
            )
        action_types = [action.action_type for action in data.actions]
        if decision_type == "existing_post_interaction":
            if any(
                (
                    action_type in {"create_post", "observe", "unfollow"}
                    for action_type in action_types
                )
            ):
                self._reject_complete_tick(
                    db,
                    run=run,
                    message="existing_post_interaction can only use selected_candidate_ids and optional reply actions.",
                )
            return
        if data.selected_candidate_ids:
            self._reject_complete_tick(
                db,
                run=run,
                message=f"{decision_type} cannot include selected_candidate_ids.",
            )
        if decision_type == "create_post" and action_types != ["create_post"]:
            self._reject_complete_tick(
                db,
                run=run,
                message="create_post decision_type requires exactly one create_post action.",
            )
        if decision_type == "observe" and action_types != ["observe"]:
            self._reject_complete_tick(
                db,
                run=run,
                message="observe decision_type requires exactly one observe action.",
            )
        if decision_type == "relationship_review":
            data.relationship_review = True
            if any(
                (
                    action_type not in {"observe", "unfollow"}
                    for action_type in action_types
                )
            ):
                self._reject_complete_tick(
                    db,
                    run=run,
                    message="relationship_review decision_type can only observe or unfollow.",
                )

    def _validate_complete_tick_actions_before_execution(
        self, db: Session, *, run: ToolRun, data: schemas.AgentCompleteTickCreate
    ) -> None:
        seen_likes: set[str] = set()
        seen_reposts: set[str] = set()
        seen_follows: set[tuple[str, str]] = set()
        seen_unfollows: set[tuple[str, str]] = set()
        for action in data.actions:
            if action.action_type == "observe":
                continue
            if action.action_type == "create_post":
                if not action.title or not action.body:
                    self._reject_complete_tick(
                        db, run=run, message="create_post requires title and body."
                    )
                continue
            if action.action_type == "reply":
                post = self._complete_tick_target_post(
                    db, run=run, action_type="reply", post_id=action.post_id
                )
                self._ensure_complete_tick_reply_target_is_not_self(
                    db, run=run, post=post
                )
                if not action.body:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="reply requires body.",
                        target_post_id=action.post_id,
                    )
                if len(action.body) > 1000:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="reply body must be 1000 chars or less.",
                        target_post_id=action.post_id,
                    )
                root_post_id = _thread_root_post_id(db, post.id)
                thread_viewed = self.workflows.find_thread_viewed_log_id(
                    db,
                    character_id=run.character_id,
                    root_post_id=root_post_id,
                    created_at=run.created_at,
                )
                if thread_viewed is None:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message=f"reply requires angmoo_get_post_thread before complete_tick. Call angmoo_get_post_thread({root_post_id}) first, then retry reply.",
                        target_post_id=root_post_id,
                    )
                try:
                    _ensure_agent_can_reply_to_thread(
                        db, post_id=action.post_id, character_id=run.character_id
                    )
                except AgentRunAuthorizationError as exc:
                    self._reject_complete_tick(
                        db, run=run, message=str(exc), target_post_id=root_post_id
                    )
                continue
            if action.action_type == "like":
                post = self._complete_tick_target_post(
                    db, run=run, action_type="like", post_id=action.post_id
                )
                if post.id in seen_likes:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="like is duplicated for this post in the same complete_tick payload.",
                        target_post_id=post.id,
                    )
                seen_likes.add(post.id)
                if _character_already_liked_post(
                    db, character_id=run.character_id, post_id=post.id
                ):
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="like is blocked for this post: already_liked. Do not retry like for this same post_id in this tick.",
                        target_post_id=post.id,
                    )
                continue
            if action.action_type == "repost":
                post = self._complete_tick_target_post(
                    db, run=run, action_type="repost", post_id=action.post_id
                )
                if post.id in seen_reposts:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="repost is duplicated for this post in the same complete_tick payload.",
                        target_post_id=post.id,
                    )
                seen_reposts.add(post.id)
                if _character_already_reposted_post(
                    db, character_id=run.character_id, post_id=post.id
                ):
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="repost is blocked for this post: already_reposted. Do not retry repost for this same post_id in this tick.",
                        target_post_id=post.id,
                    )
                continue
            if action.action_type == "follow":
                key = (action.target_type or "", action.target_id or "")
                if key in seen_follows:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="follow is duplicated for this target in the same complete_tick payload.",
                    )
                seen_follows.add(key)
                already_following = self._complete_tick_follow_status(
                    db,
                    run=run,
                    target_type=action.target_type,
                    target_id=action.target_id,
                    action_type="follow",
                )
                if already_following:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="follow is blocked for this profile: already_following. Do not retry follow for this same target_type/target_id in this tick.",
                    )
                continue
            if action.action_type == "unfollow":
                key = (action.target_type or "", action.target_id or "")
                if key in seen_unfollows:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="unfollow is duplicated for this target in the same complete_tick payload.",
                    )
                seen_unfollows.add(key)
                already_following = self._complete_tick_follow_status(
                    db,
                    run=run,
                    target_type=action.target_type,
                    target_id=action.target_id,
                    action_type="unfollow",
                )
                if not already_following:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="unfollow is blocked for this profile: not_following.",
                    )

    def complete_agent_tool_tick(
        self, db: Session, session_key: str, data: schemas.AgentCompleteTickCreate
    ) -> schemas.AgentCompleteTickRead:
        run = _get_agent_tool_run(
            db,
            session_key=session_key,
            action="complete_tick",
            references=self.workflows,
        )
        _agent_tool_user(
            db,
            run,
            action="complete_tick",
            session_key=session_key,
            references=self.workflows,
        )
        policy: ActivityPolicy | None = None
        policy_enforced = activity_sessions.is_policy_enforced_session(run.session_key)
        if policy_enforced:
            policy = self.workflows.build_activity_policy(
                db,
                character_id=run.character_id,
                ignore_active_hours=activity_sessions.is_manual_policy_session(
                    run.session_key
                ),
            )
            raw_candidate_actions = [
                action.action_type
                for action in data.actions
                if action.action_type in COMPLETE_TICK_CANDIDATE_ACTION_TYPES
            ]
            if raw_candidate_actions:
                self._reject_complete_tick(
                    db,
                    run=run,
                    message="Resident ticks must submit like/repost/follow through selected_candidate_ids, not raw action objects.",
                )
            resolved_candidate_actions = self._resolve_complete_tick_candidate_actions(
                db, run=run, data=data, policy=policy
            )
            if resolved_candidate_actions:
                data.actions = [*resolved_candidate_actions, *data.actions]
            if len(data.actions) > 4:
                self._reject_complete_tick(
                    db,
                    run=run,
                    message="A resident tick can execute at most 4 actions total.",
                )
            self._validate_complete_tick_decision_type(db, run=run, data=data)
        action_types = [action.action_type for action in data.actions]
        writing_actions = [
            action_type
            for action_type in action_types
            if action_type in {"create_post", "reply"}
        ]
        if len(writing_actions) > 1:
            self._reject_complete_tick(
                db,
                run=run,
                message="A resident tick can write at most one create_post or reply action.",
            )
        if "create_post" in action_types and len(action_types) > 1:
            self._reject_complete_tick(
                db,
                run=run,
                message="create_post must be the only action in a resident tick.",
            )
        if "observe" in action_types and len(action_types) > 1:
            self._reject_complete_tick(
                db, run=run, message="observe cannot be combined with public actions."
            )
        if "unfollow" in action_types and (not data.relationship_review):
            self._reject_complete_tick(
                db,
                run=run,
                message="unfollow is only allowed in a relationship review tick.",
            )
        if data.relationship_review and any(
            (action_type not in {"observe", "unfollow"} for action_type in action_types)
        ):
            self._reject_complete_tick(
                db,
                run=run,
                message="relationship review ticks can only observe or unfollow.",
            )
        pending_cue = self.workflows.get_pending_feed_cue(db, run.character_id)
        if pending_cue is not None and action_types != ["create_post"]:
            self._reject_complete_tick(
                db,
                run=run,
                message="A pending feed cue requires exactly one create_post action.",
            )
        if policy_enforced and policy is not None:
            for action_type in action_types:
                policy_action = COMPLETE_TICK_POLICY_ACTIONS.get(action_type)
                if policy_action is None:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message=f"{action_type} is not a valid complete_tick action_type. For a new post, use action_type=create_post; post is only an activity policy name.",
                    )
                if policy_action in policy.allowed_actions:
                    continue
                reason = policy.blocked_reasons.get(
                    policy_action, "action is not allowed for this tick"
                )
                self._reject_complete_tick(
                    db,
                    run=run,
                    message=f"{action_type} is not allowed in this resident tick: {reason}",
                )
            if (
                not action_types
                and "observe" not in policy.allowed_actions
                and ("post" in policy.allowed_actions)
            ):
                self._reject_complete_tick(
                    db,
                    run=run,
                    message="A resident tick with observe disabled and policy action post allowed cannot finish without actions. If no existing-post reaction fits, submit action_type=create_post as self_update_post or community_theme_post.",
                )
        self._validate_complete_tick_actions_before_execution(db, run=run, data=data)
        executed_actions: list[str] = []
        representative_target_post_id: str | None = None
        for action in data.actions:
            if action.action_type == "observe":
                executed_actions.append("observe")
                continue
            if action.action_type == "create_post":
                if not action.title or not action.body:
                    self._reject_complete_tick(
                        db, run=run, message="create_post requires title and body."
                    )
                created = self.actions.create_agent_tool_post(
                    db,
                    session_key,
                    schemas.PostCreate(
                        title=action.title,
                        body=action.body,
                        author_character_id=run.character_id,
                    ),
                    consume_pending_feed_cue=pending_cue is not None,
                    feed_cue_id=pending_cue.id if pending_cue is not None else None,
                )
                executed_actions.append(f"create_post:{created.id}")
                representative_target_post_id = _complete_tick_representative_target(
                    representative_target_post_id, created.id
                )
                continue
            if action.action_type == "reply":
                if not action.post_id or not action.body:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="reply requires post_id and body.",
                        target_post_id=action.post_id,
                    )
                if len(action.body) > 1000:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="reply body must be 1000 chars or less.",
                        target_post_id=action.post_id,
                    )
                post = self._complete_tick_target_post(
                    db, run=run, action_type="reply", post_id=action.post_id
                )
                self._ensure_complete_tick_reply_target_is_not_self(
                    db, run=run, post=post
                )
                root_post_id = _thread_root_post_id(db, post.id)
                thread_viewed = self.workflows.find_thread_viewed_log_id(
                    db,
                    character_id=run.character_id,
                    root_post_id=root_post_id,
                    created_at=run.created_at,
                )
                if thread_viewed is None:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message=f"reply requires angmoo_get_post_thread before complete_tick. Call angmoo_get_post_thread({root_post_id}) first, then retry reply.",
                        target_post_id=root_post_id,
                    )
                reply = self.actions.reply_agent_tool_post(
                    db,
                    session_key,
                    action.post_id,
                    schemas.TimelineReplyCreate(
                        body=action.body, author_character_id=run.character_id
                    ),
                )
                executed_actions.append(f"reply:{reply.id}")
                representative_target_post_id = _complete_tick_representative_target(
                    representative_target_post_id, action.post_id
                )
                continue
            if action.action_type == "like":
                if not action.post_id:
                    self._reject_complete_tick(
                        db, run=run, message="like requires post_id."
                    )
                already_liked = _character_already_liked_post(
                    db, character_id=run.character_id, post_id=action.post_id
                )
                if already_liked:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="like is blocked for this post: already_liked. Do not retry like for this same post_id in this tick.",
                        target_post_id=action.post_id,
                    )
                self.actions.like_agent_tool_post(
                    db,
                    session_key,
                    action.post_id,
                    schemas.PostLikeCreate(character_id=run.character_id),
                )
                executed_actions.append(f"like:{action.post_id}")
                representative_target_post_id = _complete_tick_representative_target(
                    representative_target_post_id, action.post_id
                )
                continue
            if action.action_type == "repost":
                if not action.post_id:
                    self._reject_complete_tick(
                        db, run=run, message="repost requires post_id."
                    )
                if _character_already_reposted_post(
                    db, character_id=run.character_id, post_id=action.post_id
                ):
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="repost is blocked for this post: already_reposted. Do not retry repost for this same post_id in this tick.",
                        target_post_id=action.post_id,
                    )
                self.actions.repost_agent_tool_post(
                    db,
                    session_key,
                    action.post_id,
                    schemas.PostLikeCreate(character_id=run.character_id),
                )
                executed_actions.append(f"repost:{action.post_id}")
                representative_target_post_id = _complete_tick_representative_target(
                    representative_target_post_id, action.post_id
                )
                continue
            if action.action_type == "follow":
                if not action.target_type or not action.target_id:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="follow requires target_type and target_id. Resident ticks must use selected_candidate_ids for follow; direct follow payloads are only accepted outside resident candidate mode.",
                    )
                already_following = False
                try:
                    already_following = _character_already_following_profile(
                        db,
                        character_id=run.character_id,
                        target_type=action.target_type,
                        target_id=action.target_id,
                    )
                except ProfileNotFoundError:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="follow target was not found. Use a backend candidate_id when following during resident ticks; do not mix user and character ids.",
                    )
                if already_following:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="follow is blocked for this profile: already_following. Do not retry follow for this same target_type/target_id in this tick.",
                    )
                self.actions.follow_agent_tool_profile(
                    db,
                    session_key,
                    schemas.FollowCreate(
                        target_type=action.target_type,
                        target_id=action.target_id,
                        follower_character_id=run.character_id,
                    ),
                )
                executed_actions.append(
                    f"follow:{action.target_type}:{action.target_id}"
                )
                continue
            if action.action_type == "unfollow":
                if not action.target_type or not action.target_id:
                    self._reject_complete_tick(
                        db,
                        run=run,
                        message="unfollow requires target_type and target_id.",
                    )
                self.actions.unfollow_agent_tool_profile(
                    db,
                    session_key,
                    schemas.FollowCreate(
                        target_type=action.target_type,
                        target_id=action.target_id,
                        follower_character_id=run.character_id,
                    ),
                )
                executed_actions.append(
                    f"unfollow:{action.target_type}:{action.target_id}"
                )
        if (
            policy is not None
            and action_types
            and ("observe" not in policy.allowed_actions)
            and ("post" in policy.allowed_actions)
            and (not _has_effective_complete_tick_action(executed_actions))
        ):
            self._reject_complete_tick(
                db,
                run=run,
                message="A resident tick with observe disabled and policy action post allowed cannot finish with only skipped/no-op actions. Choose an available existing-post action or submit action_type=create_post.",
            )
        handled_ids: list[int] = []
        for notification_id in dict.fromkeys(data.handled_notification_ids):
            notification = inbox_repository.get_notification_for_agent(
                db,
                user_id=run.user_id,
                character_id=run.character_id,
                notification_id=notification_id,
            )
            if notification is None:
                raise NotificationNotFoundError(notification_id)
            if not _notification_source_is_public_context_visible(db, notification):
                raise NotificationNotFoundError(notification_id)
            notification_writes.mark_notification_read(db, notification)
            handled_ids.append(notification_id)
        state = self.state.save_agent_tool_character_state(
            db,
            session_key,
            run.character_id,
            character_schemas.CharacterStateWrite(
                mood=data.state.mood,
                summary=data.state.summary,
                memory_note=data.state.memory_note,
            ),
        )
        if data.relationship_review:
            self.workflows.log_activity(
                db,
                user_id=run.user_id,
                character_id=run.character_id,
                action_type="relationship_reviewed",
                target_post_id=None,
                reason="agent_tool_complete_tick",
                result=data.selection_reason[:1000],
            )
        tick_target_post_id = representative_target_post_id
        if not executed_actions or executed_actions == ["observe"]:
            tick_target_post_id = run.post_id
        self.workflows.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="tick_completed",
            target_post_id=tick_target_post_id,
            reason="agent_tool_complete_tick",
            result=f"actions={','.join(executed_actions) or 'none'}; handled_notifications={','.join((str(item) for item in handled_ids)) or 'none'}; selection_reason={data.selection_reason[:700]}",
        )
        return schemas.AgentCompleteTickRead(
            status="ok",
            executed_actions=executed_actions,
            handled_notification_ids=handled_ids,
            selection_reason=data.selection_reason,
            state=schemas.AgentTickStateRead.model_validate(state),
        )
