"""Exact import compatibility for the immutable SQLite v2->v3 migration.

The definitions are owned by app.domains.worlds.contracts; this module has no implementation.
"""

from app.domains.worlds.contracts import (
    NO_SPECIFIC_ROLE_KEY,
    NO_SPECIFIC_ROLE_PORTABLE_REF,
    NO_SPECIFIC_ROLE_NAME,
    NO_SPECIFIC_ROLE_DESCRIPTION,
    WorldRoleLike,
    is_canonical_no_specific_role,
)

__all__ = [
    "NO_SPECIFIC_ROLE_KEY",
    "NO_SPECIFIC_ROLE_PORTABLE_REF",
    "NO_SPECIFIC_ROLE_NAME",
    "NO_SPECIFIC_ROLE_DESCRIPTION",
    "WorldRoleLike",
    "is_canonical_no_specific_role",
]
