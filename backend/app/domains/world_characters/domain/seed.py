"""Caller-owned autonomous WorldCharacter seed contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AutonomousWorldCharacterSeedData:
    world_id: str
    character_id: str
    membership_id: str
    role_key: str
    role_description: str
    background: str
    access_scope: tuple[str, ...]


__all__ = ["AutonomousWorldCharacterSeedData"]
