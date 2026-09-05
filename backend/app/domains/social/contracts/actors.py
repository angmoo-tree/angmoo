"""Read-only actor values consumed by Social writes in the caller's Session."""
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
