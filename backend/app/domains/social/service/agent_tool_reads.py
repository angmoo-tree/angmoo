"""Social tool feed, inbox visibility, bounded response and observation workflows."""

import json
from sqlalchemy.orm import Session
from app.core.context_text import neutralize_context_text
from app.domains.social.models import posts as models
from app.domains.social.schemas import community as schemas
from app.domains.social.contracts.agent_tools import AgentToolReadWorkflows, ToolRun
from app.domains.social.exceptions import (
    PostNotFoundError,
    ProfileNotFoundError,
    NotificationNotFoundError,
)
from app.domains.social.repository import (
    posts as post_repository,
    profiles as profile_repository,
    inbox as inbox_repository,
)
from app.domains.social.service import notifications as notification_writes
from app.domains.social.service.agent_tool_authorization import (
    _get_agent_tool_run,
    _ensure_tick_action_allowed,
    _agent_tool_scratch_lane,
    _session_fingerprint,
)
from app.domains.social.service.visibility import _is_post_public_context_visible
from app.domains.social.service.resident_affordances import (
    _post_has_resident_feed_action,
    _thread_root_post_id,
    list_resident_actionable_inbox_notifications,
    _notification_source_is_public_context_visible,
)
from app.domains.social.service.agent_presentation import (
    _neutralize_feed_page_for_agent,
    _neutralize_post_thread_for_agent,
    _compact_agent_notification_read,
)
from app.domains.social.service.presentation import (
    _post_summary,
    _post_author_identity,
    _notification_read,
)
from app.domains.social.service.profiles import get_user_profile, get_character_profile
from app.domains.social.service.posts import get_post_thread
from app.domains.social.service.topic_metadata import post_topic_signature_for_prompt
from app.domains.social.service.activity_results import _safe_topic_text, _body_preview
from app.domains.social.utils.limits import _safe_limit


