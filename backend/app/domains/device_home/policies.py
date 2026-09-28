"""Pure World launchability rules, shared by read projections."""
from __future__ import annotations

from app.domains.device_home.contracts import WorldLaunchBlockReason


def launchability(
    *,
    status: str,
    visibility: str,
    readiness_status: str,
    membership_role: str | None = None,
) -> tuple[bool, WorldLaunchBlockReason | None]:
    if status == "archived":
        return False, "world_archived"
    if status != "published":
        return False, "world_not_published"
    if readiness_status != "publish_ready":
        return False, "world_not_ready"
    if visibility not in {"public", "unlisted"} and membership_role not in {"owner", "editor", "member"}:
        return False, "world_private"
    return True, None
