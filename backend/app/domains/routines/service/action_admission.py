from __future__ import annotations

from app.domains.routines.contracts.action_context import ResidentActionReferences


def _profile_following_status(
    references: ResidentActionReferences,
    *,
    follower_character_id: str,
    target_user_id: str | None = None,
    target_character_id: str | None = None,
) -> str:
    if target_character_id:
        if target_character_id == follower_character_id:
            return "self"
        target_character = references.get_character(target_character_id)
        if target_character is None or target_character.deleted_at is not None:
            return "not_applicable_deleted"
        exists = references.find_follow_id(
            follower_character_id=follower_character_id,
            target_character_id=target_character_id,
        )
        return "yes" if exists is not None else "no"
    if target_user_id:
        return "not_applicable_user"
    return "not_applicable_unknown"


def _v6_allowed_tool_calls(
    references: ResidentActionReferences,
    *,
    character_id: str,
    allowed: set[str],
    post_id: str,
    author_target_type: str | None,
    author_target_id: str | None,
    reply_root_post_id: str,
    reply_label: str,
) -> list[str]:
    post = references.get_post(post_id)
    if post is None or not references.is_post_public_context_visible(post):
        return []
    actions: list[str] = []
    self_authored = post.author_character_id == character_id
    already_replied_to_thread = references.has_character_replied_to_thread(
        root_post_id=reply_root_post_id, character_id=character_id
    )
    direct_reply_to_character = references.is_direct_reply_to_character_post(
        post_id=post_id, character_id=character_id
    )
    if "like" in allowed and not self_authored and not references.has_character_like(
        post_id=post_id, character_id=character_id
    ):
        actions.extend(
            [
                "- tool: angmoo_like_post",
                f"  post_id: {post_id}",
                f"  character_id: {character_id}",
            ]
        )
    if (
        "reply" in allowed
        and not self_authored
        and (not already_replied_to_thread or direct_reply_to_character)
    ):
        actions.extend(
            [
                "- tool: angmoo_reply_to_post_from_brief",
                f"  post_id: {post_id}",
                f"  author_character_id: {character_id}",
                "  brief: write the reply intent, stance, and emotional angle only; do not write final body here.",
            ]
        )
    if "repost" in allowed and not self_authored and not references.has_character_repost(
        post_id=post_id, character_id=character_id
    ):
        actions.extend(
            [
                "- tool: angmoo_repost_post",
                f"  post_id: {post_id}",
                f"  character_id: {character_id}",
            ]
        )
    if (
        "follow" in allowed
        and author_target_type == "character"
        and author_target_id is not None
        and not (author_target_type == "character" and author_target_id == character_id)
        and _profile_following_status(
            references,
            follower_character_id=character_id,
            target_user_id=None,
            target_character_id=author_target_id,
        )
        == "no"
    ):
        actions.extend(
            [
                "- tool: angmoo_follow_profile",
                f"  target_type: {author_target_type}",
                f"  target_id: {author_target_id}",
                f"  follower_character_id: {character_id}",
            ]
        )
    return actions


def _v6_unavailable_post_actions(
    references: ResidentActionReferences,
    *,
    character_id: str,
    allowed: set[str],
    post_id: str,
    author_target_type: str | None,
    author_target_id: str | None,
    reply_root_post_id: str,
) -> list[str]:
    post = references.get_post(post_id)
    if post is None or not references.is_post_public_context_visible(post):
        return []
    unavailable: list[str] = []
    self_authored = post.author_character_id == character_id
    if "like" in allowed:
        if self_authored:
            unavailable.append("- like: self-authored post")
        elif references.has_character_like(post_id=post_id, character_id=character_id):
            unavailable.append("- like: already liked")
    if "reply" in allowed:
        already_replied_to_thread = references.has_character_replied_to_thread(
            root_post_id=reply_root_post_id, character_id=character_id
        )
        direct_reply_to_character = references.is_direct_reply_to_character_post(
            post_id=post_id, character_id=character_id
        )
        if self_authored:
            unavailable.append("- reply: self-authored post")
        elif already_replied_to_thread and not direct_reply_to_character:
            unavailable.append("- reply: already replied to this thread")
    if "repost" in allowed:
        if self_authored:
            unavailable.append("- repost: self-authored post")
        elif references.has_character_repost(post_id=post_id, character_id=character_id):
            unavailable.append("- repost: already reposted")
    if "follow" in allowed:
        if author_target_type is None or author_target_id is None:
            unavailable.append("- follow: author profile target is unavailable")
        elif author_target_type == "character" and author_target_id == character_id:
            unavailable.append("- follow: own profile")
        elif (
            _profile_following_status(
                references,
                follower_character_id=character_id,
                target_user_id=None,
                target_character_id=author_target_id
                if author_target_type == "character"
                else None,
            )
            != "no"
        ):
            unavailable.append("- follow: already following author")
    return unavailable
