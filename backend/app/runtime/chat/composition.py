"""Application composition root for the compatibility Chat HTTP route."""

from app.domains.chat.application.messages import ChatService
from app.runtime.chat.sqlalchemy_adapter import SqlAlchemyChatRuntime


chat_service = ChatService(SqlAlchemyChatRuntime())

__all__ = ["chat_service"]
