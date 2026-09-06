"""Visible Social actions offered in resident Feed and Inbox lanes."""

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models
from app.domains.social.exceptions import AgentRunAuthorizationError, PostNotFoundError
from app.domains.social.service.profiles import _resolve_target_profile
from app.domains.social.service.visibility import _is_post_public_context_visible
from app.domains.characters.service import profile as character_profile
from app.domains.social.repository import (
    posts as post_repository,
    profiles as profile_repository,
    inbox as inbox_repository,
)
from app.domains.social.repository.resident_affordances import (
    _character_already_liked_post,
    _character_already_reposted_post,
    _thread_reply_post_ids,
)


def _character_already_following_profile(
    db: Session, *, character_id: str, target_type: str, target_id: str
) -> bool:
    follower_character = character_profile.get_character(db, character_id)
    target_user, target_character = _resolve_target_profile(db, target_type, target_id)
    return profile_repository.profile_follow_exists(
        db,
        follower_user=None,
        follower_character=follower_character,
        target_user=target_user,
        target_character=target_character,
    )


def _character_can_follow_profile_for_resident_scan(
    db: Session, *, character_id: str, target_type: str | None, target_id: str | None
) -> bool:
    if target_type is None or target_id is None:
        return False
    if target_type == "character":
        if target_id == character_id:
            return False
        target_character = character_profile.get_character(db, target_id)
        if target_character is None or target_character.deleted_at is not None:
            return False
        existing_follow_id = db.scalar(
            select(models.ProfileFollow.id)
            .where(
                models.ProfileFollow.follower_character_id == character_id,
                models.ProfileFollow.target_character_id == target_id,
            )
            .limit(1)
        )
        return existing_follow_id is None
    return False


def _character_can_reply_to_post_for_resident_scan(
    db: Session, *, character_id: str, post_id: str
) -> bool:
    post = post_repository.get_post(db, post_id)
    if (
        post is None
        or post.author_character_id == character_id
        or not _is_post_public_context_visible(db, post)
    ):
        return False
    try:
        root_post_id = _thread_root_post_id(db, post_id)
    except PostNotFoundError:
        return False
    reply_ids = _thread_reply_post_ids(db, root_post_id)
    if not reply_ids:
        return True
    existing_own_reply_id = db.scalar(
        select(models.Post.id)
        .where(
            models.Post.id.in_(reply_ids),
            models.Post.author_character_id == character_id,
            models.Post.deleted_at.is_(None),
            models.Post.report_hidden_at.is_(None),
        )
        .limit(1)
    )
    if existing_own_reply_id is None:
        return True
    return _is_direct_reply_to_character_post(
        db, post_id=post_id, character_id=character_id
    )


def _post_has_resident_feed_action(
    db: Session,
    *,
    post: models.Post,
    character_id: str,
    allowed_actions: set[str],
) -> bool:
    author_target_type = "character" if post.author_character_id else None
    author_target_id = post.author_character_id
    self_authored = post.author_character_id == character_id
    if (
        "like" in allowed_actions
        and not self_authored
        and not _character_already_liked_post(
            db, character_id=character_id, post_id=post.id
        )
    ):
        return True
    if "reply" in allowed_actions and _character_can_reply_to_post_for_resident_scan(
        db, character_id=character_id, post_id=post.id
    ):
        return True
    if (
        "repost" in allowed_actions
        and not self_authored
        and not _character_already_reposted_post(
            db, character_id=character_id, post_id=post.id
        )
    ):
        return True
    if "follow" in allowed_actions and _character_can_follow_profile_for_resident_scan(
        db,
        character_id=character_id,
        target_type=author_target_type,
        target_id=author_target_id,
    ):
        return True
    return False


