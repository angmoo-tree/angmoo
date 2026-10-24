"""Canonical system-owned World role contracts."""

from __future__ import annotations

from typing import Protocol

from app.domains.worlds.exceptions import WorldServiceError

NO_SPECIFIC_ROLE_KEY = "no_specific_role"
NO_SPECIFIC_ROLE_PORTABLE_REF = "roles/no-specific-role"
NO_SPECIFIC_ROLE_NAME = "No role"
NO_SPECIFIC_ROLE_DESCRIPTION = "A character with no specific World role."
_SUPPORTED_NO_SPECIFIC_ROLE_TEXT = frozenset({
    (NO_SPECIFIC_ROLE_NAME, NO_SPECIFIC_ROLE_DESCRIPTION),
    ("역할 없음", "별도의 World 역할을 지정하지 않은 캐릭터"),
})


class WorldRoleLike(Protocol):
    name: str
    description: str
    responsibilities: list[str]
    allowed_activity_scope: list[str]
    autonomous_allowed: bool


def has_supported_no_specific_role_content(role: WorldRoleLike) -> bool:
    """Accept complete current or legacy pairs without rewriting stored content."""
    return (
        (role.name, role.description) in _SUPPORTED_NO_SPECIFIC_ROLE_TEXT
        and role.responsibilities == []
        and role.allowed_activity_scope == []
        and role.autonomous_allowed is True
    )


def is_canonical_no_specific_role(role: WorldRoleLike) -> bool:
    role_key = getattr(role, "role_key", getattr(role, "key", None))
    return role_key == NO_SPECIFIC_ROLE_KEY and has_supported_no_specific_role_content(role)


__all__ = [
    "NO_SPECIFIC_ROLE_DESCRIPTION",
    "NO_SPECIFIC_ROLE_KEY",
    "NO_SPECIFIC_ROLE_NAME",
    "NO_SPECIFIC_ROLE_PORTABLE_REF",
    "has_supported_no_specific_role_content",
    "is_canonical_no_specific_role",
]
