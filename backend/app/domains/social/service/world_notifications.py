"""Current owner-profile reads and explicit read mutations; never ensure an identity."""
import base64
import binascii
import json
from sqlalchemy.orm import Session
from app.domains.social.contracts.world_notifications import WorldNotificationError, WorldNotificationReferences
from app.domains.social.repository import world_notifications as repository
from app.domains.social.schemas.world_notifications import (
    NotificationScopeRead, NotificationTargetRead, WorldNotificationRead,
    WorldNotificationCountRead, WorldNotificationPage, WorldNotificationReadResult,
    WorldNotificationReadAllResult,
    WorldUnreadCountItem, WorldUnreadCountsRead,
)


def scope_view(scope):
    return NotificationScopeRead(world_id=scope.world_id, recipient_world_character_id=scope.recipient_world_character_id)


class WorldNotificationService:
    def __init__(self, db: Session, references: WorldNotificationReferences):
        self.db, self.references = db, references

    def count(self, *, world_id, user_id):
        scope = self.references.require_scope(world_id=world_id, user_id=user_id)
        return WorldNotificationCountRead(scope=scope_view(scope), unread_count=repository.unread_counts(self.db, [scope], self.references.profile_target_ids([scope])).get(world_id, 0))

    def batch(self, *, world_ids, user_id):
        if not 1 <= len(world_ids) <= 50 or any(not value or len(value) > 64 for value in world_ids):
            raise WorldNotificationError("notification_world_ids_invalid", 422)
        ids = list(dict.fromkeys(world_ids))
        scopes = self.references.scopes(world_ids=ids, user_id=user_id)
        counts = repository.unread_counts(self.db, list(scopes.values()), self.references.profile_target_ids(list(scopes.values())))
        return WorldUnreadCountsRead(items=[WorldUnreadCountItem(world_id=key,
            recipient_world_character_id=scopes[key].recipient_world_character_id if key in scopes else None,
            status="available" if key in scopes else "unavailable", unread_count=counts.get(key, 0) if key in scopes else None) for key in ids])

    def page(self, *, world_id, user_id, limit=20, cursor=None):
        if not 1 <= limit <= 100:
            raise WorldNotificationError("notification_limit_invalid", 422)
        scope = self.references.require_scope(world_id=world_id, user_id=user_id)
        before = None
        if cursor:
            try:
                if len(cursor) > 1024:
                    raise ValueError()
                value = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
                if value[:3] != [1, world_id, scope.recipient_world_character_id] or len(value) != 4 or type(value[3]) is not int or value[3] < 1:
                    raise ValueError()
                before = value[3]
            except (ValueError, TypeError, UnicodeError, binascii.Error) as exc:
                raise WorldNotificationError("notification_cursor_invalid", 422) from exc
        profile_ids = self.references.profile_target_ids([scope])
        rows = repository.list_page(self.db, scope, limit=limit, before_id=before, profile_ids=profile_ids)
        authors = self.references.author_profiles(world_id=world_id, author_ids={row.actor_world_character_id for row in rows})
        previews = repository.previews(self.db, {row.source_post_id or row.post_id for row in rows if row.source_post_id or row.post_id})
        items = []
        for row in rows[:limit]:
            author = authors.get(row.actor_world_character_id)
            actor_available = author is not None and not author.deleted
            follow = row.notification_type == "follow"
            items.append(WorldNotificationRead(id=row.id, notification_type=row.notification_type,
                actor_world_character_id=row.actor_world_character_id if actor_available else None,
                actor_name=author.display_name if actor_available else None,
                actor_handle=author.handle if actor_available else None,
                actor_avatar_url=author.avatar_url if actor_available else None, actor_deleted=not actor_available,
                read_at=row.read_at, created_at=row.created_at,
                preview_text=None if follow else previews.get(row.source_post_id or row.post_id),
                target=NotificationTargetRead(kind="world_character" if follow else "post",
                    post_id=None if follow else row.source_post_id or row.post_id,
                    world_character_id=row.actor_world_character_id if follow and actor_available else None,
                    can_open=actor_available if follow else True)))
        next_cursor = base64.urlsafe_b64encode(json.dumps([1, world_id, scope.recipient_world_character_id, rows[limit-1].id], separators=(",", ":")).encode()).decode() if len(rows) > limit else None
        return WorldNotificationPage(scope=scope_view(scope), items=items, next_cursor=next_cursor,
            unread_count=repository.unread_counts(self.db, [scope], profile_ids).get(world_id, 0))

    def mark_read(self, *, world_id, user_id, notification_id):
        scope = self.references.require_scope(world_id=world_id, user_id=user_id)
        profile_ids = self.references.profile_target_ids([scope])
        row = repository.readable(self.db, scope, notification_id, profile_ids)
        if row is None:
            raise WorldNotificationError("notification_not_found")
        repository.mark_read(self.db, row)
        return WorldNotificationReadResult(scope=scope_view(scope), notification_id=row.id, read_at=row.read_at,
            unread_count=repository.unread_counts(self.db, [scope], profile_ids).get(world_id, 0))

    def mark_all_read(self, *, world_id, user_id, recipient_world_character_id):
        scope = self.references.require_scope(world_id=world_id, user_id=user_id)
        if scope.recipient_world_character_id != recipient_world_character_id:
            raise WorldNotificationError("notification_scope_changed", 409)
        profile_ids = self.references.profile_target_ids([scope])
        marked_count, read_at, through_id = repository.mark_all_read(self.db, scope, profile_ids)
        return WorldNotificationReadAllResult(scope=scope_view(scope), marked_count=marked_count,
            read_at=read_at, through_notification_id=through_id,
            unread_count=repository.unread_counts(self.db, [scope], profile_ids).get(world_id, 0))
