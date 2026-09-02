"""Framework-free execution port for the existing Chat v1 use cases."""

from __future__ import annotations

from typing import Any, Protocol


class ChatRuntimePort(Protocol):
    def get_world_chat_entry(
        self, db: Any, user: Any, world_id: str, responding_id: str
    ) -> Any: ...

    def list_world_threads(
        self, db: Any, user: Any, world_id: str
    ) -> Any: ...

    def get_world_thread(
        self, db: Any, user: Any, world_id: str, thread_id: str
    ) -> Any: ...

    def create_or_get_world_thread(
        self, db: Any, user: Any, world_id: str, data: Any
    ) -> Any: ...

    def update_world_thread_model(
        self,
        db: Any,
        user: Any,
        world_id: str,
        thread_id: str,
        data: Any,
    ) -> Any: ...

    def accept_world_message(
        self, db: Any, user: Any, world_id: str, thread_id: str, data: Any
    ) -> Any: ...

    def retry_world_response(
        self, db: Any, user: Any, world_id: str, thread_id: str, data: Any
    ) -> Any: ...

    def get_world_response_request(
        self,
        db: Any,
        user: Any,
        world_id: str,
        thread_id: str,
        request_id: str,
    ) -> Any: ...

    def get_latest_world_response_request(
        self, db: Any, user: Any, world_id: str, thread_id: str
    ) -> Any: ...

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
    ) -> Any: ...

    def list_threads(self, db: Any, user: Any) -> Any: ...

    def get_thread(self, db: Any, user: Any, thread_id: str) -> Any: ...

    def create_or_get_thread(self, db: Any, user: Any, data: Any) -> Any: ...

    def update_thread(self, db: Any, user: Any, thread_id: str, data: Any) -> Any: ...

    def delete_thread(self, db: Any, user: Any, thread_id: str) -> None: ...

    async def send_message(
        self, db: Any, user: Any, thread_id: str, data: Any
    ) -> Any: ...

    async def retry_message(
        self, db: Any, user: Any, thread_id: str, message_id: int
    ) -> Any: ...

    def get_user_settings(self, db: Any, user: Any) -> Any: ...

    def update_user_settings(self, db: Any, user: Any, data: Any) -> Any: ...

    def get_character_message_settings(
        self, db: Any, user: Any, character_id: str
    ) -> Any: ...

    def update_character_message_settings(
        self, db: Any, user: Any, character_id: str, data: Any
    ) -> Any: ...
