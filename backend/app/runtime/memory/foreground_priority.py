"""Read-only foreground priority; never interrupt a started provider request."""

from datetime import timedelta
from sqlalchemy import and_, or_, select
from app.domains.chat.models import ChatResponseRequest


def chat_is_active(db, *, now):
    return db.scalar(select(ChatResponseRequest.request_id).where(
        ChatResponseRequest.terminal_at.is_(None),
        or_(ChatResponseRequest.lease_expires_at > now,
            and_(ChatResponseRequest.state == "accepted", ChatResponseRequest.created_at > now - timedelta(minutes=2))),
    ).limit(1)) is not None
