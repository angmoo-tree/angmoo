from __future__ import annotations

from app.domains.world_characters.contracts.owner_identity import (
    OwnerControlledIdentitySnapshot,
    OwnerControlledProfile,
)
from app.domains.world_characters.ports.owner_controlled_identity import (
    OwnerControlledIdentityRepository,
)


def get_owner_controlled_identity(
    repository: OwnerControlledIdentityRepository,
    *,
    world_id: str,
    current_user_id: str,
) -> OwnerControlledIdentitySnapshot:
    return repository.get(
        world_id=world_id,
        current_user_id=current_user_id,
    )


def create_owner_controlled_identity(
    repository: OwnerControlledIdentityRepository,
    *,
    world_id: str,
    current_user_id: str,
    profile: OwnerControlledProfile,
) -> OwnerControlledIdentitySnapshot:
    return repository.create(
        world_id=world_id,
        current_user_id=current_user_id,
        profile=profile,
    )


def update_owner_controlled_identity(
    repository: OwnerControlledIdentityRepository,
    *,
    world_id: str,
    current_user_id: str,
    profile: OwnerControlledProfile,
) -> OwnerControlledIdentitySnapshot:
    return repository.update(
        world_id=world_id,
        current_user_id=current_user_id,
        profile=profile,
    )


__all__ = [
    "create_owner_controlled_identity",
    "get_owner_controlled_identity",
    "update_owner_controlled_identity",
]
