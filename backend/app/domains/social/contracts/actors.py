"""Read-only actor values consumed by Social writes in the caller's Session."""
from datetime import datetime
from typing import Protocol


class SocialUser(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def display_name(self) -> str: ...


class SocialCharacter(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def owner_id(self) -> str: ...

    @property
    def deleted_at(self) -> datetime | None: ...

    @property
    def moderation_status(self) -> str: ...
