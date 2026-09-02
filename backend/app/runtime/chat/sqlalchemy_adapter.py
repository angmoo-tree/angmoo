"""Runtime port adapter for the existing SQLAlchemy Chat v1 workflow."""

from __future__ import annotations

from typing import Any

from app.runtime.chat import sqlalchemy_service
from app.runtime.chat import world_generation


class SqlAlchemyChatRuntime:
    def get_world_chat_entry(
        self, db: Any, user: Any, world_id: str, responding_id: str
    ) -> Any:
        return sqlalchemy_service.get_world_chat_entry(
            db, user, world_id, responding_id
        )

    def list_world_threads(self, db: Any, user: Any, world_id: str) -> Any:
        return sqlalchemy_service.list_world_threads(db, user, world_id)

    def get_world_thread(
        self, db: Any, user: Any, world_id: str, thread_id: str
    ) -> Any:
        return sqlalchemy_service.get_world_thread(db, user, world_id, thread_id)

    def create_or_get_world_thread(
        self, db: Any, user: Any, world_id: str, data: Any
    ) -> Any:
        return sqlalchemy_service.create_or_get_world_thread(
            db, user, world_id, data
        )

    def update_world_thread_model(
        self,
        db: Any,
        user: Any,
        world_id: str,
        thread_id: str,
        data: Any,
    ) -> Any:
        return sqlalchemy_service.update_world_thread_model(
            db, user, world_id, thread_id, data
        )

    def accept_world_message(
        self, db: Any, user: Any, world_id: str, thread_id: str, data: Any
    ) -> Any:
        return world_generation.accept_world_message(
            db, user, world_id, thread_id, data
        )

    def retry_world_response(
        self, db: Any, user: Any, world_id: str, thread_id: str, data: Any
    ) -> Any:
        return world_generation.retry_world_response(
            db, user, world_id, thread_id, data
        )

    def get_world_response_request(
        self,
        db: Any,
        user: Any,
        world_id: str,
        thread_id: str,
        request_id: str,
    ) -> Any:
        return world_generation.get_world_response_request(
            db, user, world_id, thread_id, request_id
        )

    def get_latest_world_response_request(
        self, db: Any, user: Any, world_id: str, thread_id: str
    ) -> Any:
        return world_generation.get_latest_world_response_request(
            db, user, world_id, thread_id
        )

    def stream_world_response(
        self,
        db: Any,
        user: Any,
        world_id: str,
        thread_id: str,
        request_id: str,
        *,
        memory_recall_service: Any | None,
        runtime_settings: Any,
    ) -> Any:
        return world_generation.stream_world_response(
            db,
            user,
            world_id,
            thread_id,
            request_id,
            memory_recall_service=memory_recall_service,
            runtime_settings=runtime_settings,
        )

    def list_threads(self, db: Any, user: Any) -> Any:
        return sqlalchemy_service.list_threads(db, user)

    def get_thread(self, db: Any, user: Any, thread_id: str) -> Any:
        return sqlalchemy_service.get_thread(db, user, thread_id)

    def create_or_get_thread(self, db: Any, user: Any, data: Any) -> Any:
        return sqlalchemy_service.create_or_get_thread(db, user, data)

    def update_thread(self, db: Any, user: Any, thread_id: str, data: Any) -> Any:
        return sqlalchemy_service.update_thread(db, user, thread_id, data)

    def delete_thread(self, db: Any, user: Any, thread_id: str) -> None:
        sqlalchemy_service.delete_thread(db, user, thread_id)

    async def send_message(
        self, db: Any, user: Any, thread_id: str, data: Any
    ) -> Any:
        return await sqlalchemy_service.send_message(db, user, thread_id, data)

    async def retry_message(
        self, db: Any, user: Any, thread_id: str, message_id: int
    ) -> Any:
        return await sqlalchemy_service.retry_message(db, user, thread_id, message_id)

    def get_user_settings(self, db: Any, user: Any) -> Any:
        return sqlalchemy_service.get_user_settings(db, user)

    def update_user_settings(self, db: Any, user: Any, data: Any) -> Any:
        return sqlalchemy_service.update_user_settings(db, user, data)

    def get_character_message_settings(
        self, db: Any, user: Any, character_id: str
    ) -> Any:
        return sqlalchemy_service.get_character_message_settings(db, user, character_id)

    def update_character_message_settings(
        self, db: Any, user: Any, character_id: str, data: Any
    ) -> Any:
        return sqlalchemy_service.update_character_message_settings(
            db, user, character_id, data
        )