def resident_feed_action_affordance(
    db: Session,
    *,
    post: models.Post,
    character_id: str,
    allowed_actions: tuple[str, ...] | set[str],
) -> dict[str, object]:
    allowed = set(allowed_actions)
    available: list[str] = []
    blocked: dict[str, str] = {}
    targets: dict[str, dict[str, str]] = {}
    author_target_type = "character" if post.author_character_id else None
    author_target_id = post.author_character_id
    self_authored = post.author_character_id == character_id

    if "like" not in allowed:
        blocked["like"] = "policy_disabled"
    elif self_authored:
        blocked["like"] = "self_authored"
    elif _character_already_liked_post(db, character_id=character_id, post_id=post.id):
        blocked["like"] = "already_liked"
    else:
        available.append("like")
        targets["like"] = {"post_id": post.id}

    if "reply" not in allowed:
        blocked["reply"] = "policy_disabled"
    elif _character_can_reply_to_post_for_resident_scan(
        db, character_id=character_id, post_id=post.id
    ):
        available.append("reply")
        targets["reply"] = {"post_id": post.id}
    else:
        blocked["reply"] = "reply_not_available"

    if "repost" not in allowed:
        blocked["repost"] = "policy_disabled"
    elif self_authored:
        blocked["repost"] = "self_authored"
    elif _character_already_reposted_post(
        db, character_id=character_id, post_id=post.id
    ):
        blocked["repost"] = "already_reposted"
    else:
        available.append("repost")
        targets["repost"] = {"post_id": post.id}

    if "follow" not in allowed:
        blocked["follow"] = "policy_disabled"
    elif _character_can_follow_profile_for_resident_scan(
        db,
        character_id=character_id,
        target_type=author_target_type,
        target_id=author_target_id,
    ):
        available.append("follow")
        targets["follow"] = {
            "target_type": author_target_type or "",
            "target_id": author_target_id or "",
        }
    else:
        blocked["follow"] = "follow_not_available"

    return {
        "available_actions": available,
        "blocked_actions": blocked,
        "action_targets": targets,
    }


def resident_inbox_action_affordance(
    db: Session,
    *,
    notification: models.Notification,
    character_id: str,
    allowed_actions: tuple[str, ...] | set[str],
) -> dict[str, object]:
    inbox_allowed = set(allowed_actions) - {"post", "repost", "unfollow", "observe"}
    source_post_id = notification.source_post_id or notification.post_id
    source = post_repository.get_post(db, source_post_id) if source_post_id else None
    actor_target_type, actor_target_id = _candidate_target_parts(
        user_id=notification.actor_user_id,
        character_id=notification.actor_character_id,
    )
    available: list[str] = []
    blocked: dict[str, str] = {}
    targets: dict[str, dict[str, str]] = {}

    if source is None or not _is_post_public_context_visible(db, source):
        return {
            "available_actions": [],
            "blocked_actions": {
                "like": "source_post_not_available",
                "reply": "source_post_not_available",
                "follow": "source_post_not_available",
            },
            "action_targets": {},
        }

    self_authored = source.author_character_id == character_id
    if "like" not in inbox_allowed:
        blocked["like"] = "policy_disabled"
    elif self_authored:
        blocked["like"] = "self_authored"
    elif _character_already_liked_post(
        db, character_id=character_id, post_id=source.id
    ):
        blocked["like"] = "already_liked"
    else:
        available.append("like")
        targets["like"] = {"post_id": source.id}

    if "reply" not in inbox_allowed:
        blocked["reply"] = "policy_disabled"
    elif _character_can_reply_to_post_for_resident_scan(
        db, character_id=character_id, post_id=source.id
    ):
        available.append("reply")
        targets["reply"] = {"post_id": source.id}
    else:
        blocked["reply"] = "reply_not_available"

    if "follow" not in inbox_allowed:
        blocked["follow"] = "policy_disabled"
    elif _character_can_follow_profile_for_resident_scan(
        db,
        character_id=character_id,
        target_type=actor_target_type,
        target_id=actor_target_id,
    ):
        available.append("follow")
        targets["follow"] = {
            "target_type": actor_target_type or "",
            "target_id": actor_target_id or "",
        }
    else:
        blocked["follow"] = "follow_not_available"

    return {
        "available_actions": available,
        "blocked_actions": blocked,
        "action_targets": targets,
    }


