from __future__ import annotations

from app.core.context_text import neutralize_context_text
from app.domains.routines.constants import GEMINI_FREE_FEED_CANDIDATE_MAX
from app.domains.routines.contracts.context_reads import ContextNotification
from app.domains.routines.contracts.context_reads import ResidentContextReferences
from app.domains.routines.service.action_admission import _profile_following_status
from app.domains.routines.service.action_candidates import _format_actionable_feed_candidate
from app.domains.routines.service.action_candidates import _format_feed_post_action_candidates
from app.domains.routines.service.action_candidates import _format_feed_post_action_status
from app.domains.routines.service.action_candidates import _format_profile_ref
from app.domains.routines.service.action_candidates import _profile_display_name_for_action_menu
from app.domains.routines.service.action_candidates import _profile_target_parts
from app.domains.routines.service.action_candidates import _resident_action_candidate_id
from app.domains.routines.utils.context_text import _clip_text
from typing import Any


def _format_recent_feed_sections(
    references: ResidentContextReferences, *, run_id: str, character_id: str, allowed_actions: tuple[str, ...]
) -> tuple[str, str]:
    feed = references.list_feed(limit=50)
    if not feed.items:
        return "- none", "- none"
    lines: list[str] = []
    candidate_lines: list[str] = []
    allowed = set(allowed_actions)
    for index, post in enumerate(feed.items, start=1):
        self_authored = post.author_character_id == character_id
        author_target_type, author_target_id = _profile_target_parts(
            user_id=post.author_user_id,
            character_id=post.author_character_id,
        )
        already_liked = references.has_character_like(
            post_id=post.id, character_id=character_id
        )
        already_reposted = references.has_character_repost(
            post_id=post.id, character_id=character_id
        )
        already_following_author = _profile_following_status(
            references,
            follower_character_id=character_id,
            target_user_id=post.author_user_id,
            target_character_id=post.author_character_id,
        )
        available_actions, _blocked_actions = _format_feed_post_action_status(
            allowed_actions=allowed,
            self_authored=self_authored,
            already_liked=already_liked,
            already_reposted=already_reposted,
            already_following_author=already_following_author,
        )
        action_candidates = _format_feed_post_action_candidates(
            run_id=run_id,
            character_id=character_id,
            available_actions=available_actions,
            post_id=post.id,
            author_target_type=author_target_type,
            author_target_id=author_target_id,
        )
        reply_next_step = (
            (
                "candidate_id="
                + _resident_action_candidate_id(
                    run_id=run_id,
                    character_id=character_id,
                    action_type="reply",
                    target_key=f"post:{post.id}",
                )
                + f"; call angmoo_get_post_thread({post.id}) before any reply action"
            )
            if "reply" in allowed
            else "none"
        )
        candidate = _format_actionable_feed_candidate(
            index=index,
            post_id=post.id,
            author_name=post.author_name,
            title=post.title,
            available_actions=available_actions,
            reply_next_step=reply_next_step,
            action_candidates=action_candidates,
        )
        if candidate is not None:
            candidate_lines.append(candidate)
        lines.append(
            "\n".join(
                [
                    f"{index}. post_id: {post.id}",
                    f"   post_type: {post.post_type}",
                    f"   repost_of_post_id: {post.repost_of_post_id or '-'}",
                    f"   author: {post.author_name} ({_format_profile_ref(user_id=post.author_user_id, character_id=post.author_character_id)})",
                    f"   created_at: {post.created_at.isoformat()}",
                    f"   title: {_clip_text(neutralize_context_text(post.title), 160)}",
                    f"   body: {_clip_text(neutralize_context_text(post.body), 1200)}",
                    f"   stats: likes={post.like_count}, replies={post.reply_count}, reposts={post.repost_count}",
                    "   reading_context_only: yes",
                    "   surface_style: neutralized",
                ]
            )
        )
    return "\n".join(lines), "\n".join(candidate_lines) or "- none"


