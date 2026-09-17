"""Bounded bulk read using durable request links, never adjacent-message guesses."""

from datetime import UTC
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.contracts.activity_thought import ActivityThought
from app.domains.chat.contracts.memory_turns import CommittedMemoryTurn
from app.domains.chat.models import ChatMessageThought, ChatResponseRequest, MessageMessage, MessageThread


class SqlAlchemyChatMemoryTurns:
    def __init__(self, session: Session):
        self.session = session

    def cutoff(self, *, owner_id: str, world_id: str, subject_id: str, thread_id: str) -> int:
        statement = select(func.max(ChatResponseRequest.committed_assistant_message_id)).join(
            MessageThread, MessageThread.id == ChatResponseRequest.thread_id,
        ).where(*self._scope(owner_id, world_id, subject_id, thread_id), ChatResponseRequest.state == "committed")
        return self.session.scalar(statement) or 0

    @staticmethod
    def _scope(owner_id, world_id, subject_id, thread_id):
        return (
            MessageThread.id == thread_id, MessageThread.requester_id == owner_id,
            MessageThread.world_id == world_id, MessageThread.responding_world_character_id == subject_id,
            MessageThread.world_scope_status == "resolved", MessageThread.deleted_at.is_(None),
        )

    def read_page(self, *, owner_id: str, world_id: str, subject_id: str, thread_id: str,
                  cutoff: int, after: int = 0, limit: int = 50,
                  latest: bool = False, assistant_ids: tuple[int, ...] | None = None) -> tuple[CommittedMemoryTurn, ...]:
        if not 1 <= limit <= 55 or after < 0 or cutoff < 0:
            raise ValueError("memory_turn_page_invalid")
        if assistant_ids is not None and len(assistant_ids) > 50:
            raise ValueError("memory_turn_id_limit")
        user, assistant = aliased(MessageMessage), aliased(MessageMessage)
        rows = self.session.execute(select(ChatResponseRequest, user, assistant, ChatMessageThought)
            .join(MessageThread, MessageThread.id == ChatResponseRequest.thread_id)
            .join(user, user.id == ChatResponseRequest.user_message_id)
            .join(assistant, assistant.id == ChatResponseRequest.committed_assistant_message_id)
            .outerjoin(ChatMessageThought, ChatMessageThought.message_id == assistant.id)
            .where(*self._scope(owner_id, world_id, subject_id, thread_id),
                   ChatResponseRequest.state == "committed", assistant.id > after, assistant.id <= cutoff,
                   True if assistant_ids is None else assistant.id.in_(assistant_ids),
                   user.thread_id == MessageThread.id, assistant.thread_id == MessageThread.id,
                   user.role == "user", assistant.role == "assistant", user.status == "ok", assistant.status == "ok")
            .order_by(assistant.id.desc() if latest else assistant.id).limit(limit)).all()
        if latest:
            rows.reverse()
        result = []
        for request, question, answer, row in rows:
            thought = ActivityThought()
            if row is not None:
                if row.request_id != request.request_id or row.source_digest != sha256(answer.content.encode()).hexdigest():
                    thought = ActivityThought(status="invalid")
                else:
                    thought = ActivityThought(text=row.thought_text, status=row.status, truncated=row.truncated)
            occurred = answer.created_at
            if occurred.tzinfo is None:
                occurred = occurred.replace(tzinfo=UTC)
            result.append(CommittedMemoryTurn(
                request_id=request.request_id, thread_id=thread_id,
                user_message_id=question.id, user_text=question.content,
                assistant_message_id=answer.id, assistant_text=answer.content,
                occurred_at=occurred, thought=thought, thought_recorded=row is not None,
            ))
        return tuple(result)
