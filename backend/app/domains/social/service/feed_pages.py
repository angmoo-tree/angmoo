"""Bounded owner/World/actor-scoped cursors for manual root feed reads."""
from datetime import UTC, datetime
import json
import re

from app.pagination import decode_cursor_bytes, encode_cursor_bytes
from app.domains.social.contracts.writes import SocialWriteValidationError


def encode_feed_cursor(post, owner_id: str, actor_id: str) -> str:
    return encode_cursor_bytes(json.dumps({"v": 2, "kind": "manual_feed", "owner": owner_id,
        "world": post.world_id, "actor": actor_id, "at": post.created_at.replace(tzinfo=UTC).isoformat(),
        "id": post.id}, separators=(",", ":")).encode())


def decode_feed_cursor(cursor: str, owner_id: str, world_id: str, actor_id: str):
    try:
        if len(cursor) > 1024 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
            raise ValueError("encoding")
        value = json.loads(decode_cursor_bytes(cursor))
        if not isinstance(value, dict) or set(value) != {"v", "kind", "owner", "world", "actor", "at", "id"}:
            raise ValueError("shape")
        if (type(value["v"]) is not int or value["v"] != 2 or value["kind"] != "manual_feed"
            or value["owner"] != owner_id or value["world"] != world_id or value["actor"] != actor_id):
            raise ValueError("scope")
        if not isinstance(value["id"], str) or not 1 <= len(value["id"]) <= 64:
            raise ValueError("id")
        at = datetime.fromisoformat(value["at"])
        if at.tzinfo is None:
            raise ValueError("time")
        return at.astimezone(UTC), value["id"]
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise SocialWriteValidationError("manual_social_cursor_invalid") from exc
