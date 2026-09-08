"""Execution uses an approved pair's provenance, not today's persona hash."""
from __future__ import annotations

from typing import Protocol


class WorldBinding(Protocol):
    id: str
    character_contract_hash: str
    world_contract_hash: str


class ApprovedProfile(WorldBinding, Protocol):
    world_character_id: str
    status: str


class ApprovedRepertoire(ApprovedProfile, Protocol):
    community_profile_id: str


def approved_pair_matches_world(
    world_character: WorldBinding,
    profile: ApprovedProfile,
    repertoire: ApprovedRepertoire,
    *,
    world_hash: str,
) -> bool:
    """Keep pair identity and World validity while allowing persona edits.

    Role changes explicitly invalidate the stored outputs. Character identity,
    membership, active status and candidate validity are checked by the caller.
    Never rewrite these hashes to make an old generation look newly generated.
    """
    return bool(
        profile.status == repertoire.status == "ready"
        and profile.world_character_id == repertoire.world_character_id == world_character.id
        and repertoire.community_profile_id == profile.id
        and profile.character_contract_hash
        == repertoire.character_contract_hash
        == world_character.character_contract_hash
        and profile.world_contract_hash
        == repertoire.world_contract_hash
        == world_character.world_contract_hash
        == world_hash
    )
