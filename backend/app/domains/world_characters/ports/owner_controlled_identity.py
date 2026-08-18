from __future__ import annotations

from typing import Protocol

from app.domains.world_characters.domain.owner_controlled_identity import (
    OwnerControlledIdentitySnapshot,
    OwnerControlledProfile,
)


class OwnerControlledIdentityRepository(Protocol):
    def get(
        self, *, world_id: str, current_user_id: str
    ) -> OwnerControlledIdentitySnapshot: ...

    def create(
        self,
        *,
        world_id: str,
        current_user_id: str,
        profile: OwnerControlledProfile,
    ) -> OwnerControlledIdentitySnapshot: ...

    def update(
        self,
        *,
        world_id: str,
        current_user_id: str,
        profile: OwnerControlledProfile,
    ) -> OwnerControlledIdentitySnapshot: ...


__all__ = ["OwnerControlledIdentityRepository"]
