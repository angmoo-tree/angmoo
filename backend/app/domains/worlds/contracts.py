"""Canonical system-owned World role contracts."""

from __future__ import annotations

from typing import Protocol


NO_SPECIFIC_ROLE_KEY = "no_specific_role"
NO_SPECIFIC_ROLE_PORTABLE_REF = "roles/no-specific-role"
NO_SPECIFIC_ROLE_NAME = "역할 없음"
NO_SPECIFIC_ROLE_DESCRIPTION = "별도의 World 역할을 지정하지 않은 캐릭터"


class WorldRoleLike(Protocol):
    name: str
    description: str
    responsibilities: list[str]
    allowed_activity_scope: list[str]
    autonomous_allowed: bool


def is_canonical_no_specific_role(role: WorldRoleLike) -> bool:
    role_key = getattr(role, "role_key", getattr(role, "key", None))
    return (
        role_key == NO_SPECIFIC_ROLE_KEY
        and role.name == NO_SPECIFIC_ROLE_NAME
        and role.description == NO_SPECIFIC_ROLE_DESCRIPTION
        and role.responsibilities == []
        and role.allowed_activity_scope == []
        and role.autonomous_allowed is True
    )


__all__ = [
    "NO_SPECIFIC_ROLE_DESCRIPTION",
    "NO_SPECIFIC_ROLE_KEY",
    "NO_SPECIFIC_ROLE_NAME",
    "NO_SPECIFIC_ROLE_PORTABLE_REF",
    "is_canonical_no_specific_role",
]
