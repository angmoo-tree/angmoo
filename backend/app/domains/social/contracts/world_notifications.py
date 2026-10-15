"""Read-only World recipient and presentation collaboration in the caller Session."""
from dataclasses import dataclass
from typing import Protocol
from app.domains.social.contracts.post_authors import WorldPostAuthor


@dataclass(frozen=True, slots=True)
class NotificationScope:
    world_id: str
    recipient_world_character_id: str
    recipient_character_id: str


class WorldNotificationReferences(Protocol):
    def require_scope(self, *, world_id: str, user_id: str) -> NotificationScope: ...
    def scopes(self, *, world_ids: list[str], user_id: str) -> dict[str, NotificationScope]: ...
    def author_profiles(self, *, world_id: str, author_ids: set[str]) -> dict[str, WorldPostAuthor]: ...
    def profile_target_ids(self, scopes: list[NotificationScope]) -> set[str]: ...


class WorldNotificationError(ValueError):
    def __init__(self, code: str, status: int = 404):
        self.code, self.status = code, status
        super().__init__(code)
