"""Stable World Creator errors; HTTP translation belongs to the router."""
from __future__ import annotations

from app.domains.worlds import schemas


class ReservedWorldRoleConflictError(ValueError):
    pass


class WorldServiceError(Exception):
    reason_code = "world_error"

class WorldNotFoundError(WorldServiceError):
    reason_code = "world_not_found"

class WorldArchivedError(WorldServiceError):
    reason_code = "world_archived"

class WorldMembershipRequiredError(WorldServiceError):
    reason_code = "membership_required"

class WorldCreatorRoleRequiredError(WorldServiceError):
    reason_code = "creator_role_required"

class WorldOwnerRoleRequiredError(WorldServiceError):
    reason_code = "creator_role_required"

class WorldRowVersionConflictError(WorldServiceError):
    reason_code = "row_version_conflict"

class WorldDefinitionIncompleteError(WorldServiceError):
    reason_code = "world_definition_incomplete"

    def __init__(self, readiness: schemas.WorldReadinessRead) -> None:
        self.readiness = readiness
        super().__init__(self.reason_code)

class WorldDefinitionValidationError(WorldServiceError):
    reason_code = "world_definition_incomplete"

class WorldBannerValidationError(WorldServiceError):
    reason_code = "unsafe_banner_reference"
