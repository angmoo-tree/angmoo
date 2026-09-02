"""Application entry point for the legacy-compatible Chat v1 operations."""

from __future__ import annotations

from typing import Any

from app.domains.chat.ports.runtime import ChatRuntimePort


class ChatService:
    """Coordinates Chat use cases through a runtime port.

    P8-L-B intentionally delegates the established transaction and provider
    behavior unchanged.  World-scoped Chat v2 orchestration is introduced by
    later P8-L stages rather than hidden inside this structural move.
    """

    def __init__(self, runtime: ChatRuntimePort) -> None:
        self._runtime = runtime

    def get_world_chat_entry(
        self, db: Any, user: Any, world_id: str, responding_id: str
    ) -> Any:
        return self._runtime.get_world_chat_entry(
            db, user, world_id, responding_id
        )

    def list_world_threads(self, db: Any, user: Any, world_id: str) -> Any:
        return self._runtime.list_world_threads(db, user, world_id)

    def get_world_thread(
        self, db: Any, user: Any, world_id: str, thread_id: str
    ) -> Any:
        return self._runtime.get_world_thread(db, user, world_id, thread_id)

    def create_or_get_world_thread(
        self, db: Any, user: Any, world_id: str, data: Any
    ) -> Any:
        return self._runtime.create_or_get_world_thread(db, user, world_id, data)

    def update_world_thread_model(
        self,
        db: Any,
        user: Any,
        world_id: str,
        thread_id: str,
        data: Any,
    ) -> Any:
        return self._runtime.update_world_thread_model(
            db, user, world_id, thread_id, data
        )

    def accept_world_message(
        self, db: Any, user: Any, world_id: str, thread_id: str, data: Any
    ) -> Any:
        return self._runtime.accept_world_message(
            db, user, world_id, thread_id, data
        )

    def retry_world_response(
        self, db: Any, user: Any, world_id: str, thread_id: str, data: Any
    ) -> Any:
        return self._runtime.retry_world_response(
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
        return self._runtime.get_world_response_request(
            db, user, world_id, thread_id, request_id
        )

    def get_latest_world_response_request(
        self, db: Any, user: Any, world_id: str, thread_id: str
    ) -> Any:
        return self._runtime.get_latest_world_response_request(
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
        return self._runtime.stream_world_response(
            db,
            user,
            world_id,
            thread_id,
            request_id,
            memory_recall_service=memory_recall_service,
            runtime_settings=runtime_settings,
        )

    def list_threads(self, db: Any, user: Any) -> Any:
        return self._runtime.list_threads(db, user)

    def get_thread(self, db: Any, user: Any, thread_id: str) -> Any:
        return self._runtime.get_thread(db, user, thread_id)

    def create_or_get_thread(self, db: Any, user: Any, data: Any) -> Any:
        return self._runtime.create_or_get_thread(db, user, data)

    def update_thread(self, db: Any, user: Any, thread_id: str, data: Any) -> Any:
        return self._runtime.update_thread(db, user, thread_id, data)

    def delete_thread(self, db: Any, user: Any, thread_id: str) -> None:
        self._runtime.delete_thread(db, user, thread_id)

    async def send_message(
        self, db: Any, user: Any, thread_id: str, data: Any
    ) -> Any:
        return await self._runtime.send_message(db, user, thread_id, data)

    async def retry_message(
        self, db: Any, user: Any, thread_id: str, message_id: int
    ) -> Any:
        return await self._runtime.retry_message(db, user, thread_id, message_id)

    def get_user_settings(self, db: Any, user: Any) -> Any:
        return self._runtime.get_user_settings(db, user)

    def update_user_settings(self, db: Any, user: Any, data: Any) -> Any:
        return self._runtime.update_user_settings(db, user, data)

    def get_character_message_settings(
        self, db: Any, user: Any, character_id: str
    ) -> Any:
        return self._runtime.get_character_message_settings(db, user, character_id)

    def update_character_message_settings(
        self, db: Any, user: Any, character_id: str, data: Any
    ) -> Any:
        return self._runtime.update_character_message_settings(
            db, user, character_id, data
        )
