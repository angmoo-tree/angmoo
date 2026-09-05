"""Exact import compatibility for the immutable SQLite v2->v3 migration.

The definitions are owned by app.domains.worlds.service.reserved_roles; this module has no implementation.
"""

from app.domains.worlds.service.reserved_roles import (
    ReservedWorldRoleConflictError,
    ensure_no_specific_role,
)

__all__ = [
    "ReservedWorldRoleConflictError",
    "ensure_no_specific_role",
]
