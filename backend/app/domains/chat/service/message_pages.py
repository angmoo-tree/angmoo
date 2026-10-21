"""Bounded World Chat read cursors and the shared committed evidence projection."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from app.pagination import decode_cursor_bytes, encode_cursor_bytes
from app.domains.chat.exceptions import MessageValidationError
from app.domains.chat.schemas import WorldChatEvidenceSummaryRead

VERSION = "world-chat-message-page.v1"


def encode_message_cursor(thread, created_at: datetime, message_id: int) -> str:
    payload = {"v": 1, "kind": "chat_messages", "owner": thread.requester_id,
               "world": thread.world_id, "thread": thread.id,
               "at": created_at.replace(tzinfo=UTC).isoformat(), "id": message_id}
    return encode_cursor_bytes(json.dumps(payload, separators=(",", ":")).encode("utf-8"))


def decode_message_cursor(cursor: str, thread) -> tuple[datetime, int]:
    try:
        if len(cursor) > 1024 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
            raise ValueError("encoding")
        value = json.loads(decode_cursor_bytes(cursor))
        if not isinstance(value, dict) or set(value) != {"v", "kind", "owner", "world", "thread", "at", "id"}:
            raise ValueError("shape")
        if (type(value["v"]) is not int or value["v"] != 1 or value["kind"] != "chat_messages" or value["owner"] != thread.requester_id
                or value["world"] != thread.world_id or value["thread"] != thread.id):
            raise ValueError("scope")
        if type(value["id"]) is not int or not 0 <= value["id"] < 2**63:
            raise ValueError("id")
        at = datetime.fromisoformat(value["at"])
        if at.tzinfo is None:
            raise ValueError("time")
        return at.astimezone(UTC), value["id"]
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise MessageValidationError("chat_message_cursor_invalid") from exc


def committed_evidence_summary(request_id: str, assistant_message_id: int, metadata: dict):
    """Identical projection for a page and the committed-request status response."""
    capability = metadata.get("evidence_capability")
    count = metadata.get("public_evidence_count")
    snapshot = metadata.get("_social_context_inspector_v1")
    current = snapshot.get("items", []) if isinstance(snapshot, dict) else []
    if isinstance(current, list) and 0 < len(current) <= 12:
        count = (count if type(count) is int else 0) + len(current)
        capability = "degraded" if capability == "degraded" else "available"
    if capability not in {"available", "degraded"} or type(count) is not int or not 1 <= count <= 24:
        return None
    return WorldChatEvidenceSummaryRead(request_id=request_id, assistant_message_id=assistant_message_id,
                                        capability=capability, count=count)
