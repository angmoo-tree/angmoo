"""Read pending conversations without consuming notification or observation state."""
from sqlalchemy import select

from app.domains.social.models.posts import Notification, Post
from app.domains.social.service.resident_affordances import resident_inbox_action_affordance


def pending_conversations(db, *, actor, allowed_actions, limit=10):
    rows = list(db.scalars(select(Notification).where(
        Notification.world_id == actor.world_id,
        Notification.recipient_world_character_id == actor.id,
        Notification.recipient_character_id == actor.character_id,
        Notification.handled_at.is_(None),
        Notification.notification_type.in_(("reply", "mention", "joint_activity_started")),
    ).order_by(Notification.created_at, Notification.id).limit(limit)))
    groups = {}
    for row in rows:
        post = db.get(Post, row.source_post_id or row.post_id)
        if post is None or post.world_id != actor.world_id or post.deleted_at or post.report_hidden_at or post.visibility != "public":
            continue
        if not post.author_world_character_id or post.author_world_character_id == actor.id:
            continue
        # Siblings responding to the same utterance form one branch; separate
        # reply branches of one root never collapse just because the author matches.
        branch = post.reply_to_post_id or post.id
        key = (post.author_world_character_id, branch)
        parent = db.get(Post, post.reply_to_post_id) if post.reply_to_post_id else None
        if parent is not None and (parent.world_id != actor.world_id or parent.deleted_at or parent.report_hidden_at or parent.visibility != "public"):
            parent = None
        affordance = resident_inbox_action_affordance(db, notification=row,
            character_id=actor.character_id, allowed_actions=allowed_actions)
        entry = groups.setdefault(key, {"branch_id": branch, "counterpart_id": key[0],
            "posts": [], "notifications": [], "parent": parent, "affordance": affordance})
        entry["posts"].append(post)
        entry["notifications"].append(row)
        entry["affordance"] = affordance
    return list(groups.values())
