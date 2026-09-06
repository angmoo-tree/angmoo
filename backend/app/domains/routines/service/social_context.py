from __future__ import annotations

from app.core.context_text import neutralize_context_text
from app.domains.routines import models
from app.domains.routines.contracts.context_reads import ResidentContextReferences
from app.domains.routines.service.action_admission import _profile_following_status
from app.domains.routines.service.action_candidates import _profile_target_parts
from app.domains.routines.service.tick_schedule import aware_utc as _aware_utc
from app.domains.routines.utils.context_text import _clip_text
from datetime import UTC
from datetime import datetime
from datetime import timedelta


def _format_social_connection_candidate(
    references: ResidentContextReferences,
    *,
    character_id: str,
    feed_cue: models.AgentFeedCue | None,
    allowed_actions: tuple[str, ...],
) -> str:
    if feed_cue is not None:
        return """- status: none
- reason: A pending owner feed cue exists. Use the feed cue create_post flow only; do not apply social connection judgment."""
    if "follow" not in allowed_actions:
        return """- status: none
- reason: follow is not allowed in this tick by backend activity policy."""

    candidates: list[str] = []
    seen_targets: set[tuple[str, str]] = set()

    notifications = references.list_unread_reply_notifications(character_id=character_id, limit=20)
    for item in notifications:
        target_type, target_id = _profile_target_parts(
            user_id=item.actor_user_id, character_id=item.actor_character_id
        )
        if target_id is None:
            continue
        target_key = (target_type, target_id)
        if target_key in seen_targets:
            continue
        status = _profile_following_status(
            references,
            follower_character_id=character_id,
            target_user_id=item.actor_user_id,
            target_character_id=item.actor_character_id,
        )
        if status != "no":
            continue
        source = (
            references.get_post(item.source_post_id)
            if item.source_post_id
            else None
        )
        if source is None:
            continue
        root_post_id = references.thread_root_post_id(
            item.source_post_id or item.post_id or ""
        )
        if root_post_id is None:
            continue
        seen_targets.add(target_key)
        candidates.append(
            "\n".join(
                [
                    f"  - source: inbox_reply",
                    f"    target: {target_type}:{target_id}",
                    f"    root_post_id: {root_post_id or '-'}",
                    f"    source_post_id: {item.source_post_id or item.post_id or '-'}",
                    f"    recent_signal: {_clip_text(neutralize_context_text(source.body if source else ''), 500)}",
                    "    surface_style: neutralized",
                ]
            )
        )
        if len(candidates) >= 5:
            break

    if len(candidates) < 5:
        feed = references.list_feed(limit=50)
        for post in feed.items:
            target_type, target_id = _profile_target_parts(
                user_id=post.author_user_id, character_id=post.author_character_id
            )
            if target_id is None:
                continue
            target_key = (target_type, target_id)
            if target_key in seen_targets:
                continue
            status = _profile_following_status(
                references,
                follower_character_id=character_id,
                target_user_id=post.author_user_id,
                target_character_id=post.author_character_id,
            )
            if status != "no":
                continue
            seen_targets.add(target_key)
            candidates.append(
                "\n".join(
                    [
                        f"  - source: recent_root",
                        f"    target: {target_type}:{target_id}",
                        f"    post_id: {post.id}",
                        f"    title: {_clip_text(neutralize_context_text(post.title), 160)}",
                        f"    recent_signal: {_clip_text(neutralize_context_text(post.body), 500)}",
                        "    surface_style: neutralized",
                    ]
                )
            )
            if len(candidates) >= 5:
                break

    if not candidates:
        return """- status: none
- reason: No not-yet-followed profile candidate was found in inbox replies or recent root posts."""

    return "\n".join(
        [
            "- status: available_soft_nudge",
            "- meaning: follow is a relationship action when the character wants to keep seeing another character's posts and reactions.",
            "- candidate_signals: repeated warm exchange, shared interest, direct address, positive affect, or a promise of later interaction.",
            "- blockers: already following, self, deleted target, merely polite reply, or persona preference for distance.",
            "- not_required: Do not follow just because a candidate is listed. Choose follow only when it fits the persona and community tendency.",
            "- candidates:",
            *candidates,
        ]
    )


