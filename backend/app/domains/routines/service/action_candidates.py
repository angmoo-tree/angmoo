from __future__ import annotations

from app.domains.routines.contracts.action_context import ResidentActionReferences

from app.core.context_text import neutralize_context_text
from app.domains.routines.utils.context_text import _clip_text
from typing import Any
import hashlib


def _format_profile_ref(
    *, user_id: str | None = None, character_id: str | None = None
) -> str:
    if character_id:
        return f"character:{character_id}"
    if user_id:
        return f"user:{user_id}"
    return "unknown"


def _profile_target_parts(
    *, user_id: str | None = None, character_id: str | None = None
) -> tuple[str | None, str | None]:
    if character_id:
        return "character", character_id
    return None, None


def _resident_action_candidate_id(
    *,
    run_id: str,
    character_id: str,
    action_type: str,
    target_key: str,
) -> str:
    digest = hashlib.sha256(
        f"{run_id}:{character_id}:{action_type}:{target_key}".encode("utf-8")
    ).hexdigest()[:12]
    return f"cand_{action_type}_{digest}"


def _format_v6_inbox_scan_context(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "- none"
    lines: list[str] = []
    for index, item in enumerate(candidates[:10], start=1):
        lines.append(
            "\n".join(
                [
                    f"{index}. notification_id: {item['notification_id']}",
                    f"   root_post_id: {item['root_post_id']}",
                    f"   source_post_id: {item['source_post_id']}",
                    f"   actor: {item['actor_name']} ({item['actor_ref']})",
                    f"   reply_summary: {item['source_body']}",
                    f"   parent_preview: {item.get('parent_body') or '-'}",
                    f"   created_at: {item['created_at']}",
                ]
            )
        )
    return "\n".join(lines)


def _format_v6_inbox_compact_candidate(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "- none"
    item = candidates[0]
    return "\n".join(
        [
            "1. selected inbox candidate",
            f"   notification_id: {item['notification_id']}",
            f"   root_post_id: {item['root_post_id']}",
            f"   target_post_id: {item['source_post_id']}",
            f"   actor: {item['actor_name']} ({item['actor_ref']})",
            f"   reply_summary: {item['source_body']}",
            f"   parent_or_root_summary: {item.get('root_summary') or '-'}",
            f"   character_interest_reason: {item.get('candidate_reason') or '-'}",
            f"   short_reply_context: {item.get('reply_context') or '-'}",
        ]
    )


def _format_feed_post_action_status(
    *,
    allowed_actions: set[str],
    self_authored: bool,
    already_liked: bool,
    already_reposted: bool,
    already_following_author: str,
) -> tuple[str, str]:
    available: list[str] = []
    blocked: list[str] = []
    if "reply" in allowed_actions:
        if self_authored:
            blocked.append("reply(self_authored)")
        else:
            available.append("reply(thread_required)")
    if "like" in allowed_actions:
        if already_liked:
            blocked.append("like(already_liked)")
        else:
            available.append("like")
    if "repost" in allowed_actions:
        if already_reposted:
            blocked.append("repost(already_reposted)")
        else:
            available.append("repost")
    if "follow" in allowed_actions:
        if self_authored:
            blocked.append("follow(self_authored)")
        elif already_following_author == "yes":
            blocked.append("follow(already_following_author)")
        elif already_following_author != "no":
            blocked.append(f"follow({already_following_author})")
        else:
            available.append("follow")
    return ", ".join(available) or "none", ", ".join(blocked) or "none"


def _format_feed_post_action_candidates(
    *,
    run_id: str,
    character_id: str,
    available_actions: str,
    post_id: str,
    author_target_type: str | None,
    author_target_id: str | None,
) -> str:
    actions = {item.strip() for item in available_actions.split(",")}
    candidates: list[str] = []
    if "like" in actions:
        candidate_id = _resident_action_candidate_id(
            run_id=run_id,
            character_id=character_id,
            action_type="like",
            target_key=f"post:{post_id}",
        )
        candidates.append(
            f"candidate_id={candidate_id}; action_type=like; post_id={post_id}"
        )
    if "repost" in actions:
        candidate_id = _resident_action_candidate_id(
            run_id=run_id,
            character_id=character_id,
            action_type="repost",
            target_key=f"post:{post_id}",
        )
        candidates.append(
            f"candidate_id={candidate_id}; action_type=repost; post_id={post_id}"
        )
    if (
        "follow" in actions
        and author_target_type == "character"
        and author_target_id is not None
    ):
        candidate_id = _resident_action_candidate_id(
            run_id=run_id,
            character_id=character_id,
            action_type="follow",
            target_key=f"{author_target_type}:{author_target_id}",
        )
        candidates.append(
            (
                f"candidate_id={candidate_id}; action_type=follow; "
                f"target={author_target_type}:{author_target_id}"
            )
        )
    return " | ".join(candidates) or "none"


def _format_actionable_feed_candidate(
    *,
    index: int,
    post_id: str,
    author_name: str,
    title: str,
    available_actions: str,
    reply_next_step: str,
    action_candidates: str,
) -> str | None:
    if available_actions == "none":
        return None
    parts = [
        f"{index}. post_id: {post_id}",
        f"   author: {author_name}",
        f"   title: {_clip_text(neutralize_context_text(title), 120)}",
        f"   actions: {available_actions}",
        "   surface_style: neutralized",
    ]
    if "reply(thread_required)" in {
        item.strip() for item in available_actions.split(",")
    }:
        parts.append(f"   reply_next_step: {reply_next_step}")
    if action_candidates != "none":
        parts.append(f"   action_candidates: {action_candidates}")
    return "\n".join(parts)


def _profile_display_name_for_action_menu(
    references: ResidentActionReferences, *, user_id: str | None = None, character_id: str | None = None
) -> str:
    if character_id:
        character = references.get_character(character_id)
        if character is not None:
            return f"{character.name} (@{character.handle})"
        return f"character:{character_id}"
    if user_id:
        user = references.get_user(user_id)
        if user is not None:
            return user.display_name
        return f"user:{user_id}"
    return "unknown"