def _collect_v6_inbox_candidates(
    references: ResidentContextReferences,
    *,
    character_id: str,
    allowed_actions: tuple[str, ...],
    limit: int = 10,
) -> list[dict[str, Any]]:
    notifications = references.list_actionable_inbox(
        character_id=character_id,
        allowed_actions=allowed_actions,
        limit=max(1, min(limit, 10)),
    )
    candidates: list[dict[str, Any]] = []
    for notification in notifications:
        source_post_id = notification.source_post_id or notification.post_id
        if source_post_id is None:
            continue
        source = references.get_post(source_post_id)
        root_post_id = references.thread_root_post_id(source_post_id)
        if source is None or root_post_id is None:
            continue
        root = references.get_post(root_post_id)
        actor_target_type, actor_target_id = _profile_target_parts(
            user_id=notification.actor_user_id,
            character_id=notification.actor_character_id,
        )
        candidates.append(
            {
                "notification_id": notification.id,
                "root_post_id": root_post_id,
                "source_post_id": source_post_id,
                "actor_name": _profile_display_name_for_action_menu(
                    references,
                    user_id=notification.actor_user_id,
                    character_id=notification.actor_character_id,
                ),
                "actor_ref": _format_profile_ref(
                    user_id=notification.actor_user_id,
                    character_id=notification.actor_character_id,
                ),
                "actor_target_type": actor_target_type,
                "actor_target_id": actor_target_id,
                "source_body": _clip_text(neutralize_context_text(source.body), 400),
                "parent_body": _clip_text(
                    neutralize_context_text(root.body if root else ""), 300
                ),
                "created_at": notification.created_at.isoformat(),
            }
        )
    return candidates


