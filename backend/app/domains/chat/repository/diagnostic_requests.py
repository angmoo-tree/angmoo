"""Read-only diagnostic history, independent of committed evidence summaries."""
from datetime import UTC

from sqlalchemy import and_, or_, select

from app.domains.chat.models import ChatResponseRequest


def metadata(row):
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return {"request_id": row.request_id, "created_at": created.astimezone(UTC).isoformat(),
            "state": row.state, "user_message_id": row.user_message_id,
            "attempt_number": row.attempt_number, "retry_of_request_id": row.retry_of_request_id}


def list_requests(db, thread_id, *, limit=30, cursor=None):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("diagnostic_limit_invalid")
    query = select(ChatResponseRequest).where(ChatResponseRequest.thread_id == thread_id)
    if cursor is not None:
        if type(cursor) is not str or not 1 <= len(cursor) <= 64:
            raise ValueError("diagnostic_cursor_invalid")
        anchor = db.scalar(select(ChatResponseRequest).where(
            ChatResponseRequest.thread_id == thread_id, ChatResponseRequest.request_id == cursor))
        if anchor is None:
            raise ValueError("diagnostic_cursor_invalid")
        query = query.where(or_(ChatResponseRequest.created_at < anchor.created_at,
                               and_(ChatResponseRequest.created_at == anchor.created_at,
                                    ChatResponseRequest.request_id < anchor.request_id)))
    rows = list(db.scalars(query.order_by(ChatResponseRequest.created_at.desc(), ChatResponseRequest.request_id.desc()).limit(limit + 1)))
    return {"items": [metadata(row) for row in rows[:limit]],
            "next_cursor": rows[limit - 1].request_id if len(rows) > limit else None}