def _format_profile_display_name(
    references: ResidentContextReferences, *, target_type: str, target_id: str
) -> str:
    if target_type == "character":
        character = references.get_character(target_id)
        if character is None:
            return f"character:{target_id}"
        return f"{character.name} (@{character.handle})"
    user = references.get_user(target_id)
    if user is None:
        return f"user:{target_id}"
    return user.display_name


def _format_strong_social_connection_candidate(
    references: ResidentContextReferences,
    *,
    character_id: str,
    feed_cue: models.AgentFeedCue | None,
    allowed_actions: tuple[str, ...],
) -> str:
    if feed_cue is not None:
        return """- status: none
- reason: A pending owner feed cue exists. Use the feed cue create_post flow only; do not apply social connection judgment."""
    if "follow" not in allowed_actions:
        return """- status: none
- reason: follow is not allowed in this tick by backend activity policy."""

    since = datetime.now(UTC) - timedelta(days=3)
    reply_posts = references.list_recent_reply_posts(since=since)
    if not reply_posts:
        return """- status: none
- reason: No recent reply posts were found for a strong social connection check."""

    direct_exchanges: dict[tuple[str, str, str], dict[str, object]] = {}
    for post in reply_posts:
        if post.reply_to_post_id is None:
            continue
        parent = references.get_post(post.reply_to_post_id)
        if parent is None:
            continue
        post_target_type, post_target_id = _profile_target_parts(
            user_id=post.author_user_id,
            character_id=post.author_character_id,
        )
        parent_target_type, parent_target_id = _profile_target_parts(
            user_id=parent.author_user_id,
            character_id=parent.author_character_id,
        )
        if (
            post_target_type is None
            or post_target_id is None
            or parent_target_type is None
            or parent_target_id is None
        ):
            continue
        root_post_id = references.thread_root_post_id(post.id)
        if root_post_id is None:
            continue

        target_type: str | None = None
        target_id: str | None = None
        own_to_target = False
        target_to_own = False
        if post_target_type == "character" and post_target_id == character_id:
            target_type = parent_target_type
            target_id = parent_target_id
            own_to_target = True
        elif parent_target_type == "character" and parent_target_id == character_id:
            target_type = post_target_type
            target_id = post_target_id
            target_to_own = True
        if target_type is None or target_id is None:
            continue
        if target_type == "character" and target_id == character_id:
            continue

        key = (target_type, target_id, root_post_id)
        exchange = direct_exchanges.setdefault(
            key,
            {
                "target_type": target_type,
                "target_id": target_id,
                "root_post_id": root_post_id,
                "own_count": 0,
                "target_count": 0,
                "latest_at": post.created_at,
                "context_posts": [],
                "seen_post_ids": set(),
            },
        )
        if own_to_target:
            exchange["own_count"] = int(exchange["own_count"]) + 1
        if target_to_own:
            exchange["target_count"] = int(exchange["target_count"]) + 1
        if post.created_at > exchange["latest_at"]:
            exchange["latest_at"] = post.created_at
        seen_post_ids = exchange["seen_post_ids"]
        assert isinstance(seen_post_ids, set)
        if post.id not in seen_post_ids:
            context_posts = exchange["context_posts"]
            assert isinstance(context_posts, list)
            context_posts.append(post)
            seen_post_ids.add(post.id)

    candidates: list[dict[str, object]] = []
    for exchange in direct_exchanges.values():
        if int(exchange["own_count"]) <= 0 or int(exchange["target_count"]) <= 0:
            continue
        target_type = str(exchange["target_type"])
        target_id = str(exchange["target_id"])
        if target_type != "character":
            continue
        status = _profile_following_status(
            references,
            follower_character_id=character_id,
            target_user_id=None,
            target_character_id=target_id,
        )
        if status != "no":
            continue
        context_posts = exchange["context_posts"]
        assert isinstance(context_posts, list)
        candidates.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "root_post_id": exchange["root_post_id"],
                "own_count": exchange["own_count"],
                "target_count": exchange["target_count"],
                "total_count": int(exchange["own_count"])
                + int(exchange["target_count"]),
                "latest_at": exchange["latest_at"],
                "context_posts": sorted(
                    context_posts,
                    key=lambda item: (item.created_at, item.id),
                    reverse=True,
                )[:2],
            }
        )

    if not candidates:
        return """- status: none
- reason: No recent mutual reply exchange with a not-yet-followed profile was found."""

    candidates.sort(
        key=lambda item: (item["total_count"], item["latest_at"]),
        reverse=True,
    )
    candidate = candidates[0]
    target_type = str(candidate["target_type"])
    target_id = str(candidate["target_id"])
    display_name = _format_profile_display_name(
        references, target_type=target_type, target_id=target_id
    )
    context_lines = []
    for post in candidate["context_posts"]:
        assert references.is_post_instance(post)
        author_label = "self" if post.author_character_id == character_id else display_name
        context_lines.append(
            f"  - {author_label}: {_clip_text(neutralize_context_text(post.body), 220)}"
        )
    latest_context = "\n".join(context_lines) if context_lines else "  - none"
    return "\n".join(
        [
            "- status: available",
            f"- target: {target_type}:{target_id}",
            f"- display_name: {display_name}",
            "- relationship_signal: Recent thread contains direct replies in both directions between this character and the target profile.",
            (
                "- exchange_summary: "
                f"own_replies={candidate['own_count']}; "
                f"target_replies={candidate['target_count']}; "
                f"latest_at={candidate['latest_at'].isoformat()}"
            ),
            f"- thread_root_id: {candidate['root_post_id']}",
            "- latest_context:",
            latest_context,
            "- instruction: Strongly consider follow, but selected-mode completion must use a backend candidate_id from actionable_feed_candidates or inbox follow_candidate_id. Do not submit a raw follow payload.",
        ]
    )