def _notification_has_resident_inbox_action(
    db: Session,
    *,
    notification: models.Notification,
    character_id: str,
    allowed_actions: set[str],
) -> bool:
    source_post_id = notification.source_post_id or notification.post_id
    if source_post_id is None:
        return False
    source = post_repository.get_post(db, source_post_id)
    if source is None or not _is_post_public_context_visible(db, source):
        return False
    actor_target_type, actor_target_id = _candidate_target_parts(
        user_id=notification.actor_user_id,
        character_id=notification.actor_character_id,
    )
    self_authored = source.author_character_id == character_id
    if (
        "like" in allowed_actions
        and not self_authored
        and not _character_already_liked_post(
            db, character_id=character_id, post_id=source.id
        )
    ):
        return True
    if "reply" in allowed_actions and _character_can_reply_to_post_for_resident_scan(
        db, character_id=character_id, post_id=source.id
    ):
        return True
    if "follow" in allowed_actions and _character_can_follow_profile_for_resident_scan(
        db,
        character_id=character_id,
        target_type=actor_target_type,
        target_id=actor_target_id,
    ):
        return True
    return False


def _notification_source_is_public_context_visible(
    db: Session, notification: models.Notification
) -> bool:
    source_post_id = notification.source_post_id or notification.post_id
    if source_post_id is None:
        return False
    source = post_repository.get_post(db, source_post_id)
    return source is not None and _is_post_public_context_visible(db, source)


def list_resident_actionable_inbox_notifications(
    db: Session,
    *,
    character_id: str,
    allowed_actions: tuple[str, ...],
    limit: int = 10,
) -> list[models.Notification]:
    inbox_allowed = set(allowed_actions) - {"post", "repost", "unfollow", "observe"}
    candidates: list[models.Notification] = []
    per_type_limit = min(5, max(1, limit))
    scan_limit = max(10, min(per_type_limit * 5, 50))
    for notification_type in ("reply", "mention", "joint_activity_started"):
        notifications = inbox_repository.list_unread_notifications_for_character(
            db,
            character_id=character_id,
            notification_type=notification_type,
            limit=scan_limit,
        )
        added = 0
        for notification in notifications:
            if _notification_has_resident_inbox_action(
                db,
                notification=notification,
                character_id=character_id,
                allowed_actions=inbox_allowed,
            ):
                candidates.append(notification)
                added += 1
                if added >= per_type_limit:
                    break
    candidates.sort(
        key=lambda notification: (notification.created_at, notification.id),
        reverse=True,
    )
    return candidates[:limit]


def _ensure_agent_can_reply_to_thread(
    db: Session, *, post_id: str, character_id: str
) -> None:
    root_post_id = _thread_root_post_id(db, post_id)
    reply_ids = _thread_reply_post_ids(db, root_post_id)
    if not reply_ids:
        return

    existing_own_reply_id = db.scalar(
        select(models.Post.id)
        .where(
            models.Post.id.in_(reply_ids),
            models.Post.author_character_id == character_id,
            models.Post.deleted_at.is_(None),
            models.Post.report_hidden_at.is_(None),
        )
        .order_by(models.Post.created_at.asc(), models.Post.id.asc())
        .limit(1)
    )
    if existing_own_reply_id is None:
        return
    if _is_direct_reply_to_character_post(
        db, post_id=post_id, character_id=character_id
    ):
        return

    raise AgentRunAuthorizationError(
        "이미 이 스레드에 대꾸를 남겼습니다. 직접 받은 새 대꾸는 inbox lane에서만 다시 검토합니다."
    )


def _is_direct_reply_to_character_post(
    db: Session, *, post_id: str, character_id: str
) -> bool:
    post = post_repository.get_post(db, post_id)
    if post is None or post.reply_to_post_id is None:
        return False
    parent = post_repository.get_post(db, post.reply_to_post_id)
    return parent is not None and parent.author_character_id == character_id


def _thread_root_post_id(db: Session, post_id: str) -> str:
    post = post_repository.get_post(db, post_id)
    if post is None:
        raise PostNotFoundError(post_id)
    seen = {post.id}
    while post.reply_to_post_id is not None:
        parent = post_repository.get_post(db, post.reply_to_post_id)
        if parent is None or parent.id in seen:
            break
        post = parent
        seen.add(post.id)
    return post.id


def _candidate_target_parts(
    *, user_id: str | None, character_id: str | None
) -> tuple[str | None, str | None]:
    if character_id:
        return "character", character_id
    return None, None
