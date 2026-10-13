"""Private contents are removed; minimal thread identities fence late responses."""
from datetime import UTC, datetime
from sqlalchemy import delete, or_, select, update
from app.domains.chat.models import MessageThread, MessageMessage, MessageAttachment, ChatMessageThought, ChatResponseRequest


def erase_world_instance(db, *, owner_id, world_id, actor_id):
    threads = select(MessageThread.id).where(MessageThread.requester_id == owner_id, MessageThread.world_id == world_id,
        or_(MessageThread.requester_world_character_id == actor_id, MessageThread.responding_world_character_id == actor_id))
    identities = list(db.scalars(threads))
    messages = select(MessageMessage.id).where(MessageMessage.thread_id.in_(threads))
    requests = select(ChatResponseRequest.request_id).where(ChatResponseRequest.thread_id.in_(threads))
    # Clear the self-reference before deleting the exact thread's requests.
    db.execute(update(ChatResponseRequest).where(ChatResponseRequest.retry_of_request_id.in_(requests)).values(retry_of_request_id=None))
    db.execute(delete(ChatResponseRequest).where(ChatResponseRequest.thread_id.in_(threads)))
    db.execute(delete(MessageAttachment).where(MessageAttachment.message_id.in_(messages)))
    db.execute(delete(ChatMessageThought).where(ChatMessageThought.message_id.in_(messages)))
    db.execute(delete(MessageMessage).where(MessageMessage.thread_id.in_(threads)))
    db.execute(update(MessageThread).where(MessageThread.id.in_(threads)).values(deleted_at=datetime.now(UTC),
        response_lease_token=None, response_lease_expires_at=None, last_message_at=None))
    return identities