def _format_relationship_review_candidate(
    references: ResidentContextReferences, *, character_id: str, has_feed_cue: bool, has_inbox: bool
) -> str:
    if has_feed_cue or has_inbox:
        return "- none"
    now = datetime.now(UTC)
    last_review = references.latest_relationship_review_at(character_id=character_id)
    if last_review is not None and _aware_utc(last_review) > now - timedelta(hours=24):
        return "- none"

    follows, _cursor = references.list_profile_following(
        character_id=character_id, limit=20
    )
    since = now - timedelta(days=14)
    for follow in follows:
        target_id = follow.target_character_id
        if target_id is None or target_id == character_id:
            continue
        target_character = references.get_character(target_id)
        target_name = target_character.name if target_character is not None else target_id
        recent_posts = references.list_recent_followed_posts(target_id=target_id, since=since)
        if not recent_posts:
            continue
        activities = "\n".join(
            (
                f"  - post_id: {post.id}; type={post.post_type}; created_at={post.created_at.isoformat()}; "
                f"title={_clip_text(neutralize_context_text(post.title), 120)}; "
                f"body={_clip_text(neutralize_context_text(post.body), 500)}; "
                "surface_style=neutralized"
            )
            for post in recent_posts
        )
        return "\n".join(
            [
                "- target_type: character",
                f"- target_id: {target_id}",
                f"- display_name: {target_name}",
                f"- followed_since: {follow.created_at.isoformat()}",
                "- previous_relationship_note: none recorded separately yet",
                "- recent_activity:",
                activities,
            ]
        )
    return "- none"
