"""Framework-free execution port for the existing Chat v1 use cases."""

from __future__ import annotations

from typing import Any, Protocol


class ChatRuntimePort(Protocol):
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