class AgentToolReadService:
    def __init__(self, workflows: AgentToolReadWorkflows) -> None:
        self.workflows = workflows

    def list_agent_tool_feed(
        self,
        db: Session,
        session_key: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
    ) -> schemas.AgentFeedPage:
        run = _get_agent_tool_run(
            db, session_key=session_key, action="list_feed", references=self.workflows
        )
        scratch_lane = _agent_tool_scratch_lane(session_key)
        effective_limit = (
            max(1, min(limit, 30))
            if scratch_lane == "feed-scan"
            else max(1, min(limit, 100))
        )
        self.workflows.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="feed_viewed",
            target_post_id=run.post_id,
            reason="agent_tool_list_feed",
            result=f"Read feed limit={effective_limit}.",
        )
        if scratch_lane == "feed-scan":
            return self._list_resident_feed_scan_page(
                db, run=run, limit=effective_limit, cursor=cursor
            )
        posts, next_cursor = post_repository.list_timeline_posts(
            db, limit=effective_limit, cursor=cursor
        )
        return schemas.AgentFeedPage(
            items=[
                self._agent_feed_post_summary(db, post)
                for post in posts
                if _is_post_public_context_visible(db, post)
            ],
            next_cursor=next_cursor,
        )

    def _list_resident_feed_scan_page(
        self, db: Session, *, run: ToolRun, limit: int, cursor: str | None = None
    ) -> schemas.AgentFeedPage:
        allowed_actions = set(
            self.workflows.build_activity_policy(
                db, character_id=run.character_id
            ).allowed_actions
        )
        items: list[models.Post] = []
        page_cursor = cursor
        last_scanned_id: str | None = cursor
        scanned = 0
        while len(items) < limit and scanned < 500:
            posts, next_cursor = post_repository.list_resident_scan_posts(
                db, limit=100, cursor=page_cursor
            )
            if not posts:
                break
            scanned += len(posts)
            for post in posts:
                last_scanned_id = post.id
                if _post_has_resident_feed_action(
                    db,
                    post=post,
                    character_id=run.character_id,
                    allowed_actions=allowed_actions,
                ):
                    items.append(post)
                    if len(items) >= limit:
                        break
            if next_cursor is None or len(items) >= limit:
                break
            page_cursor = next_cursor
        return schemas.AgentFeedPage(
            items=[self._agent_feed_post_summary(db, post) for post in items],
            next_cursor=last_scanned_id if len(items) >= limit else None,
        )

    def list_agent_tool_following_feed(
        self,
        db: Session,
        session_key: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
    ) -> schemas.FeedPage:
        run = _get_agent_tool_run(
            db,
            session_key=session_key,
            action="list_following_feed",
            references=self.workflows,
        )
        followed_user_ids, followed_character_ids = (
            profile_repository.get_followed_profiles_for_character(db, run.character_id)
        )
        posts, next_cursor = post_repository.list_timeline_posts(
            db,
            limit=_safe_limit(limit),
            cursor=cursor,
            followed_user_ids=followed_user_ids,
            followed_character_ids=followed_character_ids,
        )
        return _neutralize_feed_page_for_agent(
            schemas.FeedPage(
                items=[
                    _post_summary(db, post)
                    for post in posts
                    if _is_post_public_context_visible(db, post)
                ],
                next_cursor=next_cursor,
            )
        )

    def _agent_feed_post_summary(
        self, db: Session, post: models.Post
    ) -> schemas.AgentFeedPostSummary:
        author = _post_author_identity(db, post)
        return schemas.AgentFeedPostSummary(
            post_id=post.id,
            author=neutralize_context_text(author["name"] or "-"),
            created_at=post.created_at,
            topic_signature=post_topic_signature_for_prompt(
                db, post, references=self.workflows.topic_history
            ),
            title=_safe_topic_text(post.title, 120),
            body_preview=_body_preview(post.body),
        )

    def get_agent_tool_post_thread(
        self, db: Session, session_key: str, post_id: str
    ) -> schemas.PostThreadRead:
        run = _get_agent_tool_run(
            db,
            session_key=session_key,
            action="get_thread",
            requested_post_id=post_id,
            references=self.workflows,
        )
        post = post_repository.get_post(db, post_id)
        if post is None or not _is_post_public_context_visible(db, post):
            raise PostNotFoundError(post_id)
        self.workflows.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="thread_viewed",
            target_post_id=_thread_root_post_id(db, post_id),
            reason="agent_tool_get_thread",
            result=f"Read thread {post_id}.",
        )
        return _neutralize_post_thread_for_agent(get_post_thread(db, post_id))

    def get_agent_tool_profile(
        self, db: Session, session_key: str, profile_type: str, profile_id: str
    ) -> schemas.ProfileRead:
        _get_agent_tool_run(
            db, session_key=session_key, action="get_profile", references=self.workflows
        )
        if profile_type == "user":
            return get_user_profile(db, profile_id)
        if profile_type == "character":
            return get_character_profile(db, profile_id)
        raise ProfileNotFoundError(profile_id)

    def _log_inbox_notifications_provided(
        self,
        db: Session,
        *,
        run: ToolRun,
        session_key: str,
        notifications: list[models.Notification],
    ) -> None:
        payload = {
            "session_fingerprint": _session_fingerprint(session_key),
            "notification_ids": [
                notification.id for notification in notifications[:10]
            ],
        }
        first = notifications[0] if notifications else None
        self.workflows.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="inbox_notifications_provided",
            target_post_id=first.source_post_id or first.post_id
            if first
            else run.post_id,
            reason="agent_tool_get_notifications",
            result=json.dumps(payload, ensure_ascii=False)[:4000],
        )

    def _latest_inbox_delivery_notification_ids(
        self, db: Session, *, run: ToolRun, session_key: str
    ) -> list[int]:
        fingerprint = _session_fingerprint(session_key)
        logs = self.workflows.inbox_delivery_logs(db, run=run)
        for log in logs:
            try:
                payload = json.loads(log.result)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("session_fingerprint") != fingerprint:
                continue
            ids = payload.get("notification_ids")
            if not isinstance(ids, list):
                return []
            normalized: list[int] = []
            for item in ids[:10]:
                if isinstance(item, bool):
                    continue
                try:
                    normalized.append(int(item))
                except (TypeError, ValueError):
                    continue
            return normalized
        return []

    def _mark_provided_inbox_notifications_read(
        self, db: Session, *, run: ToolRun, session_key: str
    ) -> None:
        for notification_id in self._latest_inbox_delivery_notification_ids(
            db, run=run, session_key=session_key
        ):
            notification = inbox_repository.get_notification_for_agent(
                db,
                user_id=run.user_id,
                character_id=run.character_id,
                notification_id=notification_id,
            )
            if (
                notification is not None
                and notification.notification_type == "reply"
                and (notification.read_at is None)
            ):
                notification_writes.mark_notification_read(db, notification)

    def list_agent_tool_notifications(
        self, db: Session, session_key: str, *, limit: int = 50
    ) -> list[schemas.NotificationRead]:
        run = _get_agent_tool_run(
            db,
            session_key=session_key,
            action="get_notifications",
            references=self.workflows,
        )
        if _agent_tool_scratch_lane(session_key) == "inbox":
            policy = self.workflows.build_activity_policy(
                db, character_id=run.character_id
            )
            notifications = list_resident_actionable_inbox_notifications(
                db,
                character_id=run.character_id,
                allowed_actions=policy.allowed_actions,
                limit=max(1, min(limit, 10)),
            )
            self._log_inbox_notifications_provided(
                db, run=run, session_key=session_key, notifications=notifications
            )
            return [
                _compact_agent_notification_read(_notification_read(db, item))
                for item in notifications
            ]
        else:
            notifications = [
                item
                for item in inbox_repository.list_notifications_for_agent(
                    db,
                    user_id=run.user_id,
                    character_id=run.character_id,
                    limit=max(1, min(limit, 100)),
                )
                if _notification_source_is_public_context_visible(db, item)
            ]
        return [_notification_read(db, item) for item in notifications]

    def mark_agent_tool_notification_read(
        self, db: Session, session_key: str, notification_id: int
    ) -> schemas.NotificationRead:
        run = _get_agent_tool_run(
            db,
            session_key=session_key,
            action="read_notification",
            references=self.workflows,
        )
        notification = inbox_repository.get_notification_for_agent(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            notification_id=notification_id,
        )
        if notification is None or not _notification_source_is_public_context_visible(
            db, notification
        ):
            raise NotificationNotFoundError(notification_id)
        return _notification_read(
            db, notification_writes.mark_notification_read(db, notification)
        )

    def _single_post_id_hint(self, value: str | None) -> str | None:
        if value is None:
            return None
        post_id = value.strip()
        if not post_id:
            return None
        if "," in post_id or any((ch.isspace() for ch in post_id)):
            return None
        return post_id

    def _resolve_inbox_review_target_post_id(
        self, db: Session, *, run: ToolRun, data: schemas.AgentInboxReviewCreate
    ) -> tuple[str | None, str, list[str]]:
        warnings: list[str] = []
        raw_candidate_post_id = data.candidate_post_id or ""
        candidate_post_id = self._single_post_id_hint(data.candidate_post_id)
        resolved_post_id: str | None = None
        if raw_candidate_post_id and candidate_post_id is None:
            warnings.append("candidate_post_id_invalid_format")
        if data.candidate_notification_id is not None:
            notification = inbox_repository.get_notification_for_agent(
                db,
                user_id=run.user_id,
                character_id=run.character_id,
                notification_id=data.candidate_notification_id,
            )
            if notification is None:
                warnings.append("candidate_notification_id_not_found")
            elif notification.notification_type != "reply":
                warnings.append("candidate_notification_id_not_reply")
            else:
                source_post_id = notification.source_post_id or notification.post_id
                source = (
                    post_repository.get_post(db, source_post_id)
                    if source_post_id
                    else None
                )
                if source is not None and _is_post_public_context_visible(db, source):
                    resolved_post_id = source_post_id
                else:
                    warnings.append("candidate_notification_source_post_not_found")
        if candidate_post_id is not None:
            candidate = post_repository.get_post(db, candidate_post_id)
            if candidate is None or not _is_post_public_context_visible(db, candidate):
                warnings.append("candidate_post_id_not_found")
            elif resolved_post_id is None:
                resolved_post_id = candidate_post_id
            elif candidate_post_id != resolved_post_id:
                warnings.append("candidate_post_id_mismatch_used_notification_source")
        stored_candidate_post_id = resolved_post_id or ""
        return (resolved_post_id or run.post_id, stored_candidate_post_id, warnings)

    def note_agent_tool_inbox_review(
        self, db: Session, session_key: str, data: schemas.AgentInboxReviewCreate
    ) -> schemas.AgentToolNoteRead:
        run = _get_agent_tool_run(
            db,
            session_key=session_key,
            action="note_inbox_review",
            references=self.workflows,
        )
        target_post_id, stored_candidate_post_id, warnings = (
            self._resolve_inbox_review_target_post_id(db, run=run, data=data)
        )
        payload = {
            "notification_ids": data.notification_ids[:10],
            "reviewed_thread_ids": data.reviewed_thread_ids[:5],
            "response_plan": data.response_plan or "",
            "no_public_response_reason": data.no_public_response_reason or "",
            "candidate_notification_id": data.candidate_notification_id,
            "candidate_post_id": stored_candidate_post_id,
            "candidate_summary": data.candidate_summary or "",
            "candidate_reason": data.candidate_reason or "",
            "reply_context": data.reply_context or "",
        }
        if warnings:
            payload["warnings"] = warnings
        result = json.dumps(payload, ensure_ascii=False)
        self.workflows.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="inbox_reviewed",
            target_post_id=target_post_id,
            reason="agent_tool_note_inbox_review",
            result=result[:4000],
        )
        if _agent_tool_scratch_lane(session_key) == "inbox":
            self._mark_provided_inbox_notifications_read(
                db, run=run, session_key=session_key
            )
        return schemas.AgentToolNoteRead(
            status="ok", action_type="inbox_reviewed", result=result
        )

    def observe_agent_tool_community(
        self, db: Session, session_key: str, data: schemas.AgentObserveCreate
    ) -> schemas.AgentToolNoteRead:
        run = _get_agent_tool_run(
            db,
            session_key=session_key,
            action="observe",
            requested_post_id=data.target_post_id,
            references=self.workflows,
        )
        _ensure_tick_action_allowed(
            db,
            session_key=session_key,
            run=run,
            action="observe",
            references=self.workflows,
        )
        if data.target_post_id:
            target_post = post_repository.get_post(db, data.target_post_id)
            if target_post is None or not _is_post_public_context_visible(
                db, target_post
            ):
                raise PostNotFoundError(data.target_post_id)
        result = data.summary
        if data.memory_hint:
            result = f"{result}\n메모 힌트: {data.memory_hint}"
        self.workflows.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="observed",
            target_post_id=data.target_post_id or run.post_id,
            reason="agent_tool_observe",
            result=result[:2000],
        )
        return schemas.AgentToolNoteRead(
            status="ok", action_type="observed", result=result
        )
