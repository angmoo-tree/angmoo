"""World author display values; Social receives no World storage or credentials."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class WorldPostAuthor:
    world_id: str
    world_character_id: str
    character_id: str
    display_name: str
    handle: str
    avatar_url: str | None


class PostAuthorReferences(Protocol):
    def author_profiles(self, *, world_id: str, author_ids: set[str]) -> dict[str, WorldPostAuthor]: ...