def _v6_inbox_candidates_from_review(
    references: ResidentContextReferences, *, character_id: str, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    raw_notification_id = payload.get("candidate_notification_id")
    if isinstance(raw_notification_id, bool):
        return []
    try:
        notification_id = int(raw_notification_id)
    except (TypeError, ValueError):
        return []
    notification = references.find_review_notification(notification_id=notification_id, character_id=character_id)
    if notification is None:
        return []
    source_post_id = notification.source_post_id or notification.post_id
    if source_post_id is None:
        return []
    source = references.get_post(source_post_id)
    root_post_id = references.thread_root_post_id(source_post_id)
    if source is None or root_post_id is None:
        return []
    root = references.get_post(root_post_id)
    actor_target_type, actor_target_id = _profile_target_parts(
        user_id=notification.actor_user_id,
        character_id=notification.actor_character_id,
    )
    return [
        {
            "notification_id": notification.id,
            "root_post_id": root_post_id,
            "source_post_id": source_post_id,
            "actor_name": _profile_display_name_for_action_menu(
                references,
                user_id=notification.actor_user_id,
                character_id=notification.actor_character_id,
            ),
            "actor_ref": _format_profile_ref(
                user_id=notification.actor_user_id,
                character_id=notification.actor_character_id,
            ),
            "actor_target_type": actor_target_type,
            "actor_target_id": actor_target_id,
            "source_body": _clip_text(neutralize_context_text(source.body), 500),
            "root_summary": _clip_text(
                neutralize_context_text(
                    str(payload.get("candidate_summary") or (root.body if root else ""))
                ),
                500,
            ),
            "candidate_reason": _clip_text(
                neutralize_context_text(str(payload.get("candidate_reason") or "")),
                500,
            ),
            "reply_context": _clip_text(
                neutralize_context_text(str(payload.get("reply_context") or "")),
                700,
            ),
            "created_at": notification.created_at.isoformat(),
        }
    ]


def _format_v6_feed_interests(
    references: ResidentContextReferences, *, feed_interest_payload: dict[str, Any]
) -> str:
    interests = feed_interest_payload.get("interests")
    if not isinstance(interests, list) or not interests:
        return "- none"
    lines: list[str] = []
    for index, item in enumerate(interests[:GEMINI_FREE_FEED_CANDIDATE_MAX], start=1):
        if not isinstance(item, dict):
            continue
        post_id = str(item.get("post_id") or "").strip()
        if not post_id:
            continue
        post = references.get_post(post_id)
        if post is None or not references.is_post_public_context_visible(post):
            continue
        topic_signature = _clip_text(
            neutralize_context_text(
                str(feed_interest_payload.get("topic_signature") or "")
            ),
            300,
        )
        novelty_basis = _clip_text(
            neutralize_context_text(
                str(feed_interest_payload.get("novelty_basis") or "")
            ),
            300,
        )
        lines.append(
            "\n".join(
                [
                    f"{index}. post_id: {post.id}",
                    f"   author: {_profile_display_name_for_action_menu(references, user_id=post.author_user_id, character_id=post.author_character_id)}",
                    f"   topic_signature: {topic_signature or '-'}",
                    f"   novelty_basis: {novelty_basis or '-'}",
                    f"   summary: {_clip_text(neutralize_context_text(str(item.get('summary') or post.title)), 240)}",
                    f"   interest_reason: {_clip_text(neutralize_context_text(str(item.get('reason') or '')), 240)}",
                    f"   short_reply_context: {_clip_text(neutralize_context_text(post.body), 500)}",
                ]
            )
        )
    return "\n".join(lines) if lines else "- none"


def _format_recent_own_posts_to_avoid(references: ResidentContextReferences, *, character_id: str) -> str:
    posts = references.list_recent_own_posts(character_id=character_id)
    if not posts:
        return "- none"
    return "\n".join(
        (
            f"- post_id: {post.id}; type={post.post_type}; created_at={post.created_at.isoformat()}; "
            f"title={_clip_text(neutralize_context_text(post.title), 120)}; "
            f"body={_clip_text(neutralize_context_text(post.body), 300)}; "
            "surface_style=neutralized"
        )
        for post in posts
    )


def _format_recent_activity_summary(references: ResidentContextReferences, *, character_id: str) -> str:
    logs = references.list_recent_activity(character_id, limit=8)
    if not logs:
        return "- none"
    return "\n".join(
        (
            f"- {log.created_at.isoformat()} {log.action_type}: "
            f"{_clip_text(neutralize_context_text(references.activity_result_text(log.result, log.reason)), 240)}"
        )
        for log in logs
    )


def _format_inbox_threads(
    references: ResidentContextReferences,
    *,
    run_id: str,
    user_id: str,
    character_id: str,
    allowed_actions: tuple[str, ...],
) -> tuple[str, bool]:
    notifications = references.list_unread_reply_notifications(character_id=character_id, limit=30)
    grouped: dict[str, list[ContextNotification]] = {}
    for notification in notifications:
        anchor_post_id = notification.source_post_id or notification.post_id
        if anchor_post_id is None:
            continue
        root_post_id = references.thread_root_post_id(anchor_post_id)
        if root_post_id is None:
            continue
        grouped.setdefault(root_post_id, []).append(notification)
    if not grouped:
        return "- none", False

    lines: list[str] = []
    follow_allowed = "follow" in set(allowed_actions)
    for root_post_id, items in list(grouped.items())[:5]:
        root_post = references.get_post(root_post_id)
        root_title = _clip_text(
            neutralize_context_text(root_post.title if root_post else ""), 160
        )
        notification_ids = ", ".join(str(item.id) for item in items)
        lines.append(
            f"- root_post_id: {root_post_id}; notification_ids: [{notification_ids}]; root_title: {root_title}"
        )
        for item in items[:5]:
            source = (
                references.get_post(item.source_post_id)
                if item.source_post_id
                else None
            )
            if item.source_post_id and source is None:
                continue
            actor_ref = _format_profile_ref(
                user_id=item.actor_user_id, character_id=item.actor_character_id
            )
            actor_following_status = _profile_following_status(
                references,
                follower_character_id=character_id,
                target_user_id=item.actor_user_id,
                target_character_id=item.actor_character_id,
            )
            source_post_id = item.source_post_id or item.post_id or "-"
            source_body = _clip_text(
                neutralize_context_text(source.body if source else ""), 500
            )
            follow_candidate = "none"
            target_type, target_id = _profile_target_parts(
                user_id=item.actor_user_id,
                character_id=item.actor_character_id,
            )
            if (
                follow_allowed
                and actor_following_status == "no"
                and target_type is not None
                and target_id is not None
            ):
                follow_candidate = _resident_action_candidate_id(
                    run_id=run_id,
                    character_id=character_id,
                    action_type="follow",
                    target_key=f"{target_type}:{target_id}",
                )
            lines.append(
                f"  - notification_id: {item.id}; source_post_id: {source_post_id}; actor={actor_ref}; actor_already_following={actor_following_status}; follow_candidate_id={follow_candidate}; created_at={item.created_at.isoformat()}; body={source_body}; surface_style=neutralized"
            )
    return "\n".join(lines), True
